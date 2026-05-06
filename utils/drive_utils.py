import re
import requests
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

def get_folder_id_from_url(drive_url):
    """
    Extract the folder ID from a Google Drive URL.
    
    Args:
        drive_url (str): The Google Drive folder URL
        
    Returns:
        str: The extracted folder ID
        
    Raises:
        ValueError: If the URL format is invalid
    """
    # Pattern to match folder ID in various Google Drive URL formats
    patterns = [
        r'/folders/([a-zA-Z0-9_-]+)',  # https://drive.google.com/drive/folders/FOLDER_ID
        r'open\?id=([a-zA-Z0-9_-]+)',  # https://drive.google.com/open?id=FOLDER_ID
        r'folderview\?id=([a-zA-Z0-9_-]+)'  # Other possible formats
    ]
    
    for pattern in patterns:
        match = re.search(pattern, drive_url)
        if match:
            return match.group(1)
    
    raise ValueError("Invalid Google Drive folder URL format")

def _get_public_folder_file_ids(folder_id):
    """Try to scrape file IDs from a public Google Drive folder page (best-effort)."""
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        # Find occurrences of `/file/d/<id>` in the HTML
        ids = re.findall(r"/file/d/([a-zA-Z0-9_-]+)", resp.text)
        # Preserve order and uniqueness
        seen = set()
        unique = []
        for i in ids:
            if i not in seen:
                seen.add(i)
                unique.append(i)
        return unique
    except Exception:
        return []


def _download_public_file(file_id):
    """Download a public file by file id using the standard uc?export=download endpoint."""
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return None, None
        # Try to get filename from headers
        cd = r.headers.get('Content-Disposition') or ''
        name = None
        m = re.search(r'filename="?([^";]+)"?', cd)
        if m:
            name = m.group(1)
        else:
            # Guess extension from content-type
            ct = r.headers.get('Content-Type', '').split(';')[0]
            ext_map = {
                'image/jpeg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/bmp': '.bmp',
                'image/webp': '.webp'
            }
            ext = ext_map.get(ct, '')
            name = f"{file_id}{ext if ext else ''}"
        return name, r.content
    except Exception:
        return None, None


def get_images_from_drive_folder(credentials_dict, folder_id, max_images=200):
    """
    Fetch image files from a Google Drive folder. First attempts Drive API using provided
    credentials; if that fails, attempts a public-folder HTML fallback (best-effort).
    """
    # Try Drive API flow first
    try:
        # Create credentials object from dictionary
        credentials = Credentials(
            token=credentials_dict.get('token'),
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri'),
            client_id=credentials_dict.get('client_id'),
            client_secret=credentials_dict.get('client_secret'),
            scopes=credentials_dict.get('scopes')
        )

        # Refresh the credentials if needed
        try:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
        except Exception:
            # Best-effort refresh; if it fails, the API calls may still work
            pass

        drive_service = build('drive', 'v3', credentials=credentials)

        image_mime_types = {
            'image/jpeg',
            'image/png',
            'image/jpg',
            'image/gif',
            'image/bmp',
            'image/webp'
        }

        images = []

        def fetch_folder_contents(fid):
            nonlocal images
            page_token = None
            while True:
                results = drive_service.files().list(
                    q=f"'{fid}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageToken=page_token
                ).execute()

                for file in results.get('files', []):
                    mime_type = file.get('mimeType', '')
                    if mime_type == 'application/vnd.google-apps.folder':
                        fetch_folder_contents(file['id'])
                        if len(images) >= max_images:
                            return
                    elif mime_type in image_mime_types:
                        try:
                            request_file = drive_service.files().get_media(fileId=file['id'])
                            file_data = request_file.execute()
                            images.append({
                                'id': file['id'],
                                'name': file['name'],
                                'data': file_data
                            })
                        except Exception:
                            continue

                        if len(images) >= max_images:
                            return

                page_token = results.get('nextPageToken')
                if not page_token or len(images) >= max_images:
                    break

        fetch_folder_contents(folder_id)
        return images

    except Exception:
        # Drive API failed - try public HTML fallback
        ids = _get_public_folder_file_ids(folder_id)
        images = []
        for fid in ids[:max_images]:
            name, data = _download_public_file(fid)
            if name and data:
                images.append({'id': fid, 'name': name, 'data': data})
            if len(images) >= max_images:
                break
        return images