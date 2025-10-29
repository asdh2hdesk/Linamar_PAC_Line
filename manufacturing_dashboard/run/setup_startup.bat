@echo off
REM Odoo Manufacturing Dashboard - Startup Folder Script
REM This script will create a shortcut in Windows Startup folder for automatic startup

echo Setting up Odoo Manufacturing Dashboard for Windows Startup...
echo.

REM Get the current directory
set "CURRENT_DIR=%~dp0"

REM Create a VBS script to run the batch file minimized
echo Creating startup script...
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.Run "cmd /c ""%CURRENT_DIR%start_odoo.bat""", 0, False
) > "%CURRENT_DIR%start_odoo_minimized.vbs"

REM Get the Startup folder path
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

REM Create shortcut in Startup folder
echo Creating shortcut in Startup folder...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%STARTUP_FOLDER%\Odoo Manufacturing Dashboard.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%start_odoo_minimized.vbs'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'Odoo Manufacturing Dashboard - Auto Start'; $Shortcut.Save()"

echo.
echo Setup completed!
echo.
echo The Odoo Manufacturing Dashboard will now start automatically when Windows boots.
echo.
echo To disable auto-start:
echo 1. Press Win+R, type "shell:startup" and press Enter
echo 2. Delete the "Odoo Manufacturing Dashboard" shortcut
echo.
echo To manually start: Double-click start_odoo.bat
echo To start minimized: Double-click start_odoo_minimized.vbs
echo.
pause
