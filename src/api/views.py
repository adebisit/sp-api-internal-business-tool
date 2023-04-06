from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from transaction.models import *
from order.models import *
from refund.models import *
from . import serializers
from django.db.models import Q, F, Sum, Value, Case, When, BooleanField, CharField, ExpressionWrapper, OuterRef, Subquery, Min
from django.db.models.functions import Coalesce, Abs
from mws_handler import tasks as mws_tasks
from transaction import utils
from itertools import chain
from pprint import pprint
from datetime import datetime, timedelta
from pytz import timezone
import json
from dateutil.relativedelta import relativedelta


class GetOrdersData(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        orders = OrderItem.objects.all()

        # Filter for 3 months
        m3 = datetime.now(timezone("GMT")).replace(hour=0, minute=0, second=0) - relativedelta(months=3)
        orders = orders.filter(order__purchase_date__gte=m3)
        
        # Filter by Query Purchase From Date
        try:
            purchase_date_from = timezone("GMT").localize(datetime.fromtimestamp(float(request.GET.get("purchaseFromDate"))))
            orders = orders.filter(order__purchase_date__gte=purchase_date_from)
        except (ValueError, TypeError):
            pass
    
        try:
            purchase_date_to = timezone("GMT").localize(datetime.fromtimestamp(float(request.GET.get("purchaseToDate"))))
            orders = orders.filter(order__purchase_date__lte=purchase_date_to)
        except (ValueError, TypeError):
            pass
        
        # Filter by Last Updated Date
        try:
            last_updated = timezone("GMT").localize(datetime.fromtimestamp(float(request.GET.get("lastUpdated"))))
            orders = orders.filter(Q(created_date__gt=last_updated) | Q(last_modified__gt=last_updated))
        except (ValueError, TypeError):
            pass

        transactions = orders.filter(pk=OuterRef('pk')).annotate(
            per_fulfillment_unit_fee = utils.per_fulfillment_unit_fee,
            fees = Abs(utils.net_order_fees),
            net_transaction = utils.net_order_transaction,
        )
        orders = orders.annotate(
            purchase_date = F("order__purchase_date"),
            orderID = F("order__order_id"),
            order_status = F("order__order_status"),
            sales_channel = F("order__sales_channel"),
            city = F("order__city"),
            country = F("order__country"),
            postal_code = F("order__postal_code"),
            state = F("order__state"),
            is_business_order = F("order__is_business_order"),
            amz_last_updated_date = F("order__amz_last_updated_date"),
            merchant_order_id = F("order__merchant_order_id"),
            fufillment_channel=F("order__fufillment_channel"),
            item_asin = F("asin"),
            item_sku = F("sku"),
            per_fulfillment_unit_fee = Subquery(transactions.values("per_fulfillment_unit_fee")),
            fees = Subquery(transactions.values("fees")),
            net_transaction = Subquery(transactions.values("net_transaction"))
        )
        serializer = serializers.OrderSerializer(orders, many=True)
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)


class GetOrderData(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, order_item_id):
        try:
            order_item = OrderItem.objects.get(order_item_id=order_item_id)
        except ObjectDoesNotExist:
            return Response({"message": "Order Item ID does not exist"}, status=status.HTTP_404_NOT_FOUND)

        charges = TransactionCharge.objects.filter(transaction__order_item=order_item, transaction__transaction_type="Order")
        fees = charges.aggregate(fees=Sum('amount'))["fees"]
        per_fulfillment_unit_fee = charges.filter(charge_type="FBAPerUnitFulfillmentFee").aggregate(fee=Sum("amount"))["fee"]
        data = {
            "created_date": order_item.created_date.isoformat(),
            "last_modified": order_item.last_modified.isoformat(),
            "purchase_date": order_item.order.purchase_date.isoformat(),
            "orderID": order_item.order.order_id,
            "order_status": order_item.order.order_status,
            "sales_channel": order_item.order.sales_channel,
            "city": order_item.order.city,
            "country":  order_item.order.country,
            "postal_code":  order_item.order.postal_code,
            "state":  order_item.order.state,
            "is_business_order":  order_item.order.is_business_order,
            "amz_last_updated_date":  order_item.order.amz_last_updated_date,
            "merchant_order_id":  order_item.order.merchant_order_id,
            "fufillment_channel":  order_item.order.fufillment_channel,
            "item_asin": order_item.asin,
            "item_sku": order_item.sku,
            "item_status": order_item.item_status,
            "units": order_item.units,
            "price": order_item.price,
            "per_fulfillment_unit_fee": round(abs(per_fulfillment_unit_fee), 2) if per_fulfillment_unit_fee else 0,
            "fees": round(abs(fees), 2) if fees else 0,
            "net_transaction": round(order_item.price - (fees if fees else 0), 2) if order_item.price else None
        }
        return Response({"data": data}, status=status.HTTP_200_OK)


