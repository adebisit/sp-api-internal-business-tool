from django.contrib import admin
from .models import Order, OrderItem
from transaction.models import *

# Register your models here.


class OrderItemInline(admin.StackedInline):
    model = OrderItem




@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_id",
        "purchase_date",
        "order_status",
        "sales_channel"
    ]
    inline = (OrderItemInline,)



@admin.register(OrderItem)
class OrderItem(admin.ModelAdmin):
    list_display = [
        "order",
        "order_item_id",
        "item_status",
        "asin",
        "sku",
        "units",
        "price",
        "get_transaction"
    ]