@echo off
setlocal enabledelayedexpansion

REM Install dot-claude repo into %USERPROFILE%\.claude
REM Copies files from the repo so no symlinks or admin rights are needed.
REM Handles broken symlinks left over from dev container setups.

set "SCRIPT_DIR=%~dp0"
set "TARGET=%USERPROFILE%\.claude"

if not exist "%TARGET%" mkdir "%TARGET%"

echo Installing dot-claude from %SCRIPT_DIR%
echo.

REM --- Helper: remove target if it exists (file, symlink, or broken symlink) ---
REM Windows "copy /y" cannot overwrite broken symlinks, so we delete first.

REM --- Top-level files ---
for %%f in (CLAUDE.md settings.json) do (
    if exist "%TARGET%\%%f" del /f /q "%TARGET%\%%f" 2>nul
    REM Also try removing as a broken symlink (del may miss dangling symlinks)
    if exist "%TARGET%\%%f" rmdir "%TARGET%\%%f" 2>nul
    copy /y "%SCRIPT_DIR%%%f" "%TARGET%\%%f" >nul
    echo   copied %%f
)

REM --- Commands ---
echo.
echo Commands:
REM Replace broken symlink dir with a real directory
if exist "%TARGET%\commands" (
    REM Check if it's a symlink (junction/symlink dir) — rmdir removes symlink without deleting target
    dir /al "%TARGET%\commands" >nul 2>nul && (
        rmdir "%TARGET%\commands" 2>nul
    )
)
if not exist "%TARGET%\commands" mkdir "%TARGET%\commands"
REM Prune stale files no longer in the repo
for %%f in ("%TARGET%\commands\*.md") do (
    if not exist "%SCRIPT_DIR%commands\%%~nxf" (
        del /f /q "%%f" 2>nul
        echo   pruned commands\%%~nxf
    )
)
for %%f in ("%SCRIPT_DIR%commands\*.md") do (
    if exist "%TARGET%\commands\%%~nxf" del /f /q "%TARGET%\commands\%%~nxf" 2>nul
    copy /y "%%f" "%TARGET%\commands\%%~nxf" >nul
    echo   copied commands\%%~nxf
)

REM --- Guides ---
echo.
echo Guides:
REM Replace broken symlink dir with a real directory
if exist "%TARGET%\guides" (
    dir /al "%TARGET%\guides" >nul 2>nul && (
        rmdir "%TARGET%\guides" 2>nul
    )
)
if not exist "%TARGET%\guides" mkdir "%TARGET%\guides"
REM Prune stale files no longer in the repo
for %%f in ("%TARGET%\guides\*.md") do (
    if not exist "%SCRIPT_DIR%guides\%%~nxf" (
        del /f /q "%%f" 2>nul
        echo   pruned guides\%%~nxf
    )
)
for %%f in ("%SCRIPT_DIR%guides\*.md") do (
    if exist "%TARGET%\guides\%%~nxf" del /f /q "%TARGET%\guides\%%~nxf" 2>nul
    copy /y "%%f" "%TARGET%\guides\%%~nxf" >nul
    echo   copied guides\%%~nxf
)

echo.
echo Done.
