from sp_api.api import ReportsV2, FeedsV2, ProductFees, CatalogItems, Catalog, Finances, Products, FbaInboundEligibility
from sp_api.base import ReportType, FeedType
from sp_api.base.exceptions import SellingApiBadRequestException, SellingApiRequestThrottledException
import sp_api

from io import StringIO
from AmazonApp.celery_app import app
from django_celery_beat.models import PeriodicTask
from mws_handler.processors import *

from .models import ScriptSession
from order.models import *
from transaction.models import *
from refund.models import *

from django.core.cache import cache
import redis

import time
from datetime import datetime, timedelta
from pytz import timezone
from dateutil.parser import parse

from django.template.loader import render_to_string
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import IntegrityError
from django.db.models import Q

from contextlib import contextmanager
import json
import boto3
from pprint import pprint
import traceback
import csv
from dateutil.relativedelta import relativedelta

import boto3
s3 = boto3.client("s3")


refresh_token = settings.REFRESH_TOKEN
lwa_app_id = settings.LWA_APP_ID
lwa_client_secret = settings.LWA_CLIENT_SECRET
aws_access_key = settings.AWS_ACCESS_KEY
aws_secret_key = settings.AWS_SECRET_KEY
role_arn = settings.ROLE_ARN

credentials = dict(
    refresh_token=refresh_token,
    lwa_app_id=lwa_app_id,
    lwa_client_secret=lwa_client_secret,
    aws_access_key=aws_access_key,
    aws_secret_key=aws_secret_key,
    role_arn=role_arn
)

reportsAPI = ReportsV2(credentials=credentials)
financesAPI = Finances(credentials=credentials)
feedsAPI = FeedsV2(credentials=credentials)
productFeesAPI = ProductFees(credentials=credentials)
productsAPI = Products(credentials=credentials)
catalogAPI = Catalog(credentials=credentials)
catalogItemAPI = CatalogItems(credentials=credentials)
inboundEligibilityAPI = FbaInboundEligibility(credentials=credentials)

redis_client = redis.Redis(host=settings.REDIS_HOST, port=6379)


utc = timezone("UTC")


@contextmanager
def redis_lock(lock_name):
    lock = redis_client.lock(lock_name, timeout=1200)
    try:
        have_lock = lock.acquire(blocking=False)
        yield have_lock
    finally:
        if have_lock:
            lock.release()


def create_feed(feed_type, template_url, context):
    message = render_to_string(template_url, context=context)
    session_id = add_new_feed_process_queue(
        feed_type=feed_type,
        feed=message,
        content_type="text/tsv",
        context=context
    )

    print("[DEBUG] add_new_feed_process_queue called")
    return session_id


def add_new_feed_process_queue(**kwargs):
    process_name = kwargs["feed_type"].replace("_", " ").strip() 
    script_session = ScriptSession(
        process_name = process_name,
        user_enabled=True
    )
    
    script_session.save()
    session_id = str(script_session.session_id)
    print(f"[DEBUG] New Session ({session_id}, {script_session.process_name}) Created")

    default_profile = {
        "timeline": {
            "sent": datetime.now(utc),
            "start": None,
            "end": None
        },
        "args": kwargs,
        "active": False,
        "error": None,
        "sp_api_info": {
            "feed_id": None,
            "result_feed_document_id": None,
            "processing_status": None
        },
        "result": None
    }
    update_feed_request({session_id: default_profile})

    context = kwargs.get("context", {})
    print(context)
    items = context.get("items", [])
    plan_name = None
    print(kwargs["feed_type"])
    if kwargs["feed_type"] == "POST_FLAT_FILE_FBA_CREATE_INBOUND_PLAN":
        records = [item["seller_sku"] for item in items]
        plan_name = context.get("plan_name")
    elif kwargs["feed_type"] == "POST_FLAT_FILE_INVLOADER_DATA":
        records = [item["product_id"] for item in items]

    event = script_session.create_event(
        title=f"{process_name}",
        description="The process " + (f"({plan_name}) " if plan_name else "") + "has been queued on the Server."
    )
    notification = event.create_notification()
    notification.send(records=records)

    print("[DEBUG] State 1 of feed_request_queue written to file")
    return session_id


@app.task
def check_for_new_feed():
    with redis_lock("feed_queue_lock") as acquired:
        if acquired is True:
            # feed_request_queue = get_cache_key("feed_request_queue", "feed_queue_lock", {})
            feed_request_queue = cache.get("feed_request_queue")
            if feed_request_queue is None:
                return
            profiles = list(filter(lambda x: x[1]["active"] is False and (x[1]["error"] is None and x[1].get("result") is None), feed_request_queue.items()))
            if profiles:
                submit_feed.delay(session_id=profiles[0][0], profile=profiles[0][1])
                print(f"[DEBUG] Celery task for Submit Feed created for Session ({profiles[0][0]})")

            active_profiles = list(filter(lambda x: x[1]["sp_api_info"]["feed_id"] and x[1]["active"] and x[1]["sp_api_info"]["processing_status"] in ["IN_QUEUE", "IN_PROGRESS"], feed_request_queue.items()))
            if active_profiles:
                get_feed_list.delay(session_id=active_profiles[0][0], profile=active_profiles[0][1])
                print(f"[DEBUG] Celery task for Get Feed List created for {len(active_profiles)} profiles")

            valid_profiles = list(filter(lambda x: x[1]["sp_api_info"]["result_feed_document_id"] and x[1]["sp_api_info"]["processing_status"] == "DONE" and x[1]["active"], feed_request_queue.items()))
            if valid_profiles:
                get_feed_result.delay(session_id=valid_profiles[0][0], profile=valid_profiles[0][1])
                print(f"[DEBUG] Celery task for Get Feed Result created for Session ({valid_profiles[0][0]}) profiles")


