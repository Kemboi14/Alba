"""
Assets Models: Fixed asset management with depreciation
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from apps.core.models import User


class AssetCategory(models.Model):
    """Asset categories"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    default_useful_life_years = models.IntegerField(help_text='Default useful life in years')
    depreciation_method = models.CharField(
        max_length=20,
        choices=[('STRAIGHT_LINE', 'Straight Line'), ('REDUCING_BALANCE', 'Reducing Balance')],
        default='STRAIGHT_LINE'
    )
    
    class Meta:
        db_table = 'assets_categories'
        verbose_name = 'Asset Category'
        verbose_name_plural = 'Asset Categories'
    
    def __str__(self):
        return self.name


class FixedAsset(models.Model):
    """Fixed assets register"""
    asset_number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name='assets')
    
    # Purchase Information
    purchase_date = models.DateField()
    purchase_cost = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    supplier = models.CharField(max_length=200, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    
    # Depreciation
    depreciation_method = models.CharField(max_length=20)
    useful_life_years = models.IntegerField()
    salvage_value = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    
    accumulated_depreciation = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    book_value = models.DecimalField(max_digits=20, decimal_places=2)
    
    # Location and Assignment
    location = models.CharField(max_length=200)
    department = models.CharField(max_length=100, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_assets')
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=[
            ('ACTIVE', 'Active'),
            ('DISPOSED', 'Disposed'),
            ('FULLY_DEPRECIATED', 'Fully Depreciated'),
        ],
        default='ACTIVE'
    )
    
    # Disposal
    disposal_date = models.DateField(null=True, blank=True)
    disposal_value = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    disposal_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_assets')
    
    class Meta:
        db_table = 'assets_fixed_assets'
        verbose_name = 'Fixed Asset'
        verbose_name_plural = 'Fixed Assets'
        ordering = ['-purchase_date']
    
    def __str__(self):
        return f"{self.asset_number} - {self.name}"


class DepreciationEntry(models.Model):
    """Monthly depreciation entries"""
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name='depreciation_entries')
    period = models.DateField(help_text='Month of depreciation')
    depreciation_amount = models.DecimalField(max_digits=20, decimal_places=2)
    accumulated_depreciation = models.DecimalField(max_digits=20, decimal_places=2)
    book_value = models.DecimalField(max_digits=20, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    
    class Meta:
        db_table = 'assets_depreciation_entries'
        verbose_name = 'Depreciation Entry'
        verbose_name_plural = 'Depreciation Entries'
        unique_together = ['asset', 'period']
        ordering = ['-period']
    
    def __str__(self):
        return f"{self.asset.asset_number} - {self.period}"
