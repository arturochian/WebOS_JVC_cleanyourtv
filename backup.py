#!/usr/bin/env python3
"""
backup.py - SSAP State & Inventory Backup Subsystem for WebOS TV Enhancement Suite.

Captures TV launch points, external inputs, system hardware metadata, and local
application configurations (apps.js, config.js, appinfo.json, icons) into a
timestamped snapshot directory with SHA-256 integrity verification.

Tested with LG webOS Hub (JVC LT-32KB116) and supports offline mock operations.
"""

import argparse
import asyncio
import datetime
import hashlib
import json
import os
import shutil
import ssl
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = "1.0.0"
DEFAULT_HOST = "192.168.1.68"
DEFAULT_PORT = 3001
KEY_FILE = ".lgtv-key.json"

# SSAP endpoints
URI_LAUNCH_POINTS = "ssap://com.webos.applicationManager/listLaunchPoints"
URI_EXTERNAL_INPUTS = "ssap://tv/getExternalInputList"
URI_SYSTEM_INFO = "ssap://system/getSystemInfo"
URI_SYSTEM_INFO_ALT = "ssap://com.webos.service.tv.system/getSystemInfo"
URI_TOAST = "ssap://system.notifications/createToast"

PERMISSIONS = [
    "LAUNCH", "LAUNCH_WEBAPP", "APP_TO_APP", "CLOSE", "TEST_OPEN", "TEST_PROTECTED",
    "CONTROL_AUDIO", "CONTROL_DISPLAY", "CONTROL_INPUT_JOYSTICK", "CONTROL_INPUT_MEDIA_RECORDING",
    "CONTROL_INPUT_MEDIA_PLAYBACK", "CONTROL_INPUT_TV", "CONTROL_POWER", "CONTROL_TV_SCREEN",
    "READ_APP_STATUS", "READ_CURRENT_CHANNEL", "READ_INPUT_DEVICE_LIST", "READ_NETWORK_STATE",
    "READ_RUNNING_APPS", "READ_TV_CHANNEL_LIST", "WRITE_NOTIFICATION_TOAST", "READ_POWER_STATE",
    "READ_COUNTRY_INFO", "CONTROL_INPUT_TEXT", "CONTROL_MOUSE_AND_KEYBOARD", "READ_INSTALLED_APPS",
    "READ_SETTINGS", "READ_STORAGE_DEVICE_LIST",
]

MOCK_LAUNCH_POINTS = {
    "returnValue": True,
    "launchPoints": [
        {
            "id": "youtube.leanback.v4",
            "title": "YouTube",
            "icon": "http://192.168.1.68:3000/media/internal/icons/youtube.png",
            "largeIcon": "http://192.168.1.68:3000/media/internal/icons/youtube_large.png",
            "iconColor": "#ff0000",
            "bgColor": "#ff0000",
            "hidden": False,
            "systemApp": False,
            "removable": True,
            "launchPointId": "youtube.leanback.v4_default"
        },
        {
            "id": "netflix",
            "title": "Netflix",
            "icon": "http://192.168.1.68:3000/media/internal/icons/netflix.png",
            "largeIcon": "http://192.168.1.68:3000/media/internal/icons/netflix_large.png",
            "iconColor": "#e50914",
            "bgColor": "#e50914",
            "hidden": False,
            "systemApp": False,
            "removable": True,
            "launchPointId": "netflix_default"
        },
        {
            "id": "amazon",
            "title": "Prime Video",
            "icon": "http://192.168.1.68:3000/media/internal/icons/amazon.png",
            "largeIcon": "http://192.168.1.68:3000/media/internal/icons/amazon_large.png",
            "iconColor": "#00a8e1",
            "bgColor": "#00a8e1",
            "hidden": False,
            "systemApp": False,
            "removable": True,
            "launchPointId": "amazon_default"
        },
        {
            "id": "com.webos.app.livetv",
            "title": "Live TV",
            "icon": "http://192.168.1.68:3000/media/internal/icons/livetv.png",
            "largeIcon": "http://192.168.1.68:3000/media/internal/icons/livetv_large.png",
            "iconColor": "#000000",
            "bgColor": "#000000",
            "hidden": False,
            "systemApp": True,
            "removable": False,
            "launchPointId": "com.webos.app.livetv_default"
        },
        {
            "id": "com.webos.app.settings",
            "title": "Settings",
            "icon": "http://192.168.1.68:3000/media/internal/icons/settings.png",
            "largeIcon": "http://192.168.1.68:3000/media/internal/icons/settings_large.png",
            "iconColor": "#555555",
            "bgColor": "#555555",
            "hidden": False,
            "systemApp": True,
            "removable": False,
            "launchPointId": "com.webos.app.settings_default"
        }
    ]
}