@app.task
def submit_feed(session_id, profile):
    with redis_lock('feed_request') as acquired:
        if acquired is False:
            print("Submit Feed is running")
        if acquired is True:
            error = None
            script_session = ScriptSession.objects.get(session_id=session_id)
            script_session.status = "active"
            script_session.save()
            event = script_session.create_event(
                title="Process Started",
                description="The Request has been passed to Amazon SP-API. It might take some time before the next update."
            )
            notification = event.create_notification()
            notification.send()
            try: 
                feed_type = FeedType(profile["args"]["feed_type"])
                feed = StringIO()
                feed.write(profile["args"]["feed"])
                feed.seek(0)
                profile["timeline"]["start"] = datetime.now(utc)
                res = feedsAPI.submit_feed(feed_type, feed)
                time.sleep(120) 

                if res[1].errors:
                    error = res[1].errors
                else:
                    feed_id = res[1].payload.get("feedId")

                    print(f"Feed ID {feed_id}")
                    profile["active"] = True
                    profile["sp_api_info"]["feed_id"] = feed_id
                    profile["sp_api_info"]["processing_status"] = "IN_QUEUE"
                    event = script_session.create_event(
                        title="Feed ID Collected",
                        description=f"Feed ID {feed_id} collected for the process"
                    )
            except Exception as e:
                error = {
                    "title": type(e),
                    "message": str(e)
                }
            finally:
                if error:
                    event = script_session.create_event(
                        title="Error Getting Feed ID",
                        description=f"The script experienced either an internal error or an SP-API Error. Please review"
                    )
                    script_session.status = "error"
                    profile["error"] = error
                    profile["active"] = False
                    profile["timeline"]["end"] = datetime.now(utc)
                notification = event.create_notification()
                notification.send()
                script_session.save()
                update_feed_request({session_id: profile})


@app.task
def get_feed_list(session_id, profile):
    with redis_lock('feed_list') as acquired:
        if acquired is False:
            print("Get Feed List is running")
        if acquired is True:
            try:
                error = None
                event = None
                feed_id = profile["sp_api_info"]["feed_id"]
                script_session = ScriptSession.objects.get(session_id=session_id)
                print(f"Get Feed List Running, FeedID: {feed_id}")
                resp = feedsAPI.get_feed(feedId=feed_id)
                time.sleep(2)
                print(resp.payload)
                if resp.errors:
                    error = resp.errors
                else:
                    processing_status = resp.payload["processingStatus"]
                    result_feed_document_id = resp.payload.get("resultFeedDocumentId")
                    profile["sp_api_info"]["result_feed_document_id"] = result_feed_document_id
                    profile["sp_api_info"]["processing_status"] = processing_status
                    if processing_status not in ["IN_QUEUE", "IN_PROGRESS"]:
                        active = processing_status == "DONE"
                        script_session.status = "active" if active else "completed"
                        profile["active"] = active
                        event = script_session.create_event(title=f"FEED Status => {processing_status}")
            except Exception as e:
                print(str(e))
                print(type(e))
                profile["active"] = False
                error = {
                    "title": type(e),
                    "message": str(e)
                }
            finally:
                if error:
                    event = script_session.create_event(
                        title="Error Getting Feed ID",
                        description=f"The script experienced either an internal error or an SP-API Error. Please review"
                    )
                    script_session.status = "error"
                    profile["error"] = error
                    profile["active"] = False
                    profile["timeline"]["end"] = datetime.now(utc)
                if event:
                    notification = event.create_notification()
                    notification.send()
                script_session.save()
                
                update_feed_request({session_id: profile})


@app.task
def get_feed_result(session_id, profile):
    with redis_lock('feed_result') as acquired:
        if acquired is False:
            print("Get Feed Result is running")
        if acquired is True:
            script_session = ScriptSession.objects.get(session_id=session_id)
            result_feed_document_id = profile["sp_api_info"]["result_feed_document_id"]
            
            feed_response = feedsAPI.get_feed_result_document(result_feed_document_id)
            time.sleep(45)
            profile["result"] = feed_response
            profile["active"] = False

            data = process_feed_result(feed_response=feed_response)
            if data:
                description = "Feed Response is collected and data processed.\nSummary:\n\n"
                description += f"Number of Items Processed = {data['processed']}\n"
                description += f"Number of Items Successful = {data['successful']}"
            else:
                description = "Feed Response couldnt be analysed properly. Below is the Raw response from SP-API."

            
            event = script_session.create_event(
                title="Feed Response Collected and Processed",
                description=description
            )
            notification = event.create_notification()
            notification.send()

            if not data or (data['processed'] != data['successful']):
                notification.upload_file(feed_response)

            script_session.status="completed"
            script_session.save()

            profile["timeline"]["end"] = datetime.now(utc)
            update_feed_request({session_id: profile})


def to_redis():
    data = get_cache_key("feed_request_queue", "feed_queue_lock")
    for session_id in data:
        data[session_id]["args"]["feed"] = str(data[session_id]["args"]["feed"])
        error = data[session_id]["error"]
        if error is not None:
            data[session_id]["error"]["title"] = str(error.get("title", ""))


def get_cache_key(key, lock, default=None):
    while True:
        with redis_lock(lock) as acquired:
            if acquired is True:
                return cache.get(key, default)


def update_feed_request(values):
    while True:
        with redis_lock('feed_queue_lock') as acquired:
            if acquired is True:
                feed_request_queue = cache.get("feed_request_queue", {})

                for session_id in values:
                    feed_request_queue[session_id] = values[session_id]
                
                cache.set("feed_request_queue", feed_request_queue)
                cache.persist("feed_request_queue")
                return True


# Reports (Inventory, Refunds, Orders)
def testReport():
    reports = [
        {"report_type": "GET_MERCHANT_LISTINGS_DATA", "scheduled": True},
        {"report_type": "GET_MERCHANT_LISTINGS_INACTIVE_DATA", "scheduled": True},
        {"report_type": "GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA", "scheduled": True},
        {"report_type": "GET_RESTOCK_INVENTORY_RECOMMENDATIONS_REPORT", "scheduled": True},
        {
            "report_type": "GET_FBA_INVENTORY_PLANNING_DATA",
            "dataStartTime": datetime(2022, 1, 1, tzinfo=utc),
            "dataEndTime": datetime(2022, 12, 30, tzinfo=utc),
            "scheduled": False
        }
    ]

    for report in reports:
        add_new_report_queue(**report)

    print("[DEBUG] test Report called")


