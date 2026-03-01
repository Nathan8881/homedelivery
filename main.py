"""
Home Delivery System - Railway Compatible Version
With Built-in Tommy Sugo Marketing Calendar + Customer Notifications
APScheduler based - No Railway Cron needed if container is 24/7 alive
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
    NotificationQueueManager
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
app = FastAPI(title="Home Delivery - Railway Compatible", version="14.0")

# ==================== GLOBAL INSTANCES ====================
base_path = Path(__file__).parent
config_manager = ConfigManager(base_path)
google_drive_service = GoogleDriveService()
resend_service = None
sms_service = None
queue_manager = JSONQueueManager()
notification_queue = NotificationQueueManager()
scheduler = AsyncIOScheduler(timezone="Australia/Perth")
PERTH_TZ = pytz.timezone("Australia/Perth")


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
    App restart pe automatically config se times read hote hain.
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
            CronTrigger(hour=t['hour'], minute=t['minute'], timezone=PERTH_TZ),
            id=f"factory_batch_{t['hour']}_{t['minute']}",
            name=f"Factory Batch - {t['label']}",
            replace_existing=True
        )
        logger.info(f"[SCHEDULER] Factory batch scheduled: {t['label']} ({t['hour']:02d}:{t['minute']:02d} Perth)")

    # ── Customer notification jobs ──────────────────────────────────
    notif_times = schedule.get('customer_notifications', {}).get('times_perth', [])
    if not notif_times:
        notif_times = [{"hour": 6, "minute": 0, "label": "6 AM Daily"}]
        logger.warning("[SCHEDULER] customer_notifications times not in config — using default (6AM Perth)")

    for t in notif_times:
        scheduler.add_job(
            scheduled_send_notifications,
            CronTrigger(hour=t['hour'], minute=t['minute'], timezone=PERTH_TZ),
            id=f"customer_notif_{t['hour']}_{t['minute']}",
            name=f"Customer Notifications - {t['label']}",
            replace_existing=True
        )
        logger.info(f"[SCHEDULER] Customer notifications scheduled: {t['label']} ({t['hour']:02d}:{t['minute']:02d} Perth)")


# ==================== SCHEDULED JOB FUNCTIONS ====================

async def scheduled_send_batch():
    """APScheduler ye function scheduled time pe call karta hai"""
    logger.info("[SCHEDULER] ⏰ Factory batch job triggered")
    result = send_batch()
    logger.info(f"[SCHEDULER] Factory batch result: {result}")


async def scheduled_send_notifications():
    """APScheduler ye function scheduled time pe call karta hai"""
    logger.info("[SCHEDULER] ⏰ Customer notifications job triggered")
    await _process_notifications()


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


async def _process_notifications() -> dict:
    """Aaj ki delivery date wale customers ko SMS + Email bhejo."""
    due_items = notification_queue.get_due_today()

    if not due_items:
        logger.info("[NOTIFICATIONS] No notifications due today")
        return {"status": "success", "sent": 0, "message": "No notifications due today"}

    results = []

    for item in due_items:
        invoice_no     = item['invoice_no']
        customer_name  = item['customer_name']
        customer_email = item['customer_email']
        customer_phone = item['customer_phone']
        consignment_no = item['consignment_number']

        email_sent = False
        sms_sent   = False

        # Email
        if item.get('email_sent'):
            email_sent = True
        elif resend_service and resend_service.enabled:
            email_sent = resend_service.send_customer_notification(
                customer_name=customer_name,
                customer_email=customer_email,
                consignment_number=consignment_no,
                invoice_no=invoice_no,
            )

        # SMS
        if item.get('sms_sent'):
            sms_sent = True
        elif sms_service and sms_service.enabled:
            sms_sent = sms_service._send_sms_api(
                phone=sms_service._format_phone_number(customer_phone),
                message=sms_service._format_message(customer_name, consignment_no),
                invoice_no=invoice_no,
            )

        notification_queue.mark_sent(invoice_no=invoice_no, email_sent=email_sent, sms_sent=sms_sent)

        results.append({"invoice_no": invoice_no, "customer": customer_name, "email_sent": email_sent, "sms_sent": sms_sent})
        logger.info(f"[NOTIFICATIONS] {invoice_no} → email={'✅' if email_sent else '❌'} | sms={'✅' if sms_sent else '❌'}")

    notification_queue.cleanup_old_sent(days_to_keep=7)

    total_email = sum(1 for r in results if r['email_sent'])
    total_sms   = sum(1 for r in results if r['sms_sent'])
    logger.info(f"[NOTIFICATIONS] Done — Processed: {len(results)} | Email: {total_email} | SMS: {total_sms}")

    return {"status": "success", "processed": len(results), "email_sent": total_email, "sms_sent": total_sms, "results": results}


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

        perth_now = datetime.now(PERTH_TZ)
        logger.info("=" * 80)
        logger.info("APPLICATION STARTED SUCCESSFULLY")
        logger.info(f"Google Drive  : {'✅ ENABLED' if google_drive_service.enabled else '❌ DISABLED'}")
        logger.info(f"Resend Email  : {'✅ ENABLED' if resend_service.enabled else '❌ DISABLED'}")
        logger.info(f"SMS Service   : {'✅ ENABLED' if sms_service.enabled else '❌ DISABLED'}")
        logger.info(f"Factory Queue : {queue_manager.count()} items pending")
        logger.info(f"Notif Queue   : {notification_queue.count()} items pending")
        logger.info(f"Perth Time    : {perth_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
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

        # Customer Notification Queue
        notification_queued = notification_queue.add_notification(
            invoice_no=invoice_no,
            customer_name=order_data.get('customer_name', ''),
            customer_email=order_data.get('customer_email', ''),
            customer_phone=order_data.get('customer_phone', ''),
            consignment_number=consignment_number,
            delivery_date=order_data.get('delivery_date_obj'),
        )
        logger.info(f"[NOTIFICATION QUEUE] {'✅ Queued' if notification_queued else '⚠️ Failed'} for {invoice_no}")

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

        # Next scheduled times
        next_batch = next((str(j.next_run_time) for j in scheduler.get_jobs() if 'factory_batch' in j.id), "N/A")
        next_notif = next((str(j.next_run_time) for j in scheduler.get_jobs() if 'customer_notif' in j.id), "N/A")

        return {
            "status"             : "success",
            "invoice_no"         : invoice_no,
            "drive_link_pdf"     : drive_link_pdf or "Upload failed",
            "drive_link_docx"    : drive_link_docx or "Upload failed",
            "products_count"     : len(order_data['items']),
            "consignment_number" : consignment_number or "N/A",
            "customer_notifications": {
                "queued"         : notification_queued,
                "delivery_date"  : str(order_data.get('delivery_date_obj', 'N/A')),
                "tracking_link"  : f"https://mydel.info/Track/48497/{consignment_number}" if consignment_number else "N/A",
                "next_scheduled" : next_notif,
            },
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


@app.post("/trigger-notifications")
async def trigger_notifications_now():
    """
    Customer SMS + Email ABHI manually trigger karo — testing ke liye.
    Sirf aaj ki delivery date wale orders process honge.
    Test ke liye: notification_queue.json me delivery_date = aaj ki date set karo.
    """
    logger.info("[MANUAL TRIGGER] /trigger-notifications")
    result = await _process_notifications()
    result['triggered_by'] = 'manual'
    return result


@app.get("/scheduler-status")
async def scheduler_status():
    """Scheduler jobs aur next run times dekho."""
    perth_now = datetime.now(PERTH_TZ)
    schedule  = get_schedule_config()

    return {
        "scheduler_running" : scheduler.running,
        "perth_time_now"    : perth_now.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "jobs"              : [{"name": j.name, "next_run": str(j.next_run_time)} for j in scheduler.get_jobs()],
        "config_times"      : {
            "factory_batch"          : schedule.get('factory_batch', {}).get('times_perth', []),
            "customer_notifications" : schedule.get('customer_notifications', {}).get('times_perth', []),
        },
        "how_to_change": "home_delivery.json → schedule → times_perth → hour/minute → app restart"
    }


@app.get("/")
async def root():
    email_mode  = "disabled"
    if resend_service and resend_service.enabled:
        email_mode = "testing" if resend_service.testing_mode else "production"
    sms_mode = "disabled"
    if sms_service and sms_service.enabled:
        sms_mode = "testing" if sms_service.testing_mode else "production"

    from services.ai_service import TommySugoCalendar
    current_event = TommySugoCalendar.get_current_event()
    event_info    = f"{current_event['name']} (in {current_event['days_until']} days)" if current_event else "No active events"

    return {
        "status"      : "online",
        "version"     : "14.0 - APScheduler (No Railway Cron needed)",
        "perth_time"  : datetime.now(PERTH_TZ).strftime('%Y-%m-%d %H:%M:%S %Z'),
        "google_drive": "enabled" if google_drive_service.enabled else "disabled",
        "email"       : {"service": "enabled" if resend_service and resend_service.enabled else "disabled", "mode": email_mode, "factory_queue": queue_manager.count()},
        "sms"         : {"service": "enabled" if sms_service and sms_service.enabled else "disabled", "mode": sms_mode},
        "notifications": notification_queue.get_stats(),
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
        "factory_email_queue"        : {"mode": "testing" if (resend_service and resend_service.testing_mode) else "production", "total": queue_manager.count(), "items": queue_manager.get_all()},
        "customer_notification_queue": {"stats": notification_queue.get_stats(), "items": notification_queue.get_all()},
    }


@app.get("/events")
async def view_events():
    from services.ai_service import TommySugoCalendar
    current_event = TommySugoCalendar.get_current_event()
    if current_event:
        return {"status": "ACTIVE EVENT", "event": {"name": current_event['name'], "date": current_event['date'], "days_until": current_event['days_until'], "marketing_messages": current_event['messages']}}
    return {"status": "NO ACTIVE EVENTS", "message": "No marketing events in current window"}


# Run: uvicorn main:app --host 0.0.0.0 --port 8000 --reload