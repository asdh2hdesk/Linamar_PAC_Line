@echo off
echo Starting Odoo Manufacturing Dashboard...
echo.

REM Change to the Odoo directory
cd /d "D:\Projects_18\odoo"

REM Start Odoo server with your configuration
python odoo-bin -c "D:\Projects_18\conf\odoo18.conf" --logfile="D:\Projects_18\odoo.log" --log-level=info

REM Keep window open if there's an error
if %errorlevel% neq 0 (
    echo.
    echo Odoo server encountered an error. Press any key to close...
    pause > nul
)
