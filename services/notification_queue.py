"""
Notification Queue Manager
--------------------------
Alag queue sirf customer notifications ke liye (SMS + Email).
Factory email queue (JSONQueueManager) se bilkul alag hai.

Kyun alag?
- Factory queue → batch send ke baad CLEAR ho jati hai
- Notification queue → delivery date tak STORE rehti hai (days/weeks)
- Dono ka lifecycle alag hai, isliye mix karna galat hoga

Flow:
  1. Order aaya  → add_notification() se queue me save karo
  2. Roz 6am Perth (Cron) → /send-notifications endpoint call karo
  3. Endpoint → process_due_notifications() call karta hai
  4. Aaj ki date match → SMS + Email bhejo → sent mark karo
  5. Purani sent entries → auto cleanup (7 din baad)
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)


class NotificationQueueManager:
    """
    Customer notification queue - SMS aur Email dono ke liye.
    JSON file me store hoti hai, Railway restarts survive karta hai.
    """

    def __init__(self, queue_file: str = "notification_queue.json"):
        self.queue_file = Path(queue_file)
        self._ensure_file_exists()
        logger.info(f"[NOTIF QUEUE] Initialized: {self.queue_file}")

    # ─────────────────────────── Internal Helpers ───────────────────────────

    def _ensure_file_exists(self):
        if not self.queue_file.exists():
            self._save([])
            logger.info("[NOTIF QUEUE] Created new notification queue file")

    def _load(self) -> List[Dict]:
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[NOTIF QUEUE] Load error: {e}")
            return []

    def _save(self, queue: List[Dict]):
        try:
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[NOTIF QUEUE] Save error: {e}")

    def _parse_delivery_date(self, delivery_date) -> Optional[date]:
        """
        delivery_date ko date object me convert karo.
        Supports: date, datetime, 'YYYY-MM-DD' string, Jotform dict
        """
        if delivery_date is None:
            return None
        if isinstance(delivery_date, datetime):
            return delivery_date.date()
        if isinstance(delivery_date, date):
            return delivery_date
        if isinstance(delivery_date, dict):
            try:
                return date(
                    int(delivery_date['year']),
                    int(delivery_date['month']),
                    int(delivery_date['day'])
                )
            except (KeyError, ValueError, TypeError):
                return None
        if isinstance(delivery_date, str):
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                try:
                    return datetime.strptime(delivery_date.strip(), fmt).date()
                except ValueError:
                    continue
        return None

    # ─────────────────────────── Public API ─────────────────────────────────

    def add_notification(
        self,
        invoice_no: str,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        consignment_number: str,
        delivery_date,              # date / datetime / str / Jotform dict
    ) -> bool:
        """
        Nayi notification queue me add karo.
        Webhook handler is ko call karta hai jab order process ho.

        Returns:
            True  → successfully added
            False → delivery_date parse nahi hua, skip karo
        """
        parsed = self._parse_delivery_date(delivery_date)
        if parsed is None:
            logger.error(
                f"[NOTIF QUEUE] ❌ Could not parse delivery_date for invoice {invoice_no}. "
                f"Raw value: {delivery_date!r}. Notification NOT queued."
            )
            return False

        queue = self._load()

        # Duplicate check — ek invoice ek baar hi queue me hona chahiye
        existing = [item for item in queue if item.get('invoice_no') == invoice_no]
        if existing:
            logger.warning(f"[NOTIF QUEUE] ⚠️  Invoice {invoice_no} already in queue — skipping duplicate")
            return False

        item = {
            "invoice_no": invoice_no,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "consignment_number": consignment_number,
            "delivery_date": parsed.isoformat(),        # Always store as 'YYYY-MM-DD'
            "email_sent": False,
            "sms_sent": False,
            "email_sent_at": None,
            "sms_sent_at": None,
            "queued_at": datetime.now().isoformat(),
        }

        queue.append(item)
        self._save(queue)

        logger.info(
            f"[NOTIF QUEUE] ✅ Queued: {invoice_no} | "
            f"Delivery: {parsed.isoformat()} | "
            f"Total in queue: {len(queue)}"
        )
        return True

    def get_due_today(self) -> List[Dict]:
        """
        Aaj ki delivery date wale items return karo
        jo abhi tak send nahi hue (email ya sms pending hain).
        """
        today = date.today().isoformat()
        queue = self._load()

        due = [
            item for item in queue
            if item.get('delivery_date') == today
            and (not item.get('email_sent') or not item.get('sms_sent'))
        ]

        logger.info(f"[NOTIF QUEUE] Due today ({today}): {len(due)} items")
        return due

    def mark_sent(self, invoice_no: str, email_sent: bool = False, sms_sent: bool = False):
        """
        Invoice ke email/sms status update karo after sending.
        Sirf jo channel successful hua wahi True mark karo.
        """
        queue = self._load()
        now = datetime.now().isoformat()

        for item in queue:
            if item.get('invoice_no') == invoice_no:
                if email_sent:
                    item['email_sent'] = True
                    item['email_sent_at'] = now
                if sms_sent:
                    item['sms_sent'] = True
                    item['sms_sent_at'] = now
                break

        self._save(queue)
        logger.info(
            f"[NOTIF QUEUE] Marked {invoice_no} → "
            f"email_sent={email_sent}, sms_sent={sms_sent}"
        )

    def cleanup_old_sent(self, days_to_keep: int = 7):
        """
        Jo items fully sent ho gaye hain aur {days_to_keep} din purane hain unhe hatao.
        Ye roz cron ke baad call karo — queue clean rehti hai.
        """
        queue = self._load()
        cutoff = (date.today() - timedelta(days=days_to_keep)).isoformat()

        before = len(queue)
        queue = [
            item for item in queue
            if not (
                item.get('email_sent')
                and item.get('sms_sent')
                and item.get('delivery_date', '9999') <= cutoff
            )
        ]
        removed = before - len(queue)

        if removed:
            self._save(queue)
            logger.info(f"[NOTIF QUEUE] 🧹 Cleaned {removed} old sent items")
        else:
            logger.info("[NOTIF QUEUE] 🧹 Cleanup: nothing to remove")

    def count(self) -> int:
        return len(self._load())

    def get_all(self) -> List[Dict]:
        return self._load()

    def get_stats(self) -> Dict:
        """Queue ki summary — /queue endpoint ke liye useful"""
        queue = self._load()
        today = date.today().isoformat()

        total = len(queue)
        due_today = sum(1 for i in queue if i.get('delivery_date') == today)
        fully_sent = sum(1 for i in queue if i.get('email_sent') and i.get('sms_sent'))
        pending = total - fully_sent

        return {
            "total": total,
            "due_today": due_today,
            "fully_sent": fully_sent,
            "pending": pending,
        }