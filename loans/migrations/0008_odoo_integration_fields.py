# Generated migration — Odoo integration fields + WebhookDelivery model
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("loans", "0007_customer_verification_fields"),
    ]

    operations = [
        # ── LoanProduct ──────────────────────────────────────────────────────
        migrations.AddField(
            model_name="loanproduct",
            name="odoo_product_id",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                unique=True,
                help_text="ID of the corresponding alba.loan.product record in Odoo",
                verbose_name="Odoo Product ID",
            ),
        ),
        # ── LoanApplication ──────────────────────────────────────────────────
        migrations.AddField(
            model_name="loanapplication",
            name="odoo_loan_id",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Odoo alba.loan ID assigned when this application is disbursed",
                verbose_name="Odoo Loan ID",
            ),
        ),
        migrations.AddField(
            model_name="loanapplication",
            name="odoo_loan_number",
            field=models.CharField(
                blank=True,
                max_length=50,
                default="",
                help_text="Odoo loan reference number (e.g. LN-20240601-0001)",
                verbose_name="Odoo Loan Number",
            ),
        ),
        # ── Loan ─────────────────────────────────────────────────────────────
        migrations.AddField(
            model_name="loan",
            name="odoo_loan_id",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                unique=True,
                db_index=True,
                help_text="ID of the corresponding alba.loan record in Odoo",
                verbose_name="Odoo Loan ID",
            ),
        ),
        # ── LoanRepayment ────────────────────────────────────────────────────
        migrations.AddField(
            model_name="loanrepayment",
            name="odoo_repayment_id",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="ID of the posted repayment record in Odoo",
                verbose_name="Odoo Repayment ID",
            ),
        ),
        migrations.AddField(
            model_name="loanrepayment",
            name="sync_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Sync"),
                    ("posted", "Posted in Odoo"),
                    ("failed", "Sync Failed"),
                ],
                default="pending",
                db_index=True,
                max_length=20,
                help_text="Whether this repayment has been posted/reconciled in Odoo",
                verbose_name="Sync Status",
            ),
        ),
        migrations.AddField(
            model_name="loanrepayment",
            name="principal_applied",
            field=models.DecimalField(
                blank=True,
                null=True,
                decimal_places=2,
                max_digits=12,
                help_text="Principal allocation confirmed by Odoo after posting",
                verbose_name="Principal Applied",
            ),
        ),
        migrations.AddField(
            model_name="loanrepayment",
            name="interest_applied",
            field=models.DecimalField(
                blank=True,
                null=True,
                decimal_places=2,
                max_digits=12,
                help_text="Interest allocation confirmed by Odoo after posting",
                verbose_name="Interest Applied",
            ),
        ),
        # ── WebhookDelivery (new table) ──────────────────────────────────────
        migrations.CreateModel(
            name="WebhookDelivery",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "delivery_id",
                    models.CharField(
                        db_index=True,
                        max_length=128,
                        unique=True,
                        help_text="X-Alba-Delivery UUID sent by Odoo in the webhook envelope",
                        verbose_name="Delivery ID",
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        max_length=128,
                        verbose_name="Event Type",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("processing", "Processing"),
                            ("success", "Success"),
                            ("error", "Error"),
                            ("unhandled", "Unhandled Event"),
                        ],
                        db_index=True,
                        default="processing",
                        max_length=20,
                        verbose_name="Processing Status",
                    ),
                ),
                (
                    "processing_detail",
                    models.TextField(
                        blank=True,
                        verbose_name="Processing Detail",
                    ),
                ),
                (
                    "raw_body",
                    models.TextField(
                        blank=True,
                        verbose_name="Raw Request Body",
                    ),
                ),
                (
                    "remote_ip",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="Remote IP",
                    ),
                ),
                (
                    "odoo_timestamp",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Odoo Event Timestamp",
                    ),
                ),
                (
                    "received_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        verbose_name="Received At",
                    ),
                ),
            ],
            options={
                "db_table": "webhook_deliveries",
                "verbose_name": "Webhook Delivery",
                "verbose_name_plural": "Webhook Deliveries",
                "ordering": ["-received_at"],
                "indexes": [
                    models.Index(
                        fields=["event_type", "-received_at"],
                        name="wh_event_type_idx",
                    ),
                    models.Index(
                        fields=["status", "-received_at"],
                        name="wh_status_idx",
                    ),
                ],
            },
        ),
    ]
