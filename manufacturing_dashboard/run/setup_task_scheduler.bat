@echo off
REM Odoo Manufacturing Dashboard - Task Scheduler Setup
REM This script creates a scheduled task to run Odoo automatically

echo Setting up Odoo Manufacturing Dashboard with Task Scheduler...
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running as Administrator - OK
) else (
    echo ERROR: This script must be run as Administrator
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

REM Get the current directory
set "CURRENT_DIR=%~dp0"

REM Create the scheduled task
echo Creating scheduled task...
schtasks /create /tn "Odoo Manufacturing Dashboard" /tr "\"%CURRENT_DIR%start_odoo.bat\"" /sc onstart /ru "SYSTEM" /f

REM Set additional task properties
echo Configuring task properties...
schtasks /change /tn "Odoo Manufacturing Dashboard" /enable
schtasks /change /tn "Odoo Manufacturing Dashboard" /rl highest

REM Create a task to run at user logon as well
echo Creating user logon task...
schtasks /create /tn "Odoo Manufacturing Dashboard (User Logon)" /tr "\"%CURRENT_DIR%start_odoo.bat\"" /sc onlogon /ru "%USERNAME%" /f

echo.
echo Task Scheduler setup completed!
echo.
echo Created tasks:
echo - "Odoo Manufacturing Dashboard" (System startup)
echo - "Odoo Manufacturing Dashboard (User Logon)" (User logon)
echo.
echo To manage tasks:
echo 1. Open Task Scheduler (taskschd.msc)
echo 2. Look for "Odoo Manufacturing Dashboard" tasks
echo.
echo To remove tasks:
echo schtasks /delete /tn "Odoo Manufacturing Dashboard" /f
echo schtasks /delete /tn "Odoo Manufacturing Dashboard (User Logon)" /f
echo.
pause
