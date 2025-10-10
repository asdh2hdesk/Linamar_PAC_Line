#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for PLC monitoring integration
This script can be run to test the PLC monitoring functionality
"""

import sys
import os
import logging

# Add the Odoo path to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../odoo'))

# Configure logging
logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

def test_plc_service():
    """Test the PLC monitoring service directly"""
    try:
        from models.plc_monitor_service import get_plc_monitor_service
        
        _logger.info("Testing PLC Monitor Service...")
        
        # Get the service instance
        plc_service = get_plc_monitor_service()
        
        # Test configuration
        test_config = {
            'plc_ip': '192.168.1.100',  # Replace with actual PLC IP
            'plc_port': 502,
            'scan_rate': 0.5,  # 500ms scan rate for testing
            'callback': lambda machine_id, part_present, previous: _logger.info(f"Callback: Machine {machine_id}, Part present: {part_present}")
        }
        
        _logger.info("Starting test monitoring...")
        success = plc_service.start_monitoring(999, test_config)  # Use test machine ID 999
        
        if success:
            _logger.info("PLC monitoring started successfully")
            
            # Let it run for a few seconds
            import time
            time.sleep(5)
            
            # Check status
            status = plc_service.get_monitor_status(999)
            _logger.info(f"Monitor status: {status}")
            
            # Stop monitoring
            plc_service.stop_monitoring(999)
            _logger.info("PLC monitoring stopped")
            
        else:
            _logger.error("Failed to start PLC monitoring")
            
    except Exception as e:
        _logger.error(f"Error testing PLC service: {str(e)}")

def test_machine_config_integration():
    """Test the machine config integration with PLC service"""
    try:
        _logger.info("Testing Machine Config Integration...")
        
        # This would require Odoo environment setup
        # For now, just test the import
        from models.machine_config import MachineConfig
        _logger.info("MachineConfig class imported successfully")
        
        # Test method existence
        methods_to_test = [
            'start_plc_monitoring_service',
            'stop_plc_monitoring_service', 
            'get_plc_monitoring_status',
            'start_all_plc_monitoring',
            'stop_all_plc_monitoring',
            'continuous_final_station_monitoring',
            'final_station_status_update',
            'initialize_plc_monitoring_on_startup',
            'get_plc_monitoring_summary'
        ]
        
        for method_name in methods_to_test:
            if hasattr(MachineConfig, method_name):
                _logger.info(f"✓ Method {method_name} exists")
            else:
                _logger.error(f"✗ Method {method_name} missing")
                
    except Exception as e:
        _logger.error(f"Error testing machine config integration: {str(e)}")

if __name__ == "__main__":
    _logger.info("Starting PLC Integration Tests...")
    
    # Test 1: PLC Service
    test_plc_service()
    
    # Test 2: Machine Config Integration
    test_machine_config_integration()
    
    _logger.info("PLC Integration Tests completed!")
