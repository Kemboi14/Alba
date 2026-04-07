# Generated migration for Customer verification fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("loans", "0006_alter_customer_id_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="id_back_file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="kyc_documents/national_id_back/%Y/%m/%d/",
                verbose_name="National ID Back",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="additional_payslip_files",
            field=models.TextField(
                blank=True,
                default="[]",
                help_text="JSON list of uploaded payslip file paths",
                verbose_name="Additional Payslip File Paths",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="odoo_customer_id",
            field=models.IntegerField(
                blank=True,
                help_text="ID of the corresponding alba.customer record in Odoo",
                null=True,
                unique=True,
                verbose_name="Odoo Customer ID",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="verification_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("in_progress", "In Progress"),
                    ("verified", "Verified"),
                    ("rejected", "Rejected"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
                verbose_name="Verification Status",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="verification_results",
            field=models.TextField(
                blank=True,
                default="{}",
                help_text="Raw JSON output from the document verification wizard",
                verbose_name="Verification Results (JSON)",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="verification_confidence",
            field=models.IntegerField(
                default=0,
                help_text="0-100 confidence score from the document verification wizard",
                verbose_name="Verification Confidence Score",
            ),
        ),
    ]
