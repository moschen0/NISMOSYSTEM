@echo off
setlocal
title WMS - SERVIDOR DE PRODUCAO (porta 5000)
color 0A

pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Nao foi possivel acessar a pasta do sistema.
    pause
    exit /b 1
)

echo ============================================================
echo  WMS - SERVIDOR DE PRODUCAO
echo  Porta : 5000
echo  Banco : Rede ^(\\192.168.1.210\...\wms_database.mdb^)
echo  Acesse: http://localhost:5000
echo ============================================================
echo.

set "VENV_PY=%~dp0..\.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>&1
    if not errorlevel 1 (
        echo [INFO] Python: venv
        "%VENV_PY%" run_production.py
        goto :done
    )
    echo [AVISO] Venv encontrada mas Python nao executa. Tentando Python do sistema...
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Python: py -3
    py -3 run_production.py
    goto :done
)

python --version >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Python: python
    python run_production.py
    goto :done
)

echo [ERRO] Nenhum Python funcional encontrado.
echo        Instale Python 3 ou recrie a venv: py -3 -m venv ..\.venv

:done
pause
popd
endlocal
