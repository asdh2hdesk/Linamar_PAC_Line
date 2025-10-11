# -*- coding: utf-8 -*-

import threading
import time
import socket
import struct
import logging
from datetime import datetime
from collections import deque

_logger = logging.getLogger(__name__)


class PLCMonitorService:
    """
    Continuous PLC Monitoring Service with Threading
    Monitors PLC registers in real-time for part presence detection
    """
    
    def __init__(self):
        self.monitors = {}  # Dictionary of machine_id -> monitor thread
        self.stop_events = {}  # Dictionary of machine_id -> stop event
        self.lock = threading.Lock()
        
    def start_monitoring(self, machine_id, config):
        """
        Start continuous monitoring for a machine
        
        Args:
            machine_id: ID of the machine to monitor
            config: Dictionary with PLC configuration
                - plc_ip: PLC IP address
                - plc_port: PLC port (default 502)
                - scan_rate: Scan rate in seconds (default 0.1)
                - callback: Function to call when part presence changes
        """
        with self.lock:
            # Stop existing monitor if any
            if machine_id in self.monitors:
                self.stop_monitoring(machine_id)
            
            # Create stop event
            stop_event = threading.Event()
            self.stop_events[machine_id] = stop_event
            
            # Create and start monitor thread
            monitor_thread = threading.Thread(
                target=self._monitor_loop,
                args=(machine_id, config, stop_event),
                daemon=True,
                name=f"PLCMonitor-{machine_id}"
            )
            
            self.monitors[machine_id] = monitor_thread
            monitor_thread.start()
            
            _logger.info(f"Started PLC monitoring for machine {machine_id}")
            return True
    
    def stop_monitoring(self, machine_id):
        """Stop monitoring for a machine"""
        with self.lock:
            if machine_id in self.stop_events:
                self.stop_events[machine_id].set()
                
            if machine_id in self.monitors:
                thread = self.monitors[machine_id]
                thread.join(timeout=5)  # Wait up to 5 seconds for thread to stop
                
                del self.monitors[machine_id]
                del self.stop_events[machine_id]
                
                _logger.info(f"Stopped PLC monitoring for machine {machine_id}")
                return True
            
            return False
    
    def is_monitoring(self, machine_id):
        """Check if monitoring is active for a machine"""
        with self.lock:
            if machine_id in self.monitors:
                thread = self.monitors[machine_id]
                is_alive = thread.is_alive()
                _logger.info(f"PLC monitoring thread for machine {machine_id}: exists={True}, is_alive={is_alive}, name={thread.name}")
                return is_alive
            else:
                _logger.info(f"PLC monitoring thread for machine {machine_id}: exists={False}")
                return False
    
    def stop_all(self):
        """Stop all monitoring threads"""
        with self.lock:
            machine_ids = list(self.monitors.keys())
        
        for machine_id in machine_ids:
            self.stop_monitoring(machine_id)
        
        _logger.info("Stopped all PLC monitoring")
    
    def _monitor_loop(self, machine_id, config, stop_event):
        """
        Main monitoring loop - runs continuously in a separate thread
        """
        plc_ip = config.get('plc_ip')
        plc_port = config.get('plc_port', 502)
        scan_rate = config.get('scan_rate', 0.1)  # 100ms default
        callback = config.get('callback')
        connection_callback = config.get('connection_callback')
        
        _logger.info(f"PLC Monitor loop started for machine {machine_id} - {plc_ip}:{plc_port}")
        _logger.info(f"PLC Monitor configuration: scan_rate={scan_rate}, callback={'provided' if callback else 'None'}")
        
        # State tracking
        previous_part_present = None
        consecutive_errors = 0
        max_consecutive_errors = 10
        reconnect_delay = 5
        last_connection_status = None  # Track connection status changes
        
        # Performance tracking
        scan_times = deque(maxlen=100)  # Track last 100 scan times
        
        while not stop_event.is_set():
            scan_start = time.time()
            
            try:
                # Read part presence from PLC D0 register
                part_present = self._read_plc_register(plc_ip, plc_port, register=0)
                
                # Check connection status
                current_connection_status = part_present is not None
                
                # Notify connection status change
                if current_connection_status != last_connection_status:
                    _logger.info(f"Machine {machine_id}: Connection status changed: {last_connection_status} -> {current_connection_status}")
                    if connection_callback:
                        try:
                            connection_callback(machine_id, current_connection_status)
                        except Exception as cb_error:
                            _logger.error(f"Connection callback error for machine {machine_id}: {str(cb_error)}")
                    last_connection_status = current_connection_status
                
                # Reset error counter on successful read
                if part_present is not None:
                    consecutive_errors = 0
                    
                    # Log current state every 10 scans (for debugging)
                    if hasattr(self, '_scan_count'):
                        self._scan_count += 1
                    else:
                        self._scan_count = 1
                    
                    if self._scan_count % 10 == 0:  # Log every 10th scan
                        _logger.info(f"Machine {machine_id}: D0={part_present} (scan #{self._scan_count})")
                    
                    # Detect state change
                    if part_present != previous_part_present:
                        _logger.info(f"Machine {machine_id}: Part presence changed: {previous_part_present} -> {part_present}")
                        
                        # Call callback function with state change
                        if callback:
                            try:
                                _logger.info(f"Machine {machine_id}: Calling callback function...")
                                callback(machine_id, part_present, previous_part_present)
                                _logger.info(f"Machine {machine_id}: Callback function completed")
                            except Exception as cb_error:
                                _logger.error(f"Callback error for machine {machine_id}: {str(cb_error)}")
                        else:
                            _logger.warning(f"Machine {machine_id}: No callback function provided")
                        
                        previous_part_present = part_present
                
                else:
                    consecutive_errors += 1
                    _logger.warning(f"Machine {machine_id}: Failed to read PLC (error {consecutive_errors}/{max_consecutive_errors})")
                    
                    # If too many consecutive errors, wait before retrying
                    if consecutive_errors >= max_consecutive_errors:
                        _logger.error(f"Machine {machine_id}: Too many consecutive errors, pausing for {reconnect_delay}s")
                        time.sleep(reconnect_delay)
                        consecutive_errors = 0  # Reset counter after pause
                
                # Track scan performance
                scan_duration = time.time() - scan_start
                scan_times.append(scan_duration)
                
                # Log performance periodically (every 100 scans)
                if len(scan_times) == 100:
                    avg_scan_time = sum(scan_times) / len(scan_times)
                    _logger.debug(f"Machine {machine_id}: Avg scan time: {avg_scan_time*1000:.2f}ms")
                
                # Sleep for remaining scan time
                sleep_time = max(0, scan_rate - scan_duration)
                if sleep_time > 0:
                    stop_event.wait(sleep_time)
                
            except Exception as e:
                _logger.error(f"Error in monitor loop for machine {machine_id}: {str(e)}")
                consecutive_errors += 1
                time.sleep(1)  # Wait before retry on error
        
        _logger.info(f"PLC Monitor loop stopped for machine {machine_id}")
    
    def _read_plc_register(self, plc_ip, plc_port, register=0, timeout=3):
        """
        Read a single holding register from PLC using Modbus TCP with improved reliability
        
        Args:
            plc_ip: PLC IP address
            plc_port: PLC port
            register: Register address (D0=0, D1=1, etc.)
            timeout: Socket timeout in seconds
            
        Returns:
            True/False for part presence, None on error
        """
        try:
            with socket.create_connection((plc_ip, plc_port), timeout=timeout) as sock:
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
                time.sleep(0.05)  # Small delay for stability
                
                # Receive response
                response = sock.recv(1024)
                
                if len(response) >= 9:
                    # Parse response header
                    trans_id, proto_id, length, unit, func_code, byte_count = struct.unpack('>HHHBBB', response[:9])
                    
                    if func_code == 0x03 and byte_count >= 2:
                        # Extract register value
                        register_value = struct.unpack('>H', response[9:11])[0]
                        
                        # For part presence (D0), return True if value is 1
                        return (register_value == 1)
                    else:
                        _logger.warning(f"Invalid PLC response: func_code={func_code}, byte_count={byte_count}")
                        return None
                else:
                    _logger.warning(f"Short PLC response: {len(response)} bytes")
                    return None
                    
        except socket.timeout:
            _logger.debug(f"PLC read timeout for {plc_ip}:{plc_port}")
            return None
        except Exception as e:
            _logger.debug(f"PLC read error for {plc_ip}:{plc_port}: {str(e)}")
            return None
    
    def write_plc_register(self, plc_ip, plc_port, register, value, timeout=2):
        """
        Write a single holding register to PLC using Modbus TCP
        
        Args:
            plc_ip: PLC IP address
            plc_port: PLC port
            register: Register address (D0=0, D1=1, etc.)
            value: Value to write (0-65535)
            timeout: Socket timeout in seconds
            
        Returns:
            True on success, False on error
        """
        try:
            with socket.create_connection((plc_ip, plc_port), timeout=timeout) as sock:
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
                
                # Receive response
                response = sock.recv(1024)
                
                if len(response) >= 12:
                    # Parse response
                    trans_id, proto_id, length, unit, func_code, reg_addr, reg_value = struct.unpack('>HHHBBHH', response[:12])
                    
                    if func_code == 0x06 and reg_addr == register and reg_value == value:
                        return True
                    else:
                        _logger.warning(f"PLC write verification failed")
                        return False
                else:
                    _logger.warning(f"Short PLC write response: {len(response)} bytes")
                    return False
                    
        except Exception as e:
            _logger.error(f"PLC write error for {plc_ip}:{plc_port}: {str(e)}")
            return False
    
    def get_monitor_status(self, machine_id):
        """Get status information for a monitor"""
        with self.lock:
            if machine_id in self.monitors:
                thread = self.monitors[machine_id]
                return {
                    'monitoring': thread.is_alive(),
                    'thread_name': thread.name,
                    'machine_id': machine_id
                }
            else:
                return {
                    'monitoring': False,
                    'machine_id': machine_id
                }


# Global singleton instance
_plc_monitor_service = PLCMonitorService()


def get_plc_monitor_service():
    """Get the global PLC monitor service instance"""
    return _plc_monitor_service