class GetRefundsData(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        cogs_included = ExpressionWrapper(
            Case(
                When(Q(item_status="Not Returned"), then=Value(True)),
                When(Q(item_status="Pending"), then=Value(None)),
                When(Q(item_condition="Sellable"), then=Value(False)),
                When(Q(item_condition="Reimbursed"), then=Value(True)),
                When(Q(item_condition="Unsellable"), then=Value(True)),
                default=Value(None),
            ),
            output_field=BooleanField()
        )

        refunds = RefundItem.objects.filter(pk=OuterRef('pk')).annotate(
            no_items_refunded = Sum("order_item__refund_items__quantity")
        )

        refund_items__transactions = RefundItem.objects.filter(pk=OuterRef('pk')).annotate(
            total_items_refunded = Subquery(refunds.values("no_items_refunded"))
        ).annotate(
            min_posted_date = Min(
                "order_item__transactions__charges__posted_date", filter=Q(order_item__transactions__transaction_type="Refund")
            ),
            net_refund_transaction = Coalesce(utils.order_item_net_refund, None)
        )
        
        refund_items = RefundItem.objects.annotate(
            item_sku = F("order_item__sku"),
            item_asin = F("order_item__asin"),
            posted_date = Subquery(refund_items__transactions.values("min_posted_date")),
            orderID = F("order_item__order__order_id"),
            order_itemID = F("order_item__order_item_id"),
            sales_channel = F("order_item__order__sales_channel"),
            no_returned_quantity = Sum("quantity"),
            net_transaction = Subquery(refund_items__transactions.values("net_refund_transaction")),
            item_status = Value("Returned"),
            item_condition = ExpressionWrapper(
                Case(
                    When(Q(detailed_disposition="SELLABLE"), then=Value("Sellable")),
                    When(Q(detailed_disposition__in=["DEFECTIVE", "CUSTOMER_DAMAGED", "EXPIRED"]), then=Value("Unsellable")),
                    When(Q(detailed_disposition__in=["DAMAGED", "CARRIER_DAMAGED"]), then=Value("Reimbursed")),
                    default=Value("")
                ),
                output_field=CharField()
            )
        ).annotate(
            cogs_included = cogs_included
        )

        l60 = datetime.now(timezone("GMT")).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=60)
        refunds = RefundItem.objects.all()

        refunded_transactions = Transaction.objects.filter(
            ~Q(order_item__in=refunds.values("order_item")),
            transaction_type="Refund"
        ).annotate(
            item_sku = F("order_item__sku"),
            item_asin = F("order_item__asin"),
            posted_date=Min("charges__posted_date", filter=Q(transaction_type="Refund")),
            return_date = Value(None, output_field=models.DateTimeField()),
            orderID = F("order_item__order__order_id"),
            order_itemID = F("order_item__order_item_id"),
            sales_channel = F("order_item__order__sales_channel"),
            product_name=F("order_item__product_name"),
            no_returned_quantity = F("quantity"),
            detailed_disposition = Value(None, output_field=models.CharField()),
            fnsku = Value(""),
            fulfillment_center_id = Value(""),
            status = Value(""),
            reason = Value(None, output_field=models.CharField()),
            lpn = Value(None, output_field=models.CharField()),
            comment = Value(None, output_field=models.CharField()),
            net_transaction = utils.net_refund,
            item_condition = Value("", output_field=models.CharField())
        ).annotate(
            item_status = ExpressionWrapper(
                Case(
                    When(Q(posted_date__lt=l60), then=Value("Not Returned")),
                    default=Value("Pending")
                ),
                output_field=CharField()
            ),
            cogs_included = cogs_included
        )

        refunds = chain(refund_items, refunded_transactions)
        serializer = serializers.RefundSerializer(refunds, many=True)

        return Response({"data": serializer.data}, status=status.HTTP_200_OK)


class AddToInventory(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        
        items = request.data["items"]
        context_items = []
        for sku, item_info in items.items():
            context_items.append({
                "sku": sku,
                "product_id": item_info["asin"],
                "product_id_type": "1",
                "price": item_info["price"],
                "item_condition": "11",
                "add_delete": "a",
                "fulfillment_center_id": "AMAZON_NA",
                "batteries_required": "FALSE",
                "supplier_declared_dg_hz_regulation1": "Not Applicable"
            })
            
        session_id = mws_tasks.create_feed(
            feed_type="POST_FLAT_FILE_INVLOADER_DATA",
            template_url="AmazonUtils/Flat.File.InventoryLoader.txt",
            context={"items": context_items}
        )

        return Response({"session_id": session_id}, status.HTTP_200_OK)


class GetEstimatedItemFees(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        asins = request.data.get("asins")
        print(type(asins))
        print(asins)
        fees = mws_tasks.get_fees_estimate_asin(asins)
        return Response(fees, status=status.HTTP_200_OK)


class GetListingDetails(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        asins = request.data.get("asins")
        print(type(asins))
        print(asins)
        listing = mws_tasks.get_listing_details(asins)
        return Response(listing, status=status.HTTP_200_OK)


class GetItemEligibility(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        asins = request.data.get("asins")
        print(type(asins))
        print(asins)
        listing = mws_tasks.get_item_eligibility(asins)
        return Response(listing, status=status.HTTP_200_OK)