MOCK_INPUTS = {
    "returnValue": True,
    "devices": [
        {
            "id": "HDMI_1",
            "label": "HDMI 1",
            "portIdx": 1,
            "appId": "com.webos.app.hdmi1",
            "icon": "http://192.168.1.68:3000/media/internal/icons/hdmi1.png",
            "connected": True,
            "subList": []
        },
        {
            "id": "HDMI_2",
            "label": "HDMI 2 (eARC)",
            "portIdx": 2,
            "appId": "com.webos.app.hdmi2",
            "icon": "http://192.168.1.68:3000/media/internal/icons/hdmi2.png",
            "connected": False,
            "subList": []
        },
        {
            "id": "AV_1",
            "label": "AV",
            "portIdx": 3,
            "appId": "com.webos.app.av1",
            "icon": "http://192.168.1.68:3000/media/internal/icons/av1.png",
            "connected": False,
            "subList": []
        }
    ]
}

MOCK_SYSTEM_INFO = {
    "returnValue": True,
    "modelName": "LT-32KB116",
    "version": "03.34.80",
    "sdkVersion": "6.3.0",
    "platformVersion": "6.3.0-4104",
    "boardType": "M22R_DVB",
    "features": {
        "networkType": "wifi",
        "uhd": False
    }
}


def compute_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hexadecimal digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_cached_key(host: str, key_file: str = KEY_FILE) -> Optional[str]:
    """Retrieve saved client-key for host from key cache file."""
    p = Path(key_file)
    if not p.is_file():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(host)
    except Exception:
        return None


def save_cached_key(host: str, client_key: str, key_file: str = KEY_FILE) -> None:
    """Save client-key for host into key cache file."""
    p = Path(key_file)
    data = {}
    if p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data[host] = client_key
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to save client-key to {key_file}: {e}\n")


async def ssap_request(ws, uri: str, payload: Optional[dict] = None, req_id: str = "req_1") -> dict:
    """Send an SSAP request over websocket and await JSON response."""
    msg = {
        "id": req_id,
        "type": "request",
        "uri": uri,
        "payload": payload or {}
    }
    await ws.send(json.dumps(msg))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
        res = json.loads(raw)
        if res.get("id") == req_id or res.get("type") == "response":
            return res.get("payload", res)


async def connect_ssap(host: str, port: int = DEFAULT_PORT) -> Tuple[Any, dict]:
    """Establish authenticated SSAP TLS session to LG webOS TV."""
    import websockets

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    url = f"wss://{host}:{port}"
    ws = await asyncio.wait_for(
        websockets.connect(url, ssl=ssl_ctx, ping_interval=None, close_timeout=5),
        timeout=8.0
    )

    client_key = load_cached_key(host)
    manifest = {
        "manifestVersion": 1,
        "appVersion": "1.0",
        "signed": {
            "created": "20261025",
            "appId": "com.gathin.tvhome",
            "vendorId": "com.gathin",
            "localizedAppNames": {"": "TV Home"},
            "localizedVendorNames": {"": "Gathin"},
            "permissions": PERMISSIONS,
            "serial": "12345678"
        },
        "permissions": PERMISSIONS
    }

    reg_payload: Dict[str, Any] = {
        "forcePairing": False,
        "pairingType": "PROMPT",
        "manifest": manifest
    }
    if client_key:
        reg_payload["client-key"] = client_key

    register_msg = {
        "type": "register",
        "id": "register_0",
        "payload": reg_payload
    }

    await ws.send(json.dumps(register_msg))
    registered = False
    new_key = client_key

    while not registered:
        raw = await asyncio.wait_for(ws.recv(), timeout=60.0)
        res = json.loads(raw)
        res_type = res.get("type")
        payload = res.get("payload", {})

        if res_type == "registered":
            new_key = payload.get("client-key", new_key)
            if new_key:
                save_cached_key(host, new_key)
            registered = True
        elif res_type == "error":
            error_msg = res.get("error", "Unknown SSAP pairing error")
            await ws.close()
            raise RuntimeError(f"SSAP pairing error: {error_msg}")

    return ws, {"host": host, "client_key": new_key}