def add_new_report_queue(**kwargs):
    process_name = kwargs["report_type"].replace("_", " ").strip()
    script_session = ScriptSession(
        process_name=process_name
    )
    script_session.save()
    session_id = str(script_session.session_id)
    print(f"[DEBUG] New Session ({session_id}, {script_session.process_name}) Created")

    default_profile = {
        "timeline": {
            "sent": datetime.now(utc),
            "start": None,
            "end": None
        },
        "args": kwargs,
        "scheduled": kwargs.get("scheduled", False),
        "active": False,
        "error": None,
        "sp_api_info": {
            "report_id": None,
            "report_document_id": None,
            "processing_status": None
        },
        "response": None
    }
    update_report_request({session_id: default_profile})

    script_session.create_event(
        title=process_name,
        description=f"The process has been queued on our server"
    )

    print("[DEBUG] State 1 of report queue written to file")


@app.task
def check_for_new_report():
    with redis_lock("report_queue_lock") as acquired:
        if acquired is True:
            report_queue = cache.get("report_queue")
            if report_queue is None:
                return
            
            requesting_profiles = list(
                filter(
                    lambda x: x[1]["active"] is False and x[1]["error"] is None and x[1]["sp_api_info"]["report_id"] is None,
                    report_queue.items()
                )
            )
            if requesting_profiles:
                request_report.delay(session_id=requesting_profiles[0][0], profile=requesting_profiles[0][1])
                print(f"[DEBUG] Celery task for Request Report created for Session ({requesting_profiles[0][0]})")

            processing_profiles = list(
                filter(
                    lambda x: x[1]["sp_api_info"]["report_id"] and x[1]["active"] and x[1]["sp_api_info"]["processing_status"] in ["IN_QUEUE", "IN_PROGRESS"],
                    report_queue.items()
                )
            )
            if processing_profiles:
                get_report_request_list.delay(session_id=processing_profiles[0][0], profile=processing_profiles[0][1])
                print(f"[DEBUG] Celery task for Get Report Request List created for {len(processing_profiles)} profiles")

            completed_profiles = list(
                filter(
                    lambda x: x[1]["sp_api_info"]["report_document_id"] and x[1]["response"] is None,
                    report_queue.items()
                )
            )
            if completed_profiles:
                get_report_result.delay(session_id=completed_profiles[0][0], profile=completed_profiles[0][1])
                print(f"[DEBUG] Celery task for Get Report Result created for Session ({completed_profiles[0][0]}) profiles")


@app.task
def request_report(session_id, profile):
    print("Request Report function called")
    with redis_lock('report_request') as acquired:
        print(f'Acquired = {acquired}')
        if acquired is False:
            print("Cant Run Report Request Function. Currently Unavailable")
        if acquired is True:
            print("Running Report Request")
            error = None
            script_session = ScriptSession.objects.get(session_id=session_id)
            script_session.status = "active"
            script_session.save()

            response = None
            try:
                profile["timeline"]["start"] = datetime.now(utc)
                response = reportsAPI.create_report(
                    reportType=ReportType(profile["args"]["report_type"]),
                    dataStartTime=profile["args"].get("dataStartTime"),
                    dataEndTime=profile["args"].get("dataEndTime")
                )
                time.sleep(80)
                if response.errors:
                    error = response.error
                else:
                    report_id = response.payload["reportId"]

                    print(f"Request ID: {report_id}")
                    profile["active"] = True
                    profile["sp_api_info"]["report_id"] = report_id
                    profile["sp_api_info"]["processing_status"] = "IN_QUEUE"
                    event = script_session.create_event(
                        title="Report Request Collected",
                        description=f"Request ID {report_id} collected for the process"
                    )
            except sp_api.base.exceptions.SellingApiRequestThrottledException as e:
                event = script_session.create_event(
                    title="Request API Throttled",
                    description=f"Request Report API throttled. "
                )
                script_session.status = "error"
                notification = event.create_notification()
                notification.send()
            except Exception as e:
                print(str(type(e)))
                print(str(e))
                error = {
                    "title": str(type(e)),
                    "message": str(e)
                }
                event = script_session.create_event(
                        title="Error Getting Request ID",
                        description=f"The script experienced either an internal error or an SP-API Error. Please review"
                    )
                script_session.status = "error"
                notification = event.create_notification()
                notification.send()
            finally:
                if error:
                    profile["active"] = False
                    profile["error"] = error
                    profile["timeline"]["end"] = datetime.now(utc)
                script_session.save()
                update_report_request({session_id: profile})
    print("Request Report function finished")


@app.task
def get_report_request_list(session_id, profile):
    print("Report List function called")
    with redis_lock('report_list') as acquired:
        print(f'Acquired = {acquired}')
        if acquired is False:
            print("Cant run Get Report Request List; Unavailable")
        if acquired is True:
            print("Running Get Report Request List")
            script_session = ScriptSession.objects.get(session_id=session_id)
            event = None
            try:
                error = None
                report_id = profile["sp_api_info"]["report_id"]
                print(f"Get Report Request List Running, Request ID: {report_id}")

                time.sleep(2)
                response = reportsAPI.get_report(reportId=report_id)
                if response.errors:
                    error = response.errors
                else:
                    print(response.payload)
                    processing_status = response.payload["processingStatus"]
                    report_document_id = response.payload.get("reportDocumentId")
                    profile["sp_api_info"]["report_document_id"] = report_document_id
                    profile["sp_api_info"]["processing_status"] = processing_status

                    print(processing_status)
                    print(profile.get("scheduled"))
                    if processing_status == "FATAL" and profile.get("scheduled", False):
                        response = reportsAPI.get_reports(
                            reportTypes=[profile["args"]["report_type"]],
                            processingStatuses=["DONE"]
                        )
                        time.sleep(45)
                        reports = response.payload["reports"]
                        if reports:
                            report_id = reports[0]["reportId"]
                            report_document_id = reports[0]["reportDocumentId"]
                            processing_status = reports[0]["processingStatus"]
                            profile["sp_api_info"]["report_id"] = report_id
                            profile["sp_api_info"]["report_document_id"] = report_document_id
                            profile["sp_api_info"]["processing_status"] = processing_status
                            print("FATAL Report Back Up")
                            print(reports[0])
                        else:
                            profile["sp_api_info"]["processing_status"] = processing_status
                    elif processing_status not in ["IN_QUEUE", "IN_PROGRESS"]:
                        active = processing_status == "DONE"
                        script_session.status = "active" if active else "completed"
                        profile["active"] = active
                    
                        event = script_session.create_event(
                            title=f"Report Status = {processing_status}",
                            description=f"Report Document ID for {report_id} collected => {report_document_id}"
                        )
            except Exception as e:
                print(str(type(e)))
                print(str(e))
                error = {
                    "title": str(type(e)),
                    "message": str(e)
                }
            finally:
                if error:
                    profile["active"] = False
                    profile["error"] = error
                    profile["timeline"]["end"] = datetime.now(utc)
                    event = script_session.create_event(
                        title="Error Getting Report Document ID",
                        description=f"The script experienced either an internal error or an SP-API Error. Please review"
                    )
                    script_session.status = "error"
                    if event:
                        notification = event.create_notification()
                        notification.send()
                script_session.save()
                update_report_request({session_id: profile})
    print("Get Report List function finished")


