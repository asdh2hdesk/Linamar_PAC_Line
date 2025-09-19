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
            charts: {},
            tableFilter: 'today',
            tableRecords: [],
            tableLoading: false,
            currentPage: 1,
            totalPages: 1,
            recordsPerPage: 20,
            treeData: [],
            treeLoading: false
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
                [machineId, 'today', 1, 50] // Default parameters for basic machine detail
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

        // Load table records with current filter
        await this.loadTableRecords();

        // Load tree data
        await this.loadTreeData();

        // Update charts after data load
        setTimeout(() => {
            this.updateCharts();
        }, 100);
    }

    async loadTableRecords() {
        if (!this.state.selectedMachine) return;

        this.state.tableLoading = true;
        try {
            console.log('Loading table records with params:', {
                machineId: this.state.selectedMachine.id,
                filter: this.state.tableFilter,
                page: this.state.currentPage,
                recordsPerPage: this.state.recordsPerPage
            });

            const data = await this.orm.call(
                "manufacturing.machine.config",
                "get_machine_detail_data",
                [this.state.selectedMachine.id, this.state.tableFilter, this.state.currentPage, this.state.recordsPerPage]
            );

            console.log('Table records response:', data);

            this.state.tableRecords = data.records || [];
            this.state.totalPages = data.pagination?.total_pages || 1;
            this.state.tableLoading = false;
        } catch (error) {
            console.error("Error loading table records:", error);
            this.state.tableLoading = false;
        }
    }

    async onFilterChange(filter) {
        this.state.tableFilter = filter;
        this.state.currentPage = 1;
        await this.loadTableRecords();
    }

    async onPageChange(page) {
        if (page >= 1 && page <= this.state.totalPages) {
            this.state.currentPage = page;
            await this.loadTableRecords();
        }
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
        if (!window.Chart || !this.chartInstances.production || !this.state.selectedMachine) return;

        const okCount = this.state.selectedMachine.ok_count || 0;
        const rejectCount = this.state.selectedMachine.reject_count || 0;

        this.chartInstances.production.data.datasets[0].data = [okCount, rejectCount];
        this.chartInstances.production.update('none');
    }

    updateQualityChart() {
        if (!window.Chart || !this.chartInstances.quality || !this.state.machineDetailData) return;

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
        if (!window.Chart || !this.chartInstances.trend || !this.state.machineDetailData) return;

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
        if (!window.Chart || !this.chartInstances.measurement || !this.state.machineDetailData?.records?.length) return;

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

    viewRecordDetails(record) {
        // Open modal or detailed view for record
        console.log('Viewing details for record:', record);
        // You can implement a modal here to show full record details
    }

    exportRecord(record) {
        // Export single record data
        const dataStr = JSON.stringify(record, null, 2);
        const dataBlob = new Blob([dataStr], {type: 'application/json'});

        const link = document.createElement('a');
        link.href = URL.createObjectURL(dataBlob);
        link.download = `record_${record.serial_number}.json`;
        link.click();
    }

    getFilterDisplayName(filter) {
        const filterNames = {
            'today': 'Today',
            'week': 'This Week',
            'month': 'This Month',
            'year': 'This Year'
        };
        return filterNames[filter] || filter;
    }

    // Tree Data Methods
    async loadTreeData() {
        if (!this.state.selectedMachine) return;

        this.state.treeLoading = true;
        try {
            // Generate sample tree data based on machine records
            const treeData = this.generateTreeData();
            this.state.treeData = treeData;
            this.state.treeLoading = false;
        } catch (error) {
            console.error("Error loading tree data:", error);
            this.state.treeLoading = false;
        }
    }

    generateTreeData() {
        if (!this.state.machineDetailData?.records) return [];

        const treeData = [];
        const records = this.state.machineDetailData.records;

        // Group records by batch or create hierarchical structure
        const groupedRecords = this.groupRecordsHierarchically(records);

        let idCounter = 1;
        
        // Create parent nodes (batches or time periods)
        Object.entries(groupedRecords).forEach(([groupKey, groupRecords]) => {
            const parentNode = {
                id: idCounter++,
                level: 1,
                levelName: 'Batch',
                serialNumber: groupKey,
                batchNumber: groupKey,
                category: 'Batch',
                categoryIcon: 'fas fa-layer-group',
                status: this.calculateGroupStatus(groupRecords),
                statusIcon: this.getStatusIcon(this.calculateGroupStatus(groupRecords)),
                statusText: this.calculateGroupStatus(groupRecords).toUpperCase(),
                progress: this.calculateGroupProgress(groupRecords),
                timestamp: groupRecords[0]?.test_date || new Date().toISOString(),
                measurements: this.getGroupMeasurements(groupRecords),
                hasChildren: groupRecords.length > 1,
                expanded: false,
                children: []
            };

            // Create child nodes (individual records)
            groupRecords.forEach((record, index) => {
                const childNode = {
                    id: idCounter++,
                    level: 2,
                    levelName: 'Record',
                    serialNumber: record.serial_number,
                    batchNumber: groupKey,
                    category: 'Production',
                    categoryIcon: 'fas fa-cogs',
                    status: record.result,
                    statusIcon: this.getStatusIcon(record.result),
                    statusText: record.result.toUpperCase(),
                    progress: record.result === 'pass' ? 100 : 0,
                    timestamp: record.test_date,
                    measurements: this.formatRecordMeasurements(record.measurements),
                    hasChildren: false,
                    expanded: false,
                    parentId: parentNode.id
                };
                parentNode.children.push(childNode);
            });

            treeData.push(parentNode);
        });

        return treeData;
    }

    groupRecordsHierarchically(records) {
        // Group by batch number if available, otherwise by hour
        const groups = {};
        
        records.forEach(record => {
            const batchKey = record.batch_serial || this.getHourKey(record.test_date);
            if (!groups[batchKey]) {
                groups[batchKey] = [];
            }
            groups[batchKey].push(record);
        });

        return groups;
    }

    getHourKey(timestamp) {
        const date = new Date(timestamp);
        return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()} ${date.getHours()}:00`;
    }

    calculateGroupStatus(records) {
        const passCount = records.filter(r => r.result === 'pass').length;
        const totalCount = records.length;
        
        if (passCount === totalCount) return 'pass';
        if (passCount === 0) return 'fail';
        return 'partial';
    }

    calculateGroupProgress(records) {
        const passCount = records.filter(r => r.result === 'pass').length;
        return Math.round((passCount / records.length) * 100);
    }

    getGroupMeasurements(records) {
        // Get average measurements for the group
        const measurements = {};
        const measurementKeys = Object.keys(records[0]?.measurements || {});
        
        measurementKeys.forEach(key => {
            const values = records.map(r => parseFloat(r.measurements?.[key] || 0)).filter(v => !isNaN(v));
            if (values.length > 0) {
                const avg = values.reduce((sum, val) => sum + val, 0) / values.length;
                measurements[key] = {
                    name: key,
                    value: avg.toFixed(3),
                    status: 'pass' // Simplified for group view
                };
            }
        });

        return Object.values(measurements);
    }

    formatRecordMeasurements(measurements) {
        if (!measurements) return [];
        
        return Object.entries(measurements).map(([name, value]) => ({
            name,
            value: parseFloat(value || 0).toFixed(3),
            status: 'pass' // You can add logic to determine pass/fail based on tolerances
        }));
    }

    getStatusIcon(status) {
        const icons = {
            'pass': 'fas fa-check-circle',
            'fail': 'fas fa-times-circle',
            'partial': 'fas fa-exclamation-triangle',
            'running': 'fas fa-play-circle',
            'stopped': 'fas fa-stop-circle',
            'error': 'fas fa-exclamation-circle'
        };
        return icons[status] || 'fas fa-question-circle';
    }

    // Tree interaction methods
    toggleTreeRow(itemId) {
        const item = this.state.treeData.find(item => item.id === itemId);
        if (item) {
            item.expanded = !item.expanded;
        }
    }

    expandAllTreeRows() {
        this.state.treeData.forEach(item => {
            if (item.hasChildren) {
                item.expanded = true;
            }
        });
    }

    collapseAllTreeRows() {
        this.state.treeData.forEach(item => {
            item.expanded = false;
        });
    }

    viewTreeItemDetails(item) {
        console.log('Viewing tree item details:', item);
        // Implement modal or detailed view
    }

    editTreeItem(item) {
        console.log('Editing tree item:', item);
        // Implement edit functionality
    }

    deleteTreeItem(item) {
        console.log('Deleting tree item:', item);
        // Implement delete functionality
    }

    // Add the missing formatMeasurement function
    formatMeasurement(value) {
        if (value === null || value === undefined || value === '') {
            return '0.000';
        }
        return parseFloat(value || 0).toFixed(3);
    }
}

registry.category("actions").add("modern_manufacturing_dashboard", ModernManufacturingDashboard);