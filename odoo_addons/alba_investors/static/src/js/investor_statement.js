/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class InvestorStatementComponent extends Component {
    static template = "alba_investors.InvestorStatement";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        const params = this.props.action.params || {};
        const context = this.props.action.context || {};

        this.state = useState({
            investorId: params.investor_id || context.investor_id || false,
            dateFrom: params.date_from || context.date_from || "",
            dateTo: params.date_to || context.date_to || "",
            investmentIds: params.investment_ids || context.investment_ids || [],
            data: null,
            loading: true,
            error: null,
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        if (!this.state.investorId) {
            this.state.loading = false;
            this.state.error = "No investor selected.";
            return;
        }
        this.state.loading = true;
        this.state.error = null;
        try {
            const data = await this.orm.call(
                "alba.investor",
                "get_statement_data",
                [
                    this.state.investorId,
                    this.state.dateFrom,
                    this.state.dateTo,
                    this.state.investmentIds,
                ]
            );
            this.state.data = data;
        } catch (err) {
            console.error("Error loading statement data:", err);
            this.state.error = "Failed to load statement data.";
        } finally {
            this.state.loading = false;
        }
    }

    async onRefresh() {
        await this.loadData();
    }

    onDownloadPdf() {
        if (!this.state.investorId) return;
        return this.action.doAction("alba_investors.action_investor_statement_report", {
            resIds: [this.state.investorId],
            additionalContext: {
                date_from: this.state.dateFrom,
                date_to: this.state.dateTo,
            },
        });
    }
}

registry.category("actions").add("alba_investors.InvestorStatement", InvestorStatementComponent);