@app.task
def get_report_result(session_id, profile):
    print("Report Result function called")
    with redis_lock('report_result') as acquired:
        print(f'Acquired = {acquired}')
        if acquired is False:
            print("Cant run Get Report Result; Unavailable")
        if acquired is True:
            print("Running Report Result")
            error = None
            report_document_id = profile["sp_api_info"]["report_document_id"]
            script_session = ScriptSession.objects.get(session_id=session_id)
            
            try:
                report = StringIO()
                response = reportsAPI.get_report_document(report_document_id, file=report)
                time.sleep(60)
                if response.errors:
                    error = response.errors
                else:
                    dataRaw = report.read()
                    
                    if profile["args"]["report_type"] == "GET_XML_ALL_ORDERS_DATA_BY_LAST_UPDATE_GENERAL":
                        data = order_report_processor(dataRaw)
                    elif profile["args"]["report_type"] == "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA":
                        data = refund_order_processor(dataRaw)
                    else:
                        data = dataRaw
                    profile["response"] = data
                    # profile = None
                    event = script_session.create_event(
                        title="Data Collected & Processed",
                        description="The Report Data for is now stored in the cache.\nPlease note it might be some time before it reflects in the inventory page"
                    )
                    script_session.status="completed"
            except Exception as e:
                tb = traceback.format_exc()
                line = tb.splitlines()[-3]
                print(f"An error occurred on line {line}")
                print(tb)
                error = {
                    "title": str(type(e)),
                    "message": str(e)
                }
            finally:
                if error:
                    profile["error"] = error
                    event = script_session.create_event(
                        title="Error Getting Report Result",
                        description=f"The script experienced either an internal error or an SP-API Error. Please review"
                    )
                    script_session.status = "error"
                    notification = event.create_notification()
                    notification.send()
                
                profile["timeline"]["end"] = datetime.now(utc)
                profile["active"] = False
                script_session.save()
                update_report_request({session_id: profile})
    print("Report Result Finished")         


def update_report_request(values):
    while True:
        with redis_lock('report_queue_lock') as acquired:
            if acquired is True:
                report_queue = cache.get("report_queue", {})

                for session_id in values:
                    report_queue[session_id] = values[session_id]
                
                cache.set("report_queue", report_queue)
                cache.persist("report_queue")
                return True


@app.task
def get_inventory_reports(report_type, scheduled):
    args = {
        "report_type": report_type,
        "scheduled": scheduled
    }
    if not scheduled:
        now = datetime.now()
        args["dataStartTime"] = now - timedelta(days=1)
        args["dataEndTime"] = now

    add_new_report_queue(**args)

    print("[DEBUG] get_inventory_reports called")


@app.task
def get_orders():
    fmt = "%d %b %Y, %H:%M:%S"
    end = datetime.now(utc)
    start = end - timedelta(days=2)

    print(f"Start Time: {start.strftime(fmt)}")
    print(f"End Date: {end.strftime(fmt)}\n")
    add_new_report_queue(
        report_type = "GET_XML_ALL_ORDERS_DATA_BY_LAST_UPDATE_GENERAL",
        dataStartTime = start,
        dataEndTime =  end
    )


@app.task
def get_returns():
    fmt = "%d %b %Y, %H:%M:%S"
    end = datetime.now(utc)
    start_utc = end - timedelta(days=6)
    
    print(f"Start Time: {start_utc.strftime(fmt)}")
    print(f"End Date: {end.strftime(fmt)}")

    add_new_report_queue(
        report_type = "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA",
        dataStartTime = start_utc,
        dataEndTime = end
    )



def get_fees_estimate_asin(asins):
    fees = {}
    for asin in asins:
        price = asins[asin]
        response = productFeesAPI.get_product_fees_estimate_for_asin(asin=asin, price=price, is_fba=True)
        time.sleep(0.3)

        fees_estimate_result = response.payload["FeesEstimateResult"]

        if isinstance(fees_estimate_result, dict):
            fees_estimate_result = [fees_estimate_result]

        for fee_est_result in fees_estimate_result:
            id_value = fee_est_result["FeesEstimateIdentifier"]["IdValue"]
            if fee_est_result["Status"] == "Success":
                fees[id_value] = {
                    "total": fee_est_result["FeesEstimate"]["TotalFeesEstimate"]["Amount"],
                    "others": 0
                }
                fee_details = fee_est_result["FeesEstimate"]["FeeDetailList"]
                for fee_detail in fee_details:
                    fee_type = fee_detail["FeeType"]
                    fee_amount = fee_detail["FinalFee"]["Amount"]
                    if fee_type not in ["ReferralFee", "FBAFees"]:
                        fees[id_value]["others"] += fee_amount
                    else:
                        fees[id_value][fee_type] = fee_amount
            else:
                fees[id_value] = None
    return fees


def get_listing_details(asins):
    items_data = dict()

    for asin in asins:
        try:
            response = catalogAPI.get_item(asin=asin, MarketplaceId="ATVPDKIKX0DER")
        except SellingApiBadRequestException:
            items_data[asin] = None
            continue
        time.sleep(0.5)
        attributes = response.payload.get("AttributeSets", {})
        if len(attributes) > 1:
            raise Exception()
        attribute = attributes[0] if isinstance(attributes, list) else attributes
        package_dimension = attribute.get("PackageDimensions")
        if not package_dimension:
            items_data[asin] = None
            continue
        height = package_dimension["Height"]["value"]
        length = package_dimension["Length"]["value"]
        width = package_dimension["Width"]["value"]
        weight = package_dimension["Weight"]["value"]
        volume = (height * length * width) / (12 * 12 * 12)

        product_tier = getProductTier(length=length, width=width, height=height, weight=weight)
        if 0 <= datetime.now(utc).month <= 9:
            monthly_storage = volume * (0.83 if product_tier == "standard-size" else 0.53)
        else:
            monthly_storage = volume * (2.40 if product_tier == "standard-size" else 1.20)

        items_data[asin] = {
            "product_tier": product_tier,
            "monthly_storage_fee": round(monthly_storage, 2) if monthly_storage >= 0.01 else 0.01
        }
    return items_data


