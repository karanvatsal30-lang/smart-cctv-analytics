"""
Universal Retail CCTV Analytics Server (4 Approved Features + Supabase Auth).
Endpoints:
- /api/config/public        : Returns Supabase URL + anon key for frontend (safe to expose)
- /api/auth/me              : Returns authenticated user's profile
- /api/video_feed           : Real-time MJPEG stream with user regions and validated detections
- /api/analytics            : Structured status of the 4 approved analytics features
- /api/config/regions       : Per-user checkout and shelf region configuration (DB-backed)
- /api/config/shelf/reset_baseline : Baseline reference calibration
- /api/source/*             : Video source ingestion & connection diagnostics

Security:
- All /api/config/* and /api/source/* routes require a valid Supabase JWT.
- /api/video_feed and /api/analytics are public (streaming must not require auth per-frame).
- /api/config/public serves only the ANON_KEY — the SERVICE_ROLE_KEY is NEVER sent to the client.
"""

import os
import sys
import time
import json
import threading
from flask import Flask, Response, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import cv2

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.video_source import VideoSource
from backend.analytics import StoreAnalyticsEngine
from backend.auth import require_auth, AuthError, get_bearer_token, get_user_id

def is_supabase_configured():
    return bool(
        os.environ.get("SUPABASE_URL", "").strip()
        and os.environ.get("SUPABASE_ANON_KEY", "").strip()
        and (os.environ.get("SUPABASE_SERVICE_KEY", "").strip() or os.environ.get("SUPABASE_JWT_SECRET", "").strip())
    )

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "frontend"),
    static_url_path=""
)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB

# Global Video Source & Analytics Engine
video_source = VideoSource()
analytics_engine = StoreAnalyticsEngine()

display_options = {
    "show_boxes": True,
    "show_regions": True,
    "apply_privacy_blur": False,
}
display_lock = threading.Lock()

latest_jpeg_frame = None
latest_raw_frame = None
frame_lock = threading.Lock()
running = True

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,PUT,POST,DELETE,OPTIONS"
    return response

@app.route("/api/<path:subpath>", methods=["OPTIONS"])
def handle_options(subpath):
    return "", 204

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "success": False,
        "error": "The uploaded video file is too large (maximum limit is 2GB)."
    }), 413

def processing_worker():
    global latest_jpeg_frame, latest_raw_frame, running
    video_source.open_benchmark()

    while running:
        success, frame = video_source.read_frame()
        if not success or frame is None:
            time.sleep(0.04)
            continue

        with display_lock:
            sb = display_options["show_boxes"]
            sr = display_options["show_regions"]
            pb = display_options["apply_privacy_blur"]

        with frame_lock:
            latest_raw_frame = frame.copy()

        annotated_frame, analytics_data = analytics_engine.process_frame(
            frame=frame,
            show_boxes=sb,
            show_regions=sr,
            apply_privacy_blur=pb,
        )

        if annotated_frame is not None:
            ret, buffer = cv2.imencode(".jpg", annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
                with frame_lock:
                    latest_jpeg_frame = buffer.tobytes()

worker_thread = threading.Thread(target=processing_worker, daemon=True)
worker_thread.start()


# -------------------------------------------------------------
# STATIC FRONTEND ROUTES
# -------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def static_proxy(path):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


# -------------------------------------------------------------
# PUBLIC CONFIG — Safe for Frontend
# (Anon key only — service key is NEVER sent here)
# -------------------------------------------------------------
@app.route("/api/config/public", methods=["GET"])
def get_public_config():
    """
    Returns only the publishable (anon) Supabase credentials to the browser.
    The SERVICE_ROLE_KEY is never included here.
    """
    return jsonify({
        "supabase_url": os.environ.get("SUPABASE_URL", "").strip(),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", "").strip(),
        "auth_enabled": is_supabase_configured(),
    })


# -------------------------------------------------------------
# AUTH & USER IDENTIFICATION
# -------------------------------------------------------------
@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    """First-time user registration (creates local/cloud account)."""
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    display_name = data.get("display_name", "").strip()

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required."}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters."}), 400

    from backend.db import register_user
    res = register_user(email, password, display_name)
    status_code = 200 if res.get("success") else 400
    return jsonify(res), status_code


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """User authentication."""
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required."}), 400

    from backend.db import authenticate_user
    res = authenticate_user(email, password)
    status_code = 200 if res.get("success") else 401
    return jsonify(res), status_code


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def get_me(user_id):
    """Returns the authenticated user's profile."""
    try:
        from backend.db import get_user_profile
        profile = get_user_profile(user_id)
        return jsonify({
            "user_id": user_id,
            "display_name": profile.get("display_name", ""),
            "email": profile.get("email", ""),
        })
    except Exception as e:
        return jsonify({
            "user_id": user_id,
            "display_name": "",
            "email": "",
            "note": str(e),
        })


