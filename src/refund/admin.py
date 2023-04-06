from django.contrib import admin
from .models import Refund, RefundItem
# Register your models here.


class RefundItemInline(admin.TabularInline):
    model = RefundItem


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = [
        "order"
    ]

    inlines = (RefundItemInline,)


@admin.register(RefundItem)
class RefundItem(admin.ModelAdmin):
    list_display = [
        "get_order_id",
        "order_item",
        "asin",
        "return_date",
        "detailed_disposition",
        "quantity",
        "reason",
        "status",
        "lpn",
        "comment"
    ]

