@echo off
setlocal
title WMS - Sistema de Gestao de Armazem
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
	echo [ERRO] Nao foi possivel acessar a pasta do sistema.
	pause
	exit /b 1
)

echo ============================================================
echo WMS - Warehouse Management System
echo ============================================================
echo.
echo Iniciando servidor em modo producao...
echo.

set "VENV_PY=%CD%\..\.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
	"%VENV_PY%" run_production.py
) else (
	python run_production.py
)

pause
popd
endlocal