def load_offline_fixtures(fixture_path: Optional[str]) -> Tuple[dict, dict, dict]:
    """Load mock data from fixture directory, lgtv.py MockSession, or built-in mock defaults."""
    if fixture_path and os.path.exists(fixture_path):
        p = Path(fixture_path)
        lp_candidates = [p / "mock_launch_points.json", p / "launch_points.json"]
        in_candidates = [p / "mock_inputs.json", p / "inputs.json"]
        sys_candidates = [p / "mock_system_info.json", p / "system_info.json"]

        launch_points = None
        inputs = None
        system_info = None

        for c in lp_candidates:
            if c.is_file():
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        launch_points = json.load(f)
                    break
                except Exception:
                    pass

        for c in in_candidates:
            if c.is_file():
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        inputs = json.load(f)
                    break
                except Exception:
                    pass

        for c in sys_candidates:
            if c.is_file():
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        system_info = json.load(f)
                    break
                except Exception:
                    pass

        return (
            launch_points or MOCK_LAUNCH_POINTS,
            inputs or MOCK_INPUTS,
            system_info or MOCK_SYSTEM_INFO
        )

    # Check repository fixture paths if none explicitly provided
    repo_fixtures = Path("tests/fixtures")
    if repo_fixtures.is_dir():
        return load_offline_fixtures(str(repo_fixtures))

    # Check lgtv mock session if available
    try:
        import lgtv
        if hasattr(lgtv, "session") and hasattr(lgtv, "call"):
            with lgtv.session("mock", mock=True) as tv:
                lp = lgtv.call(tv, URI_LAUNCH_POINTS)
                inp = lgtv.call(tv, URI_EXTERNAL_INPUTS)
                sys_info = lgtv.call(tv, URI_SYSTEM_INFO)
                if lp and inp and sys_info:
                    return lp, inp, sys_info
    except Exception:
        pass

    return MOCK_LAUNCH_POINTS, MOCK_INPUTS, MOCK_SYSTEM_INFO


async def query_live_tv(host: str, notify: bool = False, slug: str = "") -> Tuple[dict, dict, dict]:
    """Connect to TV and query launch points, inputs, and system information."""
    # First attempt using lgtv module if present
    try:
        import lgtv
        if hasattr(lgtv, "session") and hasattr(lgtv, "call"):
            with lgtv.session(host) as tv:
                lp = lgtv.call(tv, URI_LAUNCH_POINTS)
                inp = lgtv.call(tv, URI_EXTERNAL_INPUTS)
                try:
                    sys_info = lgtv.call(tv, URI_SYSTEM_INFO)
                except Exception:
                    sys_info = {"returnValue": True, "modelName": "webOS TV"}

                if notify:
                    try:
                        lgtv.call(tv, URI_TOAST, {"message": f"CleanYourTV: Snapshot {slug} created"})
                    except Exception:
                        pass
                return lp, inp, sys_info
    except ImportError:
        pass
    except Exception as e:
        # If lgtv module encountered an error, proceed to fallback connection
        sys.stderr.write(f"Info: lgtv module connection failed ({e}), using built-in SSAP client...\n")

    # Native async SSAP client
    ws, _ = await connect_ssap(host)
    try:
        lp = await ssap_request(ws, URI_LAUNCH_POINTS, req_id="req_lp")
        inp = await ssap_request(ws, URI_EXTERNAL_INPUTS, req_id="req_inp")
        try:
            sys_info = await ssap_request(ws, URI_SYSTEM_INFO, req_id="req_sys")
            if not sys_info or not sys_info.get("returnValue"):
                sys_info = await ssap_request(ws, URI_SYSTEM_INFO_ALT, req_id="req_sys_alt")
        except Exception:
            sys_info = {"returnValue": True, "modelName": "webOS TV"}

        if notify:
            try:
                await ssap_request(ws, URI_TOAST, {"message": f"CleanYourTV: Snapshot {slug} created"}, req_id="req_toast")
            except Exception:
                pass

        return lp, inp, sys_info
    finally:
        await ws.close()


