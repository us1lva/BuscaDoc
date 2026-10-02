#!/usr/bin/env python3
"""Checklist de Ativos: vigia a pasta, guarda tudo em SQLite e atualiza o painel ao vivo.
Só usa a biblioteca padrão do Python (3.8+). Configuração em config.json."""
import os, re, json, sqlite3, threading, time, unicodedata, webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

AQUI = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(AQUI, 'config.json'), encoding='utf-8'))
PASTA, HOST, PORTA = CFG['pasta'], CFG.get('host', '127.0.0.1'), CFG.get('porta', 8080)
INTERVALO, NIVEIS = CFG.get('intervalo_segundos', 10), CFG.get('max_niveis', 6)
DOCS = [(d['k'], d['n'], re.compile(d['re'])) for d in CFG['docs']]
IGN_ARQ = re.compile(r'^(~\$|\.|thumbs\.db$|desktop\.ini$)', re.I)
norm = lambda s: ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()
agora = lambda: time.strftime('%d/%m/%Y %H:%M:%S')

db = sqlite3.connect(os.path.join(AQUI, 'checklist.db'), check_same_thread=False)
db.executescript('''pragma journal_mode=wal;
create table if not exists pessoas(nome text primary key);
create table if not exists arquivos(pessoa text, caminho text, tam int, mtime int, primary key(pessoa, caminho));
create table if not exists manual(pessoa text, doc text, valor text, primary key(pessoa, doc));
create table if not exists eventos(id integer primary key autoincrement, ts text, pessoa text, tipo text, caminho text);
create table if not exists cfg(k text primary key, v text);''')
LOCK, COND, GATILHO = threading.RLock(), threading.Condition(), threading.Event()
EST = {'ver': 0, 'gen': 0, 'hora': '', 'ts': '', 'dur': 0, 'erros': []}


def cfgget(k):
    r = db.execute('select v from cfg where k=?', (k,)).fetchone()
    return r[0] if r else ''


def ev(p, t, c=''):
    db.execute('insert into eventos(ts,pessoa,tipo,caminho) values(?,?,?,?)', (agora(), p, t, c))


def pulso(mudou):  # acorda os navegadores conectados; ver só sobe quando os dados mudaram
    with COND:
        EST['gen'] += 1
        EST['ver'] += bool(mudou)
        COND.notify_all()


def ler(caminho):  # lista todos os arquivos de uma pessoa; tenta de novo se a rede falhar
    for i in range(3):
        out, erros = {}, []

        def rec(d, rel, n):
            try:
                with os.scandir(d) as it:
                    for e in it:
                        if IGN_ARQ.match(e.name):
                            continue
                        if e.is_dir():
                            if n < NIVEIS:
                                rec(e.path, rel + e.name + '/', n + 1)
                        else:
                            s = e.stat()
                            out[rel + e.name] = (s.st_size, int(s.st_mtime))
            except OSError as x:
                erros.append(f'{rel or "(raiz)"} → {x}')
        rec(caminho, '', 0)
        if not erros:
            break
        time.sleep(0.4 * (i + 1))
    return out, erros


def varrer():
    t0, erros = time.time(), []
    ign = [norm(x.strip()) for x in cfgget('ignorar').split(',') if x.strip()]
    dirs = [e for e in os.scandir(PASTA) if e.is_dir() and e.name[0] not in '_.' and norm(e.name) not in ign]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda e: (e.name, *ler(e.path)), dirs))
    with LOCK:
        conhecidos = {n for (n,) in db.execute('select nome from pessoas')}
        primeira, mudou, antigo = not conhecidos, False, {}
        for p, c, t, m in db.execute('select pessoa,caminho,tam,mtime from arquivos'):
            antigo.setdefault(p, {})[c] = (t, m)
        if primeira:
            ev('—', 'primeira varredura', f'{len(res)} pastas')
        for n, novo, errs in res:
            if errs:
                erros += [f'{n}/{x}' for x in errs]
                if n in conhecidos:
                    continue  # erro de rede: mantém o que já sabia
            old = antigo.get(n, {})
            if n not in conhecidos:
                db.execute('insert into pessoas values(?)', (n,))
                mudou = True
                if not primeira:
                    ev(n, 'pasta nova')
            if not primeira:
                for c, v in novo.items():
                    if c not in old:
                        ev(n, 'adicionado', c)
                    elif old[c] != v:
                        ev(n, 'alterado', c)
                for c in old:
                    if c not in novo:
                        ev(n, 'removido', c)
            if novo != old:
                mudou = True
                db.execute('delete from arquivos where pessoa=?', (n,))
                db.executemany('insert into arquivos values(?,?,?,?)', [(n, c, *v) for c, v in novo.items()])
        for n in conhecidos - {r[0] for r in res}:  # pasta apagada (ou agora ignorada)
            db.execute('delete from pessoas where nome=?', (n,))
            db.execute('delete from arquivos where pessoa=?', (n,))
            ev(n, 'pasta removida')
            mudou = True
        db.commit()
    ch = mudou or erros != EST['erros']
    EST.update(erros=erros, hora=time.strftime('%H:%M:%S'), ts=agora(), dur=int((time.time() - t0) * 1000))
    pulso(ch)


