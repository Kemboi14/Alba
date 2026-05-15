# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models

CHART_COLORS = [
    "#0d2d5e", "#1a4b8c", "#2e6bbf", "#e07b2a",
    "#10b981", "#6366f1", "#ec4899", "#f59e0b",
]


class AlbaLoanModificationMixin(models.AbstractModel):
    """Shared chart helpers and document support for loan modification records."""

    _name = "alba.loan.modification.mixin"
    _description = "Loan Modification UI Mixin"

    comparison_chart_data = fields.Char(
        string="Comparison Chart",
        compute="_compute_modification_charts",
    )
    impact_chart_data = fields.Char(
        string="Impact Chart",
        compute="_compute_modification_charts",
    )

    def _compute_modification_charts(self):
        for rec in self:
            comparison = rec._get_modification_comparison_chart()
            impact = rec._get_modification_impact_chart()
            rec.comparison_chart_data = json.dumps(comparison) if comparison else False
            rec.impact_chart_data = json.dumps(impact) if impact else False

    def _get_modification_comparison_chart(self):
        """Override in each model. Return Chart.js data dict or None."""
        return None

    def _get_modification_impact_chart(self):
        """Override in each model. Return Chart.js doughnut data dict or None."""
        return None

    @api.model
    def _chart_amount(self, amount):
        return float(amount or 0.0)

    @api.model
    def _build_grouped_bar_chart(self, labels, before_values, after_values):
        return {
            "labels": labels,
            "datasets": [
                {
                    "label": "Before",
                    "data": before_values,
                    "backgroundColor": "#94a3b8",
                    "borderRadius": 4,
                },
                {
                    "label": "After",
                    "data": after_values,
                    "backgroundColor": "#0d2d5e",
                    "borderRadius": 4,
                },
            ],
        }

    @api.model
    def _build_doughnut_chart(self, labels, values):
        colors = CHART_COLORS[: len(labels)]
        return {
            "labels": labels,
            "datasets": [
                {
                    "data": values,
                    "backgroundColor": colors,
                    "borderWidth": 2,
                    "borderColor": "#ffffff",
                }
            ],
        }
