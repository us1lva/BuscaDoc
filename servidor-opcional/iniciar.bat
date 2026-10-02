@echo off
cd /d "%~dp0"
set ABRIR=1
where py >nul 2>nul && (py server.py) || (python server.py)
pause
