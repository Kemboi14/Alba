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

export class InvestorDashboardCharts extends Component {
    static template = "alba_investors.InvestorDashboardCharts";
    static props = { ...standardFieldProps };

    setup() {
        this.charts = {};
        this.canvasRefs = {
            investmentComposition: useRef("investment_composition_canvas"),
            investorStatus: useRef("investor_status_canvas"),
            investmentTrends: useRef("investment_trends_canvas"),
            interestPayout: useRef("interest_payout_trends_canvas"),
            withdrawal: useRef("withdrawal_analysis_canvas"),
            investorType: useRef("investor_type_distribution_canvas"),
            amountDist: useRef("investment_amount_distribution_canvas"),
            tenure: useRef("tenure_distribution_canvas")
        };

        onMounted(() => {
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
        if (typeof Chart === "undefined") {
            console.error("Chart.js is not loaded");
            return;
        }
        
        this._renderInvestmentComposition();
        this._renderInvestorStatus();
        this._renderInvestmentTrends();
        this._renderInterestPayoutTrends();
        this._renderWithdrawalAnalysis();
        this._renderInvestorTypeDistribution();
        this._renderInvestmentAmountDistribution();
        this._renderTenureDistribution();
    }

    _renderPieChart(fieldName, canvasRef, labelSuffix = "") {
        const raw = this.recordData[fieldName];
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs[canvasRef].el;
            if (!ctx) {
                console.error(`Canvas element not found for ${canvasRef}`);
                return;
            }
            this.charts[canvasRef] = new Chart(ctx, {
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
            console.error(`Error rendering chart [${canvasRef}]:`, e);
        }
    }

    _renderInvestmentComposition() {
        this._renderPieChart("investment_composition_data", "investmentComposition");
    }

    _renderInvestorStatus() {
        this._renderPieChart("investor_status_data", "investorStatus", " investors");
    }

    _renderInvestorTypeDistribution() {
        this._renderPieChart("investor_type_distribution_data", "investorType", " investors");
    }

    _renderInvestmentAmountDistribution() {
        const raw = this.recordData.investment_amount_distribution_data;
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs.amountDist.el;
            if (!ctx) return;
            this.charts.amountDist = new Chart(ctx, {
                type: "bar",
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: ANIMATION_CONFIG,
                    scales: { y: { beginAtZero: true, title: { display: true, text: "Number of Investors" } } },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function(c) {
                                    return `Investors: ${(c.parsed.y || 0).toLocaleString()}`;
                                },
                            },
                        },
                    },
                },
            });
        } catch (e) {
            console.error("Error rendering investment amount distribution chart:", e);
        }
    }

    _renderTenureDistribution() {
        this._renderPieChart("tenure_distribution_data", "tenure", " investments");
    }

    _renderInvestmentTrends() {
        const raw = this.recordData.investment_trends_data;
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs.investmentTrends.el;
            if (!ctx) return;
            this.charts.investmentTrends = new Chart(ctx, {
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
            console.error("Error rendering investment trends chart:", e);
        }
    }

    _renderInterestPayoutTrends() {
        const raw = this.recordData.interest_payout_trends_data;
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs.interestPayout.el;
            if (!ctx) return;
            this.charts.interestPayout = new Chart(ctx, {
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
            console.error("Error rendering interest payout trends chart:", e);
        }
    }

    _renderWithdrawalAnalysis() {
        const raw = this.recordData.withdrawal_analysis_data;
        if (!raw) return;
        try {
            const chartData = JSON.parse(raw);
            const ctx = this.canvasRefs.withdrawal.el;
            if (!ctx) return;
            this.charts.withdrawal = new Chart(ctx, {
                type: "bar",
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: ANIMATION_CONFIG,
                    scales: { y: { beginAtZero: true, title: { display: true, text: "Amount" } } },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function(c) {
                                    return `Amount: ${(c.parsed.y || 0).toLocaleString("en-KE", { style: "currency", currency: "KES" })}`;
                                },
                            },
                        },
                    },
                },
            });
        } catch (e) {
            console.error("Error rendering withdrawal analysis chart:", e);
        }
    }
}

registry.category("fields").add("investor_dashboard_charts", {
    component: InvestorDashboardCharts,
});
