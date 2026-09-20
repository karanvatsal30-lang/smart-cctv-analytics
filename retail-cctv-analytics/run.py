"""
Launcher for Software-Only CCTV Analytics Prototype.
Usage:
    python run.py [--port PORT] [--host HOST]
"""

import sys
import os
import argparse

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Load environment variables from .env BEFORE importing backend modules
# so that SUPABASE_URL, SUPABASE_SERVICE_KEY, etc. are available at import time.
try:
    from dotenv import load_dotenv
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print("[Config] Loaded environment variables from .env")
    else:
        print(
            "[Config] WARNING: No .env file found. "
            "Copy .env.example to .env and fill in your Supabase credentials. "
            "User account features will be disabled until configured."
        )
except ImportError:
    print("[Config] python-dotenv not installed. Run: pip install python-dotenv")

from backend.app import app

def main():
    parser = argparse.ArgumentParser(description="Software-Only CCTV Analytics Prototype for Retail Stores")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    args = parser.parse_args()

    print("=" * 70)
    print("  SOFTWARE-ONLY CCTV ANALYTICS PROTOTYPE FOR RETAIL STORES")
    print("  Conservative • Explainable • Privacy-Preserving")
    print("=" * 70)
    print(f"\n>> Dashboard running at: http://{args.host}:{args.port}")
    print(f">> Streaming endpoint:   http://{args.host}:{args.port}/api/video_feed")
    print("\nPress Ctrl+C to terminate the server.\n")

    import threading
    import time
    import webbrowser

    def launch_browser():
        time.sleep(1.2)
        url = f"http://{args.host}:{args.port}"
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=launch_browser, daemon=True).start()

    app.run(host=args.host, port=args.port, debug=False)

if __name__ == "__main__":
    main()
