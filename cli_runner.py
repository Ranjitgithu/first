import os
import uuid
import shutil
import argparse
import time
from math import ceil

from utils.drive_utils import get_folder_id_from_url, get_images_from_drive_folder
from utils.face_utils import process_images, find_matching_images
from utils.zip_utils import create_zip_file

TMP_DIR = "temp_images_cli"
BATCH_SIZE = 25
MAX_IMAGES = 2000


def log(msg):
    print(msg, flush=True)


def run_cli(drive_link, reference_path, credentials_path=None, threshold=0.6, max_images=MAX_IMAGES):
    creds = {}
    if credentials_path and os.path.exists(credentials_path):
        import json
        with open(credentials_path, 'r', encoding='utf-8') as fh:
            creds = json.load(fh)

    if not os.path.exists(reference_path):
        log(f"Reference image not found: {reference_path}")
        return 1

    try:
        ref_embeddings = process_images([reference_path])
        if not ref_embeddings:
            log("No face detected in reference image.")
            return 1
        ref_embedding = ref_embeddings[0]
        log("[REF] Reference image processed")

        folder_id = get_folder_id_from_url(drive_link)
        images = get_images_from_drive_folder(creds, folder_id, max_images=max_images)
        log(f"[DRIVE] Total images found: {len(images)}")

        if not images:
            log("No images found in Drive folder (ensure folder is shared public or provide credentials).")
            return 1

        session_id = str(uuid.uuid4())
        session_dir = os.path.join(TMP_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)

        image_paths = []
        total_images = len(images)
        for idx, img in enumerate(images, start=1):
            ext = os.path.splitext(img['name'])[1] or '.jpg'
            path = os.path.join(session_dir, f"{img['id']}{ext}")
            with open(path, 'wb') as f:
                f.write(img['data'])
            image_paths.append(path)
            log(f"[DOWNLOAD] {idx}/{total_images} downloaded: {path}")

        embeddings = []
        total_batches = ceil(len(image_paths) / BATCH_SIZE)
        for batch_no, i in enumerate(range(0, len(image_paths), BATCH_SIZE), start=1):
            batch = image_paths[i:i + BATCH_SIZE]
            log(f"[PROCESS] Batch {batch_no}/{total_batches} started")
            batch_embeddings = process_images(batch)
            embeddings.extend(batch_embeddings)
            log(f"[PROCESS] Batch {batch_no}/{total_batches} completed")

        matched_idx = find_matching_images(ref_embedding, embeddings, threshold)
        matched_images = [image_paths[i] for i in matched_idx]

        log(f"[MATCH] Found {len(matched_images)} matching image(s)")
        for p in matched_images:
            log(f" - {p}")

        # Create zip of matches
        if matched_images:
            zip_path = os.path.join(session_dir, "matched_images.zip")
            create_zip_file(matched_images, zip_path)
            log(f"ZIP created: {zip_path}")
        else:
            log("No matches to zip.")

        return 0

    except Exception as e:
        log(f"[ERROR] {e}")
        return 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run facial search from the terminal')
    parser.add_argument('--drive-link', required=True, help='Google Drive folder link')
    parser.add_argument('--reference', required=True, help='Path to reference image')
    parser.add_argument('--credentials', help='Optional credentials JSON file saved from web login')
    parser.add_argument('--threshold', type=float, default=0.6, help='Matching threshold')
    parser.add_argument('--max-images', type=int, default=MAX_IMAGES, help='Maximum images to scan')

    args = parser.parse_args()
    rc = run_cli(args.drive_link, args.reference, args.credentials, args.threshold, args.max_images)
    if rc != 0:
        log(f"Exit code: {rc}")
    if rc == 0:
        log("Done.")
    exit(rc)