def get_item_eligibility(asins):
    data = {}
    for asin in asins:
        response = inboundEligibilityAPI.get_item_eligibility_preview(
            marketplaceIds=["ATVPDKIKX0DER"],
            asin=asin,
            program="INBOUND"
        )
        time.sleep(1)
        data[asin] = response.payload.get("isEligibleForProgram")

    return data


def getProductTier(length, width, height, weight):
    longest = max(length, width, height)
    shortest = min(length, width, height)
    median = (length + width + height) - longest - shortest

    if weight <= 20 and longest <= 18 and median <= 14 and shortest <= 8:
        return "standard-size"
    else:
        return "oversize"




def get_my_fees_estimate(items):
    fees = dict()
    for asin in items:
        if asin not in fees:
            fees[asin] = {}
        for price in items[asin]:
            trial = 10
            while True:
                try:
                    response = productFeesAPI.get_product_fees_estimate_for_asin(asin=asin, price=price, is_fba=True)
                    break
                except SellingApiRequestThrottledException:
                    print(f"API Throttled -> Wait time = {response.rate_limit}")
                    print(asin, price)
                    time.sleep(float(response.rate_limit))
                    time.sleep(1)
                    trial -= 1
                    if trial == 0:
                        raise Exception("Trials Exceeded")
            fee_estimate_result = response.payload["FeesEstimateResult"]
            status = fee_estimate_result["Status"]
            if status != "Success":
                fees[asin][price] = None
                continue
            fee_estimates = fee_estimate_result["FeesEstimate"]
            fee_estimates = fee_estimates if isinstance(fee_estimates, list) else [fee_estimates]
            
            for fee_estimate in fee_estimates:
                total_fees = fee_estimate["TotalFeesEstimate"]["Amount"]
                fees[asin][price] = {
                    "total": total_fees
                }
                fee_details = fee_estimate["FeeDetailList"]
                fee_details = fee_details if isinstance(fee_details, list) else [fee_details]
                for fee_detail in fee_details:
                    fee_type = fee_detail["FeeType"]
                    fees[asin][price][fee_type] = fee_detail["FinalFee"]["Amount"]

    return fees


@app.task
def get_item_fees():
    try:
        script_session = ScriptSession(
            process_name = "GET FEE ESTIMATES",
            status="active"
        )
        script_session.save()

        event = script_session.create_event(
            title="GET FEE ESTIMATES",
            description="Fees Estimated (Referral, FBA and Monthly Storage Fees) data of items in db is processing."
        )
        session_id = str(script_session.session_id)
        print(f"[DEBUG] New Session ({session_id}, {script_session.process_name}) Created")

        items = cache.get("listings")
        inactive_items = cache.get("inactive_listings")

        for asin in inactive_items:
            if asin not in items:
                items[asin] = []
            for price in inactive_items[asin]:
                if price not in items[asin]:
                    items[asin].append(price)

        fees = get_my_fees_estimate(items)
        last_sync = datetime.now(timezone("UTC")).isoformat()
        file = StringIO()
        writer = csv.writer(file, delimiter=',', lineterminator='\n')
        writer.writerow(["ASIN", "Price", "FBA Fees", "Referral Fees", "Other Fees", "last_sync"])
        
        cleaned_fees_data = {}
        for asin in fees:
            if asin not in cleaned_fees_data:
                cleaned_fees_data[asin] = {}

            for price in fees[asin]:
                if fees[asin][price] is None:
                    writer.writerow([asin, price, "", "", "", last_sync])
                    cleaned_fees_data[asin][price] = {
                        "Fba Fees": None,
                        "referral Fees": None,
                        "Other Fees": None,
                        "Total Fees": None
                    }
                else:
                    total_fee = float(fees[asin][price]["total"])
                    fba_fee = float(fees[asin][price]["FBAFees"])
                    referral_fee = float(fees[asin][price]["ReferralFee"])
                    other_fees = round(total_fee - (fba_fee + referral_fee), 2) + 0
                    writer.writerow([asin, price, fba_fee, referral_fee, other_fees, last_sync])
                    cleaned_fees_data[asin][price] = {
                        "Fba Fees": fba_fee,
                        "referral Fees": referral_fee,
                        "Other Fees": other_fees,
                        "Total Fees": total_fee
                    }
                cleaned_fees_data[asin][price]["Last Sync"] = last_sync
                
        
        csv_string = file.getvalue()
        send_to_airtable('https://api.airtable.com/v0/appiaIHQERVLuVbEG/tblxggcffIrfga5GM/sync/K7jsoMvz', csv_string)
    except Exception as e:
        print(type(e), str(e))
        event = script_session.create_event(
            title=f"Error getting Item Fees",
            description=f"Script Experienced an error {type(e)} => {str(e)}",
        )
        notification = event.create_notification()
        notification.send()


