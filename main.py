"""
Home Delivery System - Railway Compatible Version
With Built-in Tommy Sugo Marketing Calendar + Customer Notifications
APScheduler based - No Railway Cron needed if container is 24/7 alive

FIXES HISTORY:
  v14.3 - Double email fix: testing mode loop hataya
  v14.3 - Date filter: sirf aaj ki Perth date wali TransVirtual requests process hongi
  v14.4 - email_service: testing mode mein customer_email empty check bypass
  v14.5 - SMS added to TransVirtual webhook (InTransit + Delivered)
         - SMS bhi email ki tarah Perth date filter follow karta hai
         - ReceiverPhone TransVirtual payload se directly use hota hai
  v14.6 - SMS: send_delivery_notification() deprecated
         - InTransit → send_intransit_notification()
         - Delivered → send_delivered_notification()
"""
from fastapi import FastAPI, Request, HTTPException
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from pathlib import Path
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Import services
from services import (
    OpenAIService,
    TransvirtualService,
    ResendEmailService,
    GoogleDriveService,
    MobileMessageService,
    generate_barcode,
    JSONQueueManager,
    resolve_deals,
)
from services.pdf_docx_service import create_packing_slip_pdf, create_packing_slip_docx
from utils import (
    ConfigManager,
    extract_field_value,
    extract_products,
    extract_form_id
)

load_dotenv()

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==================== FASTAPI APP ====================
app = FastAPI(title="Home Delivery - Railway Compatible", version="14.6")

# ==================== GLOBAL INSTANCES ====================
base_path = Path(__file__).parent
config_manager = ConfigManager(base_path)
google_drive_service = GoogleDriveService()
resend_service = None
sms_service = None
queue_manager = JSONQueueManager()
scheduler = AsyncIOScheduler(timezone="Australia/Perth")
PERTH_TZ = pytz.timezone("Australia/Perth")


# ==================== DATE FILTER HELPER ====================

def is_today_perth(date_time_str: str) -> bool:
    """
    TransVirtual ka DateTime Perth time mein aata hai (format: 'YYYY-MM-DD HH:MM').
    Sirf aaj ki date wali requests allow karo — purani / backdated deliveries skip.

    Returns:
        True  → request aaj ki hai, process karo
        False → purani date hai, skip karo
    """
    if not date_time_str:
        logger.warning("[DATE FILTER] DateTime empty — allowing through (safe fallback)")
        return True
    try:
        dt = datetime.strptime(str(date_time_str).strip(), '%Y-%m-%d %H:%M')
        dt_perth = PERTH_TZ.localize(dt)
        today_perth = datetime.now(PERTH_TZ).date()
        is_today = dt_perth.date() == today_perth
        if not is_today:
            logger.info(
                f"[DATE FILTER] ⏭️  Old date detected: {date_time_str} "
                f"(Perth date: {dt_perth.date()} vs today: {today_perth})"
            )
        return is_today
    except Exception as e:
        logger.warning(f"[DATE FILTER] DateTime parse failed '{date_time_str}': {e} — allowing through")
        return True


# ==================== SCHEDULE HELPERS ====================

def get_schedule_config() -> dict:
    """Config file se schedule load karo"""
    try:
        config = config_manager.load_form_config('home_delivery.json')
        return config.get('schedule', {})
    except Exception as e:
        logger.error(f"[SCHEDULER] Schedule config load failed: {e}")
        return {}


def setup_scheduler():
    """
    home_delivery.json ke schedule section se APScheduler jobs setup karo.
    Customer notification scheduled job REMOVE kar di gayi hai.
    Ab customer emails + SMS SIRF TransVirtual webhook se trigger hongi:
    - InTransit  → Out for Delivery email + SMS
    - Delivered  → Delivered email + SMS
    """
    schedule = get_schedule_config()

    # ── Factory batch jobs ──────────────────────────────────────────
    factory_times = schedule.get('factory_batch', {}).get('times_perth', [])
    if not factory_times:
        factory_times = [
            {"hour": 13, "minute": 0, "label": "1 PM Batch"},
            {"hour": 20, "minute": 0, "label": "8 PM Batch"},
        ]
        logger.warning("[SCHEDULER] factory_batch times not in config — using defaults (1PM, 8PM Perth)")

    for t in factory_times:
        scheduler.add_job(
            scheduled_send_batch,
            CronTrigger(hour=t['hour'], minute=t['minute'],day_of_week='mon-thu', timezone=PERTH_TZ),
            id=f"factory_batch_{t['hour']}_{t['minute']}",
            name=f"Factory Batch - {t['label']}",
            replace_existing=True
        )
        logger.info(f"[SCHEDULER] Factory batch scheduled: {t['label']} ({t['hour']:02d}:{t['minute']:02d} Perth)")

    logger.info("[SCHEDULER] ℹ️  Customer notifications: Scheduled job DISABLED — TransVirtual webhook se trigger hoga")


