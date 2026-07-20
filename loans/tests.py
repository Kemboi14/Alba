from django.test import SimpleTestCase

from loans.models import Loan, LoanApplication


class OdooStatusMappingTests(SimpleTestCase):
    def test_application_status_label_matches_odoo_alignment(self):
        application = LoanApplication(status=LoanApplication.DEFERRED)
        self.assertEqual(application.get_odoo_status_label(), "Deferred")

        application.status = LoanApplication.DISBURSED
        self.assertEqual(application.get_odoo_status_label(), "Disbursed")

    def test_loan_status_label_matches_odoo_alignment(self):
        loan = Loan(status=Loan.PAID)
        self.assertEqual(loan.get_odoo_status_label(), "Closed")

        loan.status = Loan.OVERDUE
        self.assertEqual(loan.get_odoo_status_label(), "Overdue")
