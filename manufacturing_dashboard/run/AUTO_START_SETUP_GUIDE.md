# Odoo Manufacturing Dashboard - Auto-Start Setup Guide

This guide provides multiple options to run your Odoo Manufacturing Dashboard automatically in the background on Windows.

## 📋 Prerequisites

- Python installed and accessible from command line
- PostgreSQL running (as configured in your `odoo18.conf`)
- Odoo 18 installation at `D:\Projects_18\odoo`
- Configuration file at `D:\Projects_18\conf\odoo18.conf`

## 🚀 Quick Start Options

### Option 1: Simple Batch Script (Recommended for beginners)
**File:** `start_odoo.bat`

**Usage:**
- Double-click to start Odoo manually
- Shows console window with logs
- Easy to stop (close window or Ctrl+C)

**Features:**
- Simple and reliable
- Shows real-time logs
- Easy to troubleshoot

---

### Option 2: Advanced PowerShell Script
**File:** `start_odoo.ps1`

**Usage:**
```powershell
# Start normally (with console)
.\start_odoo.ps1

# Start in background (hidden)
.\start_odoo.ps1 -Background

# Start minimized
.\start_odoo.ps1 -Minimized

# Start with logging to file
.\start_odoo.ps1 -LogToFile -LogLevel info
```

**Features:**
- Multiple startup modes
- Advanced logging options
- Process ID tracking
- Error handling

---

### Option 3: Windows Service (Recommended for production)
**File:** `install_odoo_service.bat`

**Usage:**
1. Right-click `install_odoo_service.bat` → "Run as administrator"
2. Follow the prompts
3. Service will start automatically on Windows boot

**Features:**
- Runs as Windows Service
- Automatic startup on boot
- Automatic restart on failure
- Runs in background (no console window)
- Professional setup

**Service Management:**
```cmd
# Start service
net start "Odoo Manufacturing Dashboard"

# Stop service
net stop "Odoo Manufacturing Dashboard"

# Check service status
sc query "Odoo Manufacturing Dashboard"
```

---

### Option 4: Windows Startup Folder
**File:** `setup_startup.bat`

**Usage:**
1. Run `setup_startup.bat`
2. Creates shortcut in Windows Startup folder
3. Odoo starts when you log in

**Features:**
- Starts when user logs in
- Runs minimized
- Easy to disable (delete shortcut)
- User-specific startup

---

### Option 5: Task Scheduler (Most flexible)
**File:** `setup_task_scheduler.bat`

**Usage:**
1. Right-click `setup_task_scheduler.bat` → "Run as administrator"
2. Creates scheduled tasks for automatic startup

**Features:**
- Runs at system startup
- Runs at user logon
- Configurable timing
- Advanced scheduling options
- Can run with different privileges

**Task Management:**
- Open Task Scheduler (`taskschd.msc`)
- Look for "Odoo Manufacturing Dashboard" tasks
- Modify, disable, or delete as needed

---

## 🔧 Configuration Details

### Your Current Setup
- **Odoo Path:** `D:\Projects_18\odoo`
- **Config File:** `D:\Projects_18\conf\odoo18.conf`
- **Port:** 8018
- **Database:** PostgreSQL (localhost:5432)
- **Admin Password:** master@123

### Access Your Application
Once running, access your dashboard at: **http://localhost:8018**

---

## 🛠️ Troubleshooting

### Common Issues

1. **"Python not found"**
   - Ensure Python is installed and in PATH
   - Try using full path: `C:\Python\python.exe`

2. **"Configuration file not found"**
   - Verify `D:\Projects_18\conf\odoo18.conf` exists
   - Check file permissions

3. **"Port already in use"**
   - Change port in `odoo18.conf`: `http_port = 8019`
   - Or stop other Odoo instances

4. **"Database connection failed"**
   - Ensure PostgreSQL is running
   - Check database credentials in config file

### Log Files
- **Service/Background mode:** `D:\Projects_18\odoo.log`
- **Console mode:** Output in terminal window

### Stopping the Application
- **Console mode:** Press `Ctrl+C` or close window
- **Service mode:** `net stop "Odoo Manufacturing Dashboard"`
- **Background mode:** Use Task Manager or `Stop-Process -Id <PID>`

---

## 📊 Recommended Setup

### For Development/Testing
Use **Option 1** (Simple Batch Script) - easy to start/stop and see logs

### For Production/Server
Use **Option 3** (Windows Service) - professional, reliable, automatic

### For Personal Use
Use **Option 4** (Startup Folder) - starts when you log in, easy to manage

---

## 🔄 Updating Your Setup

If you modify your Odoo configuration or paths, update the scripts accordingly:

1. **Batch Script:** Edit `start_odoo.bat`
2. **PowerShell Script:** Edit `start_odoo.ps1`
3. **Service:** Re-run `install_odoo_service.bat`
4. **Startup Folder:** Re-run `setup_startup.bat`
5. **Task Scheduler:** Re-run `setup_task_scheduler.bat`

---

## 📞 Support

Your Odoo Manufacturing Dashboard includes:
- VICI Vision System Integration
- Ruhlamat Press System Integration
- Aumann Measurement System Integration
- Real-time CSV data processing
- Quality control tracking and reporting
- Box management (540 parts per box)

For technical support, check the logs and ensure all dependencies are properly installed.
