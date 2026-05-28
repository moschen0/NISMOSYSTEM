@echo off
setlocal
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Nao foi possivel acessar a pasta do sistema.
    exit /b 1
)

echo ============================================================
echo  WMS - COMPILADOR (PyInstaller)
echo  Gera dist\WMS_Server\WMS_Server.exe
echo ============================================================
echo.

set "VENV_PY=%~dp0..\.venv\Scripts\python.exe"
set "PY_CMD="

if not exist "run_production.py" (
    echo [ERRO] Arquivo run_production.py nao encontrado em %CD%.
    popd
    exit /b 1
)

if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>&1
    if not errorlevel 1 set "PY_CMD=%VENV_PY%"
)

if not defined PY_CMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo [ERRO] Nenhum Python funcional foi encontrado para gerar o EXE.
    popd
    exit /b 1
)

echo [INFO] Python selecionado: %PY_CMD%

echo [INFO] Atualizando compiladores (pip/setuptools/wheel/pyinstaller)...
"%PY_CMD%" -m pip install --upgrade pip setuptools wheel pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 (
    echo [ERRO] Falha ao atualizar compiladores do build.
    popd
    exit /b 1
)

echo [INFO] Versoes do compilador:
"%PY_CMD%" -m pip show pyinstaller | findstr /I "Name Version"

"%PY_CMD%" -m PyInstaller --noconfirm --clean --onedir --console --name WMS_Server --hidden-import pyodbc --hidden-import waitress run_production.py
if errorlevel 1 (
    echo [ERRO] Falha ao gerar executavel.
    popd
    exit /b 1
)

if not exist "dist\WMS_Server\templates" mkdir "dist\WMS_Server\templates"
if exist "templates" (
    xcopy "templates" "dist\WMS_Server\templates" /E /I /Y >nul
) else (
    echo [AVISO] Pasta "templates" nao encontrada. Copia ignorada.
)

if not exist "dist\WMS_Server\static" mkdir "dist\WMS_Server\static"
if exist "static" (
    xcopy "static" "dist\WMS_Server\static" /E /I /Y >nul
) else if exist "..\WMS_Server\static" (
    xcopy "..\WMS_Server\static" "dist\WMS_Server\static" /E /I /Y >nul
) else (
    echo [AVISO] Pasta "static" nao encontrada em WMS_SISTEMA nem em WMS_Server. Copia ignorada.
)

copy /Y "wms_database.mdb" "dist\WMS_Server\wms_database.mdb" >nul 2>nul

rem Copiar arquivos de dados JSON (criados automaticamente se nao existirem)
for %%f in (zone_metadata.json zone_tag_catalog.json zone_tags_map.json sectors.json) do (
    if exist "%%f" copy /Y "%%f" "dist\WMS_Server\%%f" >nul
)

rem Copiar .env se existir
if exist ".env" copy /Y ".env" "dist\WMS_Server\.env" >nul

echo.
echo [OK] Build concluido.
echo Pasta final: dist\WMS_Server
echo Compartilhe essa pasta para os outros PCs.
echo.

popd
endlocal
