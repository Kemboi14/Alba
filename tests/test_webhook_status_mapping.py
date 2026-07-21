from django.test import SimpleTestCase

from core.services import webhooks
from loans.models import LoanApplication


class WebhookStatusMappingTests(SimpleTestCase):
    def test_maps_odoo_statuses_to_django_statuses(self):
        self.assertEqual(
            webhooks._map_odoo_application_status("deferred"),
            LoanApplication.DEFERRED,
        )
        self.assertEqual(
            webhooks._map_odoo_application_status("declined"),
            LoanApplication.DECLINED,
        )
        self.assertEqual(
            webhooks._map_odoo_application_status("pending_approval"),
            LoanApplication.PENDING_APPROVAL,
        )
        self.assertEqual(
            webhooks._map_odoo_application_status("disbursed"),
            LoanApplication.DISBURSED,
        )
