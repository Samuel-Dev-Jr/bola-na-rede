@echo off
REM Centro de Cultura e Esportes - atalho para subir o sistema.
REM Basta dar dois cliques neste arquivo.

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Python nao encontrado. Instale o Python e tente de novo.
    echo.
    pause
    exit /b 1
)

python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo  Instalando o Flask...
    python -m pip install -r requirements.txt --quiet
)

if not exist "centro.db" (
    echo  Primeira execucao: criando o banco com as modalidades e turmas...
    python configurar.py
    echo.
)

echo.
echo  ====================================================
echo   Centro de Cultura e Esportes esta subindo em http://localhost:5000
echo   Feche esta janela ou tecle Ctrl+C para parar.
echo  ====================================================
echo.

REM Abre o navegador so depois que o servidor subir, senao da erro de conexao.
start "" /b python -c "import time, webbrowser; time.sleep(3); webbrowser.open('http://localhost:5000')"

python app.py
