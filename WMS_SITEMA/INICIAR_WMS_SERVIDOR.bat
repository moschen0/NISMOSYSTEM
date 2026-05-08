@echo off
setlocal
title WMS Master Server - v1.2.1
color 0A

pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
	echo [ERRO] Nao foi possivel acessar a pasta do sistema.
	pause
	exit /b 1
)

echo ========================================
echo    WMS Master Server v1.2.1
echo    Desenvolvido por:
echo    - Gustavo Detoni
echo    - Vitor Moschen
echo ========================================
echo.
echo Iniciando servidor WMS...
echo.
echo O servidor estara disponivel em:
echo   http://192.168.1.210:5000
echo   http://localhost:5000
echo.
echo Pressione CTRL+C para parar o servidor
echo ========================================
echo.

set "BASE_DIR=%CD%\"
set "DIST_EXE=%BASE_DIR%dist\WMS_Server\WMS_Server.exe"
set "ROOT_EXE=%BASE_DIR%WMS_Server.exe"
set "VENV_PY=%BASE_DIR%..\.venv\Scripts\python.exe"
set "RUN_SCRIPT=%BASE_DIR%run_production.py"

if exist "%DIST_EXE%" (
	echo [INFO] Iniciando via EXE em dist...
	"%DIST_EXE%"
) else if exist "%ROOT_EXE%" (
	echo [INFO] Iniciando via EXE na raiz...
	"%ROOT_EXE%"
) else if exist "%VENV_PY%" if exist "%RUN_SCRIPT%" (
	echo [INFO] EXE nao encontrado. Iniciando via Python da venv...
	"%VENV_PY%" "%RUN_SCRIPT%"
) else (
	echo [ERRO] Nao foi encontrado EXE funcional nem Python da venv para iniciar o servidor.
)

:end
pause
popd
endlocal
