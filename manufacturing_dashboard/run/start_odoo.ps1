# Odoo Manufacturing Dashboard Startup Script
# This script provides advanced startup options for your Odoo application

param(
    [switch]$Background,
    [switch]$Minimized,
    [switch]$LogToFile,
    [string]$LogLevel = "info"
)

# Configuration
$OdooPath = "D:\Projects_18\odoo"
$ConfigPath = "D:\Projects_18\conf\odoo18.conf"
$LogPath = "D:\Projects_18\odoo.log"
$PythonExe = "python"

# Check if Odoo directory exists
if (-not (Test-Path $OdooPath)) {
    Write-Error "Odoo directory not found: $OdooPath"
    exit 1
}

# Check if config file exists
if (-not (Test-Path $ConfigPath)) {
    Write-Error "Configuration file not found: $ConfigPath"
    exit 1
}

# Change to Odoo directory
Set-Location $OdooPath

# Build command arguments
$Arguments = @(
    "odoo-bin"
    "-c", $ConfigPath
    "--log-level=$LogLevel"
)

if ($LogToFile) {
    $Arguments += "--logfile=$LogPath"
}

# Display startup information
Write-Host "Starting Odoo Manufacturing Dashboard..." -ForegroundColor Green
Write-Host "Odoo Path: $OdooPath" -ForegroundColor Yellow
Write-Host "Config: $ConfigPath" -ForegroundColor Yellow
Write-Host "Log Level: $LogLevel" -ForegroundColor Yellow

if ($LogToFile) {
    Write-Host "Log File: $LogPath" -ForegroundColor Yellow
}

Write-Host ""

# Start the process
try {
    if ($Background) {
        # Start in background (hidden window)
        $Process = Start-Process -FilePath $PythonExe -ArgumentList $Arguments -WindowStyle Hidden -PassThru
        Write-Host "Odoo started in background (PID: $($Process.Id))" -ForegroundColor Green
        Write-Host "To stop the server, run: Stop-Process -Id $($Process.Id)" -ForegroundColor Cyan
    } elseif ($Minimized) {
        # Start minimized
        $Process = Start-Process -FilePath $PythonExe -ArgumentList $Arguments -WindowStyle Minimized -PassThru
        Write-Host "Odoo started minimized (PID: $($Process.Id))" -ForegroundColor Green
    } else {
        # Start normally
        & $PythonExe $Arguments
    }
} catch {
    Write-Error "Failed to start Odoo: $($_.Exception.Message)"
    exit 1
}

Write-Host ""
Write-Host "Odoo Manufacturing Dashboard is running!" -ForegroundColor Green
Write-Host "Access your application at: http://localhost:8018" -ForegroundColor Cyan
