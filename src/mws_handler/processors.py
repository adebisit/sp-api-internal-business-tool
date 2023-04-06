from order.models import Order, OrderItem
from refund.models import Refund, RefundItem
from transaction import *
import xmltodict
from django.core.exceptions import ObjectDoesNotExist
from pytz import timezone
from datetime import datetime, timedelta
import boto3

s3_obj = boto3.client("s3")


def process_feed_result(feed_response):
    try:
        message_divide = feed_response.split("\n\n")

        message_divide = feed_response.split("\n\n")

        summary = message_divide[0]
        processed_message = summary.split("\n")[1]
        successful_message = summary.split("\n")[2]
        processed = int(processed_message.split("\t")[-1])
        successful = int(successful_message.split("\t")[-1])

        log = {
            "processed": processed,
            "successful": successful
        }
        return log
    except Exception:
        return False


def order_report_processor(data):
    parsed_report = xmltodict.parse(data)
    ordersXML = parsed_report.get("AmazonEnvelope", {}).get("Message", [])
    ordersXML = ordersXML if isinstance(ordersXML, list) else [ordersXML]

    new_orders_count = 0
    transaction_update_orders = []

    for orderXML in ordersXML:
        orderDict = orderXML.get("Order")
        order_id = orderDict.get("AmazonOrderID")
        fufillment_data = orderDict.get("FulfillmentData", [])
        fufillment_data = [fufillment_data] if isinstance(fufillment_data, dict) else fufillment_data
        
        fufillment_channel = city = country = postal_code = state = None
        if fufillment_data:
            fufillment_channel = fufillment_data[0].get("FulfillmentChannel", "")
            city = fufillment_data[0].get("Address", {}).get("City")
            country = fufillment_data[0].get("Address", {}).get("Country")
            postal_code = fufillment_data[0].get("Address", {}).get("PostalCode")
            state = fufillment_data[0].get("Address", {}).get("State")
        
        is_business_order = None
        if orderDict.get("IsBusinessOrder") == "true":
            is_business_order = True
        elif orderDict.get("IsBusinessOrder") == "false":
            is_business_order = False

        order_dict = {
            "order_id": order_id,
            "purchase_date": orderDict.get("PurchaseDate"),
            "order_status": orderDict.get("OrderStatus"),
            "sales_channel": orderDict.get("SalesChannel"),
            "is_business_order": is_business_order,
            "amz_last_updated_date": orderDict.get("LastUpdatedDate"),
            "merchant_order_id": orderDict.get("MerchantOrderID", ""),
            "fufillment_channel": fufillment_channel if fufillment_channel else "",
            "city": city if city else "",
            "country": country if country else "",
            "postal_code": postal_code if postal_code else "",
            "state": state if state else "",
            
        }
        orderItems = orderDict.get("OrderItem")
        orderItems = orderItems if isinstance(orderItems, list) else [orderItems]

        for orderItem in orderItems:
            itemID = orderItem.get("AmazonOrderItemCode")
            if itemID == "Removal_CODE":
                continue

            if itemID is None:
                print(f"{order_dict.get('order_id')} does not have an Item ID")
                continue

            price_components = orderItem.get("ItemPrice", {}).get("Component", {})
            price_components = price_components if isinstance(price_components, list) else [price_components]
            price = None
            for component in price_components:
                if component.get("Type", "") == "Principal":
                    price = component.get("Amount", {}).get("#text")
                    break
            try:
                order = Order.objects.get(order_id=order_id)
                Order.objects.filter(order_id=order_id).update(
                    last_modified=datetime.now(timezone("GMT")),
                    **order_dict
                )
            except ObjectDoesNotExist:
                order = Order(**order_dict)
                order.save()
            
            order_item_dict = {
                "order_item_id": itemID,
                "asin": orderItem.get("ASIN"),
                "item_status": orderItem.get("ItemStatus"),
                "product_name": orderItem.get("ProductName"),
                "units": orderItem.get("Quantity"),
                "price": price if price is None else float(price),
                "sku": orderItem.get("SKU"),
                "order": order
            }

            order_items = OrderItem.objects.filter(order_item_id=itemID)
            if order_items.count() == 0:
                OrderItem(**order_item_dict).save()
                new_orders_count += 1
            elif order_items.count() > 1:
                print(f"Error! ItemID duplicate => {itemID}")
                raise Exception("Order Item has more than one order_item_id")
            else:
                updated = order_items[0].is_updated(order_item_dict)
                # if not updated:
                order_items.update(
                    last_modified=datetime.now(timezone("GMT")),
                    **order_item_dict
                )

            order_item_dict["order"] = order.order_id

            transaction_update_orders.append(order_item_dict)

    print(f"New Orders = {new_orders_count}")
    print(f"Updated Orders = {len(transaction_update_orders)}")

    # delete all Orders from 182 days ago
    start_182 = datetime.now(timezone("GMT")) - timedelta(days=182)
    del_orders = Order.objects.filter(purchase_date__lte=start_182)
    print(f"No of Deleted Orders Before L182 = {del_orders.count()}")
    del_orders.delete()
    
    return transaction_update_orders


