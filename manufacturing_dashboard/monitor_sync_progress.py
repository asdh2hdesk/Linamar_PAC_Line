#!/usr/bin/env python3
"""
Script to monitor Ruhlamat MDB sync progress
This script can be run to check the progress of large MDB file syncing
"""

import time
import sys
import os

# Add the Odoo path to sys.path if needed
# sys.path.append('/path/to/odoo')

def monitor_sync_progress(machine_name=None):
    """
    Monitor sync progress for Ruhlamat machines
    
    Args:
        machine_name (str): Specific machine name to monitor, or None for all machines
    """
    
    try:
        # Import Odoo environment
        import odoo
        from odoo import api, SUPERUSER_ID
        
        # Initialize Odoo environment
        odoo.cli.server.report_configuration()
        
        # Get database connection
        db_name = 'your_database_name'  # Replace with your database name
        registry = odoo.registry(db_name)
        
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            
            # Get machine config model
            MachineConfig = env['manufacturing.machine.config']
            
            # Search for machines (Ruhlamat and Aumann)
            domain = [('machine_type', 'in', ['ruhlamat', 'aumann'])]
            if machine_name:
                domain.append(('machine_name', '=', machine_name))
            
            machines = MachineConfig.search(domain)
            
            if not machines:
                print("No Ruhlamat or Aumann machines found")
                return
            
            print(f"Monitoring {len(machines)} machine(s)...")
            print("=" * 80)
            
            while True:
                for machine in machines:
                    progress_info = machine.get_sync_progress()
                    
                    print(f"\nMachine: {progress_info['machine_name']} ({machine.machine_type})")
                    print(f"Status: {progress_info['status']}")
                    print(f"Progress: {progress_info['sync_progress']:.1f}%")
                    print(f"Stage: {progress_info['sync_stage']}")
                    
                    if progress_info['sync_total_records'] > 0:
                        if machine.machine_type == 'ruhlamat':
                            print(f"Cycles: {progress_info['sync_processed_records']}/{progress_info['sync_total_records']}")
                        elif machine.machine_type == 'aumann':
                            print(f"CSV Files: {progress_info['sync_processed_records']}/{progress_info['sync_total_records']}")
                        else:
                            print(f"Records: {progress_info['sync_processed_records']}/{progress_info['sync_total_records']}")
                        
                        # Calculate estimated time remaining
                        if progress_info['sync_start_time'] and progress_info['sync_progress'] > 0:
                            from datetime import datetime
                            start_time = datetime.fromisoformat(progress_info['sync_start_time'].replace('Z', '+00:00'))
                            elapsed = datetime.now() - start_time.replace(tzinfo=None)
                            
                            if progress_info['sync_progress'] < 100:
                                estimated_total = elapsed.total_seconds() * (100 / progress_info['sync_progress'])
                                remaining = estimated_total - elapsed.total_seconds()
                                print(f"Elapsed: {elapsed}")
                                print(f"Estimated remaining: {remaining:.0f} seconds")
                    
                    print("-" * 40)
                
                # Check if any machine is still syncing
                syncing_machines = machines.filtered(lambda m: m.status == 'running' and m.sync_progress < 100)
                if not syncing_machines:
                    print("\nAll sync operations completed!")
                    break
                
                # Wait before next update
                time.sleep(5)  # Update every 5 seconds
                
    except ImportError:
        print("Odoo not found. Please run this script from within Odoo environment.")
        print("Alternative: Check Odoo logs for sync progress messages.")
        print("\nLog messages to look for:")
        print("- 'Starting Ruhlamat MDB sync for machine: [machine_name]'")
        print("- 'Found X cycles to process'")
        print("- 'Progress: X.X% - Processing cycle Y/Z'")
        print("- 'Ruhlamat MDB sync completed. Created X cycles and Y gaugings'")
        
    except Exception as e:
        print(f"Error monitoring sync progress: {e}")

def check_logs_for_progress():
    """
    Instructions for checking sync progress in logs
    """
        print("How to check sync progress in Odoo logs:")
        print("=" * 50)
        print("1. Check Odoo log file (usually in /var/log/odoo/ or your Odoo config)")
        print("2. Look for these log messages:")
        print("\n   Ruhlamat MDB sync:")
        print("   - 'Starting Ruhlamat MDB sync for machine: [machine_name]'")
        print("   - 'Found X cycles to process'")
        print("   - 'Progress: X.X% - Processing cycle Y/Z'")
        print("   - 'Found X gaugings for cycle Y'")
        print("   - 'Ruhlamat MDB sync completed. Created X cycles and Y gaugings'")
        print("   - 'Total processing time: [time]'")
        print("\n   Aumann CSV sync:")
        print("   - 'Starting Aumann data sync for machine: [machine_name]'")
        print("   - 'Found X CSV files in Aumann folder'")
        print("   - 'Progress: X.X% - Processing file Y/Z'")
        print("   - 'Successfully decoded [filename] using [encoding]'")
        print("   - 'Aumann data sync completed. Total records created: X'")
        print("   - 'Total processing time: [time]'")
        print("\n3. Use tail -f to follow logs in real-time:")
        print("   tail -f /var/log/odoo/odoo-server.log | grep -E '(Ruhlamat|Aumann|Progress)'")
        print("\n4. Or use grep to find specific progress:")
        print("   grep 'Progress:' /var/log/odoo/odoo-server.log")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        machine_name = sys.argv[1]
        print(f"Monitoring sync progress for machine: {machine_name}")
        monitor_sync_progress(machine_name)
    else:
        print("Monitoring sync progress for all Ruhlamat machines...")
        print("Usage: python monitor_sync_progress.py [machine_name]")
        print("\nIf Odoo environment is not available, check logs manually:")
        check_logs_for_progress()

