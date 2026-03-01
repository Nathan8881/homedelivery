"""
Email Service - Resend Integration with Multiple Recipients Support
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
        
        if self.enabled:
            resend.api_key = self.api_key
            mode = "TESTING MODE" if self.testing_mode else "PRODUCTION MODE"
            logger.info(f"[RESEND] ✅ Email service enabled - {mode}")
        else:
            logger.warning("[RESEND] ❌ Email service disabled")
    
    def _generate_tracking_link(self, consignment_number: str) -> str:
        """
        Generate tracking link from consignment number
        
        Args:
            consignment_number: Consignment number from Transvirtual
            
        Returns:
            Full tracking URL
        """
        if not consignment_number:
            return "Tracking link not available"
        
        # Base URL is static, only consignment number changes
        base_url = "https://mydel.info/Track/48497"
        return f"{base_url}/{consignment_number}"
    
    def _get_first_name(self, full_name: str) -> str:
        """
        Extract first name from full name
        
        Args:
            full_name: Customer's full name
            
        Returns:
            First name only
        """
        if not full_name or not full_name.strip():
            return "Customer"
        
        # Handle name object from Jotform
        if isinstance(full_name, dict):
            first = full_name.get('first', '')
            if first:
                return first
            # Fallback to full name if available
            full_name = f"{full_name.get('first', '')} {full_name.get('last', '')}".strip()
        
        # Split and get first name
        parts = str(full_name).split()
        return parts[0] if parts else "Customer"
    
    def send_customer_notification(
        self,
        customer_name: str,
        customer_email: str,
        consignment_number: str = "",
        invoice_no: str = ""
    ) -> bool:
        """
        Send delivery notification email to customer with tracking link
        
        Args:
            customer_name: Customer's full name
            customer_email: Customer's email address
            consignment_number: Consignment number from Transvirtual
            invoice_no: Invoice number for logging
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("[RESEND] ⏭️  Customer email skipped - service disabled")
            return False
        
        if not customer_email or not customer_email.strip():
            logger.warning(f"[RESEND] ⏭️  Customer email skipped - no email for invoice {invoice_no}")
            return False
        
        try:
            # Get email settings from config
            sender_name = self.config.get('sender_name', 'Tommy Sugo')
            sender_email = self.config.get('sender_email', 'noreply@tommysugo.com')
            
            first_name = self._get_first_name(customer_name)
            tracking_link = self._generate_tracking_link(consignment_number)
            
            # Email subject
            subject = "Your Tommy Sugo Order is Out for Delivery! 🚚"
            
            # Build HTML email body
            email_body = f"""
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
                        <p style="color: #555; margin-bottom: 15px; font-size: 16px;">
                            <strong>Track your delivery:</strong>
                        </p>
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
                        Warm regards,<br>
                        <strong>Nathan and the Tommy Sugo Team</strong>
                    </p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    
                    <p style="color: #999; font-size: 12px; text-align: center;">
                        This is an automated message. Please do not reply to this email.
                    </p>
                </div>
            </div>
            """
            
            # Send email
            params = {
                "from": f"{sender_name} <{sender_email}>",
                "to": [customer_email],
                "subject": subject,
                "html": email_body
            }
            
            logger.info("=" * 80)
            logger.info("[RESEND] 📧 Sending customer notification email...")
            logger.info(f"  Invoice: {invoice_no}")
            logger.info(f"  Customer: {customer_name}")
            logger.info(f"  Email: {customer_email}")
            logger.info(f"  Consignment: {consignment_number}")
            logger.info(f"  Tracking: {tracking_link}")
            
            if self.testing_mode:
                logger.info("-" * 80)
                logger.info("[RESEND] 🧪 TESTING MODE - Email NOT SENT")
                logger.info("[RESEND] ✅ Would have sent successfully (simulated)")
                logger.info("=" * 80)
                return True
            
            email = resend.Emails.send(params)
            logger.info("-" * 80)
            logger.info(f"[RESEND] ✅ Customer email sent successfully")
            logger.info(f"  📧 To: {customer_email}")
            logger.info(f"  📝 Subject: {subject}")
            logger.info(f"  🆔 Email ID: {email.get('id', 'N/A')}")
            logger.info("=" * 80)
            return True
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"[RESEND] ❌ Customer email failed for invoice {invoice_no}")
            logger.error(f"  Customer: {customer_name}")
            logger.error(f"  Email: {customer_email}")
            logger.error(f"  Error: {e}")
            logger.error("=" * 80)
            return False
    
    def send_packing_slips(self, pdf_urls: List[str]) -> bool:
        """
        Send packing slip URLs to factory via email (multiple recipients supported).
        
        Args:
            pdf_urls: List of PDF URLs to send
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.enabled or not pdf_urls:
            logger.warning("[RESEND] ⏭️  Factory email skipped - disabled or no PDFs")
            return False
        
        try:
            # Get email settings from config
            sender_name = self.config.get('sender_name', 'Tommy Sugo')
            sender_email = self.config.get('sender_email', 'noreply@tommysugo.com')
            
            # ⬇️ SUPPORT BOTH OLD (single) AND NEW (multiple) CONFIG FORMATS
            # Try new format first (recipient_emails array)
            recipients = self.config.get('recipient_emails', [])
            
            # Fallback to old format (single recipient_email)
            if not recipients:
                single_recipient = self.config.get('recipient_email', '')
                if single_recipient:
                    recipients = [single_recipient]
            
            # If still no recipients, use default
            if not recipients:
                recipients = ['factory@tommysugo.com']
                logger.warning(f"[RESEND] ⚠️  No recipients in config - using default")
            
            subject_template = self.config.get('subject_template', 'Packing Slips Batch - {date}')
            
            # Format subject with current date
            current_date = datetime.now().strftime('%d %b %Y')
            subject = subject_template.replace('{date}', current_date)
            
            # Build email body from config template
            body_template = self.config.get('body_template', {})
            email_body = f"<h2>{body_template.get('title', 'Packing Slips - Daily Batch')}</h2><br>"
            email_body += f"<p>{body_template.get('greeting', 'Hello Team,')}</p><br>"
            email_body += f"<p>{body_template.get('intro', 'Please find the packing slips for today:')}</p><br>"
            email_body += f"<p><strong>Total slips:</strong> {len(pdf_urls)}</p><br>"
            email_body += "<ul>"
            
            for idx, url in enumerate(pdf_urls, 1):
                email_body += f"<li><a href='{url}'>Packing Slip #{idx}</a></li>"
            
            email_body += "</ul><br>"
            email_body += f"<p>{body_template.get('footer', 'Best regards,<br>Tommy Sugo System')}</p>"
            
            # ⬇️ SEND TO MULTIPLE RECIPIENTS
            params = {
                "from": f"{sender_name} <{sender_email}>",
                "to": recipients,  # ✅ List of emails
                "subject": subject,
                "html": email_body
            }
            
            email = resend.Emails.send(params)
            logger.info(f"[RESEND] ✅ Factory email sent successfully")
            logger.info(f"  📧 To: {', '.join(recipients)}")  # Show all recipients
            logger.info(f"  📝 Subject: {subject}")
            logger.info(f"  🔗 PDFs sent: {len(pdf_urls)}")
            logger.info(f"  🆔 Email ID: {email.get('id', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"[RESEND] ❌ Factory email failed: {e}")
            return False