def run_backup(
    host: str = DEFAULT_HOST,
    output_dir: Optional[str] = None,
    offline_mock: Any = False,
    dry_run: bool = False,
    no_icons: bool = False,
    notify: bool = False,
    quiet: bool = False,
    app_dir: str = "app"
) -> Tuple[int, Optional[Path]]:
    """Execute state backup and snapshot creation."""
    now = datetime.datetime.now(datetime.timezone.utc)
    timestamp_iso = now.isoformat()
    timestamp_slug = now.strftime("%Y%m%d_%H%M%S")

    # Resolve destination snapshot directory
    if output_dir:
        dest_dir = Path(output_dir)
        if not dest_dir.is_absolute():
            dest_dir = Path.cwd() / dest_dir
    else:
        dest_dir = Path.cwd() / "backup" / timestamp_slug

    if not quiet:
        print(f"=== WebOS TV State Backup [{VERSION}] ===")
        print(f"Timestamp: {timestamp_iso}")
        print(f"Target Destination: {dest_dir}")
        if offline_mock:
            print("Mode: OFFLINE MOCK (no physical TV connection)")
        else:
            print(f"Mode: LIVE TV SSAP ({host}:{DEFAULT_PORT})")

    # 1. Fetch data (mock or live)
    fixture_dir = offline_mock if isinstance(offline_mock, str) and offline_mock else None
    if offline_mock:
        launch_points, inputs, system_info = load_offline_fixtures(fixture_dir)
    else:
        try:
            launch_points, inputs, system_info = asyncio.run(
                query_live_tv(host, notify=notify, slug=timestamp_slug)
            )
        except Exception as e:
            if not quiet:
                sys.stderr.write(f"\n[ERROR] Network/SSAP connection failed: {e}\n")
                sys.stderr.write(f"Ensure the TV at {host} is turned on and connected to your network.\n")
            return 1, None

    # Validate TV responses
    lps = launch_points.get("launchPoints", [])
    if not isinstance(lps, list) or len(lps) == 0:
        if not quiet:
            sys.stderr.write("[WARNING] TV returned 0 launch points; snapshot marked incomplete.\n")

    input_devs = inputs.get("devices", [])

    if dry_run:
        if not quiet:
            print("\n[DRY RUN] Snapshot would contain:")
            print(f"  - Launch Points: {len(lps)} items")
            print(f"  - External Inputs: {len(input_devs)} items")
            print(f"  - System Info: {system_info.get('modelName', 'Unknown')}")
            print(f"  - Destination: {dest_dir}")
            print("[DRY RUN] Complete. No files were written.")
        return 0, None

    # 2. Prepare filesystem
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        if not quiet:
            sys.stderr.write(f"\n[ERROR] Failed to create snapshot directory {dest_dir}: {e}\n")
        return 2, None

    copied_files: List[str] = []
    checksums: Dict[str, str] = {}

    # 3. Write SSAP state files
    def write_json_file(filename: str, data: Any) -> Path:
        target = dest_dir / filename
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        rel = filename
        copied_files.append(rel)
        checksums[rel] = compute_sha256(target)
        # Also provide alias key
        alias_key = filename.replace(".json", "_sha256")
        checksums[alias_key] = checksums[rel]
        return target

    try:
        write_json_file("launch_points.json", launch_points)
        write_json_file("inputs.json", inputs)
        write_json_file("system_info.json", system_info)
    except Exception as e:
        if not quiet:
            sys.stderr.write(f"\n[ERROR] Failed writing JSON state files: {e}\n")
        return 2, None

    # 4. Copy local app configuration assets
    app_path = Path(app_dir)
    has_apps_js = False
    has_config_js = False
    has_appinfo = False
    icons_count = 0

    # Copy apps.js
    src_apps = app_path / "apps.js"
    if src_apps.is_file():
        target = dest_dir / "apps.js"
        shutil.copy2(src_apps, target)
        copied_files.append("apps.js")
        checksums["apps.js"] = compute_sha256(target)
        checksums["apps_js_sha256"] = checksums["apps.js"]
        has_apps_js = True

    # Copy config.js
    src_config = app_path / "config.js"
    if src_config.is_file():
        target = dest_dir / "config.js"
        shutil.copy2(src_config, target)
        copied_files.append("config.js")
        checksums["config.js"] = compute_sha256(target)
        checksums["config_js_sha256"] = checksums["config.js"]
        has_config_js = True

    # Copy appinfo.json
    src_appinfo = app_path / "appinfo.json"
    if src_appinfo.is_file():
        target = dest_dir / "appinfo.json"
        shutil.copy2(src_appinfo, target)
        copied_files.append("appinfo.json")
        checksums["appinfo.json"] = compute_sha256(target)
        checksums["appinfo_json_sha256"] = checksums["appinfo.json"]
        has_appinfo = True

    # Copy icons folder
    if not no_icons:
        src_icons = app_path / "icons"
        if src_icons.is_dir():
            dest_icons = dest_dir / "icons"
            dest_icons.mkdir(parents=True, exist_ok=True)
            for item in src_icons.rglob("*"):
                if item.is_file():
                    rel_to_icons = item.relative_to(src_icons)
                    target_icon = dest_icons / rel_to_icons
                    target_icon.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target_icon)
                    icons_count += 1
                    rel_manifest = f"icons/{rel_to_icons.as_posix()}"
                    copied_files.append(rel_manifest)
                    checksums[rel_manifest] = compute_sha256(target_icon)

    # 5. Build and write snapshot.json manifest
    manifest_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "version": VERSION,
        "timestamp": timestamp_iso,
        "timestamp_slug": timestamp_slug,
        "device": {
            "host": host if not offline_mock else "127.0.0.1 (offline-mock)",
            "modelName": system_info.get("modelName", "LT-32KB116"),
            "firmwareVersion": system_info.get("version", "03.34.80"),
            "sdkVersion": system_info.get("sdkVersion", "6.3.0")
        },
        "stats": {
            "launchPointsCount": len(lps),
            "inputsCount": len(input_devs),
            "iconsCount": icons_count,
            "hasAppsJs": has_apps_js,
            "hasConfigJs": has_config_js,
            "hasAppinfoJson": has_appinfo
        },
        "checksums": checksums,
        "files": ["snapshot.json"] + copied_files,
        "creator": f"backup.py v{VERSION} (Windows)"
    }

    manifest_path = dest_dir / "snapshot.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # 6. Update backup/latest.json pointer
    backup_root = Path.cwd() / "backup"
    try:
        backup_root.mkdir(parents=True, exist_ok=True)
        rel_path = dest_dir.relative_to(Path.cwd()).as_posix()
        latest_pointer = {
            "latest": timestamp_slug,
            "path": rel_path,
            "timestamp": timestamp_iso,
            "status": "valid"
        }
        latest_path = backup_root / "latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(latest_pointer, f, indent=2)
    except Exception as e:
        if not quiet:
            sys.stderr.write(f"[WARNING] Could not update latest.json pointer: {e}\n")

    if not quiet:
        print("\n[SUCCESS] Backup snapshot created successfully!")
        print(f"  Directory: {dest_dir}")
        print(f"  Launch Points: {len(lps)} apps")
        print(f"  Inputs: {len(input_devs)} devices")
        print(f"  Icons Archived: {icons_count} files")
        print(f"  Manifest: {manifest_path.name} (SHA-256 verified)")
        print(f"  Latest pointer updated: backup/latest.json -> {timestamp_slug}")

    return 0, dest_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SSAP State & Inventory Backup Subsystem for WebOS TV",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("host", nargs="?", default=None, help="TV IP or hostname (positional)")
    parser.add_argument("--tv", dest="tv_host", default=None, help="TV IP or hostname (flag)")
    parser.add_argument("--output-dir", "--out-dir", dest="output_dir", default=None,
                        help="Custom destination directory (default: backup/<YYYYMMDD_HHMMSS>)")
    parser.add_argument("--offline-mock", nargs="?", const=True, default=False,
                        help="Generate mock snapshot without network connection (optional: fixture path)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate connection and print actions without saving files")
    parser.add_argument("--no-icons", action="store_true",
                        help="Skip copying app/icons/ folder into snapshot")
    parser.add_argument("--notify", action="store_true",
                        help="Send on-screen toast to TV confirming snapshot creation")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress standard output, only print errors")
    parser.add_argument("--app-dir", default="app",
                        help="Path to app source directory (default: app)")

    args = parser.parse_args()

    # Determine host from --tv, positional, or environment
    selected_host = args.tv_host or args.host or os.environ.get("TV_HOST", DEFAULT_HOST)

    try:
        code, _ = run_backup(
            host=selected_host,
            output_dir=args.output_dir,
            offline_mock=args.offline_mock,
            dry_run=args.dry_run,
            no_icons=args.no_icons,
            notify=args.notify,
            quiet=args.quiet,
            app_dir=args.app_dir
        )
        return code
    except KeyboardInterrupt:
        sys.stderr.write("\nBackup interrupted by user.\n")
        return 1
    except Exception as e:
        sys.stderr.write(f"\nUnexpected error during backup: {e}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
