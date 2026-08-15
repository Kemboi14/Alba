# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase


class TestInterestAccrualStatus(TransactionCase):
    """Test cases for computed payment_status field on alba.interest.accrual."""

    def setUp(self):
        super(TestInterestAccrualStatus, self).setUp()
        self.partner = self.env["res.partner"].create({"name": "Test Investor Partner"})
        self.investor = self.env["alba.investor"].create({
            "partner_id": self.partner.id,
            "id_number": "12345678",
            "date_of_birth": date(1990, 1, 1),
            "payment_details": "Test Bank Account 0000000000",
        })
        self.currency = self.env.ref("base.KES") if self.env.ref("base.KES", raise_if_not_found=False) else self.env.company.currency_id
        
        # Product
        self.product = self.env["alba.investment.product"].search([], limit=1)
        if not self.product:
            self.product = self.env["alba.investment.product"].create({
                "name": "Standard Product",
                "investment_type": "open_ended",
                "interest_rate": 12.0,
                "currency_id": self.currency.id,
                "company_id": self.env.company.id,
            })

        self.investment = self.env["alba.investment"].create({
            "investor_id": self.investor.id,
            "investment_product_id": self.product.id,
            "investment_type": "open_ended",
            "principal_amount": 100000.0,
            "interest_rate": 12.0,
            "currency_id": self.currency.id,
            "start_date": date(2026, 1, 1),
            "state": "active",
        })

    def test_payment_status_posted_untouched(self):
        """Test untouched posted accrual shows payment_status == 'posted'."""
        accrual = self.env["alba.interest.accrual"].create({
            "investment_id": self.investment.id,
            "accrual_date": date(2026, 1, 31),
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "opening_balance": 100000.0,
            "interest_amount": 1000.0,
            "state": "posted",
            "interest_payout_id": False,
            "interest_amount_deferred": 0.0,
        })
        self.assertEqual(accrual.payment_status, "posted")

    def test_payment_status_partially_paid(self):
        """Test partially consumed accrual (payout_id set & deferred > 0) shows payment_status == 'partially_paid'."""
        payout = self.env["alba.interest.payout"].create({
            "investment_id": self.investment.id,
            "payout_date": date(2026, 2, 1),
            "gross_interest": 500.0,
            "net_amount": 500.0,
            "state": "posted",
        })
        accrual = self.env["alba.interest.accrual"].create({
            "investment_id": self.investment.id,
            "accrual_date": date(2026, 1, 31),
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "opening_balance": 100000.0,
            "interest_amount": 1000.0,
            "interest_amount_payable_now": 500.0,
            "interest_amount_deferred": 500.0,
            "interest_payout_id": payout.id,
            "state": "posted",
        })
        self.assertEqual(accrual.payment_status, "partially_paid")

    def test_payment_status_paid(self):
        """Test fully settled accrual (state == 'paid') shows payment_status == 'paid'."""
        payout = self.env["alba.interest.payout"].create({
            "investment_id": self.investment.id,
            "payout_date": date(2026, 2, 1),
            "gross_interest": 1000.0,
            "net_amount": 1000.0,
            "state": "posted",
        })
        accrual = self.env["alba.interest.accrual"].create({
            "investment_id": self.investment.id,
            "accrual_date": date(2026, 1, 31),
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "opening_balance": 100000.0,
            "interest_amount": 1000.0,
            "interest_amount_payable_now": 0.0,
            "interest_amount_deferred": 0.0,
            "interest_payout_id": payout.id,
            "state": "paid",
        })
        self.assertEqual(accrual.payment_status, "paid")

    def test_payment_status_false_positive_cutoff_split(self):
        """CRITICAL: Test period still in progress cutoff split with NO payout (payout_id is False) shows 'posted', NOT 'partially_paid'."""
        accrual = self.env["alba.interest.accrual"].create({
            "investment_id": self.investment.id,
            "accrual_date": date(2026, 8, 31),
            "period_start": date(2026, 8, 1),
            "period_end": date(2026, 8, 31),
            "opening_balance": 100000.0,
            "interest_amount": 1000.0,
            "interest_amount_payable_now": 500.0,
            "interest_amount_deferred": 500.0,  # set by 15th cutoff rule
            "interest_payout_id": False,        # NO payout made
            "state": "posted",
        })
        self.assertEqual(accrual.payment_status, "posted")
