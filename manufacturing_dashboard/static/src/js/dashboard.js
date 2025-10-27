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
            measurementChart: useRef("measurementChart"),
            oeeChart: useRef("oeeChart"),
            qualityTrendChart: useRef("qualityTrendChart")
        };

        this.state = useState({
            machines: [],
            statistics: {},
            selectedMachine: null,
            machineDetailData: null,
            loading: true,
            error: null,
            tableFilter: 'today'
        });

        this.refreshInterval = null;
        this.chartInstances = {};

        onMounted(async () => {
            try {
                console.log('Dashboard mounted, Chart.js available:', !!window.Chart);
                await this.loadDashboardData();
                this.setupCharts();
            } catch (error) {
                console.error('Error in dashboard initialization:', error);
                this.state.error = 'Dashboard initialization failed: ' + error.message;
            } finally {
                // Always set loading to false, even if there's an error
                this.state.loading = false;
                console.log('Dashboard loading completed, loading state set to false');
            }

            // Auto refresh every 30 seconds (only if no error)
            if (!this.state.error) {
                this.refreshInterval = setInterval(async () => {
                    try {
                        await this.refreshDashboardData();
                        this.updateCharts();
                    } catch (error) {
                        console.error('Error in auto refresh:', error);
                    }
                }, 30000);

                // Final station data refresh removed - now handled by separate dashboard
            }
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
            console.log('Loading dashboard data...');

            // Add timeout to prevent hanging
            const timeoutPromise = new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Request timeout')), 10000)
            );

            let data;
            try {
                // Try the enhanced dashboard data method first
                const dataPromise = this.orm.call(
                    "manufacturing.machine.config",
                    "get_enhanced_dashboard_data",
                    [this.state.tableFilter || 'today']
                );
                data = await Promise.race([dataPromise, timeoutPromise]);
            } catch (methodError) {
                console.warn('Enhanced dashboard method not available, trying fallback:', methodError.message);
                // Fallback to basic search if enhanced method doesn't exist
                const machines = await this.orm.searchRead(
                    "manufacturing.machine.config",
                    [],
                    ["id", "name", "machine_type", "status", "last_sync"]
                );
                data = {
                    machines: machines,
                    statistics: {
                        total_parts: 0,
                        passed_parts: 0,
                        rejected_parts: 0,
                        pending_parts: 0
                    }
                };
            }

            console.log('Dashboard data received:', data);

            this.state.machines = data.machines || [];
            this.state.statistics = data.statistics || {};
            this.state.error = null;

            console.log('Machines loaded:', this.state.machines.length);
            console.log('Statistics:', this.state.statistics);

            if (this.state.machines.length > 0) {
                console.log('Auto-selecting first machine:', this.state.machines[0]);
                await this.selectMachine(this.state.machines[0]);
            }
        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.state.error = "Failed to load dashboard data: " + error.message;
            // Set empty data to prevent complete failure
            this.state.machines = [];
            this.state.statistics = {
                total_parts: 0,
                passed_parts: 0,
                rejected_parts: 0,
                pending_parts: 0
            };
        }
    }

    async refreshDashboardData() {
        try {
            console.log('Refreshing dashboard data...');

            // Add timeout to prevent hanging
            const timeoutPromise = new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Request timeout')), 10000)
            );

            let data;
            try {
                // Try the enhanced dashboard data method first
                const dataPromise = this.orm.call(
                    "manufacturing.machine.config",
                    "get_enhanced_dashboard_data",
                    [this.state.tableFilter || 'today']
                );
                data = await Promise.race([dataPromise, timeoutPromise]);
            } catch (methodError) {
                console.warn('Enhanced dashboard method not available, trying fallback:', methodError.message);
                // Fallback to basic search if enhanced method doesn't exist
                const machines = await this.orm.searchRead(
                    "manufacturing.machine.config",
                    [],
                    ["id", "name", "machine_type", "status", "last_sync"]
                );
                data = {
                    machines: machines,
                    statistics: {
                        total_parts: 0,
                        passed_parts: 0,
                        rejected_parts: 0,
                        pending_parts: 0
                    }
                };
            }

            console.log('Dashboard refresh data received:', data);

            // Store current selection
            const currentSelection = this.state.selectedMachine;

            // Update machines and statistics
            this.state.machines = data.machines || [];
            this.state.statistics = data.statistics || {};
            this.state.error = null;

            console.log('Machines refreshed:', this.state.machines.length);
            console.log('Statistics refreshed:', this.state.statistics);

            // Restore selection if it still exists in the updated machines list
            if (currentSelection && this.state.machines.length > 0) {
                const updatedMachine = this.state.machines.find(m => m.id === currentSelection.id);
                if (updatedMachine) {
                    console.log('Restoring selection to:', updatedMachine.name);
                    this.state.selectedMachine = updatedMachine;
                } else {
                    console.log('Previously selected machine no longer exists, selecting first machine');
                    await this.selectMachine(this.state.machines[0]);
                }
            } else if (this.state.machines.length > 0 && !currentSelection) {
                console.log('No previous selection, selecting first machine');
                await this.selectMachine(this.state.machines[0]);
            }
        } catch (error) {
            console.error("Error refreshing dashboard data:", error);
            this.state.error = "Failed to refresh dashboard data: " + error.message;
        }
    }

    async selectMachine(machine) {
        this.state.selectedMachine = machine;
        this.state.machineDetailData = null;
        await this.loadMachineDetail(machine.id);
        setTimeout(() => {
            this.renderOEEChart();
            this.createQualityTrendChart();
        }, 300);

        // Final station specific data loading removed - now handled by separate dashboard
    }

    async loadMachineDetail(machineId) {
        try {
            console.log('Loading machine detail for ID:', machineId);
            const data = await this.orm.call(
                "manufacturing.machine.config",
                "get_machine_detail_data",
                [machineId, this.state.tableFilter || 'today']
            );

            console.log('Machine detail data received:', data);

            if (data.error) {
                console.error('Machine detail error:', data.error);
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


    async onFilterChange(filter) {
        console.log('Filter changed to:', filter);
        this.state.tableFilter = filter;

        await this.refreshDashboardData();

        if (this.state.selectedMachine) {
            console.log('Reloading machine detail with filter:', filter);
            await this.loadMachineDetail(this.state.selectedMachine.id);
        }

        // Update charts with the new filtered data
        this.updateCharts();
    }

    setupCharts() {
        console.log('Setting up charts...');
        console.log('Chart.js available:', !!window.Chart);
        console.log('Chart constructor:', typeof window.Chart);

        // Check if Chart.js is available immediately
        if (window.Chart && typeof window.Chart === 'function') {
            console.log('Chart.js available immediately, creating charts...');
            setTimeout(() => {
                try {
                    console.log('Creating charts...');
                    this.createProductionChart();
                    this.createQualityChart();
                    this.createTrendChart();
                    this.createMeasurementChart();
                    console.log('Charts created successfully');
                } catch (error) {
                    console.error('Error creating charts:', error);
                }
            }, 500);
        } else {
            console.log('Chart.js not available immediately, waiting for it to load...');
            // Wait for Chart.js to be loaded
            this.waitForChartJS().then(() => {
                console.log('Chart.js loaded, creating charts...');
                setTimeout(() => {
                    try {
                        console.log('Creating charts...');
                        this.createProductionChart();
                        this.createQualityChart();
                        this.createTrendChart();
                        this.createMeasurementChart();
                        console.log('Charts created successfully');
                    } catch (error) {
                        console.error('Error creating charts:', error);
                    }
                }, 500);
            }).catch((error) => {
                console.error('Failed to load Chart.js:', error);
            });
        }
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
                console.log(`Checking for Chart.js, attempt ${attempts}/${maxAttempts}`);

                if (window.Chart && typeof window.Chart === 'function') {
                    console.log('Chart.js loaded successfully');
                    resolve();
                } else if (attempts >= maxAttempts) {
                    console.warn('Chart.js not available after waiting, continuing without charts');
                    console.log('Available window properties:', Object.keys(window).filter(k => k.toLowerCase().includes('chart')));
                    console.log('Window.Chart type:', typeof window.Chart);
                    resolve(); // Don't reject, just continue without charts
                } else {
                    setTimeout(checkChart, 100);
                }
            };

            checkChart();
        });
    }

    async openMachineListView(machine) {
        let modelName = '';
        let viewName = '';

        console.log('Opening machine list view for:', machine);
        console.log('Machine type:', machine.machine_type);

        switch(machine.machine_type) {
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
            case 'final_station':
                modelName = 'manufacturing.final.station.measurement';
                viewName = 'Final Station Measurements';
                break;
            default:
                console.error('Unknown machine type:', machine.machine_type);
                return;
        }

        try {
            console.log(`Opening ${viewName} for machine ${machine.name} (ID: ${machine.id})`);

            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: `${viewName} - ${machine.name}`,
                res_model: modelName,
                view_mode: 'list,form',
                views: [[false, 'list'], [false, 'form']],
                domain: [['machine_id', '=', machine.id]],
                context: {
                    'default_machine_id': machine.id,
                    'search_default_machine_id': machine.id
                },
                target: 'current'
            });

            console.log(`Successfully opened ${viewName}`);
        } catch (error) {
            console.error('Error opening machine list view:', error);
            this.showNotification(`Failed to open ${viewName}: ${error.message}`, 'error');
        }
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

    formatNumber(value) {
        return value ? value.toLocaleString() : '0';
    }

    getEfficiencyColor(rejectionRate) {
        if (rejectionRate <= 2) return 'text-success';
        if (rejectionRate <= 5) return 'text-warning';
        return 'text-danger';
    }

    formatMeasurement(value) {
        if (value === null || value === undefined || value === '') {
            return '0.000';
        }
        return parseFloat(value || 0).toFixed(3);
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
        notification.className = `notification ${type}`;
        notification.innerHTML = `
            <div style="padding: 15px;">
                <strong>${type.charAt(0).toUpperCase() + type.slice(1)}</strong><br>
                ${message}
            </div>
        `;

        // Add to page
        document.body.appendChild(notification);

        // Remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    // Chart Creation Methods
    createProductionChart() {
        try {
            console.log('Creating production chart...');
            console.log('Chart.js available:', !!window.Chart);
            console.log('Chart constructor:', typeof window.Chart);

            if (!window.Chart) {
                console.warn('Chart.js not available, skipping chart creation');
                return;
            }

            const ctx = this.chartRefs.productionChart.el?.getContext('2d');
            if (!ctx) {
                console.warn('Production chart canvas not found');
                return;
            }
            if (this.chartInstances.production) {
                console.log('Production chart already exists');
                return;
            }

            console.log('Creating production chart with Chart.js...');
            this.chartInstances.production = new window.Chart(ctx, {
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
                        title: {
                            display: true,
                            text: `Production Overview (${this.state.tableFilter})`,
                            font: { size: 14, weight: 'bold' }
                        },
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
            console.log('Production chart created successfully');
        } catch (error) {
            console.error('Error creating production chart:', error);
        }
    }

    createQualityChart() {
        try {
            console.log('Creating quality chart...');
            if (!window.Chart) {
                console.warn('Chart.js not available, skipping chart creation');
                return;
            }

            const ctx = this.chartRefs.qualityChart.el?.getContext('2d');
            if (!ctx) {
                console.warn('Quality chart canvas not found');
                return;
            }
            if (this.chartInstances.quality) {
                console.log('Quality chart already exists');
                return;
            }

            console.log('Creating quality chart with Chart.js...');
            this.chartInstances.quality = new window.Chart(ctx, {
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
                plugins: {
                    title: {
                        display: true,
                        text: `Production History (${this.state.tableFilter})`,
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { display: false }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
        console.log('Quality chart created successfully');
        } catch (error) {
            console.error('Error creating quality chart:', error);
        }
    }

    createTrendChart() {
        try {
            console.log('Creating trend chart...');
            if (!window.Chart) {
                console.warn('Chart.js not available, skipping chart creation');
                return;
            }

            const ctx = this.chartRefs.trendChart.el?.getContext('2d');
            if (!ctx) {
                console.warn('Trend chart canvas not found');
                return;
            }
            if (this.chartInstances.trend) {
                console.log('Trend chart already exists');
                return;
            }

            console.log('Creating trend chart with Chart.js...');
            this.chartInstances.trend = new window.Chart(ctx, {
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
                    title: {
                        display: true,
                        text: `Quality Trend (${this.state.tableFilter})`,
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: { display: false }
                }
            }
        });
        console.log('Trend chart created successfully');
        } catch (error) {
            console.error('Error creating trend chart:', error);
        }
    }

    createMeasurementChart() {
        try {
            console.log('Creating measurement chart...');
            if (!window.Chart) {
                console.warn('Chart.js not available, skipping chart creation');
                return;
            }

            const ctx = this.chartRefs.measurementChart.el?.getContext('2d');
            if (!ctx) {
                console.warn('Measurement chart canvas not found');
                return;
            }
            if (this.chartInstances.measurement) {
                console.log('Measurement chart already exists');
                return;
            }

            console.log('Creating measurement chart with Chart.js...');
            this.chartInstances.measurement = new window.Chart(ctx, {
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
                    title: {
                        display: true,
                        text: `Measurement Analysis (${this.state.tableFilter})`,
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: { display: false }
                }
            }
        });
        console.log('Measurement chart created successfully');
        } catch (error) {
            console.error('Error creating measurement chart:', error);
        }
    }

    renderOEEChart() {
        try {
            if (!window.Chart) return;
            const ctx = this.chartRefs.oeeChart.el?.getContext('2d');
            if (!ctx) return;

            if (this.chartInstances.oee) this.chartInstances.oee.destroy();

            const oee = this.state.selectedMachine?.average_oee || 0;
            const remaining = 100 - oee;

            this.chartInstances.oee = new window.Chart(ctx, {
                type: 'pie',
                data: {
                    labels: ['OEE %', 'Loss %'],
                    datasets: [{
                        data: [oee, remaining],
                        backgroundColor: ['#4CAF50', '#E0E0E0']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: { display: true, text: 'Average OEE Performance' },
                        legend: { position: 'bottom' }
                    }
                }
            });
        } catch (error) {
            console.error('Error creating OEE chart:', error);
        }
    }

    createQualityTrendChart() {
        try {
            if (!window.Chart) return;
            const ctx = this.chartRefs.qualityTrendChart.el?.getContext('2d');
            if (!ctx) return;

            if (this.chartInstances.qualityTrend) this.chartInstances.qualityTrend.destroy();

            const trend = this.state.selectedMachine?.quality_trend || [];
            const labels = trend.map(d => d.date);
            const okRates = trend.map(d => d.ok_rate);
            const rejectRates = trend.map(d => d.reject_rate);

            this.chartInstances.qualityTrend = new window.Chart(ctx, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [
                        { label: 'OK Rate (%)', data: okRates, backgroundColor: 'rgba(76,175,80,0.7)' },
                        { label: 'Reject Rate (%)', data: rejectRates, backgroundColor: 'rgba(244,67,54,0.7)' }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true, max: 100 },
                        x: { grid: { display: false } }
                    },
                    plugins: { legend: { position: 'bottom' } }
                }
            });
        } catch (error) {
            console.error('Error creating Quality Trend chart:', error);
        }
    }


    // Chart Update Methods
    updateCharts() {
        console.log('Updating charts...');
        this.updateProductionChart();
        this.updateQualityChart();
        this.updateTrendChart();
        this.updateMeasurementChart();
        this.updateChartTitles();
        this.renderOEEChart();
        this.createQualityTrendChart();
    }

    updateChartTitles() {
        try {
            if (this.chartInstances.production && this.chartInstances.production.options?.plugins?.title) {
                this.chartInstances.production.options.plugins.title.text = `Production Overview (${this.state.tableFilter})`;
                this.chartInstances.production.update('none');
            }
            if (this.chartInstances.quality && this.chartInstances.quality.options?.plugins?.title) {
                this.chartInstances.quality.options.plugins.title.text = `Production History (${this.state.tableFilter})`;
                this.chartInstances.quality.update('none');
            }
            if (this.chartInstances.trend && this.chartInstances.trend.options?.plugins?.title) {
                this.chartInstances.trend.options.plugins.title.text = `Quality Trend (${this.state.tableFilter})`;
                this.chartInstances.trend.update('none');
            }
            if (this.chartInstances.measurement && this.chartInstances.measurement.options?.plugins?.title) {
                this.chartInstances.measurement.options.plugins.title.text = `Measurement Analysis (${this.state.tableFilter})`;
                this.chartInstances.measurement.update('none');
            }
        } catch (error) {
            console.error('Error updating chart titles:', error);
        }
    }

    updateProductionChart() {
        if (!window.Chart || !this.chartInstances.production) return;

        const okCount = this.state.machineDetailData?.summary?.ok_count ?? this.state.selectedMachine?.ok_count ?? 0;
        const rejectCount = this.state.machineDetailData?.summary?.reject_count ?? this.state.selectedMachine?.reject_count ?? 0;

        console.log(`Production Chart - Filter: ${this.state.tableFilter}, OK: ${okCount}, Reject: ${rejectCount}`);

        this.chartInstances.production.data.datasets[0].data = [okCount, rejectCount];
        this.chartInstances.production.update('none');
    }

    updateQualityChart() {
        if (!window.Chart || !this.chartInstances.quality || !this.state.machineDetailData) return;

        const series = this.state.machineDetailData.analytics?.production_series;
        if (!series || !Array.isArray(series.values)) {
            console.log('Quality Chart - No production series data available');
            return;
        }

        console.log(`Quality Chart - Filter: ${this.state.tableFilter}, Labels: ${series.labels?.length || 0}, Values: ${series.values?.length || 0}`);

        this.chartInstances.quality.data.labels = series.labels || [];
        this.chartInstances.quality.data.datasets[0].data = series.values || [];
        this.chartInstances.quality.update('none');
    }

    updateTrendChart() {
        if (!window.Chart || !this.chartInstances.trend || !this.state.machineDetailData) return;

        const series = this.state.machineDetailData.analytics?.rejection_series;
        if (!series || !Array.isArray(series.values)) {
            console.log('Trend Chart - No rejection series data available');
            return;
        }

        console.log(`Trend Chart - Filter: ${this.state.tableFilter}, Labels: ${series.labels?.length || 0}, Values: ${series.values?.length || 0}`);

        this.chartInstances.trend.data.labels = series.labels || [];
        this.chartInstances.trend.data.datasets[0].data = series.values || [];
        this.chartInstances.trend.update('none');
    }

    updateMeasurementChart() {
        if (!window.Chart || !this.chartInstances.measurement || !this.state.machineDetailData) return;

        const avg = this.state.machineDetailData.analytics?.measurement_avg;
        if (!avg || !Array.isArray(avg.values)) {
            console.log('Measurement Chart - No measurement average data available');
            return;
        }

        console.log(`Measurement Chart - Filter: ${this.state.tableFilter}, Labels: ${avg.labels?.length || 0}, Values: ${avg.values?.length || 0}`);

        this.chartInstances.measurement.data.labels = avg.labels || [];
        this.chartInstances.measurement.data.datasets[0].data = (avg.values || []).map(v => parseFloat(v) || 0);
        this.chartInstances.measurement.update('none');
    }
}

registry.category("actions").add("modern_manufacturing_dashboard", ModernManufacturingDashboard);
