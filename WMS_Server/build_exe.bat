@echo off
setlocal
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Nao foi possivel acessar a pasta do sistema.
    exit /b 1
)

echo ==============================================
echo Build do executavel WMS (Wrapper)
echo ==============================================
echo.

set "ROOT_DIR=%~dp0.."
set "CANONICAL_BUILD=%ROOT_DIR%\WMS_SISTEMA\build_exe.bat"
set "CANONICAL_DIST=%ROOT_DIR%\WMS_SISTEMA\dist\WMS_Server"

if not exist "%CANONICAL_BUILD%" (
    echo [ERRO] Build canonico nao encontrado em "%CANONICAL_BUILD%".
    popd
    exit /b 1
)

echo [INFO] Este diretorio e apenas distribuicao.
echo [INFO] Executando build canonico: "%CANONICAL_BUILD%"
call "%CANONICAL_BUILD%"
if errorlevel 1 (
    echo [ERRO] Falha no build canonico.
    popd
    exit /b 1
)

if not exist "%CANONICAL_DIST%" (
    echo [ERRO] Pasta de saida nao encontrada: "%CANONICAL_DIST%".
    popd
    exit /b 1
)

echo [INFO] Publicando build em "%CD%"...
xcopy "%CANONICAL_DIST%\*" "%CD%\" /E /I /Y >nul
if errorlevel 1 (
    echo [ERRO] Falha ao publicar arquivos no diretorio WMS_Server.
    popd
    exit /b 1
)

echo.
echo [OK] Build concluido e publicado em: %CD%
echo.

popd
endlocal