@app.route("/api/user/cctv", methods=["GET"])
@require_auth
def get_user_cctv(user_id):
    """Loads user's saved camera preferences and monitoring regions."""
    from backend.db import load_user_camera, load_user_regions
    camera = load_user_camera(user_id)
    regions = load_user_regions(user_id)
    return jsonify({
        "user_id": user_id,
        "camera": camera,
        "regions": regions,
    })


@app.route("/api/user/cctv", methods=["POST"])
@require_auth
def save_user_cctv(user_id):
    """Saves user's CCTV camera details & monitoring regions."""
    data = request.get_json() or {}
    from backend.db import save_user_camera, save_user_regions
    if "camera" in data:
        save_user_camera(user_id, data["camera"])
    if "regions" in data:
        r = data["regions"]
        save_user_regions(user_id, r.get("checkout", {}), r.get("shelf", {}))
    return jsonify({"success": True, "message": "CCTV details saved successfully."})


# -------------------------------------------------------------
# STREAMING & ANALYTICS API
# (Public — streaming cannot require per-frame auth headers)
# -------------------------------------------------------------
def mjpeg_generator():
    while True:
        with frame_lock:
            frame_bytes = latest_jpeg_frame

        if frame_bytes is not None:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        time.sleep(0.035)

@app.route("/api/video_feed")
def video_feed():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    return jsonify({
        "analytics": analytics_engine.latest_state,
        "source": video_source.get_status(),
        "display_options": display_options,
    })

@app.route("/api/audit_trail", methods=["GET"])
def get_audit_trail():
    return jsonify({
        "audit_trail": analytics_engine.audit_log,
    })


# -------------------------------------------------------------
# USER-DEFINED REGION CONFIGURATION API
# Regions are now stored per-user in Supabase DB.
# Falls back to local file if Supabase is not configured.
# -------------------------------------------------------------
@app.route("/api/config/regions", methods=["GET"])
def get_regions():
    """
    Returns this user's monitoring regions.
    - If Supabase is configured and a valid token is provided: loads from DB.
    - If no token or Supabase not configured: falls back to local file.
    """
    if is_supabase_configured():
        token = get_bearer_token()
        if token:
            try:
                user_id = get_user_id(token)
                from backend.db import load_user_regions
                regions = load_user_regions(user_id)
                # Sync in-memory engine with user's DB regions
                _apply_regions_to_engine(regions)
                return jsonify(regions)
            except AuthError:
                pass  # Fall through to local file fallback

    # Fallback: local in-memory / file-based regions
    rm = analytics_engine.region_manager
    return jsonify({
        "checkout": {
            "name": rm.checkout_region.name if rm.checkout_region else "Main Checkout",
            "polygon": rm.checkout_region.polygon if rm.checkout_region else [],
        },
        "shelf": {
            "name": rm.shelf_region.name if rm.shelf_region else "Shelf 1",
            "polygon": rm.shelf_region.polygon if rm.shelf_region else [],
        }
    })


@app.route("/api/config/regions", methods=["POST"])
@require_auth
def update_regions(user_id):
    """
    Saves user's monitoring regions to Supabase DB (and in-memory engine).
    Requires a valid JWT.
    """
    data = request.get_json() or {}
    rm = analytics_engine.region_manager

    checkout_data = data.get("checkout", {})
    shelf_data = data.get("shelf", {})

    # Update in-memory engine
    if checkout_data:
        name = checkout_data.get("name", "Main Checkout")
        poly = checkout_data.get("polygon", [])
        if poly and len(poly) >= 3:
            rm.update_checkout_region(name, poly)

    if shelf_data:
        name = shelf_data.get("name", "Shelf 1")
        poly = shelf_data.get("polygon", [])
        if poly and len(poly) >= 3:
            rm.update_shelf_region(name, poly)

    # Persist to Supabase DB if configured
    db_saved = False
    if is_supabase_configured():
        try:
            from backend.db import save_user_regions
            db_saved = save_user_regions(
                user_id,
                {
                    "name": rm.checkout_region.name if rm.checkout_region else "Main Checkout",
                    "polygon": rm.checkout_region.polygon if rm.checkout_region else [],
                },
                {
                    "name": rm.shelf_region.name if rm.shelf_region else "Shelf 1",
                    "polygon": rm.shelf_region.polygon if rm.shelf_region else [],
                },
            )
        except Exception as e:
            print(f"[Regions] DB save error: {e}")

    return jsonify({
        "status": "success",
        "message": "Regions successfully updated.",
        "persisted_to_db": db_saved,
    })