def refund_order_processor(report_str):
    cleaned_report = dict()
    rows = report_str.split("\n")
    del rows[0]

    for row in rows:
        if row != "":
            columns = row.split("\t")
            return_date = columns[0]
            order_id = columns[1]

            if order_id not in cleaned_report:
                cleaned_report[order_id] = list()
            sku = columns[2]
            asin = columns[3]
            fnsku =columns[4]
            product_name = columns[5]
            quantity = columns[6]
            fc_id = columns[7]
            detailed_disposition = columns[8]
            reason = columns[9]
            status = columns[10]
            lpn = columns[11]
            comment = columns[12]

            cleaned_report[order_id].append({
                "return_date": return_date,
                "sku": sku,
                "asin": asin,
                "fnsku": fnsku,
                "product_name": product_name,
                "quantity": quantity,
                "fulfillment_center_id": fc_id,
                "detailed_disposition": detailed_disposition,
                "reason": reason,
                "status": status,
                "lpn": lpn,
                "comment": comment,
            })

    new_refund_items_batch = []
    review = {}
    count = 0
    updated_orders_count = 0

    for order_id in cleaned_report:
        try:
            order = Order.objects.get(order_id=order_id)
        except ObjectDoesNotExist:
            continue

        count += 1
        try:
            refund = Refund.objects.get(order__order_id=order_id)
        except ObjectDoesNotExist:
            refund = Refund(order=order)
            refund.save()
        
        refund_dets = cleaned_report[order_id]
        refund_items = refund.refund_items.all()
        if refund_items.count() == 0:
            exempted = {}
            for refund_det in refund_dets:
                asin = refund_det.get("asin")
                order_items = OrderItem.objects.filter(order__order_id=order_id, asin=asin, item_status="Shipped")
                # print(f"Print Order Items Count = {order_items.count()}")
                available_order_items = []
                for order_item in order_items:
                    order_item_id = order_item.order_item_id
                    if int(exempted.get(order_item_id, "0")) < order_item.units:
                        exempted[order_item_id] = int(exempted.get(order_item_id, "0")) + int(refund_det.get("quantity"))
                        available_order_items.append(order_item)
                        break
                try:
                    order_item = available_order_items[-1]
                except Exception:
                    print(order_id)
                    raise Exception("Error!")
                refund_det["order_item"] = order_item
                refund_det["refund"] = refund
                new_refund_items_batch.append(RefundItem(**refund_det))
        elif refund_items.count() != len(refund_dets):
            if order_id not in review:
                review[order_id] = []
            review[order_id].append("Inconsistency with MWS and DB")
            continue
        else:
            for refund_det, refund_item in zip(refund_dets, refund_items):
                refund_item.__dict__.update(
                    last_modified=datetime.now(timezone("GMT")),
                    **refund_det
                )
                refund_item.save()
                updated_orders_count += 1

    print(f"Number of New Refund Orders = {str(len(new_refund_items_batch))}")
    print(f"Number of Updated Refund Orders = {updated_orders_count}")
    RefundItem.objects.bulk_create(new_refund_items_batch)

    # delete all refunds from 80 days ago
    start_182 = datetime.now(timezone("GMT")) - timedelta(days=182)
    del_refunds = Refund.objects.filter(refund_items__return_date__lte=start_182)
    print(f"No of Deleted Refunds Before L182 = {del_refunds.count()}")
    del_refunds.delete()
    return cleaned_report
