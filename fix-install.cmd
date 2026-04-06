@echo off
setlocal enabledelayedexpansion

set "REPO=%~dp0"
set "TARGET=%USERPROFILE%\.claude"

echo === Step 1: Rename broken dirs out of the way ===
rename "%TARGET%\commands" "commands_broken" 2>nul
rename "%TARGET%\guides" "guides_broken" 2>nul

echo === Step 2: Create fresh directories ===
md "%TARGET%\commands"
md "%TARGET%\guides"

echo === Step 3: Copy files ===
for %%f in ("%REPO%commands\*.md") do (
    copy /y "%%f" "%TARGET%\commands\%%~nxf"
    echo   copied %%~nxf
)
for %%f in ("%REPO%guides\*.md") do (
    copy /y "%%f" "%TARGET%\guides\%%~nxf"
    echo   copied %%~nxf
)

echo.
echo === Verify ===
dir "%TARGET%\commands" /b
echo.
dir "%TARGET%\guides" /b

echo.
echo Broken dirs renamed to commands_broken / guides_broken.
echo You can try deleting them manually later or leave them.
echo Done.
pause
