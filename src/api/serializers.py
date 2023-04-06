from rest_framework import serializers
from order.models import *
from refund.models import *
from transaction.models import *


class OrderSerializer(serializers.ModelSerializer):
    purchase_date = serializers.DateTimeField()
    orderID = serializers.CharField()
    order_status = serializers.CharField()
    sales_channel = serializers.CharField()
    city = serializers.CharField()
    country = serializers.CharField()
    postal_code = serializers.CharField()
    state = serializers.CharField()
    is_business_order = serializers.BooleanField()
    amz_last_updated_date = serializers.DateTimeField()
    merchant_order_id = serializers.CharField()
    fufillment_channel = serializers.CharField()
    item_asin = serializers.CharField()
    item_sku = serializers.CharField()
    per_fulfillment_unit_fee = serializers.FloatField()
    fees = serializers.FloatField()
    net_transaction = serializers.FloatField()

    class Meta:
        model = OrderItem
        fields = [
            "created_date",
            "last_modified",
            "purchase_date",
            "orderID",
            "order_status",
            "sales_channel",
            "city",
            "country",
            "postal_code",
            "state",
            "is_business_order",
            "amz_last_updated_date",
            "merchant_order_id",
            "fufillment_channel",
            "order_item_id",
            "item_asin",
            "item_sku",
            "item_status",
            "units",
            "price",
            "per_fulfillment_unit_fee",
            "fees",
            "net_transaction"
        ]


class RefundSerializer(serializers.Serializer):
    item_sku = serializers.CharField()
    item_asin = serializers.CharField()
    posted_date = serializers.DateTimeField()
    return_date = serializers.DateTimeField()
    orderID = serializers.CharField()
    order_itemID = serializers.CharField()
    sales_channel = serializers.CharField()
    product_name = serializers.CharField()
    no_returned_quantity = serializers.IntegerField()
    detailed_disposition = serializers.CharField()
    fnsku = serializers.CharField()
    fulfillment_center_id = serializers.CharField()
    status = serializers.CharField()
    reason = serializers.CharField()
    lpn = serializers.CharField()
    comment = serializers.CharField()
    quantity = serializers.IntegerField()
    net_transaction = serializers.FloatField()
    item_status = serializers.CharField()
    item_condition = serializers.CharField()
    cogs_included = serializers.BooleanField()
