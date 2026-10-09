# Checklist de Documentos – Ativos

Painel que lê a pasta #ATIVOS **direto no navegador** (Chrome/Edge) e se atualiza sozinho
quando arquivos são adicionados, alterados ou removidos. Nenhum arquivo sai do seu computador:
o Vercel só entrega a página; a leitura da pasta acontece localmente.


## Primeiro uso
1. Abra o endereço do Vercel no Chrome/Edge e clique em **Selecionar pasta #ATIVOS**.
2. Quando o navegador perguntar, escolha **Permitir em todas as visitas**. Assim ele reconecta sozinho nas próximas aberturas.
3. Deixe a aba aberta (pode fixar). Para abrir ao ligar o PC: Win+R > `shell:startup` > atalho para o endereço.

As marcações manuais ficam em `_checklist_dados.json` dentro da pasta lida, então todos que abrirem veem as mesmas.

## servidor-opcional/
Versão com servidor Python + SQLite (vigia a pasta mesmo sem navegador aberto). Só se a TI permitir rodar Python.
