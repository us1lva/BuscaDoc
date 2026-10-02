@echo off
> "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ChecklistAtivos.cmd" echo @start "" wscript "%~dp0segundo-plano.vbs"
wscript "%~dp0segundo-plano.vbs"
echo Pronto. O checklist agora inicia sozinho ao ligar o PC e ja esta rodando em http://localhost:8080
pause
