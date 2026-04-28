"""
Email Service - Resend Integration with Multiple Recipients Support

FIX v14.4:
  - Testing mode mein customer_email empty hone par bhi email send hogi
    (pehle empty email check ne testing emails bhi block kar di thi)
  - Email validation sirf PRODUCTION mode mein hogi
  - Testing mode mein sirf test_emails ko email jaayegi, customer ko nahi
"""
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime
import resend

logger = logging.getLogger(__name__)


class ResendEmailService:
    def __init__(self, email_config: Dict = None):
        self.api_key = os.getenv('RESEND_API_KEY', '')
        self.config = email_config or {}
        self.enabled = self.config.get('enabled', False) and bool(self.api_key)
        self.testing_mode = self.config.get('testing_mode', False)

        # ✅ Admin BCC — customer emails ki copy yahan bhi jaayegi
        self.admin_bcc_emails = self.config.get('recipient_emails', [])

        if self.enabled:
            resend.api_key = self.api_key
            mode = "TESTING MODE" if self.testing_mode else "PRODUCTION MODE"
            logger.info(f"[RESEND] ✅ Email service enabled - {mode}")
            if self.admin_bcc_emails:
                logger.info(f"[RESEND] 📋 Admin BCC for customer emails: {', '.join(self.admin_bcc_emails)}")
        else:
            logger.warning("[RESEND] ❌ Email service disabled")

    def _generate_tracking_link(self, consignment_number: str) -> str:
        if not consignment_number:
            return "Tracking link not available"
        base_url = "https://mydel.info/Track/48497"
        return f"{base_url}/{consignment_number}"

    def _get_first_name(self, full_name: str) -> str:
        if not full_name or not full_name.strip():
            return "Customer"
        if isinstance(full_name, dict):
            first = full_name.get('first', '')
            if first:
                return first
            full_name = f"{full_name.get('first', '')} {full_name.get('last', '')}".strip()
        parts = str(full_name).split()
        return parts[0] if parts else "Customer"

    # ==================== CUSTOMER NOTIFICATION (Delivery Date Day) ====================

    def send_customer_notification(
        self,
        customer_name: str,
        customer_email: str,
        consignment_number: str = "",
        invoice_no: str = ""
    ) -> bool:
        """
        Delivery date ke din subah customer ko bhejo — Out for Delivery
        TESTING MODE  → sirf admin/test emails ko jaayegi (customer ko nahi)
        PRODUCTION MODE → customer ko jaayegi + BCC admin
        """
        if not self.enabled:
            logger.warning("[RESEND] ⏭️  Customer email skipped - service disabled")
            return False

        # FIX v14.4: Email validation sirf PRODUCTION mein
        # Testing mode mein customer_email empty bhi ho toh chalega — test_emails use hongi
        if not self.testing_mode:
            if not customer_email or not customer_email.strip():
                logger.warning(f"[RESEND] ⏭️  Customer email skipped - no email for invoice {invoice_no}")
                return False

        try:
            sender_name  = self.config.get('sender_name', 'Tommy Sugo')
            sender_email = self.config.get('sender_email', 'noreply@tommysugo.com')

            first_name    = self._get_first_name(customer_name)
            tracking_link = self._generate_tracking_link(consignment_number)
            subject       = "Your Tommy Sugo Order is Out for Delivery! 🚚"

            email_body = self._build_outfordelivery_body(first_name, tracking_link)

            if self.testing_mode:
                # TESTING MODE: sirf test_emails ko bhejo, customer ko nahi
                test_emails = self.config.get('testing_emails', self.admin_bcc_emails)
                if not test_emails:
                    logger.warning("[RESEND] 🧪 TESTING MODE - No test emails configured, skipping")
                    return False

                logger.info("[RESEND] 🧪 TESTING MODE - Sending to admin test emails only (not customer)")
                logger.info(f"  Original Customer : {customer_name} <{customer_email or 'N/A'}>")
                logger.info(f"  Sending To        : {', '.join(test_emails)}")

                params = {
                    "from": f"{sender_name} <{sender_email}>",
                    "to": test_emails,
                    "subject": f"[TEST] {subject}",
                    "html": email_body
                }

                email = resend.Emails.send(params)
                logger.info(f"[RESEND] ✅ Test notification sent | ID: {email.get('id', 'N/A')}")
                return True

            # PRODUCTION MODE: customer ko bhejo + BCC admin
            params = {
                "from": f"{sender_name} <{sender_email}>",
                "to": [customer_email],
                "subject": subject,
                "html": email_body
            }

            if self.admin_bcc_emails:
                params["bcc"] = self.admin_bcc_emails

            logger.info("=" * 80)
            logger.info("[RESEND] 📧 Sending scheduled customer notification...")
            logger.info(f"  Invoice     : {invoice_no}")
            logger.info(f"  Customer    : {customer_name}")
            logger.info(f"  Email       : {customer_email}")
            logger.info(f"  Consignment : {consignment_number}")
            logger.info(f"  Tracking    : {tracking_link}")

            email = resend.Emails.send(params)
            logger.info(f"[RESEND] ✅ Scheduled notification sent | ID: {email.get('id', 'N/A')}")
            logger.info("=" * 80)
            return True

        except Exception as e:
            logger.error(f"[RESEND] ❌ Scheduled notification failed for {invoice_no}: {e}")
            return False

    # ==================== TRANSVIRTUAL WEBHOOK — IN TRANSIT ====================

    def send_intransit_notification(
        self,
        customer_name: str,
        customer_email: str,
        consignment_number: str = "",
    ) -> bool:
        """
        TransVirtual webhook se trigger — courier ne factory se order utha liya
        Status: InTransit
        TESTING MODE  → sirf admin/test emails ko jaayegi (customer ko nahi)
        PRODUCTION MODE → customer ko jaayegi + BCC admin
        """
        if not self.enabled:
            logger.warning("[RESEND] ⏭️  InTransit email skipped - service disabled")
            return False

        # FIX v14.4: Email validation sirf PRODUCTION mein
        # Testing mode mein customer_email empty bhi ho toh chalega — test_emails use hongi
        if not self.testing_mode:
            if not customer_email or not customer_email.strip():
                logger.warning("[RESEND] ⏭️  InTransit email skipped - no email provided")
                return False

        try:
            sender_name   = self.config.get('sender_name', 'Tommy Sugo')
            sender_email  = self.config.get('sender_email', 'noreply@tommysugo.com')
            first_name    = self._get_first_name(customer_name)
            tracking_link = self._generate_tracking_link(consignment_number)
            subject       = "Your Tommy Sugo Order is Out for Delivery! 🚚"

            email_body = self._build_outfordelivery_body(first_name, tracking_link)

            if self.testing_mode:
                # TESTING MODE: sirf test_emails ko bhejo, customer ko nahi
                test_emails = self.config.get('testing_emails', self.admin_bcc_emails)
                if not test_emails:
                    logger.warning("[RESEND] 🧪 TESTING MODE - No test emails configured, skipping")
                    return False

                logger.info("[RESEND] 🧪 TESTING MODE - Sending to admin test emails only (not customer)")
                logger.info(f"  Original Customer : {customer_name} <{customer_email or 'N/A'}>")
                logger.info(f"  Sending To        : {', '.join(test_emails)}")

                params = {
                    "from": f"{sender_name} <{sender_email}>",
                    "to": test_emails,
                    "subject": f"[TEST] {subject}",
                    "html": email_body
                }

                logger.info("=" * 80)
                logger.info("[TRANSVIRTUAL → RESEND] 📧 Sending InTransit notification (TEST)...")
                logger.info(f"  Customer    : {customer_name}")
                logger.info(f"  Consignment : {consignment_number}")
                logger.info(f"  Tracking    : {tracking_link}")

                email = resend.Emails.send(params)
                logger.info(f"[RESEND] ✅ InTransit test email sent | ID: {email.get('id', 'N/A')}")
                logger.info("=" * 80)
                return True

            # PRODUCTION MODE: customer ko bhejo + BCC admin
            params = {
                "from": f"{sender_name} <{sender_email}>",
                "to": [customer_email],
                "subject": subject,
                "html": email_body
            }

            if self.admin_bcc_emails:
                params["bcc"] = self.admin_bcc_emails
                logger.info(f"  Admin BCC   : {', '.join(self.admin_bcc_emails)}")

            logger.info("=" * 80)
            logger.info("[TRANSVIRTUAL → RESEND] 📧 Sending InTransit notification...")
            logger.info(f"  Customer    : {customer_name}")
            logger.info(f"  Email       : {customer_email}")
            logger.info(f"  Consignment : {consignment_number}")
            logger.info(f"  Tracking    : {tracking_link}")

            email = resend.Emails.send(params)
            logger.info(f"[RESEND] ✅ InTransit email sent | ID: {email.get('id', 'N/A')}")
            logger.info("=" * 80)
            return True

        except Exception as e:
            logger.error(f"[RESEND] ❌ InTransit email failed: {e}")
            return False

    # ==================== TRANSVIRTUAL WEBHOOK — DELIVERED ====================

    def send_delivered_notification(
        self,
        customer_name: str,
        customer_email: str,
        consignment_number: str = "",
    ) -> bool:
        """
        TransVirtual webhook se trigger — order customer tak deliver ho gaya
        Status: Delivered
        TESTING MODE  → sirf admin/test emails ko jaayegi (customer ko nahi)
        PRODUCTION MODE → customer ko jaayegi + BCC admin
        """
        if not self.enabled:
            logger.warning("[RESEND] ⏭️  Delivered email skipped - service disabled")
            return False

        # FIX v14.4: Email validation sirf PRODUCTION mein
        # Testing mode mein customer_email empty bhi ho toh chalega — test_emails use hongi
        if not self.testing_mode:
            if not customer_email or not customer_email.strip():
                logger.warning("[RESEND] ⏭️  Delivered email skipped - no email provided")
                return False

        try:
            sender_name   = self.config.get('sender_name', 'Tommy Sugo')
            sender_email  = self.config.get('sender_email', 'noreply@tommysugo.com')
            first_name    = self._get_first_name(customer_name)
            tracking_link = self._generate_tracking_link(consignment_number)
            subject       = "Your Tommy Sugo Order Has Been Delivered! 🎉"

            email_body = self._build_delivered_body(first_name, tracking_link)

            if self.testing_mode:
                # TESTING MODE: sirf test_emails ko bhejo, customer ko nahi
                test_emails = self.config.get('testing_emails', self.admin_bcc_emails)
                if not test_emails:
                    logger.warning("[RESEND] 🧪 TESTING MODE - No test emails configured, skipping")
                    return False

                logger.info("[RESEND] 🧪 TESTING MODE - Sending to admin test emails only (not customer)")
                logger.info(f"  Original Customer : {customer_name} <{customer_email or 'N/A'}>")
                logger.info(f"  Sending To        : {', '.join(test_emails)}")

                params = {
                    "from": f"{sender_name} <{sender_email}>",
                    "to": test_emails,
                    "subject": f"[TEST] {subject}",
                    "html": email_body
                }

                logger.info("=" * 80)
                logger.info("[TRANSVIRTUAL → RESEND] 📧 Sending Delivered notification (TEST)...")
                logger.info(f"  Customer    : {customer_name}")
                logger.info(f"  Consignment : {consignment_number}")
                logger.info(f"  Tracking    : {tracking_link}")

                email = resend.Emails.send(params)
                logger.info(f"[RESEND] ✅ Delivered test email sent | ID: {email.get('id', 'N/A')}")
                logger.info("=" * 80)
                return True

            # PRODUCTION MODE: customer ko bhejo + BCC admin
            params = {
                "from": f"{sender_name} <{sender_email}>",
                "to": [customer_email],
                "subject": subject,
                "html": email_body
            }

            if self.admin_bcc_emails:
                params["bcc"] = self.admin_bcc_emails
                logger.info(f"  Admin BCC   : {', '.join(self.admin_bcc_emails)}")

            logger.info("=" * 80)
            logger.info("[TRANSVIRTUAL → RESEND] 📧 Sending Delivered notification...")
            logger.info(f"  Customer    : {customer_name}")
            logger.info(f"  Email       : {customer_email}")
            logger.info(f"  Consignment : {consignment_number}")
            logger.info(f"  Tracking    : {tracking_link}")

            email = resend.Emails.send(params)
            logger.info(f"[RESEND] ✅ Delivered email sent | ID: {email.get('id', 'N/A')}")
            logger.info("=" * 80)
            return True

        except Exception as e:
            logger.error(f"[RESEND] ❌ Delivered email failed: {e}")
            return False

    # ==================== FACTORY PACKING SLIPS ====================

    def send_packing_slips(self, pdf_urls: List[str]) -> bool:
        """
        Send packing slip URLs to factory via email (multiple recipients supported).
        """
        if not self.enabled or not pdf_urls:
            logger.warning("[RESEND] ⏭️  Factory email skipped - disabled or no PDFs")
            return False

        try:
            sender_name = self.config.get('sender_name', 'Tommy Sugo')
            sender_email = self.config.get('sender_email', 'noreply@tommysugo.com')

            recipients = self.config.get('recipient_emails', [])
            if not recipients:
                single_recipient = self.config.get('recipient_email', '')
                if single_recipient:
                    recipients = [single_recipient]
            if not recipients:
                recipients = ['factory@tommysugo.com']
                logger.warning("[RESEND] ⚠️  No recipients in config - using default")

            subject_template = self.config.get('subject_template', 'Packing Slips Batch - {date}')
            current_date = datetime.now().strftime('%d %b %Y')
            subject = subject_template.replace('{date}', current_date)

            body_template = self.config.get('body_template', {})
            email_body  = f"<h2>{body_template.get('title', 'Packing Slips - Daily Batch')}</h2><br>"
            email_body += f"<p>{body_template.get('greeting', 'Hello Team,')}</p><br>"
            email_body += f"<p>{body_template.get('intro', 'Please find the packing slips for today:')}</p><br>"
            email_body += f"<p><strong>Total slips:</strong> {len(pdf_urls)}</p><br>"
            email_body += "<ul>"
            for idx, url in enumerate(pdf_urls, 1):
                email_body += f"<li><a href='{url}'>Packing Slip #{idx}</a></li>"
            email_body += "</ul><br>"
            email_body += f"<p>{body_template.get('footer', 'Best regards,<br>Tommy Sugo System')}</p>"

            params = {
                "from": f"{sender_name} <{sender_email}>",
                "to": recipients,
                "subject": subject,
                "html": email_body
            }

            email = resend.Emails.send(params)
            logger.info(f"[RESEND] ✅ Factory email sent | To: {', '.join(recipients)} | PDFs: {len(pdf_urls)} | ID: {email.get('id', 'N/A')}")
            return True

        except Exception as e:
            logger.error(f"[RESEND] ❌ Factory email failed: {e}")
            return False

    # ==================== SHARED EMAIL BODY BUILDERS ====================

    def _build_outfordelivery_body(self, first_name: str, tracking_link: str) -> str:
        return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9;">
            <div style="background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-bottom: 20px;">Hi {first_name},</h2>
                <p style="color: #555; line-height: 1.6; font-size: 16px;">
                    Your Tommy Sugo order is now out for delivery and will be arriving at your location shortly.
                </p>
                <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 4px;">
                    <p style="color: #856404; margin: 0; font-size: 14px;">
                        <strong>💡 Quality Tip:</strong> To maintain the best quality, we kindly recommend bringing
                        the products inside as soon as they arrive and placing them straight into the freezer.
                    </p>
                </div>
                <div style="margin: 30px 0; text-align: center;">
                    <p style="color: #555; margin-bottom: 15px; font-size: 16px;"><strong>Track your delivery:</strong></p>
                    <a href="{tracking_link}"
                       style="display: inline-block; background-color: #28a745; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">
                        📦 Track Order
                    </a>
                    <p style="color: #888; font-size: 12px; margin-top: 10px;">
                        Or copy this link: <a href="{tracking_link}" style="color: #007bff;">{tracking_link}</a>
                    </p>
                </div>
                <p style="color: #555; line-height: 1.6; font-size: 16px; margin-top: 30px;">
                    Thank you for choosing Tommy Sugo.
                </p>
                <p style="color: #555; line-height: 1.6; font-size: 16px;">
                    Warm regards,<br><strong>Nathan and the Tommy Sugo Team</strong>
                </p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    This is an automated message. Please do not reply to this email.
                </p>
            </div>
        </div>
        """

    def _build_delivered_body(self, first_name: str, tracking_link: str) -> str:
        return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9;">
            <div style="background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-bottom: 20px;">Hi {first_name},</h2>
                <p style="color: #555; line-height: 1.6; font-size: 16px;">
                    Great news! Your Tommy Sugo order has been successfully delivered. 🎉
                </p>
                <div style="background-color: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 20px 0; border-radius: 4px;">
                    <p style="color: #155724; margin: 0; font-size: 14px;">
                        <strong>💡 Quality Tip:</strong> If you haven't already, please place the products
                        in the freezer to keep them in perfect condition.
                    </p>
                </div>
                <div style="margin: 30px 0; text-align: center;">
                    <p style="color: #555; margin-bottom: 15px; font-size: 16px;"><strong>View delivery details:</strong></p>
                    <a href="{tracking_link}"
                       style="display: inline-block; background-color: #28a745; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">
                        📦 View Delivery
                    </a>
                    <p style="color: #888; font-size: 12px; margin-top: 10px;">
                        Or copy this link: <a href="{tracking_link}" style="color: #007bff;">{tracking_link}</a>
                    </p>
                </div>
                <p style="color: #555; line-height: 1.6; font-size: 16px; margin-top: 30px;">
                    We truly appreciate your support and hope you enjoy your meal!
                </p>
                <p style="color: #555; line-height: 1.6; font-size: 16px;">
                    Warm regards,<br><strong>Nathan and the Tommy Sugo Team</strong>
                </p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    This is an automated message. Please do not reply to this email.
                </p>
            </div>
        </div>
        """