from django.db import models
from order.models import Order, OrderItem


REASON_CHOICES = (
    ("OTHER", 'Return option not available'),
    ("ORDERED_WRONG_ITEM", 'I accidentally ordered the wrong item'),
    ("FOUND_BETTER_PRICE", 'I found better prices elsewhere'),
    ("NO_REASON_GIVEN", 'No reason--I just don\'t want the product any more'),
    ("QUALITY_UNACCEPTABLE",
        'Product performance/quality is not up to my expectations'),
    ("NOT_COMPATIBLE", 'Product is not compatible with my existing system'),
    ("DAMAGED_BY_FC", 'Product became damaged/defective after arrival'),
    ("MISSED_ESTIMATED_DELIVERY",
        'Item took too long to arrive; I don\'t want it any more'),
    ("MISSING_PARTS", 'Shipment was missing items or accessories'),
    ("DAMAGED_BY_CARRIER", 'Product was damaged/defective on arrival'),
    ("SWITCHEROO", 'Amazon sent me the wrong item'),
    ("DEFECTIVE", 'Item is defective'),
    ("EXTRA_ITEM", 'Extra item included in shipment'),
    ("UNWANTED_ITEM", 'Unwanted Item'),
    ("WARRANTY", 'Item defective after arrival -- Warranty'),
    ("UNAUTHORIZED_PURCHASE", 'Unauthorized purchase -- i.e. fraud'),
    ("UNDELIVERABLE_INSUFFICIENT_ADDRESS",
        'Undeliverable; Insufficient address'),
    ("UNDELIVERABLE_FAILED_DELIVERY_ATTEMPTS",
        'Undeliverable; Failed delivery attempts'),
    ("UNDELIVERABLE_REFUSED", 'Undeliverable; Refused'),
    ("UNDELIVERABLE_UNKNOWN", 'Undeliverable; Unknown'),
    ("UNDELIVERABLE_UNCLAIMED", 'Undeliverable; Unclaimed'),
    ("APPAREL_TOO_SMALL", 'Apparel; Product was too small'),
    ("APPAREL_TOO_LARGE", 'Apparel; Product was too large'),
    ("APPAREL_STYLE", 'Apparel; Did not like style of garment'),
    ("MISORDERED", 'Ordered wrong style/size/color'),
    ("NOT_AS_DESCRIBED", 'Not as described on website'),
    ("JEWELRY_TOO_SMALL", 'Jewelry; Too small/short'),
    ("JEWELRY_TOO_LARGE", 'Jewelry; Too large/long'),
    ("JEWELRY_BATTERY", 'Jewelry; Battery is dead'),
    ("JEWELRY_NO_DOCS", 'Jewelry; Missing manual/warranty'),
    ("JEWELRY_BAD_CLASP", 'Jewelry; Broken or malfunctioning clasp'),
    ("JEWELRY_LOOSE_STONE", 'Jewelry; Missing or loose stone'),
    ("JEWELRY_NO_CERT", 'Jewelry; Missing promised certification')
)

DETAILED_DISPOSITION_CHOICES = (
    ("CARRIER_DAMAGED", 'Carrier Damaged'),
    ("CUSTOMER_DAMAGED", 'Customer Damaged'),
    ("DAMAGED", 'Damaged'),
    ("DEFECTIVE", 'Defective'),
    ("SELLABLE", 'Sellable'),
    ("EXPIRED", 'Expired')
)


class Refund(models.Model):
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    last_modified = models.DateTimeField(auto_now=True, null=True)

    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, related_name="refunds")
    return_status = models.CharField(max_length=255, blank=True)
    
    def get_transaction(self):
        net_transaction = self.commission + self.export_charge + self.gift_wrap + self.gift_wrap_charge_back + self.gift_wrap_tax + self.good_will + self.marketplace_principal_tax \
            + self.marketplace_restocking_fee_restocking + self.marketplace_shipping_tax + self.principal + self.promotion_amount + self.refund_commission + self.restocking_fee \
            + self.return_shipping + self.sales_tax_collection_fee + self.shipping_charge + \
            self.shipping_charge_back + self.shipping_tax + \
            self.tax + self.variable_closing_fee
        return net_transaction


class RefundItem(models.Model):
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    last_modified = models.DateTimeField(auto_now=True, null=True)
    
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, null=True, related_name="refund_items")
    return_date = models.DateTimeField()
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, null=True, related_name="refund_items")
    transaction_updated = models.BooleanField(default=False, null=True)
    sku = models.CharField(max_length=255)
    asin = models.CharField(max_length=255)
    fnsku = models.CharField(max_length=255, default="", blank=True)
    product_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(null=True)
    fulfillment_center_id = models.CharField(max_length=255, default="", blank=True)
    detailed_disposition = models.CharField(max_length=19, choices=DETAILED_DISPOSITION_CHOICES)

    reason = models.CharField(max_length=255, choices=REASON_CHOICES)
    lpn = models.CharField(max_length=255, blank=True, default=True)
    status = models.CharField(max_length=255)
    comment = models.TextField(blank=True)

    def get_order_id(self):
        return self.refund.order.order_id

    def get_loss(self):
        transactions = self.order_item.refundtransaction_set.all()
        total = 0
        for transaction in transactions:
            total += transaction.get_net_transaction()
        return float(total)

