/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ModernManufacturingDashboard extends Component {
    static template = "manufacturing_dashboard.ModernDashboard";

    setup() {
        this.orm = useService("orm");
        this.chartRefs = {
            productionChart: useRef("productionChart"),
            qualityChart: useRef("qualityChart"),
            trendChart: useRef("trendChart"),
            measurementChart: useRef("measurementChart")
        };

        this.state = useState({
            machines: [],
            statistics: {},
            selectedMachine: null,
            machineDetailData: null,
            loading: true,
            error: null,
            charts: {}
        });

        this.refreshInterval = null;
        this.chartInstances = {};

        onMounted(async () => {
            await this.loadDashboardData();
            this.setupCharts();

            // Auto refresh every 30 seconds
            this.refreshInterval = setInterval(async () => {
                await this.loadDashboardData();
                this.updateCharts();
            }, 30000);
        });

        onWillUnmount(() => {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
            // Destroy chart instances
            Object.values(this.chartInstances).forEach(chart => {
                if (chart && typeof chart.destroy === 'function') {
                    chart.destroy();
                }
            });
        });
    }

    async loadDashboardData() {
        try {
            const data = await this.orm.call(
                "manufacturing.machine.config",
                "get_enhanced_dashboard_data",
                []
            );

            this.state.machines = data.machines || [];
            this.state.statistics = data.statistics || {};
            this.state.loading = false;
            this.state.error = null;

            // If a machine is selected, refresh its data
            if (this.state.selectedMachine) {
                await this.loadMachineDetail(this.state.selectedMachine.id);
            } else if (this.state.machines.length > 0) {
                // Auto-select first machine
                await this.selectMachine(this.state.machines[0]);
            }
        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.state.loading = false;
            this.state.error = "Failed to load dashboard data";
        }
    }

    async loadMachineDetail(machineId) {
        try {
            const data = await this.orm.call(
                "manufacturing.machine.config",
                "get_machine_detail_data",
                [machineId]
            );

            if (data.error) {
                this.state.error = data.error;
                return;
            }

            this.state.machineDetailData = data;
            this.state.error = null;
        } catch (error) {
            console.error("Error loading machine detail:", error);
            this.state.error = "Failed to load machine details";
        }
    }

    async selectMachine(machine) {
        this.state.selectedMachine = machine;
        this.state.machineDetailData = null;
        await this.loadMachineDetail(machine.id);

        // Update charts after data load
        setTimeout(() => {
            this.updateCharts();
        }, 100);
    }

    setupCharts() {
        // Wait for DOM to be ready
        setTimeout(() => {
            this.createProductionChart();
            this.createQualityChart();
            this.createTrendChart();
            this.createMeasurementChart();
        }, 200);
    }

    createProductionChart() {
        const ctx = this.chartRefs.productionChart.el?.getContext('2d');
        if (!ctx || this.chartInstances.production) return;

        this.chartInstances.production = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['OK Parts', 'Reject Parts'],
                datasets: [{
                    data: [0, 0],
                    backgroundColor: ['#28a745', '#dc3545'],
                    borderWidth: 0,
                    cutout: '70%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            font: { size: 12 }
                        }
                    }
                }
            }
        });
    }

    createQualityChart() {
        const ctx = this.chartRefs.qualityChart.el?.getContext('2d');
        if (!ctx || this.chartInstances.quality) return;

        this.chartInstances.quality = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Today', 'Yesterday', '2 Days Ago', '3 Days Ago', '4 Days Ago'],
                datasets: [{
                    label: 'Parts Processed',
                    data: [0, 0, 0, 0, 0],
                    backgroundColor: 'rgba(54, 162, 235, 0.8)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 2,
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { display: false }
                    },
                    x: {
                        grid: { display: false }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }

    createTrendChart() {
        const ctx = this.chartRefs.trendChart.el?.getContext('2d');
        if (!ctx || this.chartInstances.trend) return;

        this.chartInstances.trend = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Rejection Rate %',
                    data: [],
                    borderColor: '#ffc107',
                    backgroundColor: 'rgba(255, 193, 7, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }

    createMeasurementChart() {
        const ctx = this.chartRefs.measurementChart.el?.getContext('2d');
        if (!ctx || this.chartInstances.measurement) return;

        this.chartInstances.measurement = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Measurements',
                    data: [],
                    borderColor: '#17a2b8',
                    backgroundColor: 'rgba(23, 162, 184, 0.2)',
                    borderWidth: 2,
                    pointBackgroundColor: '#17a2b8',
                    pointRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }

    updateCharts() {
        this.updateProductionChart();
        this.updateQualityChart();
        this.updateTrendChart();
        this.updateMeasurementChart();
    }

    updateProductionChart() {
        if (!this.chartInstances.production || !this.state.selectedMachine) return;

        const okCount = this.state.selectedMachine.ok_count || 0;
        const rejectCount = this.state.selectedMachine.reject_count || 0;

        this.chartInstances.production.data.datasets[0].data = [okCount, rejectCount];
        this.chartInstances.production.update('none');
    }

    updateQualityChart() {
        if (!this.chartInstances.quality || !this.state.machineDetailData) return;

        // Simulate historical data (replace with real data from your backend)
        const historicalData = [
            this.state.machineDetailData.summary.total_count,
            Math.floor(Math.random() * 100) + 50,
            Math.floor(Math.random() * 100) + 40,
            Math.floor(Math.random() * 100) + 45,
            Math.floor(Math.random() * 100) + 35
        ];

        this.chartInstances.quality.data.datasets[0].data = historicalData;
        this.chartInstances.quality.update('none');
    }

    updateTrendChart() {
        if (!this.chartInstances.trend || !this.state.machineDetailData) return;

        // Simulate trend data (replace with real historical data)
        const hours = Array.from({length: 12}, (_, i) => {
            const hour = new Date().getHours() - 11 + i;
            return hour < 0 ? 24 + hour : hour > 23 ? hour - 24 : hour;
        });

        const trendData = hours.map(() => Math.random() * 10);

        this.chartInstances.trend.data.labels = hours.map(h => `${h}:00`);
        this.chartInstances.trend.data.datasets[0].data = trendData;
        this.chartInstances.trend.update('none');
    }

    updateMeasurementChart() {
        if (!this.chartInstances.measurement || !this.state.machineDetailData?.records?.length) return;

        const latestRecord = this.state.machineDetailData.records[0];
        if (!latestRecord?.measurements) return;

        const measurements = latestRecord.measurements;
        const labels = Object.keys(measurements);
        const values = Object.values(measurements).map(v => parseFloat(v) || 0);

        this.chartInstances.measurement.data.labels = labels;
        this.chartInstances.measurement.data.datasets[0].data = values;
        this.chartInstances.measurement.update('none');
    }

    getStatusClass(status) {
        const statusClasses = {
            'running': 'status-running',
            'stopped': 'status-stopped',
            'error': 'status-error',
            'maintenance': 'status-maintenance'
        };
        return statusClasses[status] || 'status-unknown';
    }

    getCardClass(machine) {
        const isSelected = this.state.selectedMachine?.id === machine.id;
        return `machine-card ${isSelected ? 'selected' : ''}`;
    }

    formatTime(datetime) {
        if (!datetime) return 'Never';
        return new Date(datetime).toLocaleString();
    }

    formatNumber(num) {
        return num?.toLocaleString() || '0';
    }

    getEfficiencyColor(rejectionRate) {
        if (rejectionRate <= 2) return 'text-success';
        if (rejectionRate <= 5) return 'text-warning';
        return 'text-danger';
    }
}

// Load Chart.js if not already loaded
if (!window.Chart) {
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.min.js';
    document.head.appendChild(script);
}

registry.category("actions").add("modern_manufacturing_dashboard", ModernManufacturingDashboard);