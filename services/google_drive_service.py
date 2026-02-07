"""
Google Drive Service - File upload with folder structure
"""
import logging
import os
from typing import Optional
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)


class GoogleDriveService:
    def __init__(self):
        self.service = None
        self.enabled = False
        
        try:
            client_id = os.getenv('GOOGLE_CLIENT_ID', '')
            client_secret = os.getenv('GOOGLE_CLIENT_SECRET', '')
            refresh_token = os.getenv('GOOGLE_REFRESH_TOKEN', '')
            token_uri = os.getenv('GOOGLE_TOKEN_URI', 'https://oauth2.googleapis.com/token')
            
            if not all([client_id, client_secret, refresh_token]):
                logger.warning("[GOOGLE DRIVE] ❌ Missing credentials - service disabled")
                return
            
            creds = Credentials(
                None,
                refresh_token=refresh_token,
                token_uri=token_uri,
                client_id=client_id,
                client_secret=client_secret
            )
            
            if creds.expired or not creds.valid:
                creds.refresh(GoogleRequest())
            
            self.service = build('drive', 'v3', credentials=creds)
            self.enabled = True
            logger.info("[GOOGLE DRIVE] ✅ Service initialized successfully")
            
        except Exception as e:
            logger.error(f"[GOOGLE DRIVE] ❌ Initialization failed: {e}")
            self.enabled = False
    
    def _find_or_create_folder(self, folder_name: str, parent_id: str = None) -> Optional[str]:
        """
        Find existing folder or create new one.
        
        Args:
            folder_name: Name of folder to find/create
            parent_id: Parent folder ID (optional)
            
        Returns:
            Optional[str]: Folder ID or None
        """
        try:
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                folder_id = files[0]['id']
                logger.info(f"[GOOGLE DRIVE] ✓ Found existing folder: {folder_name}")
                return folder_id
            
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                folder_metadata['parents'] = [parent_id]
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"[GOOGLE DRIVE] ✓ Created new folder: {folder_name}")
            return folder_id
            
        except Exception as e:
            logger.error(f"[GOOGLE DRIVE] ❌ Error finding/creating folder {folder_name}: {e}")
            return None
    
    def upload_file(self, file_path: str, order_date: str = None, invoice_no: str = "", file_type: str = "pdf") -> Optional[str]:
        """
        Upload file to Google Drive with folder structure based on ORDER DATE (when order was placed).
        Root Folder: "MONTH - YEAR" (e.g., "FEB - 2026")
        Sub Folder: "DD - MM - YY" (e.g., "05 - 02 - 26")
        Filename: "INV-XXXXX.pdf" or "INV-XXXXX.docx" (unique per invoice)
        
        Args:
            file_path: Path to file to upload
            order_date: Order submission date (if None, uses current date)
            invoice_no: Invoice number for unique filename
            file_type: File type ("pdf" or "docx")
            
        Returns:
            Optional[str]: Google Drive web view link or None
        """
        if not self.enabled or not self.service:
            logger.warning(f"[GOOGLE DRIVE] ⏭️  Upload skipped - service disabled")
            return None
        
        try:
            # Use current date if order_date not provided
            if not order_date:
                from datetime import datetime
                now = datetime.now()
                day = now.strftime('%d')
                month = now.strftime('%m')
                year = now.strftime('%Y')
            else:
                # Parse order date (format can be "DD-MM-YYYY" or datetime object)
                if isinstance(order_date, str):
                    date_parts = order_date.split('-')
                    if len(date_parts) != 3:
                        logger.error(f"[GOOGLE DRIVE] ❌ Invalid date format: {order_date}")
                        # Fallback to current date
                        from datetime import datetime
                        now = datetime.now()
                        day = now.strftime('%d')
                        month = now.strftime('%m')
                        year = now.strftime('%Y')
                    else:
                        day = date_parts[0].strip().zfill(2)
                        month = date_parts[1].strip().zfill(2)
                        year = date_parts[2].strip()
                else:
                    # Assume datetime object
                    day = order_date.strftime('%d')
                    month = order_date.strftime('%m')
                    year = order_date.strftime('%Y')
            
            # Convert month number to month name
            month_names = {
                '01': 'JAN', '02': 'FEB', '03': 'MAR', '04': 'APR',
                '05': 'MAY', '06': 'JUN', '07': 'JUL', '08': 'AUG',
                '09': 'SEP', '10': 'OCT', '11': 'NOV', '12': 'DEC'
            }
            month_name = month_names.get(month, 'JAN')
            
            # Create folder structure
            # Root: "MONTH - YEAR" (e.g., "FEB - 2026") - based on ORDER DATE
            root_folder_name = f"{month_name} - {year}"
            
            # Sub-folder: "DD - MM - YY" (e.g., "05 - 02 - 26") - based on ORDER DATE
            year_short = year[-2:] if len(year) == 4 else year
            date_folder_name = f"{day} - {month} - {year_short}"
            
            # Filename: Use invoice number for uniqueness
            extension = "pdf" if file_type == "pdf" else "docx"
            if invoice_no:
                new_filename = f"{invoice_no}.{extension}"
            else:
                new_filename = f"{date_folder_name}.{extension}"
            
            logger.info(f"[GOOGLE DRIVE] 📤 Uploading {file_type.upper()}")
            logger.info(f"  Order Date: {day}-{month}-{year}")
            logger.info(f"  Root Folder: {root_folder_name}")
            logger.info(f"  Date Folder: {date_folder_name}")
            logger.info(f"  Filename: {new_filename}")
            
            # Find or create root folder (Month - Year)
            root_folder_id = self._find_or_create_folder(root_folder_name)
            if not root_folder_id:
                logger.error("[GOOGLE DRIVE] ❌ Failed to create/find root folder")
                return None
            
            # Find or create date sub-folder
            date_folder_id = self._find_or_create_folder(date_folder_name, root_folder_id)
            if not date_folder_id:
                logger.error("[GOOGLE DRIVE] ❌ Failed to create/find date folder")
                return None
            
            # Check if file already exists in date folder
            query = f"name='{new_filename}' and '{date_folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            existing_files = results.get('files', [])
            
            # Delete existing file if found
            if existing_files:
                for existing_file in existing_files:
                    self.service.files().delete(fileId=existing_file['id']).execute()
                    logger.info(f"[GOOGLE DRIVE] 🗑️  Deleted existing: {new_filename}")
            
            # Upload new file
            mime_type = 'application/pdf' if file_type == "pdf" else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            
            file_metadata = {
                'name': new_filename,
                'parents': [date_folder_id]
            }
            
            media = MediaFileUpload(
                file_path,
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            
            file_id = file.get('id')
            web_link = file.get('webViewLink', 'N/A')
            
            # Make file publicly accessible (anyone with link can view)
            try:
                permission = {
                    'type': 'anyone',
                    'role': 'reader'
                }
                self.service.permissions().create(
                    fileId=file_id,
                    body=permission
                ).execute()
                logger.info(f"[GOOGLE DRIVE] 🔓 File set to public access")
            except Exception as e:
                logger.warning(f"[GOOGLE DRIVE] ⚠️  Could not set public access: {e}")
            
            logger.info(f"[GOOGLE DRIVE] ✅ {file_type.upper()} uploaded")
            logger.info(f"  🔗 Link: {web_link}")
            
            return web_link
            
        except Exception as e:
            logger.error(f"[GOOGLE DRIVE] ❌ Upload failed: {e}")
            return None