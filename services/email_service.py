"""
Email Service - Resend Integration with Multiple Recipients Support
"""
import logging
import os
from typing import Dict, List
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
    
    def send_packing_slips(self, pdf_urls: List[str]) -> bool:
        """
        Send packing slip URLs to factory via email (multiple recipients supported).
        
        Args:
            pdf_urls: List of PDF URLs to send
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.enabled or not pdf_urls:
            logger.warning("[RESEND] ⏭️  Email skipped - disabled or no PDFs")
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
            logger.info(f"[RESEND] ✅ Email sent successfully")
            logger.info(f"  📧 To: {', '.join(recipients)}")  # Show all recipients
            logger.info(f"  📝 Subject: {subject}")
            logger.info(f"  🔗 PDFs sent: {len(pdf_urls)}")
            logger.info(f"  🆔 Email ID: {email.get('id', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"[RESEND] ❌ Email failed: {e}")
            return False