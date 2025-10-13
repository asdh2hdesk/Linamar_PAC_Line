# -*- coding: utf-8 -*-

import json
import logging
import time
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class FinalStationAPIController(http.Controller):
    """API Controller for Final Station Dashboard"""

    @http.route('/manufacturing/final_station/<int:machine_id>/live_data', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def get_live_data(self, machine_id):
        """Get live data for final station dashboard"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            live_data = machine.get_final_station_live_data()
            return live_data
            
        except Exception as e:
            _logger.error(f"Error getting live data for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/toggle_mode', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def toggle_operation_mode(self, machine_id):
        """Toggle operation mode for final station"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            result = machine.toggle_operation_mode()
            return {'success': True, 'result': result}
            
        except Exception as e:
            _logger.error(f"Error toggling mode for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/trigger_camera', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def trigger_camera(self, machine_id):
        """Manual camera trigger for final station"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            result = machine.manual_trigger_camera()
            return {'success': True, 'result': result}
            
        except Exception as e:
            _logger.error(f"Error triggering camera for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/check_part', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def check_part_presence(self, machine_id):
        """Check part presence for final station"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            result = machine.check_part_presence()
            return {'success': True, 'result': result}
            
        except Exception as e:
            _logger.error(f"Error checking part presence for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/cylinder_forward', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def cylinder_forward(self, machine_id):
        """Cylinder forward action for final station"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            result = machine.manual_cylinder_forward_action()
            return {'success': True, 'result': result}
            
        except Exception as e:
            _logger.error(f"Error controlling cylinder forward for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/cylinder_reverse', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def cylinder_reverse(self, machine_id):
        """Cylinder reverse action for final station"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            result = machine.manual_cylinder_reverse_action()
            return {'success': True, 'result': result}
            
        except Exception as e:
            _logger.error(f"Error controlling cylinder reverse for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/start_monitoring', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def start_monitoring(self, machine_id):
        """Start PLC monitoring for final station"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            result = machine.start_plc_monitoring_service()
            return {'success': result}
            
        except Exception as e:
            _logger.error(f"Error starting monitoring for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/stop_monitoring', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def stop_monitoring(self, machine_id):
        """Stop PLC monitoring for final station"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            result = machine.stop_plc_monitoring_service()
            return {'success': result}
            
        except Exception as e:
            _logger.error(f"Error stopping monitoring for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/test_plc', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def test_plc_connection(self, machine_id):
        """Test PLC connection for final station"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            result = machine.test_plc_connection()
            return {'success': True, 'result': result}
            
        except Exception as e:
            _logger.error(f"Error testing PLC connection for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/measurements', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def get_measurements(self, machine_id, limit=10):
        """Get recent measurements for final station"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            measurements = request.env['manufacturing.final.station.measurement'].search_read(
                [['machine_id', '=', machine_id]],
                ['serial_number', 'capture_date', 'result', 'operation_mode', 'trigger_type'],
                limit=limit,
                order='capture_date desc'
            )
            
            return {'success': True, 'measurements': measurements}
            
        except Exception as e:
            _logger.error(f"Error getting measurements for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/station_results', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def get_station_results(self, machine_id, serial_number=None):
        """Get station results for a specific serial number"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            # Use provided serial number or last serial number from machine
            if not serial_number:
                serial_number = machine.last_serial_number
            
            if not serial_number:
                return {'error': 'No serial number provided or available'}
            
            station_results = machine.get_station_results_by_serial(serial_number)
            return {'success': True, 'station_results': station_results}
            
        except Exception as e:
            _logger.error(f"Error getting station results for machine {machine_id}, serial {serial_number}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/update_station_result', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def update_station_result(self, machine_id, serial_number, station_type, result):
        """Update a specific station result for a serial number"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            if not serial_number or not station_type or not result:
                return {'error': 'Missing required parameters: serial_number, station_type, result'}
            
            success = machine.update_station_result(serial_number, station_type, result)
            return {'success': success}
            
        except Exception as e:
            _logger.error(f"Error updating station result for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/create_part_quality', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def create_part_quality(self, machine_id, serial_number):
        """Create a new part quality record for a serial number"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            if not serial_number:
                return {'error': 'Serial number is required'}
            
            part_quality = machine.get_or_create_part_quality(serial_number)
            if part_quality:
                return {'success': True, 'part_quality_id': part_quality.id}
            else:
                return {'error': 'Failed to create part quality record'}
            
        except Exception as e:
            _logger.error(f"Error creating part quality for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/test_station_results', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def test_station_results(self, machine_id, serial_number=None):
        """Test method to create sample station results"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            # Use provided serial number or create a test one
            if not serial_number:
                serial_number = f"TEST_{int(time.time())}"
            
            # Create or get part quality record
            part_quality = machine.get_or_create_part_quality(serial_number)
            if not part_quality:
                return {'error': 'Failed to create part quality record'}
            
            # Update with test results
            part_quality.write({
                'vici_result': 'pass',
                'ruhlamat_result': 'pending',
                'aumann_result': 'reject',
                'gauging_result': 'pass'
            })
            
            # Get the updated station results
            station_results = machine.get_station_results_by_serial(serial_number)
            return {'success': True, 'station_results': station_results}
            
        except Exception as e:
            _logger.error(f"Error creating test station results for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/print_box_barcode', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def print_box_barcode(self, machine_id, box_id):
        """Print barcode for a completed box"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            box = request.env['manufacturing.box.management'].browse(box_id)
            if not box.exists():
                return {'error': 'Box not found'}
            
            # Print the barcode
            result = box.print_barcode()
            
            return {'success': True, 'message': f'Barcode for box {box.box_number} sent to printer'}
            
        except Exception as e:
            _logger.error(f"Error printing barcode for machine {machine_id}, box {box_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/get_box_status', 
                type='json', auth='user', methods=['POST'], csrf=False)
    def get_box_status(self, machine_id):
        """Get current box status and statistics"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            # Get current boxes for both variants
            box_management = request.env['manufacturing.box.management']
            current_exhaust_box = box_management.get_or_create_current_box('exhaust')
            current_intake_box = box_management.get_or_create_current_box('intake')
            
            # Get box statistics
            statistics = box_management.get_box_statistics()
            
            return {
                'success': True,
                'current_boxes': {
                    'exhaust': {
                        'id': current_exhaust_box.id,
                        'box_number': current_exhaust_box.box_number,
                        'current_position': current_exhaust_box.current_position,
                        'max_capacity': current_exhaust_box.max_capacity,
                        'status': current_exhaust_box.status,
                        'passed_parts': current_exhaust_box.passed_parts
                    },
                    'intake': {
                        'id': current_intake_box.id,
                        'box_number': current_intake_box.box_number,
                        'current_position': current_intake_box.current_position,
                        'max_capacity': current_intake_box.max_capacity,
                        'status': current_intake_box.status,
                        'passed_parts': current_intake_box.passed_parts
                    }
                },
                'statistics': statistics
            }
            
        except Exception as e:
            _logger.error(f"Error getting box status for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/trigger_auto_monitoring', type='json', auth='user', methods=['POST'])
    def trigger_auto_monitoring(self, machine_id):
        """Manually trigger auto-start monitoring for testing"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            # Start PLC monitoring service if not running
            if not machine.plc_monitoring_active:
                _logger.info(f"Starting PLC monitoring service for {machine.machine_name}")
                if machine.start_plc_monitoring_service():
                    _logger.info(f"PLC monitoring service started successfully")
                else:
                    return {'error': 'Failed to start PLC monitoring service'}
            
            # Check part presence and trigger auto monitoring if part is present
            from ..models.final_station_service import FinalStationService
            service = FinalStationService(machine)
            part_present = service.check_part_presence()
            
            if part_present:
                _logger.info(f"Part detected (D0=1), triggering auto monitoring for {machine.machine_name}")
                service.direct_auto_start_monitoring()
                return {'success': True, 'message': 'Auto monitoring triggered - part detected'}
            else:
                return {'success': True, 'message': 'No part detected (D0=0) - auto monitoring not triggered'}
                
        except Exception as e:
            _logger.error(f"Error triggering auto monitoring for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/check_plc_status', type='json', auth='user', methods=['POST'])
    def check_plc_status(self, machine_id):
        """Check PLC monitoring status and current D0 value"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            # Check current PLC status
            from ..models.final_station_service import FinalStationService
            service = FinalStationService(machine)
            
            # Read D0 register directly
            part_present = service.check_part_presence()
            
            # Check PLC monitoring service status
            from ..models.plc_monitor_service import get_plc_monitor_service
            plc_service = get_plc_monitor_service()
            is_monitoring = plc_service.is_monitoring(machine_id)
            
            return {
                'success': True,
                'machine_id': machine_id,
                'machine_name': machine.machine_name,
                'plc_monitoring_active': machine.plc_monitoring_active,
                'plc_service_monitoring': is_monitoring,
                'plc_ip_address': machine.plc_ip_address,
                'plc_port': machine.plc_port,
                'current_d0_value': part_present,
                'part_present': part_present
            }
                
        except Exception as e:
            _logger.error(f"Error checking PLC status for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/restart_plc_monitoring', type='json', auth='user', methods=['POST'])
    def restart_plc_monitoring(self, machine_id):
        """Force restart PLC monitoring service"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            _logger.info(f"Force restarting PLC monitoring for {machine.machine_name}")
            
            # Stop existing monitoring
            if machine.plc_monitoring_active:
                machine.stop_plc_monitoring_service()
                _logger.info(f"Stopped existing PLC monitoring for {machine.machine_name}")
            
            # Wait a moment
            import time
            time.sleep(1)
            
            # Start fresh monitoring
            if machine.start_plc_monitoring_service():
                _logger.info(f"Successfully restarted PLC monitoring for {machine.machine_name}")
                return {'success': True, 'message': 'PLC monitoring restarted successfully'}
            else:
                return {'error': 'Failed to restart PLC monitoring service'}
                
        except Exception as e:
            _logger.error(f"Error restarting PLC monitoring for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/reset_processing_flag', type='json', auth='user', methods=['POST'])
    def reset_processing_flag(self, machine_id):
        """Reset the processing_part flag for testing"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            _logger.info(f"Resetting processing_part flag for {machine.machine_name}")
            machine.processing_part = False
            
            return {
                'success': True, 
                'message': 'Processing flag reset successfully',
                'processing_part': machine.processing_part
            }
                
        except Exception as e:
            _logger.error(f"Error resetting processing flag for machine {machine_id}: {str(e)}")
            return {'error': str(e)}

    @http.route('/manufacturing/final_station/<int:machine_id>/test_connection', type='json', auth='user', methods=['POST'])
    def test_connection(self, machine_id):
        """Test PLC connection and update status immediately"""
        try:
            machine = request.env['manufacturing.machine.config'].browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}
            
            if machine.machine_type != 'final_station':
                return {'error': 'Not a final station'}
            
            _logger.info(f"Testing PLC connection for {machine.machine_name}")
            
            # Test the connection
            from ..models.final_station_service import FinalStationService
            service = FinalStationService(machine)
            result = service.test_plc_connection()
            
            # Update the connection status immediately
            if result['success']:
                machine.plc_online = True
                machine.last_plc_communication = fields.Datetime.now()
                machine.status = 'running'
                _logger.info(f"PLC connection test successful for {machine.machine_name}")
            else:
                machine.plc_online = False
                machine.status = 'error'
                _logger.warning(f"PLC connection test failed for {machine.machine_name}: {result.get('message', 'Unknown error')}")
            
            return {
                'success': result['success'],
                'message': result.get('message', 'Connection test completed'),
                'plc_online': machine.plc_online,
                'status': machine.status,
                'last_communication': machine.last_plc_communication.isoformat() if machine.last_plc_communication else None
            }
                
        except Exception as e:
            _logger.error(f"Error testing connection for machine {machine_id}: {str(e)}")
            return {'error': str(e)}
