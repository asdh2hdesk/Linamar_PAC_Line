# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
import barcode
from barcode.writer import ImageWriter
import io
import base64
import pytz

_logger = logging.getLogger(__name__)


class BoxManagement(models.Model):
    _name = 'manufacturing.box.management'
    _description = 'Box Management for Final Station'
    _order = 'create_date desc'
    _rec_name = 'box_number'

    @api.model
    def get_ist_now(self):
        """Get current IST datetime for consistent timezone handling"""
        try:
            ist = pytz.timezone('Asia/Kolkata')
            utc_now = fields.Datetime.now()
            # Convert UTC to IST
            ist_now = pytz.UTC.localize(utc_now).astimezone(ist)
            # Return as naive datetime in IST (Odoo will handle display)
            return ist_now.replace(tzinfo=None)
        except Exception as e:
            _logger.warning(f"Error getting IST time: {e}, falling back to UTC")
            return fields.Datetime.now()

    box_number = fields.Char('Box Number', required=True, index=True)
    part_variant = fields.Selection([
        ('exhaust', 'Exhaust'),
        ('intake', 'Intake')
    ], required=True, string='Part Variant')
    
    status = fields.Selection([
        ('open', 'Open'),
        ('full', 'Full'),
        ('printed', 'Barcode Printed')
    ], default='open', string='Status')
    
    current_position = fields.Integer('Current Position', default=0)
    max_capacity = fields.Integer('Max Capacity', default=540)
    
    # Box details
    create_date = fields.Datetime('Created Date')
    complete_date = fields.Datetime('Completed Date')
    print_date = fields.Datetime('Barcode Print Date')
    
    # Related parts
    part_quality_ids = fields.One2many(
        'manufacturing.part.quality',
        'box_id',
        string='Parts in Box'
    )
    
    # Barcode data
    barcode_data = fields.Binary('Barcode Image', attachment=True)
    barcode_filename = fields.Char('Barcode Filename')
    zebra_print_data = fields.Text('Zebra Print Data')
    
    # Statistics
    total_parts = fields.Integer('Total Parts', compute='_compute_statistics', store=True)
    passed_parts = fields.Integer('Passed Parts', compute='_compute_statistics', store=True)
    rejected_parts = fields.Integer('Rejected Parts', compute='_compute_statistics', store=True)
    
    @api.depends('part_quality_ids', 'part_quality_ids.final_result')
    def _compute_statistics(self):
        for record in self:
            record.total_parts = len(record.part_quality_ids)
            record.passed_parts = len(record.part_quality_ids.filtered(lambda p: p.final_result == 'pass'))
            record.rejected_parts = len(record.part_quality_ids.filtered(lambda p: p.final_result == 'reject'))
    
    @api.model
    def get_or_create_current_box(self, part_variant):
        """Get the current open box for a specific variant or create a new one"""
        current_box = self.search([
            ('status', '=', 'open'),
            ('part_variant', '=', part_variant)
        ], limit=1, order='create_date desc')
        
        if not current_box:
            # Create new box for this variant
            box_number = self._generate_box_number(part_variant)
            current_box = self.create({
                'box_number': box_number,
                'part_variant': part_variant,
                'status': 'open',
                'current_position': 0
            })
            _logger.info(f"Created new {part_variant} box: {box_number}")
        
        return current_box
    
    def _generate_box_number(self, part_variant):
        """Generate a unique box number for a specific variant"""
        # Get the last box number for this variant
        last_box = self.search([
            ('part_variant', '=', part_variant)
        ], limit=1, order='box_number desc')
        
        if last_box and last_box.box_number:
            try:
                # Extract number from box number (format: EXH001, INT001, etc.)
                prefix = 'EXH' if part_variant == 'exhaust' else 'INT'
                last_number = int(last_box.box_number.replace(prefix, ''))
                next_number = last_number + 1
            except (ValueError, AttributeError):
                next_number = 1
        else:
            next_number = 1
        
        prefix = 'EXH' if part_variant == 'exhaust' else 'INT'
        return f"{prefix}{next_number:03d}"
    
    def add_part_to_box(self, part_quality_id):
        """Add a part to the current box and return position"""
        self.ensure_one()
        
        if self.status != 'open':
            raise ValueError(f"Cannot add part to box {self.box_number} - status is {self.status}")
        
        if self.current_position >= self.max_capacity:
            raise ValueError(f"Box {self.box_number} is already full")
        
        # Increment position
        self.current_position += 1
        
        # Update part quality record
        part_quality = self.env['manufacturing.part.quality'].browse(part_quality_id)
        part_quality.write({
            'box_number': self.box_number,
            'box_position': self.current_position,
            'box_id': self.id
        })
        
        _logger.info(f"Added part {part_quality.serial_number} to box {self.box_number} at position {self.current_position}")
        
        # Check if box is now full
        if self.current_position >= self.max_capacity:
            self._complete_box()
        
        return self.current_position
    
    def _complete_box(self):
        """Mark box as full and generate barcode"""
        self.ensure_one()
        
        self.write({
            'status': 'full',
            'complete_date': fields.Datetime.now()
        })
        
        _logger.info(f"Box {self.box_number} is now full with {self.current_position} parts")
        
        # Generate barcode
        self._generate_barcode()
    
    def _generate_barcode(self):
        """Generate barcode for Zebra printer"""
        self.ensure_one()
        
        try:
            # Create barcode data matching the sample format
            part_description = "Exhaust Camshaft" if self.part_variant == 'exhaust' else "Intake Camshaft"
            barcode_data = f"{part_description} / {self.box_number}"
            
            # Generate barcode image (using Data Matrix for 2D barcode like in sample)
            try:
                datamatrix = barcode.get_barcode_class('datamatrix')
                barcode_instance = datamatrix(barcode_data, writer=ImageWriter())
            except:
                # Fallback to Code128 if DataMatrix not available
                code128 = barcode.get_barcode_class('code128')
                barcode_instance = code128(barcode_data, writer=ImageWriter())
            
            # Save to buffer
            buffer = io.BytesIO()
            barcode_instance.write(buffer)
            buffer.seek(0)
            
            # Convert to base64
            barcode_image = base64.b64encode(buffer.getvalue())
            
            # Generate Zebra printer ZPL commands
            zebra_commands = self._generate_zebra_commands(barcode_data)
            
            # Update record
            self.write({
                'barcode_data': barcode_image,
                'barcode_filename': f"{self.box_number}_barcode.png",
                'zebra_print_data': zebra_commands,
                'print_date': fields.Datetime.now()
            })
            
            _logger.info(f"Generated barcode for {self.part_variant} box {self.box_number}")
            
        except Exception as e:
            _logger.error(f"Error generating barcode for box {self.box_number}: {str(e)}")
    
    def _get_logo_zpl(self, logo_x=50, logo_y=30, logo_width=100, logo_height=50):
        """Get ZPL command for company logo
        
        Args:
            logo_x: X position for logo
            logo_y: Y position for logo
            logo_width: Logo width in dots
            logo_height: Logo height in dots
        
        Returns:
            ZPL command string for logo, or empty string if logo not available
        """
        try:
            # Try to get logo from system parameters
            logo_path = self.env['ir.config_parameter'].sudo().get_param('manufacturing.company_logo_path', '')
            logo_binary = self.env['ir.config_parameter'].sudo().get_param('manufacturing.company_logo_binary', '')
            
            # If logo path is provided, try to load it
            if logo_path:
                try:
                    import os
                    if os.path.exists(logo_path):
                        from PIL import Image
                        img = Image.open(logo_path)
                        return self._image_to_zpl_gfa(img, logo_x, logo_y, logo_width, logo_height)
                except Exception as e:
                    _logger.warning(f"Could not load logo from path {logo_path}: {e}")
            
            # If logo binary is provided (base64), decode and convert
            if logo_binary:
                try:
                    import base64
                    from PIL import Image
                    import io
                    logo_data = base64.b64decode(logo_binary)
                    img = Image.open(io.BytesIO(logo_data))
                    return self._image_to_zpl_gfa(img, logo_x, logo_y, logo_width, logo_height)
                except Exception as e:
                    _logger.warning(f"Could not load logo from binary: {e}")
            
            # Try to get logo from company (if available)
            try:
                company = self.env.user.company_id
                if company.logo:
                    from PIL import Image
                    import io
                    import base64
                    logo_data = base64.b64decode(company.logo)
                    img = Image.open(io.BytesIO(logo_data))
                    return self._image_to_zpl_gfa(img, logo_x, logo_y, logo_width, logo_height)
            except Exception as e:
                _logger.debug(f"Could not get logo from company: {e}")
            
            # Return empty if no logo found
            return ""
            
        except Exception as e:
            _logger.warning(f"Error getting logo for ZPL: {e}")
            return ""
    
    def _image_to_zpl_gfa(self, img, x_pos, y_pos, width_dots, height_dots):
        """Convert PIL Image to ZPL GFA (Graphic Field ASCII) format
        
        Args:
            img: PIL Image object
            x_pos: X position on label
            y_pos: Y position on label
            width_dots: Desired width in dots
            height_dots: Desired height in dots
        
        Returns:
            ZPL command string with GFA data
        """
        try:
            from PIL import Image
            import io
            
            # Resize image to desired dimensions
            img = img.convert('1')  # Convert to 1-bit (monochrome)
            img = img.resize((width_dots, height_dots), Image.Resampling.LANCZOS)
            
            # Calculate bytes per row (width in dots / 8, rounded up)
            bytes_per_row = (width_dots + 7) // 8
            total_bytes = bytes_per_row * height_dots
            
            # Convert image to bytes
            img_bytes = bytearray()
            pixels = img.load()
            
            for y in range(height_dots):
                for x in range(0, width_dots, 8):
                    byte = 0
                    for bit in range(8):
                        if x + bit < width_dots:
                            if pixels[x + bit, y] == 0:  # Black pixel
                                byte |= (1 << (7 - bit))
                    img_bytes.append(byte)
            
            # Convert to hex string
            hex_data = ''.join(f'{b:02X}' for b in img_bytes)
            
            # Generate ZPL GFA command
            zpl = f"^FO{x_pos},{y_pos}^GFA,{total_bytes},{total_bytes},{bytes_per_row},{hex_data}^FS"
            
            return zpl
            
        except Exception as e:
            _logger.error(f"Error converting image to ZPL GFA: {e}")
            return ""
    
    def _generate_zebra_commands(self, barcode_data):
        """Generate ZPL commands for Zebra printer matching provided template format"""
        part_description = "Exhaust Camshaft" if self.part_variant == 'exhaust' else "Intake Camshaft"
        part_number = "56823"  # Based on sample
        
        # Format date - use complete_date if available, otherwise use current date
        if self.complete_date:
            date_str = self.complete_date.strftime('%d-%m-%Y %H:%M:%S')
        else:
            date_str = self.get_ist_now().strftime('%d-%m-%Y %H:%M:%S')
        
        # Label dimensions from provided template
        label_width = 1112
        label_height = 1718
        
        # Format box number to match template format (Box No.0001)
        box_display = f"Box No.{self.box_number[-4:]}" if len(self.box_number) >= 4 else f"Box No.{self.box_number.zfill(4)}"
        
        # Get logo ZPL command (for logo section at 45,45 with 130x130 size)
        logo_zpl = self._get_logo_zpl(55, 55, 120, 120)  # Slightly smaller to fit in 130x130 border
        
        # If no logo, use placeholder text
        if not logo_zpl:
            logo_zpl = "^FO55,55^A0N,28,28^FDLOGO^FS\n^FO55,90^A0N,24,24^FDHERE^FS"
        
        # ZPL template matching provided format exactly
        zpl_template = f"""
^XA
^PW{label_width}
^LL{label_height}
~comment: Outer border covering full label
^FO45,45^GB1000,1600,3^FS
~comment: Logo section with border - LARGER
^FO45,45^GB130,130,2^FS
{logo_zpl}
~comment: Company name and tagline
^FO175,55^A0N,100,100^FDLINAMAR^FS
^FO175,145^A0N,30,30^FDPower to Perform^FS
~comment: Horizontal separator line after header
^FO42,165^GB1000,2,2^FS
~comment: Information fields with labels and values
^FO55,195^A0N,40,40^FDCustomer^FS
^FO330,195^A0N,40,40^FD: PSA-AVTEC^FS
~comment: Thin separator line
^FO45,255^GB1000,1,1^FS
^FO55,275^A0N,40,40^FDPart Number^FS
^FO330,275^A0N,40,40^FD: {part_number}^FS
~comment: Thin separator line
^FO45,335^GB1000,1,1^FS
^FO55,355^A0N,40,40^FDPart Description^FS
^FO330,355^A0N,40,40^FD: {part_description}^FS
~comment: Thin separator line
^FO45,415^GB1000,1,1^FS
^FO55,435^A0N,40,40^FDDate^FS
^FO330,435^A0N,40,40^FD: {date_str}^FS
~comment: Thin separator line
^FO45,495^GB1000,1,1^FS
^FO55,515^A0N,40,40^FDBox/Skid#^FS
^FO330,515^A0N,40,40^FD: {box_display}^FS
~comment: Horizontal separator line before barcode
^FO42,575^GB1000,2,2^FS
~comment: QR Code barcode - centered and larger
^FO150,620^BQN,2,27^FDQA,{barcode_data}^FS
~comment: Horizontal separator line after barcode
^FO42,1525^GB1000,2,2^FS
~comment: Footer text with barcode data - centered
^FO80,1555^A0N,38,38^FD{barcode_data}^FS
^XZ
"""
        return zpl_template.strip()
    
    def print_barcode(self):
        """Print barcode to Zebra printer"""
        self.ensure_one()
        
        if not self.zebra_print_data:
            from odoo.exceptions import UserError
            raise UserError("No barcode data available for printing. Please ensure the box is full and barcode is generated.")
        
        # Send ZPL command to printer (same approach as print_wizard)
        try:
            success = self._send_to_printer(self.zebra_print_data)
            
            if success:
                # Update status and print date
                self.write({
                    'status': 'printed',
                    'print_date': self.get_ist_now()
                })
                
                # Get printer info for message
                use_local = self.env['ir.config_parameter'].sudo().get_param('manufacturing.use_local_printer', 'True').lower() == 'true'
                if use_local:
                    printer_name = self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_name', '')
                    printer_info = f"printer '{printer_name}'"
                else:
                    printer_ip = self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_ip', '192.168.1.100')
                    printer_port = self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_port', '9100')
                    printer_info = f"{printer_ip}:{printer_port}"
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Barcode Printed',
                        'message': f'Barcode for box {self.box_number} has been sent to {printer_info}',
                        'type': 'success',
                        'sticky': False,
                    }
                }
        except Exception as e:
            from odoo.exceptions import UserError
            _logger.error(f"Error printing barcode: {e}")
            raise UserError(f'Error printing barcode: {str(e)}')
    
    def _send_to_local_printer(self, zpl_command, printer_name):
        """Send ZPL command to local Windows printer via print spooler"""
        try:
            import platform
            if platform.system() != 'Windows':
                raise Exception("Local printer support is only available on Windows")
            
            try:
                import win32print
            except ImportError:
                raise Exception("win32print module not available. Install pywin32: pip install pywin32")
            
            _logger.info(f"Sending ZPL command to local printer: {printer_name}")
            _logger.info(f"ZPL command length: {len(zpl_command)} characters")
            
            # Try to open the printer
            try:
                printer_handle = win32print.OpenPrinter(printer_name)
            except Exception as e:
                # List available printers for debugging
                try:
                    printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
                    printer_list = [p[2] for p in printers]
                    _logger.info(f"Available printers: {', '.join(printer_list)}")
                except:
                    pass
                raise Exception(f"Cannot open printer '{printer_name}'. Error: {str(e)}")
            
            try:
                # Start a print job
                job_info = ("Box Management Print Job", None, "RAW")
                job_id = win32print.StartDocPrinter(printer_handle, 1, job_info)
                win32print.StartPagePrinter(printer_handle)
                
                # Send ZPL command as raw data
                zpl_bytes = zpl_command.encode('utf-8')
                win32print.WritePrinter(printer_handle, zpl_bytes)
                
                # End print job
                win32print.EndPagePrinter(printer_handle)
                win32print.EndDocPrinter(printer_handle)
                
                _logger.info(f"Successfully sent ZPL command to local printer: {printer_name}")
                return True
                
            finally:
                # Always close printer handle
                try:
                    win32print.ClosePrinter(printer_handle)
                except:
                    pass
                    
        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Error sending to local printer {printer_name}: {error_msg}")
            raise Exception(error_msg)
    
    def _send_to_printer(self, zpl_command, printer_ip=None, printer_port=None):
        """Send ZPL command to Zebra printer - supports both network and local Windows printer"""
        try:
            # Check if using local printer (same approach as print_wizard)
            use_local = self.env['ir.config_parameter'].sudo().get_param('manufacturing.use_local_printer', 'True').lower() == 'true'
            printer_name = self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_name', '')
            
            _logger.info(f"Printer config - use_local: {use_local}, printer_name: {printer_name}")
            
            if use_local:
                if printer_name:
                    # Use local Windows printer (same as print_wizard approach)
                    _logger.info(f"Using local printer: {printer_name}")
                    return self._send_to_local_printer(zpl_command, printer_name)
                else:
                    # Try to get default printer if name not set
                    try:
                        import platform
                        if platform.system() == 'Windows':
                            try:
                                import win32print
                                default_printer = win32print.GetDefaultPrinter()
                                if default_printer:
                                    _logger.info(f"Using default printer: {default_printer}")
                                    return self._send_to_local_printer(zpl_command, default_printer)
                            except:
                                pass
                    except:
                        pass
                    
                    # If no printer name and can't get default, fall through to network
                    _logger.warning("Local printer enabled but no printer name configured. Falling back to network printer.")
            
            # Use network printer (socket connection - same as print_wizard)
            if not printer_ip:
                printer_ip = self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_ip', '192.168.1.100')
            if not printer_port:
                try:
                    printer_port = int(self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_port', '9100'))
                except (ValueError, TypeError):
                    printer_port = 9100
            
            _logger.info(f"Using network printer: {printer_ip}:{printer_port}")
            return self._send_to_network_printer(zpl_command, printer_ip, printer_port)
                
        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Error sending to printer: {error_msg}")
            
            # Provide helpful error message
            use_local = self.env['ir.config_parameter'].sudo().get_param('manufacturing.use_local_printer', 'True').lower() == 'true'
            printer_name = self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_name', '')
            
            if use_local and not printer_name:
                raise Exception(f"Local printer is enabled but printer name is not configured. Please set 'manufacturing.zebra_printer_name' system parameter. Error: {error_msg}")
            elif "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                raise Exception(f"Printer connection timed out. If using USB/wired printer, ensure 'manufacturing.use_local_printer' is 'True' and 'manufacturing.zebra_printer_name' is set to your printer name. Error: {error_msg}")
            else:
                raise Exception(error_msg)
    
    def _send_to_network_printer(self, zpl_command, printer_ip, printer_port):
        """Send ZPL command to Zebra printer via network socket (same as print_wizard)"""
        try:
            import socket
            
            _logger.info(f"Sending ZPL command to printer {printer_ip}:{printer_port}")
            
            # Create socket connection (same timeout as print_wizard)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)  # 5 second timeout (same as print_wizard)
            
            # Connect to printer
            sock.connect((printer_ip, printer_port))
            
            # Send ZPL command (same as print_wizard)
            sock.send(zpl_command.encode('utf-8'))
            
            # Close connection
            sock.close()
            
            _logger.info(f"Successfully sent ZPL command to printer {printer_ip}:{printer_port}")
            return True
            
        except Exception as e:
            _logger.error(f"Error sending to printer: {e}")
            raise Exception(f"Network printer error: {str(e)}")
    
    @api.model
    def set_printer_config(self, printer_ip=None, printer_port=9100, printer_name=None, use_local=True):
        """Set Zebra printer configuration
        
        Args:
            printer_ip: IP address for network printer (optional if using local)
            printer_port: Port for network printer (default: 9100)
            printer_name: Name of local Windows printer (required if use_local=True)
            use_local: If True, use local Windows printer instead of network
        """
        if use_local:
            if not printer_name:
                from odoo.exceptions import UserError
                raise UserError("Printer name is required when using local printer")
            self.env['ir.config_parameter'].sudo().set_param('manufacturing.use_local_printer', 'True')
            self.env['ir.config_parameter'].sudo().set_param('manufacturing.zebra_printer_name', printer_name)
            _logger.info(f"Printer configuration updated: Local printer '{printer_name}'")
        else:
            if not printer_ip:
                from odoo.exceptions import UserError
                raise UserError("Printer IP is required when using network printer")
            self.env['ir.config_parameter'].sudo().set_param('manufacturing.use_local_printer', 'False')
            self.env['ir.config_parameter'].sudo().set_param('manufacturing.zebra_printer_ip', printer_ip)
            self.env['ir.config_parameter'].sudo().set_param('manufacturing.zebra_printer_port', str(printer_port))
            _logger.info(f"Printer configuration updated: Network printer {printer_ip}:{printer_port}")
    
    @api.model
    def get_available_printers(self):
        """Get list of available Windows printers"""
        try:
            import platform
            if platform.system() != 'Windows':
                return []
            
            try:
                import win32print
            except ImportError:
                return []
            
            printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
            return [p[2] for p in printers]
        except Exception as e:
            _logger.error(f"Error getting printer list: {e}")
            return []
    
    @api.model
    def get_printer_config(self):
        """Get Zebra printer configuration"""
        use_local = self.env['ir.config_parameter'].sudo().get_param('manufacturing.use_local_printer', 'False').lower() == 'true'
        printer_name = self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_name', '')
        printer_ip = self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_ip', '192.168.1.100')
        try:
            printer_port = int(self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_port', '9100'))
        except (ValueError, TypeError):
            printer_port = 9100
        
        return {
            'use_local': use_local,
            'printer_name': printer_name,
            'printer_ip': printer_ip,
            'printer_port': printer_port,
            'available_printers': self.get_available_printers()
        }
    
    def _test_printer_connection(self, printer_ip, printer_port):
        """Test printer connection and return detailed error message"""
        try:
            import socket
            
            _logger.info(f"Testing connection to printer {printer_ip}:{printer_port}")
            
            # Create socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)  # 5 second timeout for test
            
            # Try to connect
            sock.connect((printer_ip, printer_port))
            sock.close()
            
            return "Connection test successful"
            
        except socket.timeout:
            return f"Connection timeout: Printer at {printer_ip}:{printer_port} did not respond within 5 seconds."
        except socket.gaierror as e:
            return f"Invalid IP address: {printer_ip} - {str(e)}"
        except ConnectionRefusedError:
            return f"Connection refused: Printer at {printer_ip}:{printer_port} is not accepting connections."
        except OSError as e:
            if "No route to host" in str(e) or "Network is unreachable" in str(e):
                return f"Network unreachable: Cannot reach {printer_ip}. Check network connectivity."
            elif "WinError 10061" in str(e):
                return f"Connection refused (Windows): Check if printer is on and port {printer_port} is open."
            else:
                return f"Network error: {str(e)}"
        except Exception as e:
            return f"Connection test failed: {str(e)}"
    
    def test_printer_connection(self):
        """Test printer connection - public method for UI"""
        self.ensure_one()
        
        # Get printer configuration
        printer_ip = self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_ip', '192.168.1.100')
        printer_port = int(self.env['ir.config_parameter'].sudo().get_param('manufacturing.zebra_printer_port', '9100'))
        
        # Test connection
        result = self._test_printer_connection(printer_ip, printer_port)
        
        if "successful" in result.lower():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Connection Successful',
                    'message': f'Successfully connected to printer at {printer_ip}:{printer_port}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            from odoo.exceptions import UserError
            raise UserError(f"Printer Connection Test Failed:\n\n{result}\n\nCurrent Configuration:\n- IP: {printer_ip}\n- Port: {printer_port}")
    
    @api.model
    def get_box_statistics(self):
        """Get overall box statistics by variant"""
        all_boxes = self.search([])
        exhaust_boxes = all_boxes.filtered(lambda b: b.part_variant == 'exhaust')
        intake_boxes = all_boxes.filtered(lambda b: b.part_variant == 'intake')
        
        return {
            'total_boxes': len(all_boxes),
            'exhaust_boxes': {
                'total': len(exhaust_boxes),
                'open': len(exhaust_boxes.filtered(lambda b: b.status == 'open')),
                'full': len(exhaust_boxes.filtered(lambda b: b.status == 'full')),
                'printed': len(exhaust_boxes.filtered(lambda b: b.status == 'printed')),
                'total_parts': sum(exhaust_boxes.mapped('total_parts')),
                'passed_parts': sum(exhaust_boxes.mapped('passed_parts')),
            },
            'intake_boxes': {
                'total': len(intake_boxes),
                'open': len(intake_boxes.filtered(lambda b: b.status == 'open')),
                'full': len(intake_boxes.filtered(lambda b: b.status == 'full')),
                'printed': len(intake_boxes.filtered(lambda b: b.status == 'printed')),
                'total_parts': sum(intake_boxes.mapped('total_parts')),
                'passed_parts': sum(intake_boxes.mapped('passed_parts')),
            }
        }
