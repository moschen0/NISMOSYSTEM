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
set "WORKSPACE_EXE=%BASE_DIR%..\WMS_Server\WMS_Server.exe"
set "VENV_PY=%BASE_DIR%..\.venv\Scripts\python.exe"
set "RUN_SCRIPT=%BASE_DIR%run_production.py"
set "SYS_PY="

if exist "%DIST_EXE%" (
	echo [INFO] Iniciando via EXE em dist...
	"%DIST_EXE%"
) else if exist "%ROOT_EXE%" (
	echo [INFO] Iniciando via EXE na raiz...
	"%ROOT_EXE%"
) else if exist "%WORKSPACE_EXE%" (
	echo [INFO] Iniciando via EXE em ..\WMS_Server...
	"%WORKSPACE_EXE%"
) else (
	if not exist "%RUN_SCRIPT%" (
		echo [ERRO] Script de execucao nao encontrado: %RUN_SCRIPT%
		goto :end
	)

	if exist "%VENV_PY%" (
		"%VENV_PY%" --version >nul 2>&1
		if not errorlevel 1 (
			echo [INFO] EXE nao encontrado. Iniciando via Python da venv...
			"%VENV_PY%" "%RUN_SCRIPT%"
			goto :end
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
		echo [INFO] EXE nao encontrado. Iniciando via %SYS_PY%...
		%SYS_PY% "%RUN_SCRIPT%"
	) else (
		echo [ERRO] Nao foi encontrado EXE funcional nem Python funcional para iniciar o servidor.
		echo [ERRO] Recomendado: recriar a venv com: py -3 -m venv ..\.venv
	)
)

:end
pause
popd
endlocal
