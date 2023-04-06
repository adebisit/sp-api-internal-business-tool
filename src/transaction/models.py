from django.db import models
from order.models import *
from refund.models import *

# Create your models here.
class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ('Order', "Order"),
        ('Refund', "Refund"),
        ("ServiceFee", "ServiceFee")
    )
    transaction_type = models.CharField(max_length=255, choices=TRANSACTION_TYPE_CHOICES)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="transactions")
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="transactions", null=True)
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    last_modified = models.DateTimeField(auto_now=True, null=True)
    quantity = models.PositiveIntegerField(default=None, null=True)

    fulfillment_unit_fee = models.FloatField(default=0)


class TransactionCharge(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="charges")
    posted_date = models.DateTimeField(null=True, default=None)
    charge_type = models.CharField(max_length=255)
    amount = models.FloatField(default=0)

