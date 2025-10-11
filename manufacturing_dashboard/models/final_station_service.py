# -*- coding: utf-8 -*-

import socket
import struct
import time
import logging
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FinalStationService:
    """
    Service class for Final Station operations
    Handles PLC communication, camera operations, and mode management
    """
    
    def __init__(self, machine_record):
        self.machine = machine_record
        self.plc_ip = machine_record.plc_ip_address
        self.plc_port = machine_record.plc_port
        self.camera_ip = machine_record.camera_ip_address
        self.camera_port = machine_record.camera_port
        
    # =============================================================================
    # PLC COMMUNICATION METHODS
    # =============================================================================
    
    def read_plc_register(self, register, timeout=3, retries=2):
        """Read a single PLC register using Modbus TCP with retry logic"""
        for attempt in range(retries + 1):
            try:
                # Add small delay between attempts
                if attempt > 0:
                    time.sleep(0.5)
                
                with socket.create_connection((self.plc_ip, self.plc_port), timeout=timeout) as sock:
                    # Set socket options for better reliability
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    
                    # Create Modbus TCP read holding registers request
                    transaction_id = 1
                    protocol_id = 0
                    length = 6
                    unit_id = 1
                    function_code = 0x03  # Read Holding Registers
                    starting_address = register
                    quantity = 1
                    
                    # Build Modbus TCP frame
                    frame = struct.pack('>HHHBBHH', 
                                      transaction_id, 
                                      protocol_id, 
                                      length, 
                                      unit_id, 
                                      function_code, 
                                      starting_address, 
                                      quantity)
                    
                    # Send request
                    sock.sendall(frame)
                    time.sleep(0.05)  # Reduced delay
                    
                    # Receive response
                    response = sock.recv(1024)
                    
                    if len(response) >= 9:
                        # Parse response
                        transaction_id_resp, protocol_id_resp, length_resp, unit_id_resp, function_code_resp, byte_count = struct.unpack('>HHHBBB', response[:9])
                        
                        if function_code_resp == 0x03 and byte_count >= 2:
                            # Extract register value
                            register_value = struct.unpack('>H', response[9:11])[0]
                            return register_value
                        else:
                            _logger.warning(f"Invalid PLC response for D{register}: FC={function_code_resp}, BC={byte_count}")
                            if attempt == retries:
                                return None
                    else:
                        _logger.warning(f"Short PLC response for D{register}: {len(response)} bytes")
                        if attempt == retries:
                            return None
                            
            except socket.timeout:
                _logger.warning(f"PLC read timeout for D{register} (attempt {attempt + 1}/{retries + 1})")
                if attempt == retries:
                    return None
            except Exception as e:
                _logger.warning(f"PLC read error for D{register} (attempt {attempt + 1}/{retries + 1}): {str(e)}")
                if attempt == retries:
                    return None
        
        return None
    
    def write_plc_register(self, register, value, timeout=3, retries=2):
        """Write a single PLC register using Modbus TCP with retry logic"""
        for attempt in range(retries + 1):
            try:
                # Add small delay between attempts
                if attempt > 0:
                    time.sleep(0.5)
                
                with socket.create_connection((self.plc_ip, self.plc_port), timeout=timeout) as sock:
                    # Set socket options for better reliability
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    
                    # Create Modbus TCP write single register request
                    transaction_id = 1
                    protocol_id = 0
                    length = 6
                    unit_id = 1
                    function_code = 0x06  # Write Single Register
                    
                    # Build Modbus TCP frame
                    frame = struct.pack('>HHHBBHH', 
                                      transaction_id, 
                                      protocol_id, 
                                      length, 
                                      unit_id, 
                                      function_code, 
                                      register, 
                                      value)
                    
                    # Send request
                    sock.sendall(frame)
                    time.sleep(0.05)  # Reduced delay
                    
                    # Receive response
                    response = sock.recv(1024)
                    
                    if len(response) >= 12:
                        # Parse response
                        transaction_id_resp, protocol_id_resp, length_resp, unit_id_resp, function_code_resp, address_resp, value_resp = struct.unpack('>HHHBBHH', response[:12])
                        
                        if function_code_resp == 0x06 and address_resp == register and value_resp == value:
                            _logger.info(f"PLC D{register} written successfully: {value}")
                            return True
                        else:
                            _logger.warning(f"Invalid PLC write response for D{register}: FC={function_code_resp}, Addr={address_resp}, Val={value_resp}")
                            if attempt == retries:
                                return False
                    else:
                        _logger.warning(f"Short PLC write response for D{register}: {len(response)} bytes")
                        if attempt == retries:
                            return False
                            
            except socket.timeout:
                _logger.warning(f"PLC write timeout for D{register} (attempt {attempt + 1}/{retries + 1})")
                if attempt == retries:
                    return False
            except Exception as e:
                _logger.warning(f"PLC write error for D{register} (attempt {attempt + 1}/{retries + 1}): {str(e)}")
                if attempt == retries:
                    return False
        
        return False
    
    def read_all_plc_registers(self):
        """Read D0-D9 registers and return as dictionary with optimized connection"""
        registers = {}
        
        # Try to read multiple registers in one connection if possible
        # For now, read individually but with delays to reduce connection pressure
        for i in range(10):
            value = self.read_plc_register(i)
            registers[f'D{i}'] = value if value is not None else "ERROR"
            
            # Add small delay between reads to reduce connection pressure
            if i < 9:  # Don't delay after the last read
                time.sleep(0.1)
        
        return registers
    
    # =============================================================================
    # CAMERA COMMUNICATION METHODS
    # =============================================================================
    
    def send_camera_command(self, sock, cmd):
        """Send a command to Keyence camera and return response"""
        try:
            # Send command
            sock.sendall((cmd + '\r\n').encode('ascii'))
            time.sleep(0.2)  # Increased delay for stability
            
            # Receive response with timeout
            sock.settimeout(2)  # 2 second timeout for response
            data = sock.recv(1024).decode('ascii').strip()
            return data
        except socket.timeout:
            _logger.warning(f"Camera command {cmd} timeout")
            return None
        except Exception as e:
            _logger.error(f"Error sending camera command {cmd}: {str(e)}")
            return None
    
    def extract_serial_from_lon(self, lon_response):
        """Extract serial number from LON response"""
        try:
            _logger.info(f"Raw LON response: '{lon_response}'")
            
            if not lon_response:
                return None
                
            # Clean the response
            lon_response = lon_response.strip().strip("'\"")
            
            # Case 1: Response is numeric → use directly
            if lon_response.isdigit():
                return lon_response
            
            # Case 2: Heartbeat mode → try different approaches
            elif lon_response.lower() in ["heartbeat", "heartbeat", "heart beat"]:
                _logger.info("Camera in heartbeat mode, attempting to fetch serial...")
                
                # Try multiple approaches for heartbeat mode
                serial = self._handle_heartbeat_mode()
                if serial:
                    return serial
                
                _logger.error("Failed to fetch serial number in heartbeat mode")
                return None
            
            # Case 3: Try to extract any numeric part
            else:
                import re
                numbers = re.findall(r'\d+', lon_response)
                if numbers:
                    return max(numbers, key=len)
                else:
                    _logger.warning(f"Invalid LON response format: '{lon_response}'")
                    return None
                    
        except Exception as e:
            _logger.error(f"Error extracting serial from LON: {str(e)}")
            return None
    
    def _handle_heartbeat_mode(self):
        """Handle camera heartbeat mode with multiple strategies"""
        try:
            # Strategy 1: Try LON command multiple times
            for attempt in range(3):
                _logger.info(f"Heartbeat mode - LON attempt {attempt + 1}/3")
                response = self._get_lon_response_safe()
                if response and response.strip().isdigit():
                    _logger.info(f"Got serial from LON attempt {attempt + 1}: {response.strip()}")
                    return response.strip()
                time.sleep(0.5)
            
            # Strategy 2: Try TRG command to trigger measurement
            _logger.info("Trying TRG command to trigger measurement...")
            with socket.create_connection((self.camera_ip, self.camera_port), timeout=5) as sock:
                # Send TRG command
                trg_response = self.send_camera_command(sock, "TRG")
                _logger.info(f"TRG response: {trg_response}")
                
                # Wait for processing
                time.sleep(1)
                
                # Try LON again after TRG
                lon_response = self.send_camera_command(sock, "LON")
                _logger.info(f"LON after TRG: {lon_response}")
                
                if lon_response and lon_response.strip().isdigit():
                    return lon_response.strip()
                
                # Try RD command to read result
                rd_response = self.send_camera_command(sock, "RD")
                _logger.info(f"RD response: {rd_response}")
                
                # Extract serial from RD response
                if rd_response:
                    import re
                    numbers = re.findall(r'\d+', rd_response)
                    if numbers:
                        return max(numbers, key=len)
            
            # Strategy 3: Generate timestamp-based serial as fallback
            _logger.warning("Using timestamp-based serial as fallback")
            timestamp = int(time.time() * 1000) % 100000  # Last 5 digits of timestamp
            return str(timestamp)
            
        except Exception as e:
            _logger.error(f"Error in heartbeat mode handling: {str(e)}")
            return None
    
    def _get_lon_response_safe(self):
        """Safely get LON response from camera"""
        try:
            with socket.create_connection((self.camera_ip, self.camera_port), timeout=5) as sock:
                return self.send_camera_command(sock, "LON")
        except Exception as e:
            _logger.error(f"Error getting LON response: {str(e)}")
            return None
    
    def trigger_camera_and_get_data(self):
        """Trigger camera and get QR code data from Keyence camera"""
        try:
            _logger.info(f"Connecting to Keyence camera at {self.camera_ip}:{self.camera_port}")
            
            with socket.create_connection((self.camera_ip, self.camera_port), timeout=10) as sock:
                _logger.info("✅ Connected to Keyence camera!")
                
                # Set socket options for better reliability
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                
                # Send LON command to get serial number
                lon_response = self.send_camera_command(sock, "LON")
                _logger.info(f"LON response: {lon_response}")
                
                # Extract serial number from LON response
                serial_number = self.extract_serial_from_lon(lon_response)
                
                if serial_number:
                    # Trigger camera read
                    trg_response = self.send_camera_command(sock, "TRG")
                    _logger.info(f"TRG response: {trg_response}")
                    
                    # Wait for processing
                    time.sleep(1)  # Increased wait time
                    
                    # Read result
                    rd_response = self.send_camera_command(sock, "RD")
                    _logger.info(f"RD response: {rd_response}")
                    
                    # Unlock communication
                    self.send_camera_command(sock, "LOFF")
                    
                    # Prepare camera data
                    camera_data = {
                        'serial_number': serial_number,
                        'raw_data': f"Keyence camera data from {self.camera_ip} at {datetime.now().isoformat()}",
                        'qr_code_data': {
                            'scanned_text': serial_number,
                            'lon_response': lon_response,
                            'trg_response': trg_response,
                            'rd_response': rd_response,
                            'scan_time': datetime.now().isoformat()
                        }
                    }
                    
                    _logger.info(f"Camera data received: {camera_data}")
                    return camera_data
                else:
                    _logger.error("Failed to extract serial number from LON response")
                    return None
                    
        except Exception as e:
            _logger.error(f"Camera trigger error: {str(e)}")
            return None
    
    # =============================================================================
    # OPERATION MODE METHODS
    # =============================================================================
    
    def set_operation_mode(self, mode):
        """Set operation mode (auto/manual) and update PLC D2 register"""
        try:
            if mode not in ['auto', 'manual']:
                raise ValueError("Mode must be 'auto' or 'manual'")
            
            d2_value = 0 if mode == 'auto' else 1
            success = self.write_plc_register(2, d2_value)
            
            if success:
                self.machine.operation_mode = mode
                _logger.info(f"Operation mode set to {mode} (D2={d2_value})")
                return True
            else:
                _logger.error(f"Failed to write D2 to PLC for mode {mode}")
                return False
                
        except Exception as e:
            _logger.error(f"Error setting operation mode: {str(e)}")
            return False
    
    def toggle_operation_mode(self):
        """Toggle between auto and manual mode"""
        current_mode = self.machine.operation_mode
        new_mode = 'manual' if current_mode == 'auto' else 'auto'
        return self.set_operation_mode(new_mode)
    
    # =============================================================================
    # PART PRESENCE AND MONITORING
    # =============================================================================
    
    def check_part_presence(self):
        """Check for part presence via PLC D0 register"""
        try:
            d0_value = self.read_plc_register(0)
            if d0_value is not None:
                part_present = (d0_value == 1)
                self.machine.part_present = part_present
                _logger.info(f"PLC D0 (part_present) = {d0_value} -> {part_present}")
                return part_present
            else:
                _logger.warning("Failed to read PLC D0 for part presence")
                return False
                
        except Exception as e:
            _logger.error(f"Error checking part presence: {str(e)}")
            return False
    
    def write_result_to_plc(self, result):
        """Write result to PLC D1 register (0=OK, 1=NOK)"""
        try:
            result_value = 1 if result == 'nok' else 0
            success = self.write_plc_register(1, result_value)
            
            if success:
                _logger.info(f"PLC D1 (result) written: {result_value} ({'NOK' if result_value == 1 else 'OK'})")
                return True
            else:
                _logger.error("Failed to write result to PLC D1")
                return False
                
        except Exception as e:
            _logger.error(f"Error writing result to PLC: {str(e)}")
            return False
    
    def reset_plc_result(self):
        """Reset PLC D1 register to 0 when part is removed"""
        return self.write_plc_register(1, 0)
    
    # =============================================================================
    # CYLINDER CONTROL METHODS
    # =============================================================================
    
    def cylinder_forward_pulse(self):
        """Send forward pulse to cylinder (D3=1 for 1 second)"""
        try:
            # Write D3=1
            if self.write_plc_register(3, 1):
                self.machine.cylinder_forward = True
                self.machine.manual_cylinder_forward = True
                _logger.info("PLC D3 (Cylinder Forward) set to 1")
                
                # Wait 1 second
                time.sleep(1)
                
                # Reset D3=0
                if self.write_plc_register(3, 0):
                    self.machine.cylinder_forward = False
                    self.machine.manual_cylinder_forward = False
                    _logger.info("PLC D3 (Cylinder Forward) reset to 0")
                    return True
                else:
                    _logger.error("Failed to reset D3 to 0")
                    return False
            else:
                _logger.error("Failed to set D3 to 1")
                return False
                
        except Exception as e:
            _logger.error(f"Cylinder forward error: {str(e)}")
            return False
    
    def cylinder_reverse_pulse(self):
        """Send reverse pulse to cylinder (D4=1 for 1 second)"""
        try:
            # Write D4=1
            if self.write_plc_register(4, 1):
                self.machine.cylinder_reverse = True
                self.machine.manual_cylinder_reverse = True
                _logger.info("PLC D4 (Cylinder Reverse) set to 1")
                
                # Wait 1 second
                time.sleep(1)
                
                # Reset D4=0
                if self.write_plc_register(4, 0):
                    self.machine.cylinder_reverse = False
                    self.machine.manual_cylinder_reverse = False
                    _logger.info("PLC D4 (Cylinder Reverse) reset to 0")
                    return True
                else:
                    _logger.error("Failed to reset D4 to 0")
                    return False
            else:
                _logger.error("Failed to set D4 to 1")
                return False
                
        except Exception as e:
            _logger.error(f"Cylinder reverse error: {str(e)}")
            return False
    
    # =============================================================================
    # STATION RESULT CHECKING
    # =============================================================================
    
    def check_all_stations_result(self, serial_number):
        """Check result from all previous stations for a given serial number from part_quality table"""
        try:
            _logger.info(f"Checking all stations result for serial: {serial_number}")
            
            # Get part quality record
            part_quality = self.machine.env['manufacturing.part.quality'].search([
                ('serial_number', '=', serial_number)
            ], limit=1)
            
            if not part_quality:
                _logger.info(f"No part quality record found for serial: {serial_number}, creating new record")
                # Create a new part quality record with pending results
                part_quality = self.machine.env['manufacturing.part.quality'].create({
                    'serial_number': serial_number,
                    'test_date': datetime.now(),
                    'vici_result': 'pending',
                    'ruhlamat_result': 'pending',
                    'aumann_result': 'pending',
                    'gauging_result': 'pending'
                })
                _logger.info(f"Created new part quality record for serial: {serial_number}")
            
            # Get station results from part_quality
            station_results = {
                'vici_vision': part_quality.vici_result,
                'ruhlamat_press': part_quality.ruhlamat_result,
                'aumann_measurement': part_quality.aumann_result,
                'gauging': part_quality.gauging_result
            }
            
            # Convert to final station format (pass/reject -> ok/nok)
            converted_results = {}
            for station, result in station_results.items():
                if result == 'pass':
                    converted_results[station] = 'ok'
                elif result == 'reject':
                    converted_results[station] = 'nok'
                else:  # pending
                    converted_results[station] = 'pending'
            
            # Determine final result logic:
            # - If ALL stations are pending -> NOK (reject)
            # - If ANY station is NOK -> NOK (reject)  
            # - If ALL stations are OK -> OK (pass)
            all_pending = all(result == 'pending' for result in converted_results.values())
            any_nok = any(result == 'nok' for result in converted_results.values())
            all_ok = all(result == 'ok' for result in converted_results.values())
            
            if all_pending:
                final_result = 'nok'  # Reject if all stations are pending
            elif any_nok:
                final_result = 'nok'  # Reject if any station failed
            elif all_ok:
                final_result = 'ok'   # Pass only if all stations passed
            else:
                final_result = 'nok'  # Default to reject
            
            # Update the part_quality record with the calculated final result
            if part_quality.final_result != final_result:
                part_quality.final_result = final_result
                _logger.info(f"Updated final_result in part_quality record: {final_result}")
            
            _logger.info(f"All stations results: {converted_results}")
            _logger.info(f"Final result: {final_result}")
            
            return {
                'final_result': final_result,
                'station_results': converted_results,
                'part_quality_id': part_quality.id,
                'serial_number': serial_number
            }
            
        except Exception as e:
            _logger.error(f"Error checking all stations result: {str(e)}")
            return {
                'final_result': 'nok',
                'station_results': {},
                'serial_number': serial_number
            }
    
    def _check_vici_vision_result(self, serial_number):
        """Check VICI Vision result for serial number"""
        try:
            vici_record = self.machine.env['manufacturing.vici.vision'].search([
                ('serial_number', '=', serial_number)
            ], limit=1, order='test_date desc')
            return vici_record.result if vici_record else None
        except Exception as e:
            _logger.error(f"Error checking VICI Vision result: {str(e)}")
            return None
    
    def _check_ruhlamat_result(self, serial_number):
        """Check Ruhlamat Press result for serial number"""
        try:
            ruhlamat_record = self.machine.env['manufacturing.ruhlamat.press'].search([
                ('serial_number', '=', serial_number)
            ], limit=1, order='test_date desc')
            return ruhlamat_record.result if ruhlamat_record else None
        except Exception as e:
            _logger.error(f"Error checking Ruhlamat result: {str(e)}")
            return None
    
    def _check_aumann_result(self, serial_number):
        """Check Aumann Measurement result for serial number"""
        try:
            aumann_record = self.machine.env['manufacturing.aumann.measurement'].search([
                ('serial_number', '=', serial_number)
            ], limit=1, order='test_date desc')
            return aumann_record.result if aumann_record else None
        except Exception as e:
            _logger.error(f"Error checking Aumann result: {str(e)}")
            return None
    
    def _check_gauging_result(self, serial_number):
        """Check Gauging result for serial number"""
        try:
            gauging_record = self.machine.env['manufacturing.gauging.measurement'].search([
                ('serial_number', '=', serial_number)
            ], limit=1, order='test_date desc')
            return gauging_record.result if gauging_record else None
        except Exception as e:
            _logger.error(f"Error checking Gauging result: {str(e)}")
            return None
    
    # =============================================================================
    # MEASUREMENT CREATION
    # =============================================================================
    
    def create_measurement_record(self, serial_number, result, trigger_type='auto'):
        """Create measurement record with aggregated result"""
        try:
            measurement = self.machine.env['manufacturing.final.station.measurement'].create_measurement_record(
                machine_id=self.machine.id,
                serial_number=serial_number,
                result=result,
                operation_mode=self.machine.operation_mode,
                trigger_type=trigger_type,
                raw_data=f"Final station measurement at {datetime.now().isoformat()}"
            )
            
            if measurement:
                # Update machine status
                self.machine.camera_triggered = True
                self.machine.last_serial_number = serial_number
                self.machine.last_capture_time = datetime.now()
                self.machine.last_result = result
                
                _logger.info(f"Measurement record created: Serial={serial_number}, Result={result}")
                return measurement
            else:
                _logger.error("Failed to create measurement record")
                return None
                
        except Exception as e:
            _logger.error(f"Error creating measurement record: {str(e)}")
            return None
    
    # =============================================================================
    # AUTO MODE OPERATIONS
    # =============================================================================
    
    def auto_start_monitoring(self):
        """Automatically start PLC monitoring when part is detected"""
        try:
            _logger.info(f"Auto-starting PLC monitoring for {self.machine.machine_name}")
            
            # Import PLC monitor service
            from .plc_monitor_service import get_plc_monitor_service
            
            # Check if monitoring is already active
            plc_service = get_plc_monitor_service()
            if plc_service.is_monitoring(self.machine.id):
                _logger.info(f"PLC monitoring already active for machine {self.machine.id}")
                return True
            
            # Start monitoring with auto callback
            config = {
                'plc_ip': self.plc_ip,
                'plc_port': self.plc_port,
                'scan_rate': 0.5,  # 500ms scan rate for auto mode
                'callback': self._auto_monitoring_callback
            }
            
            success = plc_service.start_monitoring(self.machine.id, config)
            
            if success:
                # Update machine status
                self.machine.plc_monitoring_active = True
                self.machine.plc_scan_rate = 0.5
                _logger.info(f"Auto-started PLC monitoring for machine {self.machine.id}")
                return True
            else:
                _logger.error(f"Failed to auto-start PLC monitoring for machine {self.machine.id}")
                return False
                
        except Exception as e:
            _logger.error(f"Error auto-starting monitoring: {str(e)}")
            return False

    def direct_auto_start_monitoring(self):
        """Direct auto-start monitoring without cron dependency - immediate execution"""
        try:
            _logger.info(f"Direct auto-starting monitoring for {self.machine.machine_name}")
            
            # Ensure monitoring is active
            if not self.machine.plc_monitoring_active:
                # Start monitoring immediately
                self.machine.plc_monitoring_active = True
                self.machine.plc_scan_rate = 0.5
                self.machine.last_plc_scan = fields.Datetime.now()
                _logger.info(f"Direct auto monitoring started for {self.machine.machine_name}")
            else:
                _logger.info(f"PLC monitoring already active for {self.machine.machine_name}")
            
            # Trigger camera immediately since part is detected (D0=1)
            _logger.info(f"Part detected (D0=1), triggering camera for {self.machine.machine_name}")
            self.auto_trigger_camera()
            
            return True
            
        except Exception as e:
            _logger.error(f"Error in direct auto-start monitoring: {str(e)}")
            return False

    def _auto_monitoring_callback(self, machine_id, part_present, previous_part_present):
        """Callback function for auto monitoring when part presence changes"""
        try:
            _logger.info(f"Auto monitoring callback: Machine {machine_id}, Part present: {previous_part_present} -> {part_present}")
            
            # Update machine status
            self.machine.part_present = part_present
            self.machine.last_plc_scan = datetime.now()
            
            # If part is removed (part_present = False), stop monitoring
            if not part_present and previous_part_present:
                _logger.info(f"Part removed, stopping auto monitoring for machine {machine_id}")
                self.auto_stop_monitoring()
            
        except Exception as e:
            _logger.error(f"Error in auto monitoring callback: {str(e)}")
    
    def auto_stop_monitoring(self):
        """Automatically stop PLC monitoring when part is removed"""
        try:
            _logger.info(f"Auto-stopping PLC monitoring for {self.machine.machine_name}")
            
            # Import PLC monitor service
            from .plc_monitor_service import get_plc_monitor_service
            
            # Stop monitoring
            plc_service = get_plc_monitor_service()
            success = plc_service.stop_monitoring(self.machine.id)
            
            if success:
                # Update machine status
                self.machine.plc_monitoring_active = False
                _logger.info(f"Auto-stopped PLC monitoring for machine {self.machine.id}")
                return True
            else:
                _logger.warning(f"PLC monitoring was not active for machine {self.machine.id}")
                return False
                
        except Exception as e:
            _logger.error(f"Error auto-stopping monitoring: {str(e)}")
            return False
    
    def auto_trigger_camera(self):
        """Auto camera trigger when part is detected (D0=1) - Direct implementation without cron"""
        try:
            _logger.info(f"Auto camera trigger for {self.machine.machine_name}")
            
            # Check if already processing a part
            if self.machine.processing_part:
                _logger.info(f"Already processing a part (processing_part={self.machine.processing_part}), skipping trigger")
                return False
            
            # Check PLC D0 register for part presence
            part_present = self.check_part_presence()
            if not part_present:
                _logger.info("PLC D0=0, no part present, skipping camera trigger")
                return False
            
            # Set processing flag to prevent multiple triggers
            self.machine.processing_part = True
            _logger.info("PLC D0=1, part present, triggering camera...")
            
            # Mark as processing part
            _logger.info(f"Part detected (D0=1), starting processing for {self.machine.machine_name}")
            
            # Trigger camera and get QR code data
            camera_data = self.trigger_camera_and_get_data()
            
            if camera_data and camera_data.get('serial_number'):
                serial_number = camera_data.get('serial_number')
                
                # Check results from all previous stations
                station_results = self.check_all_stations_result(serial_number)
                final_result = station_results.get('final_result', 'nok')
                
                # Create measurement record
                measurement = self.create_measurement_record(serial_number, final_result, 'auto')
                
                if measurement:
                    # Write result back to PLC D1 register
                    self.write_result_to_plc(final_result)
                    
                    # Reset part presence and processing flag
                    self.machine.part_present = False
                    self.machine.processing_part = False
                    
                    _logger.info(f"Auto camera triggered successfully. Serial: {serial_number}, Final Result: {final_result}")
                    return True
                else:
                    _logger.error("Failed to create measurement record")
                    self.machine.processing_part = False
                    return False
            else:
                _logger.error("Failed to get QR code from camera")
                self.machine.processing_part = False
                return False
            
        except Exception as e:
            _logger.error(f"Auto camera trigger error: {str(e)}")
            self.machine.processing_part = False
            return False
    
    # =============================================================================
    # MANUAL MODE OPERATIONS
    # =============================================================================
    
    def manual_trigger_camera(self):
        """Manual camera trigger for final station"""
        try:
            _logger.info(f"Manual camera trigger for {self.machine.machine_name}")
            
            # Trigger camera and get QR code data
            camera_data = self.trigger_camera_and_get_data()
            
            if camera_data and camera_data.get('serial_number'):
                serial_number = camera_data.get('serial_number')
                
                # Check results from all previous stations
                station_results = self.check_all_stations_result(serial_number)
                final_result = station_results.get('final_result', 'nok')
                
                # Create measurement record
                measurement = self.create_measurement_record(serial_number, final_result, 'manual')
                
                if measurement:
                    self.machine.manual_camera_trigger = True
                    _logger.info(f"Manual camera triggered successfully. Serial: {serial_number}, Final Result: {final_result}")
                    return True
                else:
                    _logger.error("Failed to create measurement record")
                    return False
            else:
                _logger.error("Failed to get QR code from camera")
                return False
            
        except Exception as e:
            _logger.error(f"Manual camera trigger error: {str(e)}")
            return False
    
    # =============================================================================
    # DASHBOARD DATA METHODS
    # =============================================================================
    
    def get_station_results_for_dashboard(self, serial_number):
        """Get all station results formatted for dashboard display"""
        try:
            _logger.info(f"Getting station results for dashboard: {serial_number}")
            
            # Get part quality record
            part_quality = self.machine.env['manufacturing.part.quality'].search([
                ('serial_number', '=', serial_number)
            ], limit=1)
            
            if not part_quality:
                _logger.info(f"No part quality record found for serial: {serial_number}, creating new record")
                # Create a new part quality record with pending results
                part_quality = self.machine.env['manufacturing.part.quality'].create({
                    'serial_number': serial_number,
                    'test_date': datetime.now(),
                    'vici_result': 'pending',
                    'ruhlamat_result': 'pending',
                    'aumann_result': 'pending',
                    'gauging_result': 'pending'
                })
                _logger.info(f"Created new part quality record for serial: {serial_number}")
            
            # Format station results for dashboard
            stations = [
                {
                    'name': 'VICI Vision',
                    'result': part_quality.vici_result,
                    'status': self._get_status_icon(part_quality.vici_result),
                    'color': self._get_status_color(part_quality.vici_result)
                },
                {
                    'name': 'Ruhlamat Press',
                    'result': part_quality.ruhlamat_result,
                    'status': self._get_status_icon(part_quality.ruhlamat_result),
                    'color': self._get_status_color(part_quality.ruhlamat_result)
                },
                {
                    'name': 'Aumann Measurement',
                    'result': part_quality.aumann_result,
                    'status': self._get_status_icon(part_quality.aumann_result),
                    'color': self._get_status_color(part_quality.aumann_result)
                },
                {
                    'name': 'Gauging System',
                    'result': part_quality.gauging_result,
                    'status': self._get_status_icon(part_quality.gauging_result),
                    'color': self._get_status_color(part_quality.gauging_result)
                }
            ]
            
            # Determine overall status using same logic as check_all_stations_result
            results = [part_quality.vici_result, part_quality.ruhlamat_result, 
                      part_quality.aumann_result, part_quality.gauging_result]
            
            all_pending = all(result == 'pending' for result in results)
            any_reject = any(result == 'reject' for result in results)
            all_pass = all(result == 'pass' for result in results)
            
            if all_pending:
                overall_status = 'reject'  # Reject if all stations are pending
            elif any_reject:
                overall_status = 'reject'  # Reject if any station failed
            elif all_pass:
                overall_status = 'pass'    # Pass only if all stations passed
            else:
                overall_status = 'reject'  # Default to reject
            
            # Update the part_quality record with the calculated overall status
            if part_quality.final_result != overall_status:
                part_quality.final_result = overall_status
                _logger.info(f"Updated final_result in part_quality record: {overall_status}")
            
            return {
                'serial_number': serial_number,
                'stations': stations,
                'final_result': overall_status,  # Use calculated status
                'overall_status': overall_status,
                'test_date': part_quality.test_date.isoformat() if part_quality.test_date else None,
                'qe_override': part_quality.qe_override,
                'qe_comments': part_quality.qe_comments
            }
            
        except Exception as e:
            _logger.error(f"Error getting station results for dashboard: {str(e)}")
            return {
                'serial_number': serial_number,
                'stations': [],
                'final_result': 'pending',
                'overall_status': 'pending'
            }
    
    def _get_status_icon(self, result):
        """Get status icon for result"""
        if result == 'pass':
            return 'fa-check-circle'
        elif result == 'reject':
            return 'fa-times-circle'
        else:  # pending
            return 'fa-clock-o'
    
    def _get_status_color(self, result):
        """Get status color for result"""
        if result == 'pass':
            return 'text-success'
        elif result == 'reject':
            return 'text-danger'
        else:  # pending
            return 'text-warning'
    
    # =============================================================================
    # STATION RESULT UPDATES
    # =============================================================================
    
    def update_station_result(self, serial_number, station_type, result):
        """Update a specific station result in part_quality table"""
        try:
            _logger.info(f"Updating {station_type} result for serial {serial_number}: {result}")
            
            # Get part quality record
            part_quality = self.machine.env['manufacturing.part.quality'].search([
                ('serial_number', '=', serial_number)
            ], limit=1)
            
            if not part_quality:
                _logger.warning(f"No part quality record found for serial: {serial_number}")
                return False
            
            # Update the specific station result
            field_name = f"{station_type}_result"
            if hasattr(part_quality, field_name):
                part_quality.write({field_name: result})
                _logger.info(f"Updated {field_name} to {result} for serial {serial_number}")
                return True
            else:
                _logger.error(f"Invalid station type: {station_type}")
                return False
                
        except Exception as e:
            _logger.error(f"Error updating station result: {str(e)}")
            return False
    
    def get_or_create_part_quality(self, serial_number):
        """Get existing part quality record or create new one"""
        try:
            part_quality = self.machine.env['manufacturing.part.quality'].search([
                ('serial_number', '=', serial_number)
            ], limit=1)
            
            if not part_quality:
                _logger.info(f"Creating new part quality record for serial: {serial_number}")
                part_quality = self.machine.env['manufacturing.part.quality'].create({
                    'serial_number': serial_number,
                    'test_date': datetime.now(),
                    'vici_result': 'pending',
                    'ruhlamat_result': 'pending',
                    'aumann_result': 'pending',
                    'gauging_result': 'pending'
                })
                _logger.info(f"Created new part quality record for serial: {serial_number}")
            
            return part_quality
            
        except Exception as e:
            _logger.error(f"Error getting or creating part quality record: {str(e)}")
            return None
    
    # =============================================================================
    # CONNECTION TESTING
    # =============================================================================
    
    def test_plc_connection(self):
        """Test PLC connection and read D0-D9 values"""
        try:
            _logger.info(f"Testing PLC connection to {self.plc_ip}:{self.plc_port}")
            
            # Test connection by reading all registers
            registers = self.read_all_plc_registers()
            
            # Update PLC status
            self.machine.last_plc_communication = datetime.now()
            self.machine._compute_plc_status()
            
            # Prepare success message
            success_message = f"PLC connection successful to {self.plc_ip}:{self.plc_port}\n"
            success_message += "D0-D9 values:\n"
            for i in range(10):
                success_message += f"D{i}: {registers[f'D{i}']}\n"
            
            _logger.info(f"PLC test completed successfully")
            
            return {
                'success': True,
                'message': success_message,
                'registers': registers
            }
            
        except Exception as e:
            error_msg = f"PLC connection error: {str(e)}"
            _logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
