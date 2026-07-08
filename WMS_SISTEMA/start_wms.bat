@echo off
setlocal
title WMS - SERVIDOR DE TESTE (porta 5001)
color 0B

pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Nao foi possivel acessar a pasta do sistema.
    pause
    exit /b 1
)

echo ============================================================
echo  WMS - SERVIDOR DE TESTE
echo  Porta : 5001
echo  Banco : LOCAL ^(WMS_BD\wms_database.mdb^)
echo  *** NAO afeta o banco de producao ***
echo ============================================================
echo.

REM Garantir que testes usem banco de teste local; definir producao por seguranca
set "WMS_MDB_PATH_PROD=\\192.168.1.210\apps master\DATABASE WMS\BD PRODUCAO\wms_database.mdb"
echo [ENV] WMS_MDB_PATH_PROD=%WMS_MDB_PATH_PROD%


set "VENV_PY=%~dp0..\.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>&1
    if not errorlevel 1 (
        echo [INFO] Python: venv
        "%VENV_PY%" run_test.py
        goto :done
    )
    echo [AVISO] Venv encontrada mas Python nao executa. Tentando Python do sistema...
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Python: py -3
    py -3 run_test.py
    goto :done
)

python --version >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Python: python
    python run_test.py
    goto :done
)

echo [ERRO] Nenhum Python funcional encontrado.
echo        Instale Python 3 ou recrie a venv: py -3 -m venv ..\.venv

:done
pause
popd
endlocal
