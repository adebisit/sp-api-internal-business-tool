from .models import *
from django.db.models import Sum, Q


def update():
    transactions = Transaction.objects.filter(transaction_type="Order")

    for transaction in transactions:
        fulfillment_unit_fee = transaction.charges.aggregate(
            fulfillment_unit_fee=Sum("amount", filter=Q(charge_type="FBAPerUnitFulfillmentFee"))
        )["fulfillment_unit_fee"]
        if fulfillment_unit_fee is None:
            row = [
                transaction.transaction_type,
                transaction.order.order_id,
                transaction.order_item.order_item_id,
                transaction.order_item.item_status,
                str(transaction.order_item.units),
                str(transaction.order_item.price)
            ]
            print("\t".join(row))
        else:
            transaction.fulfillment_unit_fee = fulfillment_unit_fee
            transaction.save()