def loop():
    while True:
        try:
            varrer()
        except Exception as x:
            EST['erros'] = [f'Falha geral: {x}']
            pulso(True)
        GATILHO.wait(INTERVALO)
        GATILHO.clear()


def estado():
    with LOCK:
        P = {n: {'files': []} for (n,) in db.execute('select nome from pessoas order by nome')}
        for p, c in db.execute('select pessoa,caminho from arquivos order by caminho'):
            if p in P:
                P[p]['files'].append(c)
        for p in P.values():
            nf = [norm(f) for f in p['files']]
            p['docs'] = {k: [f for f, x in zip(p['files'], nf) if r.search(x)] for k, _, r in DOCS}
        M = {}
        for p, d, v in db.execute('select pessoa,doc,valor from manual'):
            M.setdefault(p, {})[d] = v == '1' or 'nao'
        E = [dict(ts=t, pessoa=p, tipo=y, caminho=c) for t, p, y, c in
             db.execute('select ts,pessoa,tipo,caminho from eventos order by id desc limit 40')]
    return {'pasta': PASTA, 'docs': [{'k': k, 'n': n} for k, n, _ in DOCS], 'pessoas': P, 'manual': M,
            'ignorar': cfgget('ignorar'), 'eventos': E, 'ver': EST['ver'],
            **{k: EST[k] for k in ('hora', 'ts', 'dur', 'erros')}}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, corpo, tipo='application/json; charset=utf-8', code=200):
        self.send_response(code)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/':
            self._send(open(os.path.join(AQUI, 'index.html'), 'rb').read(), 'text/html; charset=utf-8')
        elif p == '/api/estado':
            self._send(json.dumps(estado(), ensure_ascii=False).encode())
        elif p == '/api/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            g = -1
            try:
                while True:
                    with COND:
                        COND.wait_for(lambda: EST['gen'] != g, timeout=15)  # sem novidade: envia batida de vida
                        g = EST['gen']
                    self.wfile.write(('data: ' + json.dumps({'ver': EST['ver'], 'hora': EST['hora']}) + '\n\n').encode())
                    self.wfile.flush()
            except OSError:
                pass
        else:
            self._send(b'{}', code=404)

    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        p = self.path
        if p == '/api/manual':
            v = b.get('valor')
            with LOCK:
                if v is None:
                    db.execute('delete from manual where pessoa=? and doc=?', (b['pessoa'], b['doc']))
                else:
                    db.execute('insert or replace into manual values(?,?,?)',
                               (b['pessoa'], b['doc'], '1' if v is True else '0'))
                ev(b['pessoa'], 'marcação manual', b['doc'] + ': ' + ('marcado à mão' if v is True else 'arquivo ignorado' if v else 'marcação removida'))
                db.commit()
            pulso(True)
        elif p == '/api/ignorar':
            with LOCK:
                db.execute('insert or replace into cfg values("ignorar",?)', (b.get('valor', ''),))
                db.commit()
            GATILHO.set()
        elif p == '/api/scan':
            GATILHO.set()
        self._send(b'{"ok":true}')


if __name__ == '__main__':
    threading.Thread(target=loop, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORTA), H)
    srv.daemon_threads = True
    url = f'http://localhost:{PORTA}'
    print(f'Checklist rodando em {url}  (Ctrl+C para parar)\nPasta vigiada: {PASTA}')
    if os.environ.get('ABRIR'):
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