def _apply_regions_to_engine(regions: dict):
    """Syncs loaded DB regions into the in-memory analytics engine."""
    rm = analytics_engine.region_manager
    c = regions.get("checkout", {})
    if c.get("polygon") and len(c["polygon"]) >= 3:
        rm.update_checkout_region(c.get("name", "Main Checkout"), c["polygon"])
    s = regions.get("shelf", {})
    if s.get("polygon") and len(s["polygon"]) >= 3:
        rm.update_shelf_region(s.get("name", "Shelf 1"), s["polygon"])


@app.route("/api/config/shelf/reset_baseline", methods=["POST"])
@require_auth
def reset_shelf_baseline(user_id):
    with frame_lock:
        frame = latest_raw_frame

    if frame is not None:
        success = analytics_engine.region_manager.capture_shelf_baseline(frame)
        return jsonify({"success": success, "message": "Shelf reference baseline captured."})
    return jsonify({"success": False, "message": "No video frame available to calibrate baseline."}), 400


@app.route("/api/settings", methods=["POST"])
@require_auth
def update_settings(user_id):
    data = request.get_json() or {}
    with display_lock:
        if "show_boxes" in data:
            display_options["show_boxes"] = bool(data["show_boxes"])
        if "show_regions" in data:
            display_options["show_regions"] = bool(data["show_regions"])
        if "apply_privacy_blur" in data:
            display_options["apply_privacy_blur"] = bool(data["apply_privacy_blur"])

    return jsonify({"status": "success", "display_options": display_options})


# -------------------------------------------------------------
# VIDEO SOURCE INGESTION & SIMULATION CONTROLS
# -------------------------------------------------------------
@app.route("/api/source/benchmark", methods=["POST"])
@require_auth
def switch_to_benchmark(user_id):
    video_source.open_benchmark()
    try:
        from backend.db import save_user_camera
        save_user_camera(user_id, {"name": "Built-in Store CCTV Simulation", "source_type": "benchmark", "config_data": {}})
    except Exception:
        pass
    return jsonify(video_source.get_status())

@app.route("/api/source/webcam", methods=["POST"])
@require_auth
def switch_to_webcam(user_id):
    data = request.get_json() or {}
    idx = int(data.get("index", 0))
    success = video_source.open_webcam(idx)
    if success:
        try:
            from backend.db import save_user_camera
            save_user_camera(user_id, {"name": f"USB Webcam (Device {idx})", "source_type": "webcam", "config_data": {"index": idx}})
        except Exception:
            pass
    return jsonify({
        "success": success,
        "source": video_source.get_status()
    })

@app.route("/api/source/rtsp", methods=["POST"])
@require_auth
def switch_to_rtsp(user_id):
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"success": False, "error": "Empty RTSP URL provided."}), 400

    success = video_source.open_rtsp(url)
    if success:
        try:
            from backend.db import save_user_camera
            save_user_camera(user_id, {"name": "RTSP IP Camera Stream", "source_type": "rtsp", "config_data": {"url": url}})
        except Exception:
            pass
    return jsonify({
        "success": success,
        "source": video_source.get_status()
    })

@app.route("/api/source/upload", methods=["POST"])
@require_auth
def upload_video(user_id):
    try:
        if "video_file" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded in form data."}), 400

        file = request.files["video_file"]
        if not file or file.filename == "":
            return jsonify({"success": False, "error": "No file selected."}), 400

        filename = secure_filename(file.filename)
        if not filename:
            filename = f"upload_{int(time.time())}.mp4"

        upload_dir = os.path.join(BASE_DIR, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        save_path = os.path.join(upload_dir, filename)
        file.save(save_path)

        success = video_source.open_file(save_path)
        if not success:
            return jsonify({
                "success": False,
                "error": video_source.connection_error or "Failed to decode video file. Ensure standard H.264/MP4 encoding.",
                "source": video_source.get_status()
            }), 400

        try:
            from backend.db import save_user_camera
            save_user_camera(user_id, {"name": f"Video: {filename}", "source_type": "file", "config_data": {"filename": filename}})
        except Exception:
            pass

        return jsonify({
            "success": True,
            "filename": filename,
            "source": video_source.get_status()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Server error during video upload: {str(e)}"
        }), 500

@app.route("/api/sim/toggle_shelf", methods=["POST"])
@require_auth
def toggle_shelf_sim(user_id):
    video_source.toggle_shelf_depletion_simulation()
    return jsonify({
        "status": "success",
        "shelf_depleted": video_source.shelf_empty_sim
    })

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
