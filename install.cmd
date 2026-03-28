@echo off
setlocal enabledelayedexpansion

REM Install dot-claude repo into %USERPROFILE%\.claude
REM Creates symlinks (requires admin or Developer Mode enabled)

set "SCRIPT_DIR=%~dp0"
set "TARGET=%USERPROFILE%\.claude"

if not exist "%TARGET%\commands" mkdir "%TARGET%\commands"
if not exist "%TARGET%\guides" mkdir "%TARGET%\guides"

echo Installing dot-claude from %SCRIPT_DIR%
echo.

REM CLAUDE.md
call :linkfile "%SCRIPT_DIR%CLAUDE.md" "%TARGET%\CLAUDE.md"

REM settings.json
call :linkfile "%SCRIPT_DIR%settings.json" "%TARGET%\settings.json"

REM Commands
echo Commands:
for %%f in ("%SCRIPT_DIR%commands\*.md") do (
    call :linkfile "%%f" "%TARGET%\commands\%%~nxf"
)

REM Guides
echo Guides:
for %%f in ("%SCRIPT_DIR%guides\*.md") do (
    call :linkfile "%%f" "%TARGET%\guides\%%~nxf"
)

echo.
echo Done. Runtime dirs (sessions, projects, etc.) are untouched.
goto :eof

:linkfile
set "src=%~1"
set "dst=%~2"
if exist "%dst%" (
    echo   backup: %dst% -^> %dst%.bak
    move /y "%dst%" "%dst%.bak" >nul 2>&1
)
mklink "%dst%" "%src%" >nul 2>&1
if errorlevel 1 (
    echo   copy:   %dst% (symlink failed, copying instead)
    copy /y "%src%" "%dst%" >nul
) else (
    echo   linked: %dst% -^> %src%
)
goto :eof
