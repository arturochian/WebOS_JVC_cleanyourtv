#!/usr/bin/env python3
"""
home-watch.py - Foreground Home Screen Watcher for LG webOS Hub

Subscribes to foreground app changes. When the stock LG Home screen
('com.webos.app.home') is brought to the foreground, this daemon automatically
launches 'com.gathin.tvhome'.

Features:
- Escape window: Pressing Home twice within ESCAPE_SECONDS (default 3.0s) allows
  bypassing CleanYourTV to access native LG webOS settings.
- Automatic exponential backoff reconnection.
- --offline-mock mode for automated verification without TV.
"""

import argparse
import json
import os
import sys
import time
import lgtv

TARGET_APP_ID = "com.gathin.tvhome"
STOCK_HOME_ID = "com.webos.app.home"
DEFAULT_ESCAPE_SECONDS = 3.0


def run_mock_watch(escape_seconds: float = DEFAULT_ESCAPE_SECONDS) -> None:
    """Simulate Home button interception for offline testing."""
    print("[home-watch] Running in --offline-mock mode.")
    print(f"[home-watch] Configured escape window: {escape_seconds}s")

    # Simulate event 1: Home pressed once -> intercept and launch
    last_home_press = 0.0
    now = time.time()
    print("[home-watch-mock] Event: Foreground app is 'com.webos.app.home'")
    if now - last_home_press > escape_seconds:
        print(f"[home-watch-mock] Intercepting! Launching {TARGET_APP_ID}...")
        last_home_press = now
    else:
        print("[home-watch-mock] Double Home pressed: Allowing stock LG Home.")

    # Simulate event 2: Home pressed within escape window -> bypass allowed
    now = last_home_press + 1.0
    print("[home-watch-mock] Event: Foreground app is 'com.webos.app.home' again within 1.0s")
    if now - last_home_press <= escape_seconds:
        print("[home-watch-mock] Double Home detected! Bypass allowed: Staying on stock LG Home.")
    else:
        print(f"[home-watch-mock] Intercepting! Launching {TARGET_APP_ID}...")

    print("[home-watch-mock] Mock watch cycle completed successfully.")


def run_watch(
    tv_host: str = "192.168.1.68",
    escape_seconds: float = DEFAULT_ESCAPE_SECONDS,
    client_key_path: str = ".lgtv-key.json",
    offline_mock: bool = False,
) -> None:
    """Main watcher loop."""
    if offline_mock:
        run_mock_watch(escape_seconds)
        return

    print(f"[home-watch] Starting Home button watcher for TV at {tv_host}...")
    print(f"[home-watch] Escape window: {escape_seconds}s (double-press Home for stock settings)")

    last_home_time = 0.0
    backoff = 2.0

    while True:
        try:
            with lgtv.session(tv_host, client_key_path=client_key_path) as session:
                print("[home-watch] Connected to TV. Subscribing to foreground app changes...")
                backoff = 2.0

                # Subscribe to foreground app
                req_packet = {
                    "type": "subscribe",
                    "id": "sub_foreground",
                    "uri": "ssap://com.webos.applicationManager/getForegroundAppInfo",
                    "payload": {"subscribe": True},
                }
                session.ws.send(json.dumps(req_packet))

                while True:
                    raw = session.ws.recv(timeout=60)
                    msg = json.loads(raw)
                    payload = msg.get("payload", {})
                    app_id = payload.get("appId")

                    if app_id == STOCK_HOME_ID:
                        now = time.time()
                        elapsed = now - last_home_time
                        if elapsed <= escape_seconds:
                            print(f"[home-watch] Double-press detected ({elapsed:.2f}s). Allowing stock Home.")
                            last_home_time = 0.0
                        else:
                            print(f"[home-watch] Stock home detected. Redirecting to {TARGET_APP_ID}...")
                            last_home_time = now
                            session.call("ssap://system.launcher/launch", {"id": TARGET_APP_ID})
        except KeyboardInterrupt:
            print("[home-watch] Stopping on user request.")
            break
        except Exception as exc:
            print(f"[home-watch] Connection lost ({exc}). Reconnecting in {backoff:.1f}s...", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)


def main():
    parser = argparse.ArgumentParser(description="Watch and redirect LG webOS Home button to TV Home.")
    parser.add_argument("tv_host", nargs="?", default=os.environ.get("TV_HOST", "192.168.1.68"), help="TV IP Address")
    parser.add_argument("--escape-seconds", type=float, default=DEFAULT_ESCAPE_SECONDS, help="Escape window in seconds")
    parser.add_argument("--client-key-path", default=".lgtv-key.json", help="Path to pairing key cache")
    parser.add_argument("--offline-mock", action="store_true", help="Run simulated test loop and exit")

    args = parser.parse_args()
    try:
        run_watch(
            tv_host=args.tv_host,
            escape_seconds=args.escape_seconds,
            client_key_path=args.client_key_path,
            offline_mock=args.offline_mock,
        )
        return 0
    except Exception as exc:
        print(f"[home-watch] Fatal error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
