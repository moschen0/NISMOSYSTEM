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

if not exist "run_production.py" (
    echo [ERRO] Arquivo run_production.py nao encontrado em %CD%.
    popd
    exit /b 1
)

rem ── Detecta Python ──────────────────────────────────────────
set "PY_CMD="

rem 1. Python instalado no caminho padrao desta maquina
set "_KNOWN=C:\Users\supor\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if exist "%_KNOWN%" (
    "%_KNOWN%" --version >nul 2>&1
    if not errorlevel 1 set "PY_CMD=%_KNOWN%"
)

rem 2. Venv local do projeto
if not defined PY_CMD (
    if exist "%~dp0..\.venv\Scripts\python.exe" (
        "%~dp0..\.venv\Scripts\python.exe" --version >nul 2>&1
        if not errorlevel 1 set "PY_CMD=%~dp0..\.venv\Scripts\python.exe"
    )
)

rem 3. py launcher
if not defined PY_CMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py"
)

rem 4. python no PATH
if not defined PY_CMD (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo [ERRO] Nenhum Python funcional foi encontrado.
    popd
    exit /b 1
)

echo [INFO] Python: %PY_CMD%

rem ── Remove build/dist antigos (sem --clean para evitar erro OneDrive) ──
echo [INFO] Removendo build e dist anteriores...
if exist "build" (
    attrib -R "build\*.*" /S /D >nul 2>&1
    rd /S /Q "build" >nul 2>&1
)
if exist "dist\WMS_Server" (
    attrib -R "dist\WMS_Server\*.*" /S /D >nul 2>&1
    rd /S /Q "dist\WMS_Server" >nul 2>&1
)

rem ── Compila ─────────────────────────────────────────────────
echo [INFO] Compilando EXE...
"%PY_CMD%" -m PyInstaller --noconfirm --onedir --console --name WMS_Server ^
    --hidden-import pyodbc ^
    --hidden-import waitress ^
    --hidden-import telegram_notifier ^
    --hidden-import dotenv ^
    --hidden-import reportlab.graphics.barcode.code128 ^
    --hidden-import reportlab.graphics.barcode.code39 ^
    --hidden-import reportlab.graphics.barcode.code93 ^
    --hidden-import reportlab.graphics.barcode.common ^
    --hidden-import reportlab.graphics.barcode.dmtx ^
    --hidden-import reportlab.graphics.barcode.eanbc ^
    --hidden-import reportlab.graphics.barcode.ecc200datamatrix ^
    --hidden-import reportlab.graphics.barcode.fourstate ^
    --hidden-import reportlab.graphics.barcode.lto ^
    --hidden-import reportlab.graphics.barcode.qr ^
    --hidden-import reportlab.graphics.barcode.qrencoder ^
    --hidden-import reportlab.graphics.barcode.usps ^
    --hidden-import reportlab.graphics.barcode.usps4s ^
    --hidden-import reportlab.graphics.barcode.widgets ^
    run_production.py

rem PyInstaller retorna 1 mesmo com sucesso em alguns ambientes — valida pelo EXE
if not exist "dist\WMS_Server\WMS_Server.exe" (
    echo [ERRO] EXE nao gerado. Verifique o log acima.
    popd
    exit /b 1
)

rem ── Copia templates ─────────────────────────────────────────
if not exist "dist\WMS_Server\templates" mkdir "dist\WMS_Server\templates"
if exist "templates" (
    xcopy "templates" "dist\WMS_Server\templates" /E /I /Y >nul
    echo [OK] Templates copiados.
) else (
    echo [AVISO] Pasta "templates" nao encontrada.
)

rem ── Copia static ────────────────────────────────────────────
if not exist "dist\WMS_Server\static" mkdir "dist\WMS_Server\static"
if exist "static" (
    xcopy "static" "dist\WMS_Server\static" /E /I /Y >nul
    echo [OK] Static copiado.
) else (
    echo [AVISO] Pasta "static" nao encontrada.
)

rem ── Copia JSONs de configuracao ─────────────────────────────
for %%f in (zone_metadata.json zone_tag_catalog.json zone_tags_map.json sectors.json) do (
    if exist "%%f" (
        copy /Y "%%f" "dist\WMS_Server\%%f" >nul
        echo [OK] %%f copiado.
    )
)

rem ── Copia banco local para fallback offline ─────────────────
if exist "..\WMS_BD\wms_database.mdb" (
    copy /Y "..\WMS_BD\wms_database.mdb" "dist\WMS_Server\wms_database.mdb" >nul
    echo [OK] wms_database.mdb copiado.
) else (
    echo [AVISO] Banco local nao encontrado em ..\WMS_BD\wms_database.mdb.
)

rem ── Copia OPTO_INTEGRATIONS (necessario para etiquetas de envio) ──────────
if exist "..\OPTO_INTEGRATIONS" (
    if not exist "dist\WMS_Server\OPTO_INTEGRATIONS" mkdir "dist\WMS_Server\OPTO_INTEGRATIONS"
    xcopy "..\OPTO_INTEGRATIONS" "dist\WMS_Server\OPTO_INTEGRATIONS" /E /I /Y /EXCLUDE:build_exe_exclude.txt >nul 2>&1
    echo [OK] OPTO_INTEGRATIONS copiado.
) else (
    echo [AVISO] Pasta OPTO_INTEGRATIONS nao encontrada em ..\OPTO_INTEGRATIONS.
)

rem ── Copia .env ──────────────────────────────────────────────
if exist ".env" (
    copy /Y ".env" "dist\WMS_Server\.env" >nul
    echo [OK] .env copiado.
) else (
    echo [AVISO] .env nao encontrado - configure credenciais manualmente em dist\WMS_Server\.env
)

echo.
echo ============================================================
echo  [OK] Build concluido com sucesso!
echo  Pasta: %CD%\dist\WMS_Server
echo  Para distribuir: copie a pasta dist\WMS_Server inteira.
echo ============================================================
echo.

popd
endlocal

