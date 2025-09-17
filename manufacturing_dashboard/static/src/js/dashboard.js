/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class ManufacturingDashboard extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.state = useState({
            machines: [],
            statistics: {},
            loading: true
        });

        onMounted(() => {
            this.loadDashboardData();
            // Refresh every 30 seconds
            setInterval(() => {
                this.loadDashboardData();
            }, 30000);
        });
    }

    async loadDashboardData() {
        try {
            const machines = await this.rpc("/web/dataset/call_kw", {
                model: "manufacturing.machine.config",
                method: "search_read",
                args: [[]],
                kwargs: {
                    fields: ['machine_name', 'machine_type', 'status', 'parts_processed_today', 'rejection_rate', 'last_sync']
                }
            });

            const stats = await this.rpc("/web/dataset/call_kw", {
                model: "manufacturing.part.quality",
                method: "read_group",
                args: [[], ['final_result'], ['final_result']],
                kwargs: {}
            });

            this.state.machines = machines;
            this.state.statistics = this.processStatistics(stats);
            this.state.loading = false;
        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.state.loading = false;
        }
    }

    processStatistics(stats) {
        const result = {
            total_parts: 0,
            passed_parts: 0,
            rejected_parts: 0,
            pending_parts: 0
        };

        stats.forEach(stat => {
            result.total_parts += stat.__count;
            if (stat.final_result === 'pass') {
                result.passed_parts = stat.__count;
            } else if (stat.final_result === 'reject') {
                result.rejected_parts = stat.__count;
            } else if (stat.final_result === 'pending') {
                result.pending_parts = stat.__count;
            }
        });

        return result;
    }

    getStatusClass(status) {
        return `status-${status}`;
    }

    formatTime(datetime) {
        if (!datetime) return 'Never';
        return new Date(datetime).toLocaleString();
    }
}

ManufacturingDashboard.template = "manufacturing_dashboard.Dashboard";

registry.category("actions").add("manufacturing_dashboard", ManufacturingDashboard);