# ==================== SCHEDULED JOB FUNCTIONS ====================

async def scheduled_send_batch():
    """APScheduler ye function scheduled time pe call karta hai"""
    logger.info("[SCHEDULER] ⏰ Factory batch job triggered")
    result = send_batch()
    logger.info(f"[SCHEDULER] Factory batch result: {result}")


# ==================== CORE LOGIC FUNCTIONS ====================

def send_batch() -> dict:
    """Factory email queue process karo — PDF links factory ko bhejo."""
    global queue_manager

    if not resend_service or not resend_service.enabled:
        logger.info("[BATCH] Email service disabled - skipping")
        return {"status": "skipped", "reason": "email_disabled"}

    queued_items = queue_manager.get_all()

    if not queued_items:
        logger.info("[BATCH] No PDFs in queue")
        return {"status": "success", "sent": 0, "message": "Queue empty"}

    logger.info("=" * 80)
    logger.info(f"[BATCH] Sending batch of {len(queued_items)} PDFs to FACTORY")
    logger.info("-" * 80)

    urls = [item['pdf_url'] for item in queued_items if item.get('pdf_url')]
    success = resend_service.send_packing_slips(urls)

    if success:
        for item in queued_items:
            if item.get('pdf_url'):
                try:
                    for path in [item.get('pdf_path'), item.get('docx_path'), item.get('barcode_path')]:
                        if path and Path(path).exists():
                            os.remove(path)
                            logger.info(f"[CLEANUP] Deleted: {Path(path).name}")
                except Exception as e:
                    logger.error(f"[CLEANUP] Delete failed: {e}")

        queue_manager.clear()
        logger.info(f"[BATCH] Queue cleared")
        return {"status": "success", "sent": len(urls), "cleared": len(queued_items)}
    else:
        logger.error(f"[BATCH] Batch send failed - keeping files for retry")
        return {"status": "failed", "sent": 0, "kept": len(queued_items)}


