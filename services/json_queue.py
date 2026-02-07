"""
JSON Queue Manager - Simple persistent queue for Google Drive URLs
Stores queue in JSON file - survives Railway restarts
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class JSONQueueManager:
    def __init__(self, queue_file: str = "email_queue.json"):
        """Initialize queue manager with JSON file storage"""
        self.queue_file = Path(queue_file)
        self._ensure_file_exists()
        logger.info(f"[QUEUE] Initialized with file: {self.queue_file}")
    
    def _ensure_file_exists(self):
        """Create queue file if it doesn't exist"""
        if not self.queue_file.exists():
            self._save([])
            logger.info("[QUEUE] Created new queue file")
    
    def _load(self) -> List[Dict]:
        """Load queue from JSON file"""
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[QUEUE] Load error: {e}")
            return []
    
    def _save(self, queue: List[Dict]):
        """Save queue to JSON file"""
        try:
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[QUEUE] Save error: {e}")
    
    def add(self, item: Dict):
        """
        Add item to queue
        
        Required fields in item:
        - pdf_url: Google Drive link
        - invoice_no: Order number
        
        Optional fields:
        - pdf_path: Local file path (for cleanup)
        - docx_path: DOCX file path (for cleanup)
        - barcode_path: Barcode image path (for cleanup)
        """
        queue = self._load()
        
        # Add timestamp if not present
        if 'timestamp' not in item:
            item['timestamp'] = datetime.now().isoformat()
        
        queue.append(item)
        self._save(queue)
        logger.info(f"[QUEUE] Added: {item.get('invoice_no', 'UNKNOWN')} - Total: {len(queue)}")
    
    def get_all(self) -> List[Dict]:
        """Get all items from queue"""
        return self._load()
    
    def count(self) -> int:
        """Get queue size"""
        return len(self._load())
    
    def clear(self):
        """Clear all items from queue"""
        self._save([])
        logger.info("[QUEUE] Cleared all items")
    
    def remove(self, invoice_no: str) -> bool:
        """Remove specific item by invoice number"""
        queue = self._load()
        original_len = len(queue)
        queue = [item for item in queue if item.get('invoice_no') != invoice_no]
        
        if len(queue) < original_len:
            self._save(queue)
            logger.info(f"[QUEUE] Removed: {invoice_no}")
            return True
        return False