# Financial Statements
@app.task
def getFinance():
    try:
        fmt = "%d %b %Y, %I:%M %p"
        posted_after = cache.get("transactions_last_updated")
        if posted_after is None:
            posted_after = TransactionCharge.objects.filter(~Q(posted_date=None)).order_by("-posted_date")[0].posted_date

        posted_before = datetime.now(timezone("UTC")) - timedelta(hours=1)
        print(f"Posted After: {posted_after.strftime(fmt)}")
        print(f"Posted Before: {posted_before.strftime(fmt)}")

        script_session = ScriptSession(
            process_name = "GET TRANSACTIONS",
            status = "active"
        )
        script_session.save()
        event = script_session.create_event(
            title="Get Transactions",
            description=f"Transaction data is being requested from SP-API for the date range; {posted_after.strftime(fmt)} to {posted_before.strftime(fmt)}")

        shipment_transactions = dict()
        refund_transactions = dict()
        service_fee_transactions = dict()

        next_token = None
        i = 1
        while True:
            trial = 0
            while True:
                try:
                    res = financesAPI.list_financial_events(
                        PostedAfter=posted_after.isoformat(),
                        PostedBefore=posted_before.isoformat(),
                        NextToken=next_token
                    )
                    payload = res.payload
                    break
                except (SellingApiBadRequestException, SellingApiRequestThrottledException, ConnectionError) as e: 
                    time.sleep(15)
                    trial += 1
                    if trial == 10:
                        break
                    print(
                        f"Connection Error...Trying again ({trial}) time{ 's' if trial!=1 else '' }"
                    )
            if trial == 10:
                print("Error collecting data from SP-API.. Please review")
                return
            print("Info Gathered")

            financial_events = payload['FinancialEvents']
            time.sleep(2)
            shipment_transactions = getShipmentTransaction(financial_events, shipment_transactions)
            refund_transactions = getRefundTransactions(financial_events, refund_transactions)
            service_fee_transactions = getServiceFees(financial_events, service_fee_transactions)
            i += 1

            next_token = payload.get('NextToken')
            if next_token is None:
                break
            
        event = script_session.create_event(f"Transaction data collected and stored in Cache.")

        event = script_session.create_event(
            title="Transaction Data Collected",
            description=f"Transaction data is collected")

        print(f"Updating {len(shipment_transactions)} Shipment Transaction")
        shipment_transaction_data_model_handler(shipment_transactions)
        print(f"Updating {len(refund_transactions)} Refund Transaction")
        refund_transaction_data_model_handler(refund_transactions)
        print(f"Updating {len(service_fee_transactions)} Service Fees Transaction")
        service_fee_model_handler(service_fee_transactions)
            
        event = script_session.create_event(
            title="Transaction Data Processed",
            description=f"Transaction data is now processed into DB"
        )

        cache.set("transactions_last_updated", posted_before)
        cache.persist("transactions_last_updated")
    except Exception as e:
        print(traceback.format_exc())
        event = script_session.create_event(
            title=f"Error getting Finance Transactions",
            description=f"Script Experienced an error {type(e)} => {str(e)}",
        )
        notification = event.create_notification()
        notification.send()


def getShipmentTransaction(financial_event, list_key_feats):
    shipment_event_list = financial_event.get("ShipmentEventList")
    if not shipment_event_list:
        return list_key_feats
    shipment_event_list = shipment_event_list if isinstance(shipment_event_list, list) else [shipment_event_list]

    for shipment_event in shipment_event_list:
        order_id = shipment_event.get("AmazonOrderId")
        posted_date = shipment_event.get("PostedDate")
        if order_id is None:
            continue
        shipment_item_list = shipment_event["ShipmentItemList"]

        shipment_item_list = shipment_item_list if isinstance(shipment_item_list, list) else [shipment_item_list]
        for shipment_item in shipment_item_list:
            order_item_id = shipment_item.get("OrderItemId")
            if order_item_id is None:
                continue
            key_feats = {
                "order_id": order_id,
                "posted_date": posted_date
            }

            item_charge_list = shipment_item.get("ItemChargeList", [])
            item_charge_list = item_charge_list if isinstance(item_charge_list, list) else [item_charge_list]
            for item_charge in item_charge_list:
                charge_type = item_charge["ChargeType"]
                charge_amount = item_charge["ChargeAmount"]["CurrencyAmount"]
                if charge_type not in key_feats:
                    key_feats[charge_type] = 0
                key_feats[charge_type] += charge_amount

            item_fee_list = shipment_item.get("ItemFeeList", [])
            item_fee_list = item_fee_list if isinstance(item_fee_list, list) else [item_fee_list]
            for item_fee in item_fee_list:
                fee_type = item_fee["FeeType"]
                fee_amount = item_fee["FeeAmount"]["CurrencyAmount"]
                if fee_type not in key_feats:
                    key_feats[fee_type] = 0
                key_feats[fee_type] += fee_amount

            item_tax_withheld_list = shipment_item.get("ItemTaxWithheldList", [])
            item_tax_withheld_list = item_tax_withheld_list if isinstance(item_tax_withheld_list, list) else [item_tax_withheld_list]
            for item_tax in item_tax_withheld_list:
                taxes_withheld = item_tax["TaxesWithheld"]
                taxes_withheld = taxes_withheld if isinstance(taxes_withheld, list) else [taxes_withheld]
                for tax_withheld in taxes_withheld:
                    tax_type = tax_withheld["ChargeType"]
                    tax_amount = tax_withheld["ChargeAmount"]["CurrencyAmount"]
                    if tax_type not in key_feats:
                        key_feats[tax_type] = 0
                    key_feats[tax_type] += tax_amount
            
            promotion_list = shipment_item.get("PromotionList", [])
            promotion_list = promotion_list if isinstance(promotion_list, list) else [promotion_list]
            for promotion in promotion_list:
                promotion_type = promotion["PromotionType"]
                promotion_amount = promotion["PromotionAmount"]["CurrencyAmount"]
                if promotion_type not in key_feats:
                    key_feats[promotion_type] = 0
                key_feats[promotion_type] += promotion_amount

            if shipment_item.get("QuantityShipped"):
                key_feats["quantity"] = shipment_item["QuantityShipped"]

            if order_item_id in list_key_feats:
                keys = set({**list_key_feats[order_item_id], **key_feats})
                updated_dict = {}
                for key in keys:
                    if key == "order_id" or key == "posted_date":
                        updated_dict[key] = key_feats[key]
                        continue
                    updated_dict[key] = float(list_key_feats[order_item_id].get(key, 0)) + float(key_feats.get(key, 0))
                list_key_feats[order_item_id] = updated_dict
            else:
                list_key_feats[order_item_id] = key_feats

    return list_key_feats