# ==================== STARTUP / SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    global resend_service, sms_service
    try:
        config_manager.initialize()

        default_config = config_manager.load_form_config('home_delivery.json')
        resend_service = ResendEmailService(default_config.get('email', {}))
        sms_service    = MobileMessageService(default_config.get('sms', {}))

        setup_scheduler()
        scheduler.start()

        is_testing    = resend_service and resend_service.testing_mode
        test_emails   = default_config.get('email', {}).get('testing_emails', [])

        perth_now = datetime.now(PERTH_TZ)
        logger.info("=" * 80)
        logger.info("APPLICATION STARTED SUCCESSFULLY")
        logger.info(f"Version       : 14.6 (SMS: intransit + delivered alag functions)")
        logger.info(f"Google Drive  : {'✅ ENABLED' if google_drive_service.enabled else '❌ DISABLED'}")
        logger.info(f"Resend Email  : {'✅ ENABLED' if resend_service.enabled else '❌ DISABLED'}")
        logger.info(f"SMS Service   : {'✅ ENABLED' if sms_service.enabled else '❌ DISABLED'}")
        logger.info(f"Factory Queue : {queue_manager.count()} items pending")
        logger.info(f"Perth Time    : {perth_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"Webhook Mode  : {'🧪 TESTING — sirf test emails' if is_testing else '🚀 PRODUCTION — customer emails'}")
        if is_testing and test_emails:
            logger.info(f"Test Emails   : {', '.join(test_emails)}")
        logger.info("Customer Emails: ✅ TransVirtual webhook se trigger hongi (InTransit / Delivered)")
        logger.info("Customer SMS  : ✅ TransVirtual webhook se trigger hongi (InTransit / Delivered)")
        logger.info("Date Filter   : ✅ ENABLED — sirf aaj ki Perth date wali requests process hongi")
        logger.info("SCHEDULED JOBS:")
        for job in scheduler.get_jobs():
            logger.info(f"  {job.name} → Next: {job.next_run_time}")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    logger.info("[SCHEDULER] Stopped")


# ==================== API ENDPOINTS ====================

@app.post("/jotform/webhook")
async def webhook_handler(request: Request):
    """Main webhook handler for Jotform submissions"""
    global queue_manager

    try:
        form = await request.form()
        data = dict(form)
        raw  = json.loads(data.get("rawRequest", "{}"))

        form_id = extract_form_id(raw)
        if not form_id:
            raise HTTPException(status_code=400, detail="Could not determine form_id")

        config = config_manager.get_config_for_form(form_id)

        order_data = {}
        for field_key, field_config in config['fields'].items():
            order_data[field_key] = extract_field_value(raw, field_config)

        order_data['delivery_date_obj'] = raw.get('q6_desiredDelivery6', {})
        order_data["items"]       = extract_products(raw, config)
        order_data["total_boxes"] = len(order_data["items"])

        invoice_no = order_data.get('invoice_no', 'UNKNOWN').replace('# ', '').strip()
        logger.info(f"Order: {invoice_no}, Products: {len(order_data['items'])}")

        order_data["items"] = resolve_deals(order_data["items"])
        logger.info(f"[DEAL RESOLVER] Items after resolve: {len(order_data['items'])}")

        # AI Processing
        openai_service = OpenAIService(config)
        order_data = openai_service.validate_and_fix_data(order_data)

        customer_feedback = order_data.get('customer_love_note', '').strip()
        feedback_enabled  = order_data.get('feedback_enabled', '').strip().lower()

        order_data['ai_feedback_response'] = (
            openai_service.generate_feedback_response(customer_feedback, order_data.get('customer_name', 'Customer'))
            if customer_feedback and feedback_enabled == "yes" else ""
        )

        is_gift_order = bool(order_data.get('gift_recipient', '').strip())
        order_data['ai_recommendation'] = openai_service.generate_product_recommendation(
            order_data['items'],
            config.get('pdf', {}).get('messages', {}).get('all_products', []),
            is_gift_order=is_gift_order
        )

        # Transvirtual
        transvirtual_service = TransvirtualService(config)
        transvirtual_result  = transvirtual_service.create_consignment(order_data)

        barcode_path = ""
        consignment_number = ""
        if transvirtual_result and transvirtual_result.get('barcode_number'):
            order_data['barcode_number']     = transvirtual_result['barcode_number']
            order_data['consignment_number'] = transvirtual_result.get('consignment_number', 'N/A')
            order_data['consignment_id']     = transvirtual_result.get('consignment_id', 'N/A')
            consignment_number = transvirtual_result.get('consignment_number', '')
            barcode_path = generate_barcode(transvirtual_result['barcode_number'], base_path / 'barcodes')
        else:
            logger.warning("[WARNING] No Transvirtual barcode")

        # PDF & DOCX
        pdf_path  = create_packing_slip_pdf(order_data, config, barcode_path, base_path)
        docx_path = create_packing_slip_docx(order_data, config, barcode_path, base_path)

        # Barcode delete karo — PDF/DOCX me add ho gaya, ab zaroorat nahi
        if barcode_path and Path(barcode_path).exists():
            try:
                os.remove(barcode_path)
                logger.info(f"[CLEANUP] 🗑️  Barcode deleted: {Path(barcode_path).name}")
            except Exception as e:
                logger.warning(f"[CLEANUP] ⚠️  Barcode delete failed: {e}")
            barcode_path = ""

        # Google Drive
        order_date      = datetime.now()
        drive_link_pdf  = google_drive_service.upload_file(pdf_path, order_date, invoice_no, "pdf")
        drive_link_docx = google_drive_service.upload_file(docx_path, order_date, invoice_no, "docx") if docx_path else ""

        # Factory Email Queue
        factory_email_sent = False
        if drive_link_pdf and resend_service and resend_service.enabled:
            if resend_service.testing_mode:
                factory_email_sent = resend_service.send_packing_slips([drive_link_pdf])
                if factory_email_sent:
                    for path in [pdf_path, docx_path, barcode_path]:
                        if path and Path(path).exists():
                            os.remove(path)
            else:
                queue_manager.add({
                    'pdf_url': drive_link_pdf, 'pdf_path': str(pdf_path),
                    'docx_path': str(docx_path) if docx_path else None,
                    'barcode_path': str(barcode_path) if barcode_path else None,
                    'invoice_no': invoice_no, 'timestamp': datetime.now().isoformat()
                })
                logger.info(f"[FACTORY QUEUE] Added (Total: {queue_manager.count()})")

        next_batch = next((str(j.next_run_time) for j in scheduler.get_jobs() if 'factory_batch' in j.id), "N/A")

        return {
            "status"             : "success",
            "invoice_no"         : invoice_no,
            "drive_link_pdf"     : drive_link_pdf or "Upload failed",
            "drive_link_docx"    : drive_link_docx or "Upload failed",
            "products_count"     : len(order_data['items']),
            "consignment_number" : consignment_number or "N/A",

            "factory_email": {
                "mode"            : "testing" if resend_service and resend_service.testing_mode else "production",
                "sent_immediately": factory_email_sent,
                "queued"          : not factory_email_sent and bool(drive_link_pdf),
                "queue_size"      : queue_manager.count(),
                "next_scheduled"  : next_batch,
            },
            "ai_features": {
                "feedback_response": order_data.get('ai_feedback_response', 'N/A'),
                "recommendation"   : order_data.get('ai_recommendation', 'N/A'),
                "is_gift_order"    : is_gift_order
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trigger-batch")
async def trigger_batch_now():
    """Factory email queue ABHI manually trigger karo — testing ke liye."""
    logger.info("[MANUAL TRIGGER] /trigger-batch")
    result = send_batch()
    result['triggered_by'] = 'manual'
    return result


# ==================== TRANSVIRTUAL WEBHOOK ====================

@app.api_route("/webhook/transvirtual", methods=["POST", "PUT"])
async def transvirtual_status_webhook(request: Request):
    """
    TransVirtual se automatic status updates receive karo.
    InTransit  = courier ne factory se order utha liya → Out for Delivery email + SMS
    Delivered  = order customer tak pahunch gaya → Delivered email + SMS

    DATE FILTER (v14.3):
        Sirf aaj ki Perth date wali requests process hongi.
        Purani / backdated deliveries automatically skip ho jaayengi.

    TESTING MODE  (testing_mode: true  in home_delivery.json):
        Email → sirf testing_emails list wali emails ko jaayegi
        SMS   → enabled hone par real SMS jaayegi (testing number set karo config mein)

    PRODUCTION MODE (testing_mode: false in home_delivery.json):
        Email → customer ko + BCC admin
        SMS   → customer ke ReceiverPhone par
    """
    try:
        data = await request.json()

        consignment_number = data.get('ConsignmentNumber', '')
        status             = data.get('Status', '')
        receiver_name      = data.get('ReceiverName', '')
        receiver_email     = data.get('ReceiverEmail', '')
        receiver_phone     = data.get('ReceiverPhone', '')
        date_time          = data.get('DateTime', '')
        comment            = data.get('Comment', '')

        # ── Full request log ────────────────────────────────────────
        logger.info("=" * 80)
        logger.info("[TRANSVIRTUAL WEBHOOK] 📥 Incoming Request")
        logger.info(f"  ConsignmentNumber : {consignment_number}")
        logger.info(f"  Status            : {status}")
        logger.info(f"  ReceiverName      : {receiver_name}")
        logger.info(f"  ReceiverEmail     : {receiver_email}")
        logger.info(f"  ReceiverPhone     : {receiver_phone}")
        logger.info(f"  DateTime          : {date_time}")
        logger.info(f"  Comment           : {comment}")
        logger.info(f"  Raw payload       : {data}")
        logger.info("=" * 80)

        if not consignment_number or not status:
            logger.error("[TRANSVIRTUAL WEBHOOK] ❌ Missing ConsignmentNumber or Status")
            raise HTTPException(status_code=400, detail="ConsignmentNumber aur Status required hain")

        # ── DATE FILTER — sirf aaj ki Perth date wali requests process karo ──
        if not is_today_perth(date_time):
            perth_today = datetime.now(PERTH_TZ).strftime('%Y-%m-%d')
            logger.info(
                f"[TRANSVIRTUAL WEBHOOK] ⏭️  SKIPPED — Old/backdated delivery\n"
                f"  Consignment : {consignment_number}\n"
                f"  DateTime    : {date_time}\n"
                f"  Perth Today : {perth_today}\n"
                f"  Reason      : Delivery date aaj ki nahi — email/SMS send nahi hogi"
            )
            logger.info("=" * 80)
            return {
                "received"    : True,
                "consignment" : consignment_number,
                "status"      : status,
                "skipped"     : True,
                "reason"      : f"Old delivery date: {date_time} — not today ({perth_today} Perth)",
                "email_sent"  : False,
                "sms_sent"    : False,
            }

        # ── Testing / Production mode decide karo ───────────────────
        is_testing = resend_service and resend_service.testing_mode

        if is_testing:
            config      = config_manager.load_form_config('home_delivery.json')
            test_emails = config.get('email', {}).get('testing_emails', ['arrehman445511@gmail.com'])
            target_name = receiver_name or "Test Customer"
            logger.info(f"[TRANSVIRTUAL WEBHOOK] 🧪 TESTING MODE → emails jaayengi: {test_emails}")
        else:
            target_name = receiver_name
            logger.info(f"[TRANSVIRTUAL WEBHOOK] 🚀 PRODUCTION MODE → customer email: {receiver_email} | phone: {receiver_phone}")

        email_sent = False
        sms_sent   = False

        # ── InTransit → Out for Delivery email + SMS ─────────────────
        if status.lower() == 'intransit':
            logger.info("[TRANSVIRTUAL WEBHOOK] 🚚 Status: InTransit → Out for Delivery email + SMS bhej raha hoon")

            # Email
            if resend_service and resend_service.enabled:
                if is_testing:
                    email_sent = resend_service.send_intransit_notification(
                        customer_name=target_name,
                        customer_email="",
                        consignment_number=consignment_number,
                    )
                    logger.info(f"[TRANSVIRTUAL WEBHOOK] 🧪 InTransit email sent | sent: {email_sent}")
                else:
                    email_sent = resend_service.send_intransit_notification(
                        customer_name=target_name,
                        customer_email=receiver_email,
                        consignment_number=consignment_number,
                    )
                    logger.info(f"[TRANSVIRTUAL WEBHOOK] 🚀 InTransit email sent | sent: {email_sent}")
            else:
                logger.warning("[TRANSVIRTUAL WEBHOOK] ⚠️  Email service disabled - InTransit email skip")

            # SMS — v14.6: send_intransit_notification() use karo
            if sms_service and sms_service.enabled:
                if receiver_phone:
                    sms_sent = sms_service.send_intransit_notification(
                        customer_name=target_name,
                        customer_phone=receiver_phone,
                        consignment_number=consignment_number,
                        delivery_date=date_time,
                    )
                    logger.info(f"[TRANSVIRTUAL WEBHOOK] 📱 InTransit SMS | sent: {sms_sent}")
                else:
                    logger.warning("[TRANSVIRTUAL WEBHOOK] ⚠️  No ReceiverPhone — InTransit SMS skip")
            else:
                logger.info("[TRANSVIRTUAL WEBHOOK] ℹ️  SMS service disabled — InTransit SMS skip")

        # ── Delivered → Delivered email + SMS ────────────────────────
        elif status.lower() == 'delivered':
            logger.info("[TRANSVIRTUAL WEBHOOK] ✅ Status: Delivered → Delivered email + SMS bhej raha hoon")

            # Email
            if resend_service and resend_service.enabled:
                if is_testing:
                    email_sent = resend_service.send_delivered_notification(
                        customer_name=target_name,
                        customer_email="",
                        consignment_number=consignment_number,
                    )
                    logger.info(f"[TRANSVIRTUAL WEBHOOK] 🧪 Delivered email sent | sent: {email_sent}")
                else:
                    email_sent = resend_service.send_delivered_notification(
                        customer_name=target_name,
                        customer_email=receiver_email,
                        consignment_number=consignment_number,
                    )
                    logger.info(f"[TRANSVIRTUAL WEBHOOK] 🚀 Delivered email sent | sent: {email_sent}")
            else:
                logger.warning("[TRANSVIRTUAL WEBHOOK] ⚠️  Email service disabled - Delivered email skip")

            # SMS — v14.6: send_delivered_notification() use karo
            if sms_service and sms_service.enabled:
                if receiver_phone:
                    sms_sent = sms_service.send_delivered_notification(
                        customer_name=target_name,
                        customer_phone=receiver_phone,
                        consignment_number=consignment_number,
                        delivery_date=date_time,
                    )
                    logger.info(f"[TRANSVIRTUAL WEBHOOK] 📱 Delivered SMS | sent: {sms_sent}")
                else:
                    logger.warning("[TRANSVIRTUAL WEBHOOK] ⚠️  No ReceiverPhone — Delivered SMS skip")
            else:
                logger.info("[TRANSVIRTUAL WEBHOOK] ℹ️  SMS service disabled — Delivered SMS skip")

        # ── Other status — koi action nahi ──────────────────────────
        else:
            logger.info(f"[TRANSVIRTUAL WEBHOOK] ℹ️  Status '{status}' — koi email/SMS action nahi")

        logger.info(
            f"[TRANSVIRTUAL WEBHOOK] Done | mode: {'TESTING' if is_testing else 'PRODUCTION'} "
            f"| email_sent: {email_sent} | sms_sent: {sms_sent}"
        )
        logger.info("=" * 80)

        return {
            "received"    : True,
            "consignment" : consignment_number,
            "status"      : status,
            "mode"        : "testing" if is_testing else "production",
            "email_sent"  : email_sent,
            "sms_sent"    : sms_sent,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRANSVIRTUAL WEBHOOK] ❌ Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== OTHER ENDPOINTS ====================

@app.get("/scheduler-status")
async def scheduler_status():
    """Scheduler jobs aur next run times dekho."""
    perth_now = datetime.now(PERTH_TZ)
    schedule  = get_schedule_config()

    return {
        "scheduler_running" : scheduler.running,
        "perth_time_now"    : perth_now.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "jobs"              : [{"name": j.name, "next_run": str(j.next_run_time)} for j in scheduler.get_jobs()],
        "customer_notifications": "TransVirtual webhook se trigger hoti hain (email + SMS)",
        "date_filter"       : f"Sirf aaj ki Perth date ({perth_now.strftime('%Y-%m-%d')}) wali requests process hongi",
        "config_times"      : {
            "factory_batch": schedule.get('factory_batch', {}).get('times_perth', []),
        },
        "how_to_change": "home_delivery.json → schedule → times_perth → hour/minute → app restart"
    }


@app.get("/")
async def root():
    email_mode = "disabled"
    if resend_service and resend_service.enabled:
        email_mode = "testing" if resend_service.testing_mode else "production"
    sms_mode = "disabled"
    if sms_service and sms_service.enabled:
        sms_mode = "testing" if sms_service.testing_mode else "production"

    from services.ai_service import TommySugoCalendar
    current_event = TommySugoCalendar.get_current_event()
    event_info    = f"{current_event['name']} (in {current_event['days_until']} days)" if current_event else "No active events"

    perth_now = datetime.now(PERTH_TZ)

    return {
        "status"      : "online",
        "version"     : "14.6 - SMS alag functions: intransit + delivered",
        "perth_time"  : perth_now.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "google_drive": "enabled" if google_drive_service.enabled else "disabled",
        "email"       : {
            "service"       : "enabled" if resend_service and resend_service.enabled else "disabled",
            "mode"          : email_mode,
            "factory_queue" : queue_manager.count()
        },
        "sms"         : {
            "service" : "enabled" if sms_service and sms_service.enabled else "disabled",
            "mode"    : sms_mode
        },
        "notifications": {
            "trigger"     : "TransVirtual webhook (InTransit / Delivered) → email + SMS",
            "date_filter" : f"✅ ACTIVE — sirf aaj ({perth_now.strftime('%Y-%m-%d')}) ki Perth date wali requests",
            "email_mode"  : "testing — sirf test emails" if (resend_service and resend_service.testing_mode) else "production — customer emails",
            "sms_mode"    : sms_mode
        },
        "scheduler"   : {"running": scheduler.running, "jobs": [{"name": j.name, "next": str(j.next_run_time)} for j in scheduler.get_jobs()]},
        "marketing"   : {"active_event": event_info},
    }


@app.get("/forms")
async def list_forms():
    if not config_manager.config_map:
        return {"forms": [], "error": "Config not loaded"}
    return {"forms": [{"form_id": fid, "name": info['name'], "config_file": info['config_file']} for fid, info in config_manager.config_map.get('forms', {}).items()]}


@app.get("/queue")
async def view_queue():
    return {
        "factory_email_queue": {"mode": "testing" if (resend_service and resend_service.testing_mode) else "production", "total": queue_manager.count(), "items": queue_manager.get_all()},
    }


@app.get("/events")
async def view_events():
    from services.ai_service import TommySugoCalendar
    current_event = TommySugoCalendar.get_current_event()
    if current_event:
        return {"status": "ACTIVE EVENT", "event": {"name": current_event['name'], "date": current_event['date'], "days_until": current_event['days_until'], "marketing_messages": current_event['messages']}}
    return {"status": "NO ACTIVE EVENTS", "message": "No marketing events in current window"}


# Run: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
