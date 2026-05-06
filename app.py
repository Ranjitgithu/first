import os
import uuid
import shutil
import threading
import time
from math import ceil

from flask import (
    Flask, render_template, request,
    redirect, url_for, session,
    send_file, flash
)
from werkzeug.utils import secure_filename

from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from google.auth.transport import requests

from utils.drive_utils import get_folder_id_from_url, get_images_from_drive_folder
from utils.face_utils import process_images, find_matching_images
from utils.zip_utils import create_zip_file

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

GOOGLE_CLIENT_ID = "244497833082-stkji8qg7cb01itn8nsdme6qao8r4qov.apps.googleusercontent.com"
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

UPLOAD_FOLDER = "uploads"
TEMP_IMAGES_FOLDER = "temp_images"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_IMAGES_FOLDER, exist_ok=True)

ALLOWED_EXT = {'.jpg', '.jpeg', '.png'}

# --- UPDATED REQUIREMENTS ---
MAX_IMAGES = 2000 
BATCH_SIZE = 25

def _cleanup_all_temp():
    for folder in [UPLOAD_FOLDER, TEMP_IMAGES_FOLDER]:
        if not os.path.exists(folder):
            continue
        for item in os.listdir(folder):
            path = os.path.join(folder, item)
            try:
                if os.path.isfile(path):
                    os.remove(path)
                else:
                    shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass

def _is_logged_in():
    return session.get("logged_in") or ("credentials" in session)

@app.route('/')
def index():
    if _is_logged_in():
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route('/login')
def login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('callback', _external=True)
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account"
    )

    session["oauth_state"] = state
    return redirect(auth_url)


@app.route('/callback')
def callback():
    if "oauth_state" not in session:
        flash("OAuth state missing.", "error")
        return redirect(url_for("index"))

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=session["oauth_state"],
        redirect_uri=url_for('callback', _external=True)
    )

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        flash(f"OAuth failed: {e}", "error")
        return redirect(url_for("index"))

    creds = flow.credentials
    session["credentials"] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }
    session["logged_in"] = True

    try:
        info = id_token.verify_oauth2_token(
            creds.id_token,
            requests.Request(),
            GOOGLE_CLIENT_ID
        )
        user_email = info.get("email") or info.get("sub") or "User"
        session["user_email"] = str(user_email)
    except Exception:
        flash("Failed to verify user.", "error")
        return redirect(url_for("index"))

    return redirect(url_for("dashboard"))


@app.route('/set_name', methods=['POST'])
def set_name():
    """Save a user-provided display name into session (until logout)."""
    name = request.form.get('display_name', '').strip()
    if name:
        session['display_name'] = name
        flash('Name saved.', 'success')
    else:
        session.pop('display_name', None)
        flash('Name cleared.', 'info')
    return redirect(request.referrer or url_for('index'))


@app.route('/dashboard')
def dashboard():
    if not _is_logged_in():
        return redirect(url_for("index"))
    email = session.get("user_email") or "User"
    username_only = (email.split('@')[0] if isinstance(email, str) and '@' in email else email)
    display_label = session.get('display_name') or username_only or 'User'
    return render_template("dashboard.html", email=email, display_label=display_label)


@app.route('/logout')
def logout():
    session.clear()
    _cleanup_all_temp()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))