def getRefundTransactions(financial_event, refund_key_feats):
    refund_event_list = financial_event.get("RefundEventList")
    if not refund_event_list:
        return refund_key_feats
    refund_event_list = refund_event_list if isinstance(refund_event_list, list) else [refund_event_list]
    for event in refund_event_list:
        order_id = event.get("AmazonOrderId")
        posted_date = event.get("PostedDate")
        if order_id is None:
            continue

        shipment_item_adjustment_list = event.get("ShipmentItemAdjustmentList")
        if not shipment_item_adjustment_list:
            continue
        shipment_item_adjustment_list = shipment_item_adjustment_list if isinstance(shipment_item_adjustment_list, list) else [shipment_item_adjustment_list]
        for shipment_item_adjustment in shipment_item_adjustment_list:
            order_item_id = shipment_item_adjustment.get("OrderAdjustmentItemId")

            if order_item_id is None:
                refund_key_feats[order_id] = None
                continue
            sku = shipment_item_adjustment.get("SellerSKU")
            key_feats = {
                "posted_date": posted_date,
                "sku": sku
            }

            item_charge_list = shipment_item_adjustment.get("ItemChargeAdjustmentList", [])
            item_charge_list = item_charge_list if isinstance(item_charge_list, list) else [item_charge_list]
            for item_charge in item_charge_list:
                charge_type = item_charge["ChargeType"]
                charge_amount = item_charge["ChargeAmount"]["CurrencyAmount"]
                key_feats[charge_type] = float(key_feats.get(charge_type, 0)) + float(charge_amount)

            item_fee_list = shipment_item_adjustment.get("ItemFeeAdjustmentList", [])
            item_fee_list = item_fee_list if isinstance(item_fee_list, list) else [item_fee_list]
            for item_fee in item_fee_list:
                fee_type = item_fee["FeeType"]
                fee_amount = item_fee["FeeAmount"]["CurrencyAmount"]
                key_feats[fee_type] = float(key_feats.get(fee_type, 0)) + float(fee_amount)

            item_tax_withheld_list = shipment_item_adjustment.get("ItemTaxWithheldList", [])
            item_tax_withheld_list = item_tax_withheld_list if isinstance(item_tax_withheld_list, list) else [item_tax_withheld_list]
            for item_tax in item_tax_withheld_list:
                taxes_withheld = item_tax.get("TaxesWithheld")
                taxes_withheld = taxes_withheld if isinstance(taxes_withheld, list) else [taxes_withheld]
                for tax_withheld in taxes_withheld:
                    tax_type = tax_withheld["ChargeType"]
                    tax_amount = float(tax_withheld["ChargeAmount"]["CurrencyAmount"])
                    key_feats[tax_type] = float(key_feats.get(tax_type, 0)) + float(tax_amount)
            
            promotion_list = shipment_item_adjustment.get("PromotionAdjustmentList", [])
            promotion_list = promotion_list if isinstance(promotion_list, list) else [promotion_list]
            for promotion in promotion_list:
                promotion_type = promotion["PromotionType"]
                promotion_amount = promotion["PromotionAmount"]["CurrencyAmount"]
                key_feats[promotion_type] = float(key_feats.get(promotion_type, 0)) + float(promotion_amount)

            if shipment_item_adjustment.get("QuantityShipped") and "Principal" in key_feats:
                key_feats["quantity"] = shipment_item_adjustment["QuantityShipped"]

            if order_id in refund_key_feats:
                updated_dict = key_feats
                if refund_key_feats[order_id] is not None:
                    if order_item_id in refund_key_feats[order_id]:
                        keys = set({**refund_key_feats[order_id][order_item_id], **key_feats})
                        for key in keys:
                            if key == "sku" or key == "posted_date":
                                continue
                            updated_dict[key] = float(refund_key_feats[order_id][order_item_id].get(key, 0)) + float(key_feats.get(key, 0))
                    refund_key_feats[order_id][order_item_id] = updated_dict
                else:
                    refund_key_feats[order_id] = {order_item_id: key_feats}
            else:
                refund_key_feats[order_id] = {order_item_id: key_feats}

    return refund_key_feats


def getServiceFees(financial_event, service_fee_dict):
    service_fee_events = financial_event["ServiceFeeEventList"]
    service_fee_events = service_fee_events if isinstance(service_fee_events, list) else [service_fee_events]

    if not service_fee_events:
        return service_fee_dict

    for service_fees in service_fee_events:
        service_fees = service_fees if isinstance(service_fees, list) else [service_fees]

        for service_fee in service_fees:
            order_id = service_fee.get("AmazonOrderId")
            if order_id is None:
                continue
            if order_id not in service_fee_dict:
                service_fee_dict[order_id] = {}
            fees = service_fee.get("FeeList", [])
            fees = fees if isinstance(fees, list) else [fees]

            for fee in fees:
                fee_type = fee["FeeType"]
                fee_amount = float(fee["FeeAmount"]["CurrencyAmount"])
                if fee_amount == 0:
                    continue
                if fee_type not in service_fee_dict[order_id]:
                    service_fee_dict[order_id][fee_type] = 0

                service_fee_dict[order_id][fee_type] += fee_amount

    return service_fee_dict


def shipment_transaction_data_model_handler(list_key_feats):
    for order_item_id in list_key_feats:
        key_feats = list_key_feats[order_item_id]
        try:
            order = Order.objects.get(order_id=key_feats["order_id"])
        except ObjectDoesNotExist:
            continue
        
        try:
            transaction = Transaction.objects.get(
                transaction_type="Order",
                order_item__order_item_id=order_item_id
            )
        except Transaction.DoesNotExist:
            try:
                order_item = OrderItem.objects.get(order_item_id=order_item_id)
            except ObjectDoesNotExist:
                try:
                    order = Order.objects.get(order_id=key_feats["order_id"])
                except ObjectDoesNotExist:
                    order = Order(order_id=key_feats["order_id"])
                    try:
                        order.save()
                    except IntegrityError:
                        pass
                    finally:
                        order = Order.objects.get(order_id=key_feats["order_id"])
                
                order_item = OrderItem(order_item_id=order_item_id, order=order)
                try:
                    order_item.save()
                except IntegrityError:
                    pass
            finally:
                order_item = OrderItem.objects.get(order_item_id=order_item_id)
            
            transaction = Transaction(
                transaction_type="Order",
                order = order,
                order_item = order_item,
                quantity = key_feats.get("quantity")
            )
            transaction.save()
        except Transaction.MultipleObjectsReturned:
            print(key_feats["order_id"])
            print(order_item_id)
            input("Duplicate Order Transactions")
            continue

        for key in key_feats:
            if key in ["order_id", "posted_date", "quantity"]:
                continue
            charge_type = key
            charge_amount = key_feats[key]
            try:
                transaction_charge = TransactionCharge.objects.get(
                    transaction=transaction,
                    charge_type=charge_type
                )
                if transaction_charge.posted_date is None or transaction_charge.posted_date < parse(key_feats["posted_date"]):
                    transaction_charge.amount += charge_amount
            except TransactionCharge.DoesNotExist:
                transaction_charge = TransactionCharge(
                    transaction = transaction,
                    posted_date = key_feats["posted_date"],
                    charge_type = charge_type,
                    amount = charge_amount
                )
            finally:
                transaction_charge.save()
                if charge_type == "FBAPerUnitFulfillmentFee":
                    transaction.fulfillment_unit_fee = transaction_charge.amount
                    transaction.save()
        
        # print(f"Percentage Complete = {round(count / total * 100, 2)}%")
        # count += 1
    start_182 = datetime.now(utc) - timedelta(days=182)
    del_order_transactions = Transaction.objects.filter(Q(transaction_type="Order"), ~Q(charges__posted_date__gte=start_182))
    print(f"No of Deleted Order Transactions = {del_order_transactions.count()}")
    del_order_transactions.delete()


