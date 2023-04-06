from django.db import models
from django.core.exceptions import ObjectDoesNotExist


STATUS_CHOICES = (
    ("PendingAvailability", 'Pending Availability'),
    ("Pending", 'Pending'),
    ("Unshipped", 'Unshipped'),
    ("PartiallyShipped", 'Partially Shipped'),
    ("Shipped", 'Shipped'),
    ("InvoiceUnconfirmed", 'Invoice Unconfirmed'),
    ("Cancelled", 'Cancelled'),
    ("Unfulfillable", 'Unfulfillable'),
)


class Order(models.Model):
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    last_modified = models.DateTimeField(auto_now=True, null=True)

    order_id = models.CharField(max_length=255, unique=True)
    purchase_date = models.DateTimeField(null=True)
    order_status = models.CharField(max_length=19, choices=STATUS_CHOICES, default="Pending")

    sales_channel = models.CharField(max_length=19, default="Amazon.com")

    city = models.CharField(max_length=255, default="", blank=True)
    country = models.CharField(max_length=255, default="", blank=True)
    postal_code = models.CharField(max_length=255, default="", blank=True)
    state = models.CharField(max_length=255, default="", blank=True)
    is_business_order = models.BooleanField(null=True)
    amz_last_updated_date = models.DateTimeField(null=True)
    merchant_order_id = models.CharField(max_length=255, default="", blank=True)
    fufillment_channel = models.CharField(max_length=255, blank="", default="")

    def __str__(self):
        return self.order_id


class OrderItem(models.Model):
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    last_modified = models.DateTimeField(auto_now=True, null=True)
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_items")
    order_item_id = models.CharField(max_length=255, unique=True)
    item_status = models.CharField(max_length=19, choices=STATUS_CHOICES, null=True)
    sku = models.CharField(max_length=255)
    asin = models.CharField(max_length=255)
    product_name = models.CharField(max_length=255)
    units = models.PositiveIntegerField(default=0)
    price = models.FloatField(null=True)

    reviewed = models.BooleanField(null=True, default=None)

    def __str__(self):
        return self.order_item_id

    def is_updated(self, data):
        temp = self.__dict__
        temp["order"] = self.order

        for key in data:
            db = temp.get(key)
            data_v = data[key]
            if key == "units":
                try:
                    db = int(db)
                except TypeError:
                    db = None
                try:
                    data_v = int(data_v)
                except TypeError:
                    data_v = None

            elif key == "price":
                try:
                    db = float(db)
                except TypeError:
                    db = None
                try:
                    data_v = float(data_v)
                except TypeError:
                    data_v = None

            if db != data_v:
                return False
        return True

    def get_transaction(self):
        try:
            return self.transaction.get_net_transaction() if self.transaction else None
        except ObjectDoesNotExist:
            return None

    def get_profit(self):
        try:
            return self.transaction.get_profit()
        except ObjectDoesNotExist:
            return None

