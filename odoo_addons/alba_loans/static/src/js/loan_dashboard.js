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
        this.charts = {};
        this.canvasRefs = {
            portfolio: useRef("portfolio_canvas"),
            customerStatus: useRef("customer_status_canvas"),
            status: useRef("status_canvas"),
            tenure: useRef("tenure_canvas"),
            disbursement: useRef("disbursement_canvas"),
            par: useRef("par_canvas"),
            amountDist: useRef("amount_dist_canvas"),
            repayment: useRef("repayment_canvas")
        };

        onMounted(() => {
            console.log("Debug: Component mounted, DOM elements:", {
                portfolio: this.canvasRefs.portfolio.el,
                customerStatus: this.canvasRefs.customerStatus.el,
                status: this.canvasRefs.status.el,
                tenure: this.canvasRefs.tenure.el,
                disbursement: this.canvasRefs.disbursement.el,
                par: this.canvasRefs.par.el,
                amountDist: this.canvasRefs.amountDist.el,
                repayment: this.canvasRefs.repayment.el
            });
            
            this._renderCharts();
        });

        onWillUnmount(() => {
            Object.values(this.charts).forEach((chart) => {
                if (chart) chart.destroy();
            });
        });
    }

    get recordData() {
        return this.props.record.data;
    }

    _renderCharts() {
        // Check if Chart.js is loaded
        if (typeof Chart === "undefined") {
            console.error("Chart.js is not loaded");
            console.log("Debug: Available window objects:", Object.keys(window).filter(k => k.includes('Chart')));
            return;
        }
        
        console.log("Debug: Chart.js loaded, Chart object:", typeof Chart);
        
        this._renderPortfolioComposition();
        this._renderCustomerLoanStatus();
        this._renderStatusDistribution();
        this._renderLoanTenureDistribution();
        this._renderDisbursementTrends();
        this._renderParAnalysis();
        this._renderLoanAmountDistribution();
        this._renderRepaymentPerformance();
    }

    _renderPieChart(fieldName, canvasId, labelSuffix = "") {
        const raw = this.recordData[fieldName];
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs[canvasId.replace('_chart', '_canvas')].el;
            if (!ctx) {
                console.error(`Canvas element not found for ${canvasId}`);
                return;
            }
            this.charts[canvasId] = new Chart(ctx, {
                type: "pie",
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: ANIMATION_CONFIG,
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
            });
        } catch (e) {
            console.error(`Error rendering chart [${canvasId}]:`, e);
        }
    }

    _renderPortfolioComposition() {
        this._renderPieChart("portfolio_composition_data", "portfolio_composition_chart");
    }

    _renderCustomerLoanStatus() {
        this._renderPieChart("customer_loan_status_data", "customer_loan_status_chart", " customers");
    }

    _renderStatusDistribution() {
        const raw = this.recordData.status_distribution_data;
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs.status.el;
            if (!ctx) {
                console.error("Status canvas not found");
                return;
            }
            this.charts.status = new Chart(ctx, {
                type: "doughnut",
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: ANIMATION_CONFIG,
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
            });
        } catch (e) {
            console.error("Error rendering status distribution chart:", e);
        }
    }

    _renderLoanTenureDistribution() {
        this._renderPieChart("loan_tenure_distribution_data", "loan_tenure_distribution_chart", " loans");
    }

    _renderDisbursementTrends() {
        const raw = this.recordData.disbursement_trends_data;
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs.disbursement.el;
            if (!ctx) {
                console.error("Disbursement canvas not found");
                return;
            }
            this.charts.disbursement = new Chart(ctx, {
                type: "line",
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: "index", intersect: false },
                    animation: ANIMATION_CONFIG,
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
            });
        } catch (e) {
            console.error("Error rendering disbursement trends chart:", e);
        }
    }

    _renderParAnalysis() {
        const raw = this.recordData.par_analysis_data;
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs.par.el;
            if (!ctx) {
                console.error("PAR canvas not found");
                return;
            }
            this.charts.par = new Chart(ctx, {
                type: "bar",
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: ANIMATION_CONFIG,
                    scales: { y: { beginAtZero: true, title: { display: true, text: "Outstanding Amount" } } },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function(c) {
                                    return `Outstanding: ${(c.parsed.y || 0).toLocaleString("en-KE", { style: "currency", currency: "KES" })}`;
                                },
                            },
                        },
                    },
                },
            });
        } catch (e) {
            console.error("Error rendering PAR analysis chart:", e);
        }
    }

    _renderLoanAmountDistribution() {
        const raw = this.recordData.loan_amount_distribution_data;
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs.amountDist.el;
            if (!ctx) {
                console.error("Amount distribution canvas not found");
                return;
            }
            this.charts.amountDist = new Chart(ctx, {
                type: "bar",
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: ANIMATION_CONFIG,
                    scales: { y: { beginAtZero: true, title: { display: true, text: "Number of Loans" } } },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function(c) {
                                    return `Loans: ${(c.parsed.y || 0).toLocaleString()}`;
                                },
                            },
                        },
                    },
                },
            });
        } catch (e) {
            console.error("Error rendering loan amount distribution chart:", e);
        }
    }

    _renderRepaymentPerformance() {
        const raw = this.recordData.repayment_performance_data;
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs.repayment.el;
            if (!ctx) {
                console.error("Repayment canvas not found");
                return;
            }
            this.charts.repayment = new Chart(ctx, {
                type: "line",
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: "index", intersect: false },
                    animation: ANIMATION_CONFIG,
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
            });
        } catch (e) {
            console.error("Error rendering repayment performance chart:", e);
        }
    }
}

registry.category("fields").add("loan_dashboard_charts", {
    component: LoanDashboardCharts,
});
