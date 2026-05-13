/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const VIBRANT_COLORS = [
    '#6366f1', '#8b5cf6', '#ec4899', '#10b981',
    '#f59e0b', '#ef4444', '#3b82f6', '#14b8a6',
    '#f97316', '#84cc16'
];

const ANIMATION_CONFIG = {
    duration: 1000,
    easing: 'easeOutQuart',
};

export class LoanDashboardCharts extends Component {
    static template = "alba_loans.DashboardCharts";
    static props = { ...standardFieldProps };

    setup() {
        this.chart = null;
        this.canvasRef = useRef("canvas");

        onMounted(() => {
            this._renderChart();
        });

        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
            }
        });
    }

    get recordData() {
        return this.props.record.data;
    }

    _renderChart() {
        if (typeof Chart === "undefined") {
            console.error("Chart.js is not loaded");
            return;
        }

        const fieldName = this.props.name;
        const raw = this.recordData[fieldName];
        if (!raw) return;

        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRef.el;
            if (!ctx) return;

            // Determine chart type and options based on field name
            let config = this._getChartConfig(fieldName, chartData, ctx);
            if (config) {
                this.chart = new Chart(ctx, config);
            }
        } catch (e) {
            console.error(`Error rendering chart [${fieldName}]:`, e);
        }
    }

    _getChartConfig(fieldName, chartData, ctx) {
        const commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: ANIMATION_CONFIG,
        };

        if (fieldName === "portfolio_composition_data" || fieldName === "customer_loan_status_data" || fieldName === "loan_tenure_distribution_data") {
            const labelSuffix = fieldName === "customer_loan_status_data" ? " customers" : (fieldName === "loan_tenure_distribution_data" ? " loans" : "");
            return {
                type: "pie",
                data: chartData,
                options: {
                    ...commonOptions,
                    plugins: {
                        legend: { position: "bottom", labels: { padding: 15, font: { size: 12 } } },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label || "";
                                    const value = context.parsed || 0;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const pct = ((value / total) * 100).toFixed(1);
                                    return `${label}: ${value.toLocaleString()}${labelSuffix} (${pct}%)`;
                                },
                            },
                        },
                    },
                },
            };
        }

        if (fieldName === "status_distribution_data") {
            return {
                type: "doughnut",
                data: chartData,
                options: {
                    ...commonOptions,
                    plugins: {
                        legend: { position: "bottom", labels: { padding: 15, font: { size: 12 } } },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const pct = ((context.parsed / total) * 100).toFixed(1);
                                    return `${context.label}: ${context.parsed} loans (${pct}%)`;
                                },
                            },
                        },
                    },
                },
            };
        }

        if (fieldName === "disbursement_trends_data") {
            return {
                type: "line",
                data: chartData,
                options: {
                    ...commonOptions,
                    interaction: { mode: "index", intersect: false },
                    scales: {
                        y:  { type: "linear", position: "left", title: { display: true, text: "Amount" } },
                        y1: { type: "linear", position: "right", title: { display: true, text: "Count"  },
                              grid: { drawOnChartArea: false } },
                    },
                    plugins: {
                        legend: { position: "bottom", labels: { padding: 15, font: { size: 12 } } },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.dataset.label || "";
                                    const value = context.parsed.y || 0;
                                    return context.datasetIndex === 0
                                        ? `${label}: ${value.toLocaleString("en-KE", { style: "currency", currency: "KES" })}` 
                                        : `${label}: ${value.toLocaleString()}`;
                                },
                            },
                        },
                    },
                },
            };
        }

        if (fieldName === "par_analysis_data" || fieldName === "loan_amount_distribution_data") {
            const yLabel = fieldName === "par_analysis_data" ? "Outstanding Amount" : "Number of Loans";
            return {
                type: "bar",
                data: chartData,
                options: {
                    ...commonOptions,
                    scales: { y: { beginAtZero: true, title: { display: true, text: yLabel } } },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function(c) {
                                    const val = c.parsed.y || 0;
                                    return fieldName === "par_analysis_data" 
                                        ? `Outstanding: ${val.toLocaleString("en-KE", { style: "currency", currency: "KES" })}`
                                        : `Loans: ${val.toLocaleString()}`;
                                },
                            },
                        },
                    },
                },
            };
        }

        if (fieldName === "repayment_performance_data") {
            return {
                type: "line",
                data: chartData,
                options: {
                    ...commonOptions,
                    interaction: { mode: "index", intersect: false },
                    scales: { y: { beginAtZero: true, title: { display: true, text: "Amount" } } },
                    plugins: {
                        legend: { position: "bottom", labels: { padding: 15, font: { size: 12 } } },
                        tooltip: {
                            callbacks: {
                                label: function(c) {
                                    return `${c.dataset.label}: ${(c.parsed.y || 0).toLocaleString("en-KE", { style: "currency", currency: "KES" })}`;
                                },
                            },
                        },
                    },
                },
            };
        }

        return null;
    }
}

registry.category("fields").add("loan_dashboard_charts", {
    component: LoanDashboardCharts,
});
