@echo off
setlocal

echo ==============================================
echo Build do executavel WMS (PyInstaller)
echo ==============================================
echo.

if not exist "run_production.py" (
    echo [ERRO] Execute este .bat na pasta raiz do projeto.
    exit /b 1
)

python -m PyInstaller --noconfirm --clean --onedir --console --name WMS_Server --hidden-import pyodbc --hidden-import waitress run_production.py
if errorlevel 1 (
    echo [ERRO] Falha ao gerar executavel.
    exit /b 1
)

if not exist "dist\WMS_Server\templates" mkdir "dist\WMS_Server\templates"
xcopy "templates" "dist\WMS_Server\templates" /E /I /Y >nul

if not exist "dist\WMS_Server\static" mkdir "dist\WMS_Server\static"
xcopy "static" "dist\WMS_Server\static" /E /I /Y >nul

copy /Y "wms_database.mdb" "dist\WMS_Server\wms_database.mdb" >nul

echo.
echo [OK] Build concluido.
echo Pasta final: dist\WMS_Server
echo Compartilhe essa pasta para os outros PCs.
echo.

endlocal