@app.route('/process', methods=['POST'])
def process():
    if not _is_logged_in():
        flash("Login required.", "error")
        return redirect(url_for("index"))

    drive_link = request.form.get("drive_link")
    reference_image = request.files.get("reference_image")
    try:
        threshold = float(request.form.get("threshold", 0.6))
    except Exception:
        threshold = 0.6

    if not drive_link or not reference_image:
        flash("Drive link and reference image required.", "error")
        return redirect(url_for("dashboard"))

    filename = secure_filename(reference_image.filename or "")
    ref_ext = os.path.splitext(filename)[1].lower()
    if ref_ext not in ALLOWED_EXT:
        ref_ext = ".jpg"

    ref_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}{ref_ext}")
    reference_image.save(ref_path)

    try:
        ref_embeddings = process_images([ref_path])
        if not ref_embeddings:
            raise ValueError("No face detected in reference image.")

        ref_embedding = ref_embeddings[0]

        folder_id = get_folder_id_from_url(drive_link)
        drive_images = get_images_from_drive_folder(
            session.get("credentials", {}), folder_id
        )

        if not drive_images:
            raise ValueError("No images found in Drive folder.")

        # --- TERMINAL LOG: NO. OF IMAGES IN DRIVE LINK ---
        total_in_drive = len(drive_images)
        print(f"\n>>> Total images found in Drive link: {total_in_drive}")

        # Applying the 2000 limit
        drive_images = drive_images[:MAX_IMAGES]
        num_to_process = len(drive_images)
        print(f">>> Limit check: Preparing to scan {num_to_process} images.")

        session_id = str(uuid.uuid4())
        session_dir = os.path.join(TEMP_IMAGES_FOLDER, session_id)
        os.makedirs(session_dir, exist_ok=True)

        image_paths = []
        for img in drive_images:
            ext = os.path.splitext(img["name"])[1].lower() or ".jpg"
            path = os.path.join(session_dir, f"{img['id']}{ext}")
            with open(path, "wb") as f:
                f.write(img["data"])
            image_paths.append(path)

        embeddings = []
        scanned_count = 0
        total_batches = ceil(num_to_process / BATCH_SIZE)

        # --- TERMINAL LOG: SCANNING PROGRESS ---
        for i in range(0, len(image_paths), BATCH_SIZE):
            batch = image_paths[i:i + BATCH_SIZE]
            embeddings.extend(process_images(batch))
            scanned_count += len(batch)
            print(f">>> Scanning Status: {scanned_count}/{num_to_process} images scanned...", flush=True)

        matched_idx = find_matching_images(
            ref_embedding, embeddings, threshold
        )

        matched_images = [image_paths[i] for i in matched_idx]

        session["matched_images"] = matched_images
        session["session_id"] = session_id

        # --- TERMINAL LOG: FINAL SUMMARY ---
        print(f">>> Final Results:")
        print(f"    - Total images in Drive link: {total_in_drive}")
        print(f"    - Images actually scanned: {scanned_count}")
        print(f"    - Matching images found: {len(matched_images)}\n")

        flash(
            f"Scanned {len(image_paths)} images. "
            f"Matched {len(matched_images)}.",
            "success"
        )

        return redirect(url_for("result"))

    except Exception as e:
        flash(str(e), "error")
        return redirect(url_for("dashboard"))

    
@app.route('/result')
def result():
    if "matched_images" not in session:
        return redirect(url_for("dashboard"))

    images = [os.path.basename(p) for p in session["matched_images"]]
    email = session.get("user_email") or "User"
    username_only = (email.split('@')[0] if isinstance(email, str) and '@' in email else email)
    display_label = session.get('display_name') or username_only or 'User'
    return render_template(
        "result.html",
        images=images,
        email=email,
        display_label=display_label
    )


@app.route('/download')
def download():
    if "matched_images" not in session:
        return redirect(url_for("dashboard"))

    zip_path = os.path.join(
        TEMP_IMAGES_FOLDER,
        f"{session['session_id']}.zip"
    )

    create_zip_file(session["matched_images"], zip_path)

    def delayed_cleanup():
        time.sleep(10)
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            shutil.rmtree(
                os.path.join(
                    TEMP_IMAGES_FOLDER,
                    session["session_id"]
                ),
                ignore_errors=True
            )
        except Exception:
            pass

    threading.Thread(
        target=delayed_cleanup, daemon=True
    ).start()

    return send_file(
        zip_path,
        as_attachment=True,
        download_name="matched_images.zip"
    )


@app.route('/image/<image_name>')
def serve_image(image_name):
    session_dir = os.path.join(
        TEMP_IMAGES_FOLDER,
        session.get("session_id", "")
    )
    path = os.path.join(session_dir, image_name)

    if not os.path.exists(path):
        flash("Image not found.", "error")
        return redirect(url_for("dashboard"))

    return send_file(path)

if __name__ == "__main__":
    app.run(debug=True)
print("ranjit kumar")
print("ranjit kumar")
print("kommasani ")