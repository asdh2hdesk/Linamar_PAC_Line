/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class FinalStationDashboard extends Component {
    static template = "manufacturing_dashboard.final_station_dashboard_view";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            final_station: null,
            station_results: null,
            final_station_statistics: {
                total_parts: 0,
                passed_parts: 0,
                rejected_parts: 0,
                pass_rate: 0,
                reject_rate: 0,
                last_updated: 'Never'
            },
            open_boxes: {
                boxes: [],
                summary: {
                    total_open_boxes: 0,
                    exhaust_boxes: 0,
                    intake_boxes: 0,
                    total_parts_in_open_boxes: 0,
                    total_passed_parts: 0,
                    total_rejected_parts: 0
                }
            },
            loading: true,
            error: null
        });

        this.refreshInterval = null;

        onMounted(async () => {
            try {
                await this.loadFinalStation();
                await this.loadFinalStationStatistics();
            } catch (error) {
                console.error('Error in final station dashboard initialization:', error);
                this.state.error = 'Dashboard initialization failed: ' + error.message;
            } finally {
                this.state.loading = false;
            }

            // Auto refresh every 5 seconds
            this.refreshInterval = setInterval(async () => {
                try {
                    if (this.state.final_station) {
                        await this.loadFinalStationData();
                        await this.loadFinalStationStatistics();
                    }
                } catch (error) {
                    console.error('Error in auto refresh:', error);
                }
            }, 5000);
        });

        onWillUnmount(() => {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
        });
    }

    async loadFinalStation() {
        try {
            console.log('Loading final station...');
            const machines = await this.orm.searchRead(
                "manufacturing.machine.config",
                [['machine_type', '=', 'final_station'], ['is_active', '=', true]],
                ["id", "machine_name", "machine_type", "status", "last_sync", "plc_ip_address", "plc_port", "camera_ip_address", "camera_port", "operation_mode", "plc_online", "camera_triggered", "part_present", "processing_part", "last_serial_number", "last_result", "plc_monitoring_active", "plc_scan_rate", "last_plc_scan", "plc_monitoring_errors", "last_plc_communication", "last_capture_time"]
            );
            
            if (machines.length > 0) {
                this.state.final_station = machines[0]; // Load the first (and only) final station
                console.log('Final station loaded:', this.state.final_station.machine_name);
                await this.loadFinalStationData();
            } else {
                this.state.error = "No final station found";
            }
        } catch (error) {
            console.error("Error loading final station:", error);
            this.state.error = "Failed to load final station: " + error.message;
        }
    }


    async loadFinalStationData() {
        try {
            if (!this.state.final_station) {
                console.log('No final station loaded');
                return;
            }
            
            console.log('Loading final station data for ID:', this.state.final_station.id);
            const data = await this.orm.call(
                "manufacturing.machine.config",
                "get_final_station_live_data",
                [this.state.final_station.id]
            );

            console.log('Final station data received:', data);

            if (data && Object.keys(data).length > 0) {
                // Merge final station data with current station
                this.state.final_station = {
                    ...this.state.final_station,
                    ...data
                };
                console.log('Final station data merged with current station');
                
                // Update PLC registers display
                if (data.plc_registers) {
                    this.updatePLCRegistersDisplay(data.plc_registers);
                }
                
                // Update recent measurements display
                if (data.recent_measurements) {
                    this.updateRecentMeasurementsDisplay(data.recent_measurements);
                }
                
                // Update station results display
                if (data.station_results) {
                    this.state.station_results = data.station_results;
                    console.log('Station results updated:', this.state.station_results);
                } else {
                    console.log('No station results in data:', data);
                    // Try to load station results manually if we have a serial number
                    if (data.last_serial_number) {
                        console.log('Attempting to load station results for serial:', data.last_serial_number);
                        this.loadStationResults(data.last_serial_number);
                    }
                }
                
                // Update open boxes data
                if (data.open_boxes) {
                    this.state.open_boxes = data.open_boxes;
                    console.log('Open boxes data updated:', this.state.open_boxes);
                }
            }
        } catch (error) {
            console.error("Error loading final station data:", error);
        }
    }

    async loadStationResults(serial_number) {
        try {
            console.log('Loading station results for serial:', serial_number);
            const data = await this.orm.call(
                "manufacturing.machine.config",
                "get_station_results_by_serial",
                [this.state.final_station.id, serial_number]
            );

            console.log('Station results data received:', data);
            
            if (data && !data.error) {
                this.state.station_results = data;
                console.log('Station results loaded successfully:', this.state.station_results);
            } else {
                console.error('Error loading station results:', data.error);
            }
        } catch (error) {
            console.error("Error loading station results:", error);
        }
    }

    async loadFinalStationStatistics() {
        try {
            if (!this.state.final_station) {
                return;
            }

            console.log('Loading final station statistics for machine:', this.state.final_station.id);
            const data = await this.orm.call(
                "manufacturing.machine.config",
                "get_final_station_statistics",
                [this.state.final_station.id]
            );

            console.log('Final station statistics received:', data);
            
            if (data && !data.error) {
                this.state.final_station_statistics = {
                    total_parts: data.total_parts || 0,
                    passed_parts: data.passed_parts || 0,
                    rejected_parts: data.rejected_parts || 0,
                    pass_rate: data.pass_rate || 0,
                    reject_rate: data.reject_rate || 0,
                    last_updated: data.last_updated || 'Never'
                };
                console.log('Final station statistics updated:', this.state.final_station_statistics);
            } else {
                console.warn('No statistics data received or error occurred:', data);
            }
        } catch (error) {
            console.error("Error loading final station statistics:", error);
        }
    }

    async refreshStationResults() {
        if (this.state.final_station && this.state.final_station.last_serial_number) {
            console.log('Manually refreshing station results...');
            await this.loadStationResults(this.state.final_station.last_serial_number);
        } else {
            console.log('No serial number available for station results refresh');
        }
    }

    async createTestStationResults() {
        try {
            console.log('Creating test station results...');
            const response = await fetch(`/manufacturing/final_station/${this.state.final_station.id}/test_station_results`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {}
                })
            });
            
            const data = await response.json();
            console.log('Test station results response:', data);
            
            if (data.result && data.result.success) {
                this.state.station_results = data.result.station_results;
                console.log('Test station results created successfully:', this.state.station_results);
            } else {
                console.error('Error creating test station results:', data.result.error);
            }
        } catch (error) {
            console.error('Error creating test station results:', error);
        }
    }

    async triggerAutoMonitoring() {
        try {
            if (!this.state.final_station) {
                console.log('No final station selected');
                return;
            }
            
            console.log('Triggering auto monitoring for final station:', this.state.final_station.id);
            
            const response = await fetch(`/manufacturing/final_station/${this.state.final_station.id}/trigger_auto_monitoring`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {}
                })
            });
            
            const data = await response.json();
            console.log('Auto monitoring response:', data);
            
            if (data.result && data.result.success) {
                console.log('Auto monitoring triggered:', data.result.message);
                // Refresh the dashboard data
                await this.loadFinalStationData();
            } else {
                console.error('Error triggering auto monitoring:', data.result.error);
            }
        } catch (error) {
            console.error('Error calling trigger auto monitoring API:', error);
        }
    }

    async checkPLCStatus() {
        try {
            if (!this.state.final_station) {
                console.log('No final station selected');
                return;
            }
            
            console.log('Checking PLC status for final station:', this.state.final_station.id);
            
            const response = await fetch(`/manufacturing/final_station/${this.state.final_station.id}/check_plc_status`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {}
                })
            });
            
            const data = await response.json();
            console.log('PLC Status response:', data);
            
            if (data.result && data.result.success) {
                const status = data.result;
                console.log('=== PLC STATUS ===');
                console.log(`Machine: ${status.machine_name} (ID: ${status.machine_id})`);
                console.log(`PLC IP: ${status.plc_ip_address}:${status.plc_port}`);
                console.log(`PLC Monitoring Active: ${status.plc_monitoring_active}`);
                console.log(`PLC Service Monitoring: ${status.plc_service_monitoring}`);
                console.log(`Current D0 Value: ${status.current_d0_value}`);
                console.log(`Part Present: ${status.part_present}`);
                console.log('==================');
                
                // Show alert with status
                alert(`PLC Status:\nMachine: ${status.machine_name}\nPLC IP: ${status.plc_ip_address}:${status.plc_port}\nPLC Monitoring Active: ${status.plc_monitoring_active}\nPLC Service Monitoring: ${status.plc_service_monitoring}\nCurrent D0 Value: ${status.current_d0_value}\nPart Present: ${status.part_present}`);
            } else {
                console.error('Error checking PLC status:', data.result.error);
            }
        } catch (error) {
            console.error('Error calling check PLC status API:', error);
        }
    }

    async restartPLCMonitoring() {
        try {
            if (!this.state.final_station) {
                console.log('No final station selected');
                return;
            }
            
            console.log('Restarting PLC monitoring for final station:', this.state.final_station.id);
            
            const response = await fetch(`/manufacturing/final_station/${this.state.final_station.id}/restart_plc_monitoring`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {}
                })
            });
            
            const data = await response.json();
            console.log('Restart PLC monitoring response:', data);
            
            if (data.result && data.result.success) {
                console.log('PLC monitoring restarted:', data.result.message);
                alert('PLC monitoring restarted successfully!');
                // Refresh the dashboard data
                await this.loadFinalStationData();
            } else {
                console.error('Error restarting PLC monitoring:', data.result.error);
                alert('Error restarting PLC monitoring: ' + data.result.error);
            }
        } catch (error) {
            console.error('Error calling restart PLC monitoring API:', error);
            alert('Error calling restart PLC monitoring API: ' + error.message);
        }
    }

    async resetProcessingFlag() {
        try {
            if (!this.state.final_station) {
                console.log('No final station selected');
                return;
            }
            
            console.log('Resetting processing flag for final station:', this.state.final_station.id);
            
            const response = await fetch(`/manufacturing/final_station/${this.state.final_station.id}/reset_processing_flag`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {}
                })
            });
            
            const data = await response.json();
            console.log('Reset processing flag response:', data);
            
            if (data.result && data.result.success) {
                console.log('Processing flag reset:', data.result.message);
                alert('Processing flag reset successfully!');
                // Refresh the dashboard data
                await this.loadFinalStationData();
            } else {
                console.error('Error resetting processing flag:', data.result.error);
                alert('Error resetting processing flag: ' + data.result.error);
            }
        } catch (error) {
            console.error('Error calling reset processing flag API:', error);
            alert('Error calling reset processing flag API: ' + error.message);
        }
    }

    closeProcessingPopup() {
        // This method can be called to close the popup by clicking outside
        // The popup will automatically close when processing_part becomes false
        console.log('Processing popup close requested');
    }

    async testConnection() {
        try {
            if (!this.state.final_station) {
                console.log('No final station selected');
                return;
            }
            
            console.log('Testing PLC connection for final station:', this.state.final_station.id);
            
            const response = await fetch(`/manufacturing/final_station/${this.state.final_station.id}/test_connection`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {}
                })
            });
            
            const data = await response.json();
            console.log('Test connection response:', data);
            
            if (data.result && data.result.success) {
                console.log('Connection test successful:', data.result.message);
                alert(`Connection Test Successful!\nStatus: ${data.result.status}\nPLC Online: ${data.result.plc_online ? 'Yes' : 'No'}`);
                // Refresh the dashboard data to show updated status
                await this.loadFinalStationData();
            } else {
                console.error('Connection test failed:', data.result.error || data.result.message);
                alert('Connection Test Failed: ' + (data.result.error || data.result.message));
                // Refresh the dashboard data to show updated status
                await this.loadFinalStationData();
            }
        } catch (error) {
            console.error('Error calling test connection API:', error);
            alert('Error calling test connection API: ' + error.message);
        }
    }

    updatePLCRegistersDisplay(registers) {
        try {
            // Update PLC register values in the DOM
            for (let i = 0; i < 10; i++) {
                const registerElement = document.querySelector(`[data-register="${i}"]`);
                if (registerElement && registers[`D${i}`] !== undefined) {
                    registerElement.textContent = registers[`D${i}`];
                }
            }
        } catch (error) {
            console.error("Error updating PLC registers display:", error);
        }
    }

    updateRecentMeasurementsDisplay(measurements) {
        try {
            const tableBody = document.querySelector('.measurements-table');
            if (tableBody) {
                tableBody.innerHTML = measurements.map(measurement => `
                    <tr>
                        <td>${measurement.serial_number || 'N/A'}</td>
                        <td>${this.formatTime(measurement.capture_date)}</td>
                        <td><span class="badge ${this.getResultClass(measurement.result)}">${measurement.result || 'N/A'}</span></td>
                        <td>${measurement.operation_mode || 'N/A'}</td>
                        <td>${measurement.trigger_type || 'N/A'}</td>
                    </tr>
                `).join('');
            }
        } catch (error) {
            console.error("Error updating recent measurements display:", error);
        }
    }

    // Final Station Methods
    async toggleOperationMode() {
        if (!this.state.final_station) {
            return;
        }
        
        try {
            const result = await this.orm.call(
                "manufacturing.machine.config",
                "toggle_operation_mode",
                [this.state.final_station.id]
            );
            
            if (result) {
                this.showNotification("Operation mode toggled successfully", "success");
                await this.loadFinalStationData(this.state.final_station.id);
            }
        } catch (error) {
            console.error("Error toggling operation mode:", error);
            this.showNotification("Error toggling operation mode", "error");
        }
    }

    async manualTriggerCamera() {
        if (!this.state.final_station) {
            return;
        }
        
        try {
            const result = await this.orm.call(
                "manufacturing.machine.config",
                "manual_trigger_camera",
                [this.state.final_station.id]
            );
            
            if (result) {
                this.showNotification("Camera triggered successfully", "success");
                await this.loadFinalStationData(this.state.final_station.id);
            }
        } catch (error) {
            console.error("Error triggering camera:", error);
            this.showNotification("Error triggering camera", "error");
        }
    }

    async checkPartPresence() {
        if (!this.state.final_station) {
            return;
        }
        
        try {
            const result = await this.orm.call(
                "manufacturing.machine.config",
                "check_part_presence",
                [this.state.final_station.id]
            );
            
            if (result) {
                this.showNotification("Part presence checked", "info");
                await this.loadFinalStationData(this.state.final_station.id);
            }
        } catch (error) {
            console.error("Error checking part presence:", error);
            this.showNotification("Error checking part presence", "error");
        }
    }

    async cylinderForward() {
        if (!this.state.final_station) {
            return;
        }
        
        try {
            const result = await this.orm.call(
                "manufacturing.machine.config",
                "manual_cylinder_forward_action",
                [this.state.final_station.id]
            );
            
            if (result) {
                this.showNotification("Cylinder moved forward", "success");
                await this.loadFinalStationData(this.state.final_station.id);
            }
        } catch (error) {
            console.error("Error controlling cylinder forward:", error);
            this.showNotification("Error controlling cylinder forward", "error");
        }
    }

    async cylinderReverse() {
        if (!this.state.final_station) {
            return;
        }
        
        try {
            const result = await this.orm.call(
                "manufacturing.machine.config",
                "manual_cylinder_reverse_action",
                [this.state.final_station.id]
            );
            
            if (result) {
                this.showNotification("Cylinder moved reverse", "success");
                await this.loadFinalStationData(this.state.final_station.id);
            }
        } catch (error) {
            console.error("Error controlling cylinder reverse:", error);
            this.showNotification("Error controlling cylinder reverse", "error");
        }
    }

    async startMonitoring() {
        if (!this.state.final_station) {
            return;
        }
        
        try {
            const result = await this.orm.call(
                "manufacturing.machine.config",
                "start_auto_monitoring",
                [this.state.final_station.id]
            );
            
            if (result) {
                this.showNotification("PLC monitoring started", "success");
                await this.loadFinalStationData(this.state.final_station.id);
            }
        } catch (error) {
            console.error("Error starting PLC monitoring:", error);
            this.showNotification("Error starting PLC monitoring", "error");
        }
    }

    async stopMonitoring() {
        if (!this.state.final_station) {
            return;
        }
        
        try {
            const result = await this.orm.call(
                "manufacturing.machine.config",
                "stop_auto_monitoring",
                [this.state.final_station.id]
            );
            
            if (result) {
                this.showNotification("PLC monitoring stopped", "info");
                await this.loadFinalStationData(this.state.final_station.id);
            }
        } catch (error) {
            console.error("Error stopping PLC monitoring:", error);
            this.showNotification("Error stopping PLC monitoring", "error");
        }
    }

    async testPLCConnection() {
        if (!this.state.final_station) {
            return;
        }
        
        try {
            const result = await this.orm.call(
                "manufacturing.machine.config",
                "test_plc_connection",
                [this.state.final_station.id]
            );
            
            if (result && result.params) {
                this.showNotification(result.params.message, result.params.type || "info");
                await this.loadFinalStationData(this.state.final_station.id);
            }
        } catch (error) {
            console.error("Error testing PLC connection:", error);
            this.showNotification("Error testing PLC connection", "error");
        }
    }

    formatTime(datetime) {
        if (!datetime) return 'Never';
        // Convert to IST timezone for display
        const date = new Date(datetime);
        return date.toLocaleString('en-IN', {
            timeZone: 'Asia/Kolkata',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

    getResultClass(result) {
        switch (result) {
            case 'ok': return 'badge-success';
            case 'nok': return 'badge-danger';
            case 'pending': return 'badge-warning';
            default: return 'badge-secondary';
        }
    }

    showNotification(message, type = "info") {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
        notification.style.position = 'fixed';
        notification.style.top = '20px';
        notification.style.right = '20px';
        notification.style.zIndex = '9999';
        notification.style.minWidth = '300px';
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        document.body.appendChild(notification);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    async refreshOpenBoxes() {
        try {
            if (!this.state.final_station) {
                console.log('No final station loaded');
                return;
            }
            
            console.log('Refreshing open boxes data for final station:', this.state.final_station.id);
            await this.loadFinalStationData();
            
        } catch (error) {
            console.error("Error refreshing open boxes:", error);
        }
    }

    async openBoxManagement() {
        try {
            // Open the box management view
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: 'Box Management',
                res_model: 'manufacturing.box.management',
                view_mode: 'kanban,list,form',
                target: 'current',
                context: {}
            });
        } catch (error) {
            console.error("Error opening box management:", error);
        }
    }

    async viewBoxDetails(event) {
        try {
            const boxId = event.target.getAttribute('data-box-id');
            if (!boxId) {
                console.error('No box ID found');
                return;
            }
            
            // Open the box details view
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: 'Box Details',
                res_model: 'manufacturing.box.management',
                res_id: parseInt(boxId),
                view_mode: 'form',
                target: 'current',
                context: {}
            });
        } catch (error) {
            console.error("Error viewing box details:", error);
        }
    }
}

// Register the component
registry.category("actions").add("final_station_dashboard", FinalStationDashboard);