def refund_transaction_data_model_handler(data):
    issues = []
    for order_id in data:
        if data[order_id] is None:
            continue
        for order_item_id in data[order_id]:
            key_feats = data[order_id][order_item_id]
            try:
                order = Order.objects.get(order_id=order_id)
            except Order.DoesNotExist:
                issues.append(f"{order.order_id}\tN/A\tOrder Does Not Exist")
                continue
            
            try:
                order_item = OrderItem.objects.get(order_item_id=order_item_id)
            except Exception:
                issues.append(f"{order.order_id}\t{order_item.order_item_id}\tOrder Item Does Not Exist")
                continue

            try:
                transaction = Transaction.objects.get(
                    transaction_type="Refund",
                    order_item=order_item
                )
            except Transaction.DoesNotExist:
                transaction = Transaction(
                    transaction_type="Refund",
                    order = order,
                    order_item = order_item,
                    quantity = key_feats.get("quantity")
                )
                transaction.save()
            except Transaction.MultipleObjectsReturned:
                print("Duplicate Refund Transactions")
                issues.append(f"{order.order_id}\t{order_item.order_item_id}\tMultiple Objects Returned")
                continue

            for key in key_feats:
                if key in ["sku", "posted_date", "quantity"]:
                    continue
                charge_type = key
                charge_amount = key_feats[key]
                try:
                    transaction_charge = TransactionCharge.objects.get(
                        transaction=transaction,
                        charge_type=charge_type
                    )
                    if transaction_charge.posted_date is None or transaction_charge.posted_date < parse(key_feats["posted_date"]):
                        transaction_charge.amount += charge_amount
                except TransactionCharge.DoesNotExist:
                    transaction_charge = TransactionCharge(
                        transaction = transaction,
                        posted_date = key_feats["posted_date"],
                        charge_type = charge_type,
                        amount = charge_amount
                    )
                finally:
                    transaction_charge.save()

        # print(f"Percentage Complete = {round(count / total * 100, 2)}%")
        # count += 1
    start_182 = datetime.now(utc) - timedelta(days=182)
    del_refund_transactions = Transaction.objects.filter(Q(transaction_type="Refund"), ~Q(charges__posted_date__gte=start_182))
    print(f"No of Deleted Refund Transactions = {del_refund_transactions.count()}")
    del_refund_transactions.delete()


def service_fee_model_handler(data):
    for order_id in data:
        try:
            order = Order.objects.get(order_id=order_id)
        except ObjectDoesNotExist:
            continue

        try:
            transaction = Transaction.objects.get(
                transaction_type="ServiceFee",
                order=order
            )
        except Transaction.DoesNotExist:
            transaction = Transaction(
                transaction_type="ServiceFee",
                order = order
            )
            transaction.save()
        except Transaction.MultipleObjectsReturned:
            input("Duplicate Order Transactions")
            continue

        key_feats = data[order_id]
        for key in key_feats:
            charge_type = key
            charge_amount = key_feats[key]
            try:
                transaction_charge = TransactionCharge.objects.get(transaction=transaction, charge_type=charge_type)
            except TransactionCharge.DoesNotExist:
                transaction_charge = TransactionCharge(
                    transaction = transaction,
                    charge_type = charge_type,
                    amount = charge_amount
                )
            finally:
                transaction_charge.save()

        # print(f"Percentage Complete = {round(count / total * 100, 2)}%")
        # count += 1
    start_182 = datetime.now(utc) - timedelta(days=182)
    del_service_fees = Transaction.objects.filter(transaction_type="SerciveFee", order__purchase_date__lt=start_182)
    print(f"No of Deleted Service Fees = {del_service_fees.count()}")
    del_service_fees.delete()


def clear_reports():
    while True:
        with redis_lock('report_queue_lock') as acquired:
            if acquired is True:
                report_queue = cache.get("report_queue", {})
                print(f"Lenght of Queue = {len(report_queue)}")
                
                valid_ids = []
                active_sessions = list(filter(lambda x: x[1]["active"], report_queue.items()))
                valid_ids += [session[0] for session in active_sessions]
                redefined_data = {}
                for session_id in valid_ids:
                    redefined_data[session_id] = report_queue[session_id]
                
                cache.set("report_queue", redefined_data)
                cache.persist("report_queue")
                ScriptSession.objects.filter(~Q(session_id__in=valid_ids)).delete()
                print(f"New Lenght of Queue = {len(redefined_data)}")
                break


def clear_feeds():
    while True:
        with redis_lock('feed_queue_lock') as acquired:
            if acquired is True:
                feed_requests = cache.get("feed_queue_lock", {})
                active_sessions = list(filter(lambda x: x[1]["active"], feed_requests.items()))
                valid_ids = [session[0] for session in active_sessions]

                redefined_data = {}
                for session_id in valid_ids:
                    redefined_data[session_id] = feed_requests[session_id]
                
                cache.set("feed_request_queue", redefined_data)
                cache.persist("feed_request_queue")
                break


@app.task(name="CleanCeleryTasks")
def clean_celery_tasks():
    tasks = PeriodicTask.objects.all()
    for task in tasks:
        task.enabled = False
        task.save()
    time.sleep(5)
    i = app.control.inspect()
    workers = i.active()
    if workers:
        for host in workers:
            for worker in workers[host]:
                print(worker["name"])
                if worker["name"] == "CleanCeleryTasks":
                    continue
                app.control.revoke(worker["id"], terminate=True, signal='SIGKILL')
    time.sleep(3)
    clear_reports()
    clear_feeds()
    time.sleep(3) 
    tasks = PeriodicTask.objects.all()
    for task in tasks:
        task.enabled = True
        task.save()
