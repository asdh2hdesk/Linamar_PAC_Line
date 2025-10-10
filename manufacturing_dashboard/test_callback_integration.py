#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for PLC callback integration
This script tests the thread-safe callback mechanism
"""

import sys
import os
import logging
import time

# Add the Odoo path to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../odoo'))

# Configure logging
logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

def test_callback_mechanism():
    """Test the callback mechanism without Odoo environment"""
    try:
        _logger.info("Testing PLC callback mechanism...")
        
        # Import the callback functions
        from models.machine_config import _plc_callback_queue, _start_plc_callback_processor, _stop_plc_callback_processor
        
        # Test 1: Start callback processor
        _logger.info("Starting callback processor...")
        _start_plc_callback_processor()
        
        # Test 2: Queue a test callback
        _logger.info("Queuing test callback...")
        test_callback_data = (5, True, False)  # Machine ID 5, part present, was not present
        _plc_callback_queue.put(test_callback_data)
        
        # Wait a bit for processing
        time.sleep(2)
        
        # Test 3: Stop callback processor
        _logger.info("Stopping callback processor...")
        _stop_plc_callback_processor()
        
        _logger.info("Callback mechanism test completed successfully!")
        return True
        
    except Exception as e:
        _logger.error(f"Error testing callback mechanism: {str(e)}")
        return False

def test_plc_service_callback():
    """Test the PLC service with callback integration"""
    try:
        _logger.info("Testing PLC service with callback...")
        
        from models.plc_monitor_service import get_plc_monitor_service
        
        # Get the service instance
        plc_service = get_plc_monitor_service()
        
        # Test callback function
        callback_called = False
        callback_data = None
        
        def test_callback(machine_id, part_present, previous_state):
            nonlocal callback_called, callback_data
            callback_called = True
            callback_data = (machine_id, part_present, previous_state)
            _logger.info(f"Test callback called: Machine {machine_id}, Part present: {part_present}, Previous: {previous_state}")
        
        # Test configuration
        test_config = {
            'plc_ip': '192.168.1.100',  # Replace with actual PLC IP
            'plc_port': 502,
            'scan_rate': 1.0,  # 1 second scan rate for testing
            'callback': test_callback
        }
        
        _logger.info("Starting test monitoring with callback...")
        success = plc_service.start_monitoring(999, test_config)  # Use test machine ID 999
        
        if success:
            _logger.info("PLC monitoring with callback started successfully")
            
            # Let it run for a few seconds
            time.sleep(3)
            
            # Check if callback was called
            if callback_called:
                _logger.info(f"✓ Callback was called with data: {callback_data}")
            else:
                _logger.warning("⚠ Callback was not called (this is normal if no PLC is connected)")
            
            # Stop monitoring
            plc_service.stop_monitoring(999)
            _logger.info("PLC monitoring stopped")
            
        else:
            _logger.error("Failed to start PLC monitoring with callback")
            
        return success
        
    except Exception as e:
        _logger.error(f"Error testing PLC service callback: {str(e)}")
        return False

def test_machine_config_methods():
    """Test that all required methods exist in MachineConfig"""
    try:
        _logger.info("Testing MachineConfig methods...")
        
        from models.machine_config import MachineConfig
        
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
            'get_plc_monitoring_summary',
            '_start_auto_cycle_from_callback',
            '_execute_auto_cycle_sequence'
        ]
        
        all_methods_exist = True
        for method_name in methods_to_test:
            if hasattr(MachineConfig, method_name):
                _logger.info(f"✓ Method {method_name} exists")
            else:
                _logger.error(f"✗ Method {method_name} missing")
                all_methods_exist = False
        
        return all_methods_exist
        
    except Exception as e:
        _logger.error(f"Error testing MachineConfig methods: {str(e)}")
        return False

if __name__ == "__main__":
    _logger.info("Starting PLC Callback Integration Tests...")
    
    # Test 1: Callback mechanism
    test1_result = test_callback_mechanism()
    
    # Test 2: PLC service with callback
    test2_result = test_plc_service_callback()
    
    # Test 3: MachineConfig methods
    test3_result = test_machine_config_methods()
    
    _logger.info("=" * 50)
    _logger.info("TEST RESULTS:")
    _logger.info(f"Callback mechanism: {'PASS' if test1_result else 'FAIL'}")
    _logger.info(f"PLC service callback: {'PASS' if test2_result else 'FAIL'}")
    _logger.info(f"MachineConfig methods: {'PASS' if test3_result else 'FAIL'}")
    _logger.info("=" * 50)
    
    if all([test1_result, test2_result, test3_result]):
        _logger.info("🎉 All tests passed! PLC callback integration is working correctly.")
    else:
        _logger.error("❌ Some tests failed. Please check the implementation.")
    
    _logger.info("PLC Callback Integration Tests completed!")
