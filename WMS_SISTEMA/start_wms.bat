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
set "SYS_PY="

if exist "%VENV_PY%" (
	"%VENV_PY%" --version >nul 2>&1
	if not errorlevel 1 (
		echo [INFO] Usando Python da venv: %VENV_PY%
		"%VENV_PY%" run_production.py
		goto :done
	)
	echo [AVISO] Python da venv encontrado, mas nao executa. Tentando Python do sistema...
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
	set "SYS_PY=py -3"
) else (
	python --version >nul 2>&1
	if not errorlevel 1 set "SYS_PY=python"
)

if defined SYS_PY (
	echo [INFO] Usando %SYS_PY% para iniciar o servidor.
	%SYS_PY% run_production.py
) else (
	echo [ERRO] Nenhum Python funcional foi encontrado.
	echo [ERRO] Recomendado: recriar a venv com: py -3 -m venv ..\.venv
	set "ERRORLEVEL=1"
)

:done

pause
popd
endlocal
