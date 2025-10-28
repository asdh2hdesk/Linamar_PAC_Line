@echo off
REM Odoo Manufacturing Dashboard Windows Service Installation Script
REM Run this script as Administrator to install Odoo as a Windows Service

echo Installing Odoo Manufacturing Dashboard as Windows Service...
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

REM Install NSSM (Non-Sucking Service Manager) if not already installed
if not exist "C:\nssm\nssm.exe" (
    echo Downloading NSSM...
    powershell -Command "Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile 'nssm.zip'"
    powershell -Command "Expand-Archive -Path 'nssm.zip' -DestinationPath 'C:\' -Force"
    del nssm.zip
    echo NSSM installed successfully
) else (
    echo NSSM already installed
)

REM Create the service
echo Creating Odoo service...
C:\nssm\win64\nssm.exe install "Odoo Manufacturing Dashboard" "D:\Projects_18\odoo\odoo-bin" "-c D:\Projects_18\conf\odoo18.conf --logfile=D:\Projects_18\odoo.log --log-level=info"

REM Set service description
C:\nssm\win64\nssm.exe set "Odoo Manufacturing Dashboard" Description "Odoo Manufacturing Dashboard - Real-time Quality Control System"

REM Set startup directory
C:\nssm\win64\nssm.exe set "Odoo Manufacturing Dashboard" AppDirectory "D:\Projects_18\odoo"

REM Set service to start automatically
C:\nssm\win64\nssm.exe set "Odoo Manufacturing Dashboard" Start SERVICE_AUTO_START

REM Set service to restart on failure
C:\nssm\win64\nssm.exe set "Odoo Manufacturing Dashboard" AppExit Default Restart

REM Set restart delay
C:\nssm\win64\nssm.exe set "Odoo Manufacturing Dashboard" AppRestartDelay 5000

REM Set service to run as Local System
C:\nssm\win64\nssm.exe set "Odoo Manufacturing Dashboard" ObjectName LocalSystem

echo.
echo Service installation completed!
echo.
echo To start the service: net start "Odoo Manufacturing Dashboard"
echo To stop the service: net stop "Odoo Manufacturing Dashboard"
echo To remove the service: C:\nssm\win64\nssm.exe remove "Odoo Manufacturing Dashboard" confirm
echo.
echo The service will start automatically when Windows boots.
echo.
pause
