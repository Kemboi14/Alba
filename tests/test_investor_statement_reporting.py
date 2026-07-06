import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "odoo_addons" / "alba_investors" / "report" / "account_statement_report.py"


class DummyModelBase:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class DummyApiModule(types.ModuleType):
    @staticmethod
    def model(method):
        return method


class DummyToolsModule(types.ModuleType):
    @staticmethod
    def formatLang(*args, **kwargs):
        return "0.00"


class FakeModel:
    def __init__(self, records):
        self.records = records

    def search(self, domain=None, order=None):
        return list(self.records)


class FakeEnv(dict):
    def __getitem__(self, key):
        return super().__getitem__(key)


class InvestorStatementReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        odoo_module = types.ModuleType("odoo")
        odoo_module.api = DummyApiModule("odoo.api")
        odoo_module.models = types.SimpleNamespace(AbstractModel=DummyModelBase)
        odoo_module.tools = DummyToolsModule("odoo.tools")
        sys.modules["odoo"] = odoo_module
        sys.modules["odoo.tools"] = odoo_module.tools

        spec = importlib.util.spec_from_file_location("alba_account_statement_report", MODULE_PATH)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.module)

    def test_collect_statement_events_includes_topups_accruals_payouts_and_withdrawals(self):
        investment = SimpleNamespace(
            id=1,
            start_date=date(2024, 1, 5),
            state="withdrawn",
            principal_amount=1000.0,
            total_topup_amount=200.0,
            total_interest_outstanding=150.0,
            withdrawal_payment_id=SimpleNamespace(date=date(2024, 1, 20)),
        )

        topup = SimpleNamespace(date=date(2024, 1, 10), amount=200.0, name="TP-1")
        payout = SimpleNamespace(payout_date=date(2024, 1, 15), gross_interest=50.0, name="PY-1")
        accrual = SimpleNamespace(accrual_date=date(2024, 1, 25), interest_amount=75.0, name="AC-1")

        fake_env = FakeEnv({
            "alba.investment.topup": FakeModel([topup]),
            "alba.interest.payout": FakeModel([payout]),
            "alba.interest.accrual": FakeModel([accrual]),
        })

        report_mixin = self.module.AccountStatementReportMixin()
        report_mixin.env = fake_env
        events = report_mixin.collect_investment_statement_events(
            investment,
            date(2024, 1, 1),
            date(2024, 1, 31),
            include_initial_deposit=True,
            env=fake_env,
        )

        event_types = [event["type"] for event in events]
        self.assertIn("deposit", event_types)
        self.assertIn("topup", event_types)
        self.assertIn("payout", event_types)
        self.assertIn("accrual", event_types)
        self.assertIn("withdrawal", event_types)


if __name__ == "__main__":
    unittest.main()
