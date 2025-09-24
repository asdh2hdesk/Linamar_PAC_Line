/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ModernManufacturingDashboard extends Component {
    static template = "manufacturing_dashboard.ModernDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
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
            charts: {},
            tableFilter: 'today'
        });

        this.refreshInterval = null;
        this.chartInstances = {};

        onMounted(async () => {
            console.log('Dashboard mounted, Chart.js available:', !!window.Chart);
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
                [this.state.tableFilter || 'today']
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
                [machineId, this.state.tableFilter || 'today']
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

    async openMachineListView(machine) {
        // Determine the model and view based on machine type
        let modelName = '';
        let viewName = '';
        
        switch(machine.type) {
            case 'vici_vision':
                modelName = 'manufacturing.vici.vision';
                viewName = 'VICI Vision Data';
                break;
            case 'ruhlamat':
                modelName = 'manufacturing.ruhlamat.press';
                viewName = 'Ruhlamat Press Data';
                break;
            case 'aumann':
                modelName = 'manufacturing.aumann.measurement';
                viewName = 'Aumann Measurement Data';
                break;
            case 'gauging':
                modelName = 'manufacturing.gauging.measurement';
                viewName = 'Gauging Measurement Data';
                break;
            default:
                console.error('Unknown machine type:', machine.type);
                return;
        }

        // Open the list view with machine filter
        await this.action.doAction({
            type: 'ir.actions.act_window',
            name: `${viewName} - ${machine.name}`,
            res_model: modelName,
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['machine_id', '=', machine.id]],
            context: {
                'default_machine_id': machine.id,
                'search_default_machine_id': machine.id
            },
            target: 'current'
        });
    }



    async onFilterChange(filter) {
        this.state.tableFilter = filter;
        await this.loadDashboardData();
        if (this.state.selectedMachine) {
            await this.loadMachineDetail(this.state.selectedMachine.id);
        }
        this.updateCharts();
    }


    setupCharts() {
        // Wait for Chart.js to be loaded and DOM to be ready
        this.waitForChartJS().then(() => {
            setTimeout(() => {
                try {
                    this.createProductionChart();
                    this.createQualityChart();
                    this.createTrendChart();
                    this.createMeasurementChart();
                } catch (error) {
                    console.error('Error creating charts:', error);
                }
            }, 200);
        }).catch((error) => {
            console.error('Failed to load Chart.js:', error);
        });
    }

    waitForChartJS() {
        return new Promise((resolve, reject) => {
            // Check if Chart.js is already available
            if (window.Chart && typeof window.Chart === 'function') {
                console.log('Chart.js already available');
                resolve();
                return;
            }

            // Wait for Chart.js to be loaded (it's included in the manifest)
            let attempts = 0;
            const maxAttempts = 50; // 5 seconds max wait time

            const checkChart = () => {
                attempts++;

                if (window.Chart && typeof window.Chart === 'function') {
                    console.log('Chart.js loaded successfully');
                    resolve();
                } else if (attempts >= maxAttempts) {
                    console.warn('Chart.js not available after waiting, continuing without charts');
                    resolve(); // Don't reject, just continue without charts
                } else {
                    setTimeout(checkChart, 100);
                }
            };

            checkChart();
        });
    }

    createProductionChart() {
        if (!window.Chart) {
            console.warn('Chart.js not available, skipping chart creation');
            return;
        }

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
        if (!window.Chart) {
            console.warn('Chart.js not available, skipping chart creation');
            return;
        }

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
        if (!window.Chart) {
            console.warn('Chart.js not available, skipping chart creation');
            return;
        }

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
        if (!window.Chart) {
            console.warn('Chart.js not available, skipping chart creation');
            return;
        }

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
        if (!window.Chart || !this.chartInstances.production) return;
        // Prefer filtered summary from machineDetailData if available
        const okCount = this.state.machineDetailData?.summary?.ok_count ?? this.state.selectedMachine?.ok_count ?? 0;
        const rejectCount = this.state.machineDetailData?.summary?.reject_count ?? this.state.selectedMachine?.reject_count ?? 0;
        this.chartInstances.production.data.datasets[0].data = [okCount, rejectCount];
        this.chartInstances.production.update('none');
    }

    updateQualityChart() {
        if (!window.Chart || !this.chartInstances.quality || !this.state.machineDetailData) return;
        const series = this.state.machineDetailData.analytics?.production_series;
        if (!series || !Array.isArray(series.values)) return;
        this.chartInstances.quality.data.labels = series.labels || [];
        this.chartInstances.quality.data.datasets[0].data = series.values || [];
        this.chartInstances.quality.update('none');
    }

    updateTrendChart() {
        if (!window.Chart || !this.chartInstances.trend || !this.state.machineDetailData) return;
        const series = this.state.machineDetailData.analytics?.rejection_series;
        if (!series || !Array.isArray(series.values)) return;
        this.chartInstances.trend.data.labels = series.labels || [];
        this.chartInstances.trend.data.datasets[0].data = series.values || [];
        this.chartInstances.trend.update('none');
    }

    updateMeasurementChart() {
        if (!window.Chart || !this.chartInstances.measurement || !this.state.machineDetailData) return;
        const avg = this.state.machineDetailData.analytics?.measurement_avg;
        if (!avg || !Array.isArray(avg.values)) return;
        this.chartInstances.measurement.data.labels = avg.labels || [];
        this.chartInstances.measurement.data.datasets[0].data = (avg.values || []).map(v => parseFloat(v) || 0);
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


    // Tree Data Methods

    // Add the missing formatMeasurement function
    formatMeasurement(value) {
        if (value === null || value === undefined || value === '') {
            return '0.000';
        }
        return parseFloat(value || 0).toFixed(3);
    }
}

registry.category("actions").add("modern_manufacturing_dashboard", ModernManufacturingDashboard);