from django.db.models import F, Q, Case, When, FloatField, DateTimeField, ExpressionWrapper, DateField, Sum, Value
from django.db.models.functions import Abs


per_fulfillment_unit_fee = ExpressionWrapper(
    Case (
        When(~Q(units=0), then = Abs(Sum(
                "transactions__charges__amount",
                filter=Q(transactions__charges__charge_type="FBAPerUnitFulfillmentFee")
            ) / F("units")
        )),
        default=Value(0.0)
    ),
    output_field=FloatField()
)


net_order_fees = Sum(
    "transactions__charges__amount",
    filter=Q(transactions__transaction_type="Order") & ~Q(transactions__charges__charge_type="Principal")
)

net_order_transaction = F('price') + net_order_fees

order_item_net_refund = Sum(
    "order_item__transactions__charges__amount",
    filter= Q(order_item__transactions__transaction_type="Refund")
) / F("total_items_refunded")


net_refund = Sum("charges__amount", filter= Q(transaction_type="Refund"))

norm_net_refund = ExpressionWrapper(
    Case(
        When(Q(order_item__order__sales_channel="Non-Amazon"), then=None),
        When(Q(order_item__order__sales_channel="Amazon.com.mx"), then=net_refund * 0.0494),
        When(Q(order_item__order__sales_channel="Amazon.ca"), then=net_refund * 0.7881),
        default=net_refund
    ),
    output_field=FloatField()
)

per_net_refund = ExpressionWrapper(
    Case(
        When(Q(quantity=0), then = Value(None)),
        default = norm_net_refund / F("quantity")
    ),
    output_field=FloatField()
)