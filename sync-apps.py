#!/usr/bin/env python3
"""
sync-apps.py - Synchronize apps and external inputs from LG webOS Hub to TV Home launcher

Queries:
- ssap://com.webos.applicationManager/listLaunchPoints
- ssap://tv/getExternalInputList

Downloads application icons with Windows-safe filename sanitization and compiles
the data into app/apps.js. Supports --offline-mock for testing without TV.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import lgtv


def sanitize_filename(name: str) -> str:
    """Sanitize filename for Windows filesystem (removes <>:"/\\|?*)."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


import ssl

def download_icon(url: str, dest_path: str, fallback_icon: str = "app/icon.png", timeout: int = 5, offline_mock: bool = False) -> str:
    """
    Download icon from TV HTTP server. If unreachable, mock, or local, fall back gracefully.
    Returns relative path to be referenced in JavaScript.
    """
    if not offline_mock and url and (url.startswith("http://") or url.startswith("https://")):
        try:
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                data = resp.read()
                if len(data) > 500:
                    with open(dest_path, "wb") as f:
                        f.write(data)
                    return dest_path.replace("\\", "/")
        except Exception:
            pass

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        return dest_path.replace("\\", "/")

    # Fallback to default icon copy
    if os.path.exists(fallback_icon):
        try:
            import shutil
            shutil.copyfile(fallback_icon, dest_path)
            return dest_path.replace("\\", "/")
        except Exception:
            pass

    # Fallback to pure minimal PNG
    try:
        from tools.generate_icons import create_solid_png
        create_solid_png(dest_path, (80, 80))
        return dest_path.replace("\\", "/")
    except Exception:
        return fallback_icon.replace("\\", "/")


def sync_apps(
    tv_host: str = "192.168.1.68",
    offline_mock: bool = False,
    output_file: str = "app/apps.js",
    icons_dir: str = "app/icons",
    client_key_path: str = ".lgtv-key.json",
) -> dict:
    """Fetch apps and inputs from TV and generate apps.js."""
    os.makedirs(icons_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

    print(f"[sync-apps] Connecting to TV at {tv_host} (offline_mock={offline_mock})...")

    with lgtv.session(tv_host, client_key_path=client_key_path, mock=offline_mock) as session:
        # 1. Fetch launch points (installed applications)
        lp_response = lgtv.call(session, "ssap://com.webos.applicationManager/listLaunchPoints")
        raw_apps = lp_response.get("launchPoints", [])

        # 2. Fetch external inputs (HDMI, AV)
        inputs_response = lgtv.call(session, "ssap://tv/getExternalInputList")
        raw_inputs = inputs_response.get("devices", [])

    print(f"[sync-apps] Retrieved {len(raw_apps)} launch points and {len(raw_inputs)} external inputs.")

    # Process and filter applications
    processed_apps = []
    for app in raw_apps:
        app_id = app.get("id", "")
        # Filter hidden apps
        if app.get("hidden") is True or app_id == "com.gathin.tvhome":
            continue

        sanitized_id = sanitize_filename(app_id)
        icon_filename = f"{sanitized_id}.png"
        icon_dest = os.path.join(icons_dir, icon_filename)
        rel_icon_path = f"icons/{icon_filename}"

        # Download or prepare icon
        remote_icon_url = app.get("largeIcon") or app.get("icon") or ""
        download_icon(remote_icon_url, icon_dest, offline_mock=offline_mock)

        processed_apps.append({
            "id": app_id,
            "title": app.get("title", app_id),
            "icon": rel_icon_path,
            "largeIcon": rel_icon_path,
            "iconColor": app.get("iconColor") or "#3b82f6",
            "bgColor": app.get("bgColor") or "#000000",
            "systemApp": app.get("systemApp", False),
            "removable": app.get("removable", True),
        })

    # Process external inputs
    processed_inputs = []
    for inp in raw_inputs:
        inp_id = inp.get("id", "")
        inp_label = inp.get("label", inp_id)
        inp_app = inp.get("appId") or f"com.webos.app.{inp_id.lower()}"
        sanitized_inp_id = sanitize_filename(inp_id)
        icon_filename = f"input_{sanitized_inp_id}.png"
        icon_dest = os.path.join(icons_dir, icon_filename)
        rel_icon_path = f"icons/{icon_filename}"

        download_icon(inp.get("icon", ""), icon_dest, offline_mock=offline_mock)

        processed_inputs.append({
            "id": inp_id,
            "label": inp_label,
            "portIdx": inp.get("portIdx") or inp.get("port") or 1,
            "appId": inp_app,
            "connected": inp.get("connected", False),
            "icon": rel_icon_path,
        })

    result_data = {
        "apps": processed_apps,
        "inputs": processed_inputs,
    }

    # Generate apps.js content
    js_content = f"""// Generated by sync-apps.py on {tv_host}
window.TV_APPS = {json.dumps(result_data, indent=2)};

// Global aliases for launcher runtime and test suites
window.APPS = window.TV_APPS.apps;
window.INPUTS = window.TV_APPS.inputs;
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"[sync-apps] Successfully written {len(processed_apps)} apps and {len(processed_inputs)} inputs to {output_file}")
    return result_data


def main():
    parser = argparse.ArgumentParser(description="Synchronize webOS apps & inputs to TV Home.")
    parser.add_argument("tv_host", nargs="?", default=os.environ.get("TV_HOST", "192.168.1.68"), help="TV IP Address")
    parser.add_argument("--offline-mock", action="store_true", help="Run with mock SSAP responses without physical TV")
    parser.add_argument("--output", "-o", default="app/apps.js", help="Path to generated apps.js")
    parser.add_argument("--icons-dir", default="app/icons", help="Directory to save downloaded icons")
    parser.add_argument("--client-key-path", default=".lgtv-key.json", help="Path to pairing key cache")

    args = parser.parse_args()

    try:
        sync_apps(
            tv_host=args.tv_host,
            offline_mock=args.offline_mock,
            output_file=args.output,
            icons_dir=args.icons_dir,
            client_key_path=args.client_key_path,
        )
        return 0
    except Exception as exc:
        print(f"[sync-apps] Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
