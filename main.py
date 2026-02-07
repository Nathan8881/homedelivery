"""
Home Delivery System - Railway Compatible Version
With Built-in Tommy Sugo Marketing Calendar
"""
from fastapi import FastAPI, Request, HTTPException
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from pathlib import Path
from dotenv import load_dotenv

# Import services
from services import (
    OpenAIService,
    TransvirtualService,
    ResendEmailService,
    GoogleDriveService,
    MobileMessageService,
    generate_barcode,
    JSONQueueManager
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
    handlers=[
        logging.FileHandler('home_delivery.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== FASTAPI APP ====================
app = FastAPI(title="Home Delivery - Railway Compatible", version="11.0")

# ==================== GLOBAL INSTANCES ====================
base_path = Path(__file__).parent
config_manager = ConfigManager(base_path)
google_drive_service = GoogleDriveService()
resend_service = None
sms_service = None
queue_manager = JSONQueueManager()


# ==================== BATCH SEND FUNCTION ====================
def send_batch():
    """
    Send accumulated PDF URLs to factory and clear the queue
    This function is called by Railway Cron service via HTTP request
    """
    global queue_manager
    
    if not resend_service or not resend_service.enabled:
        logger.info("[BATCH] Email service disabled - skipping")
        return {"status": "skipped", "reason": "email_disabled"}
    
    queued_items = queue_manager.get_all()
    
    if not queued_items:
        logger.info("[BATCH] No PDFs in queue")
        return {"status": "success", "sent": 0, "message": "Queue empty"}
    
    logger.info("=" * 80)
    logger.info(f"[BATCH] 📧 Sending batch of {len(queued_items)} PDFs")
    logger.info("-" * 80)
    
    # Extract URLs
    urls = [item['pdf_url'] for item in queued_items if item.get('pdf_url')]
    
    # Send email
    success = resend_service.send_packing_slips(urls)
    
    if success:
        logger.info(f"[BATCH] ✅ Batch sent successfully")
        
        # Delete local files ONLY if email sent successfully
        for item in queued_items:
            pdf_url = item.get('pdf_url')
            
            if pdf_url:  # Google Drive link exists
                try:
                    pdf_path = item.get('pdf_path')
                    docx_path = item.get('docx_path')
                    barcode_path = item.get('barcode_path')
                    
                    # Delete local files
                    for path in [pdf_path, docx_path, barcode_path]:
                        if path and Path(path).exists():
                            os.remove(path)
                            logger.info(f"[CLEANUP] 🗑️  Deleted: {Path(path).name}")
                    
                    logger.info(f"[CLEANUP] ✅ Files cleaned (saved on Drive)")
                except Exception as e:
                    logger.error(f"[CLEANUP] ❌ Delete failed: {e}")
            else:
                logger.warning(f"[CLEANUP] ⚠️  No Drive link - keeping local file")
        
        # Clear the queue
        queue_manager.clear()
        logger.info(f"[BATCH] 🧹 Queue cleared")
        logger.info("=" * 80)
        
        return {"status": "success", "sent": len(urls), "cleared": len(queued_items)}
    else:
        logger.error(f"[BATCH] ❌ Batch send failed - keeping files for retry")
        logger.info("=" * 80)
        return {"status": "failed", "sent": 0, "kept": len(queued_items)}


# ==================== STARTUP ====================
@app.on_event("startup")
async def startup_event():
    global resend_service, sms_service
    try:
        config_manager.initialize()
        
        # Load default config
        default_config = config_manager.load_form_config('home_delivery.json')
        email_config = default_config.get('email', {})
        sms_config = default_config.get('sms', {})
        
        # Initialize services
        resend_service = ResendEmailService(email_config)
        sms_service = MobileMessageService(sms_config)
        
        logger.info("=" * 80)
        logger.info("APPLICATION STARTED SUCCESSFULLY")
        logger.info(f"Google Drive: {'✅ ENABLED' if google_drive_service.enabled else '❌ DISABLED'}")
        logger.info(f"Resend Email: {'✅ ENABLED' if resend_service.enabled else '❌ DISABLED'}")
        if resend_service.enabled:
            mode = "TESTING" if resend_service.testing_mode else "PRODUCTION"
            logger.info(f"Email Mode: {mode}")
        logger.info(f"SMS Service: {'✅ ENABLED' if sms_service.enabled else '❌ DISABLED'}")
        if sms_service.enabled:
            mode = "TESTING" if sms_service.testing_mode else "PRODUCTION"
            logger.info(f"SMS Mode: {mode}")
        logger.info(f"Queue: {queue_manager.count()} items pending")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise


# ==================== API ENDPOINTS ====================
@app.post("/jotform/webhook")
async def webhook_handler(request: Request):
    """Main webhook handler for Jotform submissions"""
    global queue_manager
    
    try:
        # Parse request
        form = await request.form()
        data = dict(form)
        raw = json.loads(data.get("rawRequest", "{}"))
        
        # Get form configuration
        form_id = extract_form_id(raw)
        if not form_id:
            logger.error("Form ID extraction failed")
            raise HTTPException(status_code=400, detail="Could not determine form_id")
        
        logger.info(f"Processing form: {form_id}")
        config = config_manager.get_config_for_form(form_id)
        
        # Extract order data
        order_data = {}
        for field_key, field_config in config['fields'].items():
            order_data[field_key] = extract_field_value(raw, field_config)
        
        order_data['delivery_date_obj'] = raw.get('q6_desiredDelivery6', {})
        order_data["items"] = extract_products(raw, config)
        order_data["total_boxes"] = len(order_data["items"])
        
        invoice_no = order_data.get('invoice_no', 'UNKNOWN').replace('# ', '').strip()
        logger.info(f"Order: {invoice_no}, Products: {len(order_data['items'])}")
        
        # ==================== AI PROCESSING ====================
        openai_service = OpenAIService(config)
        
        # Step 1: Validate customer data
        order_data = openai_service.validate_and_fix_data(order_data)
        
        # Step 2: Generate AI feedback response
        customer_feedback = order_data.get('customer_love_note', '').strip()
        feedback_enabled = order_data.get('feedback_enabled', '').strip().lower()
        
        if customer_feedback and feedback_enabled == "yes":
            feedback_response = openai_service.generate_feedback_response(
                customer_feedback, 
                order_data.get('customer_name', 'Customer')
            )
            order_data['ai_feedback_response'] = feedback_response
        else:
            order_data['ai_feedback_response'] = ""
        
        # Step 3: Generate EVENT-AWARE product recommendation
        # Calendar checking happens inside AI service (no separate service needed!)
        is_gift_order = bool(order_data.get('gift_recipient', '').strip())
        all_products_config = config.get('pdf', {}).get('messages', {}).get('all_products', [])
        
        ai_recommendation = openai_service.generate_product_recommendation(
            order_data['items'], 
            all_products_config,
            is_gift_order=is_gift_order
        )
        order_data['ai_recommendation'] = ai_recommendation
        
        # Transvirtual Integration
        transvirtual_service = TransvirtualService(config)
        transvirtual_result = transvirtual_service.create_consignment(order_data)
        
        barcode_path = ""
        if transvirtual_result and transvirtual_result.get('barcode_number'):
            order_data['barcode_number'] = transvirtual_result['barcode_number']
            order_data['consignment_number'] = transvirtual_result.get('consignment_number', 'N/A')
            order_data['consignment_id'] = transvirtual_result.get('consignment_id', 'N/A')
            barcode_path = generate_barcode(
                transvirtual_result['barcode_number'],
                base_path / 'barcodes'
            )
        else:
            logger.warning("[WARNING] No Transvirtual barcode")
        
        # CREATE PDF
        pdf_path = create_packing_slip_pdf(order_data, config, barcode_path, base_path)
        
        # CREATE DOCX
        logger.info("=" * 80)
        logger.info("[DOCX CREATION] 📝 Creating DOCX file...")
        docx_path = create_packing_slip_docx(order_data, config, barcode_path, base_path)
        if docx_path:
            logger.info(f"[DOCX CREATION] ✅ DOCX Created: {docx_path}")
        else:
            logger.error("[DOCX CREATION] ❌ DOCX creation failed")
        logger.info("=" * 80)
        
        # SEND SMS NOTIFICATION
        if sms_service and sms_service.enabled:
            sms_service.send_delivery_notification(
                customer_name=order_data.get('customer_name', ''),
                customer_phone=order_data.get('customer_phone', ''),
                invoice_no=invoice_no
            )
        
        # UPLOAD TO GOOGLE DRIVE
        order_date = datetime.now()
        drive_link_pdf = google_drive_service.upload_file(pdf_path, order_date, invoice_no, "pdf")
        drive_link_docx = ""
        if docx_path:
            drive_link_docx = google_drive_service.upload_file(docx_path, order_date, invoice_no, "docx")
        
        # Handle email based on mode
        email_sent = False
        if drive_link_pdf and resend_service and resend_service.enabled:
            if resend_service.testing_mode:
                # TESTING MODE: Send immediately
                logger.info("[EMAIL] 🧪 TESTING MODE - Sending email immediately...")
                email_sent = resend_service.send_packing_slips([drive_link_pdf])
                
                # Delete files after email sent
                if email_sent and drive_link_pdf:
                    try:
                        for path in [pdf_path, docx_path, barcode_path]:
                            if path and Path(path).exists():
                                os.remove(path)
                                logger.info(f"[CLEANUP] 🗑️  Deleted: {Path(path).name}")
                        
                        logger.info(f"[CLEANUP] ✅ All files cleaned (saved on Drive)")
                    except Exception as e:
                        logger.error(f"[CLEANUP] ❌ Delete failed: {e}")
                else:
                    logger.warning(f"[CLEANUP] ⚠️  Files NOT deleted - keeping local copies")
            else:
                # PRODUCTION MODE: Add to JSON queue
                queue_item = {
                    'pdf_url': drive_link_pdf,
                    'pdf_path': str(pdf_path),
                    'docx_path': str(docx_path) if docx_path else None,
                    'barcode_path': str(barcode_path) if barcode_path else None,
                    'invoice_no': invoice_no,
                    'timestamp': datetime.now().isoformat()
                }
                
                queue_manager.add(queue_item)
                logger.info(f"[QUEUE] ✅ Added to JSON queue (Total: {queue_manager.count()})")
        else:
            if not drive_link_pdf:
                logger.warning(f"[CLEANUP] ⚠️  Google Drive upload failed - keeping local files")
            else:
                logger.info(f"[CLEANUP] 📁 Email disabled - files saved to Google Drive only")
        
        return {
            "status": "success",
            "form_id": form_id,
            "invoice_no": invoice_no,
            "pdf_path": str(pdf_path),
            "docx_path": str(docx_path) if docx_path else None,
            "drive_link_pdf": drive_link_pdf if drive_link_pdf else "Upload failed",
            "drive_link_docx": drive_link_docx if drive_link_docx else "Upload failed or not converted",
            "products_count": len(order_data['items']),
            "barcode_number": order_data.get('barcode_number', 'N/A'),
            "email": {
                "mode": "testing" if resend_service and resend_service.testing_mode else "production",
                "sent_immediately": email_sent,
                "queued": not email_sent and bool(drive_link_pdf),
                "queue_size": queue_manager.count()
            },
            "ai_features": {
                "feedback_enabled": feedback_enabled,
                "feedback_response": order_data.get('ai_feedback_response', 'N/A'),
                "recommendation": order_data.get('ai_recommendation', 'N/A'),
                "is_gift_order": is_gift_order
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send-batch")
async def send_batch_endpoint():
    """
    Endpoint triggered by Railway Cron service
    
    Railway Cron Setup:
    1. Create new service in Railway
    2. Set Cron Schedule: "0 5,9 * * *" (1PM & 5PM Perth time in UTC)
    3. Command: curl -X POST https://your-app.railway.app/send-batch
    """
    logger.info("[ENDPOINT] /send-batch triggered")
    result = send_batch()
    return result


@app.get("/")
async def root():
    """Health check endpoint"""
    email_mode = "disabled"
    if resend_service and resend_service.enabled:
        email_mode = "testing" if resend_service.testing_mode else "production"
    
    sms_mode = "disabled"
    if sms_service and sms_service.enabled:
        sms_mode = "testing" if sms_service.testing_mode else "production"
    
    # Check for active marketing events
    from services.ai_service import TommySugoCalendar
    current_event = TommySugoCalendar.get_current_event()
    
    event_info = "No active events"
    if current_event:
        event_info = f"{current_event['name']} (in {current_event['days_until']} days)"
    
    return {
        "status": "online",
        "service": "Home Delivery - Railway Compatible",
        "version": "11.0 - JSON Queue + Built-in Marketing Calendar",
        "google_drive": "enabled" if google_drive_service.enabled else "disabled",
        "email": {
            "service": "enabled" if resend_service and resend_service.enabled else "disabled",
            "mode": email_mode,
            "queued_pdfs": queue_manager.count() if email_mode == "production" else 0
        },
        "sms": {
            "service": "enabled" if sms_service and sms_service.enabled else "disabled",
            "mode": sms_mode
        },
        "marketing": {
            "active_event": event_info,
            "calendar_year": datetime.now().year,
            "note": "Calendar checking is FREE - no LLM calls for date checking!"
        },
        "railway_cron": {
            "endpoint": "/send-batch",
            "note": "Use Railway Cron service to trigger this endpoint at scheduled times"
        }
    }


@app.get("/forms")
async def list_forms():
    """List all registered forms"""
    if not config_manager.config_map:
        return {"forms": [], "error": "Config not loaded"}
    
    forms = []
    for form_id, info in config_manager.config_map.get('forms', {}).items():
        forms.append({
            "form_id": form_id,
            "name": info['name'],
            "config_file": info['config_file']
        })
    return {"forms": forms}


@app.get("/queue")
async def view_queue():
    """View current email queue"""
    if not resend_service or not resend_service.enabled:
        return {"error": "Email service disabled"}
    
    if resend_service.testing_mode:
        return {
            "mode": "testing",
            "message": "Testing mode - emails sent immediately, no queue"
        }
    
    queued_items = queue_manager.get_all()
    
    return {
        "mode": "production",
        "total_queued": len(queued_items),
        "items": queued_items,
        "note": "Queue stored in JSON file - persists across Railway restarts!"
    }


@app.get("/events")
async def view_events():
    """View Tommy Sugo marketing calendar status"""
    from services.ai_service import TommySugoCalendar
    
    current_event = TommySugoCalendar.get_current_event()
    
    if current_event:
        return {
            "status": "ACTIVE EVENT",
            "event": {
                "name": current_event['name'],
                "date": current_event['date'],
                "days_until": current_event['days_until'],
                "marketing_messages": current_event['messages']
            },
            "note": "This event context is automatically added to AI recommendations!"
        }
    else:
        return {
            "status": "NO ACTIVE EVENTS",
            "message": "No marketing events in current window",
            "note": "AI will generate general product recommendations"
        }


# Run: uvicorn main:app --host 0.0.0.0 --port 8000 --reload