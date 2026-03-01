from django.contrib import admin
from .models import AssetCategory, FixedAsset, DepreciationEntry

admin.site.register(AssetCategory)
admin.site.register(FixedAsset)
admin.site.register(DepreciationEntry)
