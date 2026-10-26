#!/usr/bin/env python3
"""
lgtv.py - LG webOS Hub SSAP WebSocket Client for Windows

Features:
- WebSocket TLS over wss://<TV_IP>:3001 with self-signed certificate acceptance.
- Unsigned pairing manifest (avoids 403 blacklisted certificate rejection on webOS Hub).
- Persistent client-key caching in .lgtv-key.json.
- Synchronous and asynchronous context manager support.
- Built-in --offline-mock / mock mode for testing without a physical TV.
"""

import argparse
import asyncio
import json
import os
import ssl
import sys
import time
from typing import Any, Dict, Optional

# Standard webOS permission set (28 permissions)
PERMISSIONS = [
    "LAUNCH", "LAUNCH_WEBAPP", "APP_TO_APP", "CLOSE", "TEST_OPEN", "TEST_PROTECTED",
    "CONTROL_AUDIO", "CONTROL_DISPLAY", "CONTROL_INPUT_JOYSTICK", "CONTROL_INPUT_MEDIA_RECORDING",
    "CONTROL_INPUT_MEDIA_PLAYBACK", "CONTROL_INPUT_TV", "CONTROL_POWER", "CONTROL_TV_SCREEN",
    "READ_APP_STATUS", "READ_CURRENT_CHANNEL", "READ_INPUT_DEVICE_LIST", "READ_NETWORK_STATE",
    "READ_RUNNING_APPS", "READ_TV_CHANNEL_LIST", "WRITE_NOTIFICATION_TOAST", "READ_POWER_STATE",
    "READ_COUNTRY_INFO", "CONTROL_INPUT_TEXT", "CONTROL_MOUSE_AND_KEYBOARD", "READ_INSTALLED_APPS",
    "READ_SETTINGS", "READ_STORAGE_DEVICE_LIST",
]

# Unsigned pairing manifest accepted by modern webOS Hub firmwares
MANIFEST = {
    "manifestVersion": 1,
    "appVersion": "1.0.0",
    "signed": {
        "created": "20261025",
        "appId": "com.gathin.tvhome",
        "vendorId": "com.gathin",
        "localizedAppNames": {"": "TV Home"},
        "localizedVendorNames": {"": "CleanYourTV"},
        "permissions": PERMISSIONS,
        "serial": "12345678",
    },
    "permissions": PERMISSIONS,
    "signatures": [],
}

# Standard mock responses for offline dry-run testing
MOCK_RESPONSES = {
    "ssap://com.webos.applicationManager/listLaunchPoints": {
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
                "launchPointId": "youtube.leanback.v4_default",
            },
            {
                "id": "netflix",
                "title": "Netflix",
                "icon": "http://192.168.1.68:3000/media/internal/icons/netflix.png",
                "largeIcon": "http://192.168.1.68:3000/media/internal/icons/netflix_large.png",
                "iconColor": "#e50914",
                "bgColor": "#000000",
                "hidden": False,
                "systemApp": False,
                "removable": True,
                "launchPointId": "netflix_default",
            },
            {
                "id": "com.amazon.ignition.ignite",
                "title": "Prime Video",
                "icon": "http://192.168.1.68:3000/media/internal/icons/prime.png",
                "largeIcon": "http://192.168.1.68:3000/media/internal/icons/prime_large.png",
                "iconColor": "#00a8e1",
                "bgColor": "#000000",
                "hidden": False,
                "systemApp": False,
                "removable": True,
                "launchPointId": "com.amazon.ignition.ignite_default",
            },
            {
                "id": "com.webos.app.browser",
                "title": "Web Browser",
                "icon": "http://192.168.1.68:3000/media/internal/icons/browser.png",
                "largeIcon": "http://192.168.1.68:3000/media/internal/icons/browser_large.png",
                "iconColor": "#0ea5e9",
                "bgColor": "#0ea5e9",
                "hidden": False,
                "systemApp": True,
                "removable": False,
                "launchPointId": "com.webos.app.browser_default",
            },
            {
                "id": "com.webos.app.livetv",
                "title": "Live TV",
                "icon": "http://192.168.1.68:3000/media/internal/icons/livetv.png",
                "largeIcon": "http://192.168.1.68:3000/media/internal/icons/livetv_large.png",
                "iconColor": "#10b981",
                "bgColor": "#10b981",
                "hidden": False,
                "systemApp": True,
                "removable": False,
                "launchPointId": "com.webos.app.livetv_default",
            },
            {
                "id": "com.gathin.tvhome",
                "title": "TV Home",
                "icon": "icon.png",
                "largeIcon": "largeIcon.png",
                "iconColor": "#3b82f6",
                "bgColor": "#000000",
                "hidden": True,
                "systemApp": False,
                "removable": True,
                "launchPointId": "com.gathin.tvhome_default",
            },
        ],
    },
    "ssap://tv/getExternalInputList": {
        "returnValue": True,
        "devices": [
            {
                "id": "HDMI_1",
                "label": "HDMI 1",
                "portIdx": 1,
                "appId": "com.webos.app.hdmi1",
                "icon": "http://192.168.1.68:3000/media/internal/icons/hdmi1.png",
                "connected": True,
                "subList": [],
            },
            {
                "id": "HDMI_2",
                "label": "HDMI 2 (eARC)",
                "portIdx": 2,
                "appId": "com.webos.app.hdmi2",
                "icon": "http://192.168.1.68:3000/media/internal/icons/hdmi2.png",
                "connected": True,
                "subList": [],
            },
            {
                "id": "HDMI_3",
                "label": "HDMI 3",
                "portIdx": 3,
                "appId": "com.webos.app.hdmi3",
                "icon": "http://192.168.1.68:3000/media/internal/icons/hdmi3.png",
                "connected": False,
                "subList": [],
            },
            {
                "id": "AV_1",
                "label": "AV Composite",
                "portIdx": 4,
                "appId": "com.webos.app.externalinput.av1",
                "icon": "http://192.168.1.68:3000/media/internal/icons/av.png",
                "connected": False,
                "subList": [],
            },
        ],
    },
    "ssap://system/getSystemInfo": {
        "returnValue": True,
        "modelName": "JVC LT-32KB116",
        "boardType": "LG webOS Hub",
        "firmwareVersion": "03.34.90",
        "features": {
            "screenSize": "32",
            "resolution": "1920x1080",
            "wifi": True,
            "hdr": False,
        },
    },
    "ssap://system.notifications/createToast": {
        "returnValue": True,
        "toastId": "toast_mock_001",
    },
    "ssap://com.webos.applicationManager/getForegroundAppInfo": {
        "returnValue": True,
        "appId": "com.webos.app.livetv",
        "windowId": "",
        "processId": "",
    },
}


def load_client_key(host: str, client_key_path: str = ".lgtv-key.json") -> Optional[str]:
    """Load cached pairing token for host."""
    if not os.path.exists(client_key_path):
        return None
    try:
        with open(client_key_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(host)
    except Exception:
        return None


def save_client_key(host: str, client_key: str, client_key_path: str = ".lgtv-key.json") -> None:
    """Save persistent pairing token for host."""
    data = {}
    if os.path.exists(client_key_path):
        try:
            with open(client_key_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    data[host] = client_key
    try:
        with open(client_key_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        print(f"[lgtv] Warning: Failed to save client key to {client_key_path}: {exc}", file=sys.stderr)


class MockSession:
    """Mock session simulating webOS SSAP WebSocket for offline testing."""

    def __init__(self, host: str = "mock", client_key_path: str = ".lgtv-key.json"):
        self.host = host
        self.client_key_path = client_key_path
        self.client_key = "mock_client_key_jvc_987654321"
        self.is_mock = True
        save_client_key(self.host, self.client_key, self.client_key_path)

    def call(self, uri: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return simulated SSAP response."""
        if uri in MOCK_RESPONSES:
            return json.loads(json.dumps(MOCK_RESPONSES[uri]))
        return {"returnValue": True, "uri": uri, "mock": True}

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()


class LGTVSession:
    """Synchronous webOS SSAP client using websockets.sync.client."""

    def __init__(self, host: str, client_key_path: str = ".lgtv-key.json", timeout: int = 20):
        self.host = host
        self.client_key_path = client_key_path
        self.timeout = timeout
        self.ws = None
        self.req_id = 0
        self.is_mock = False
        self._connect()

    def _connect(self) -> None:
        import websockets.sync.client

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        uri = f"wss://{self.host}:3001"
        self.ws = websockets.sync.client.connect(
            uri,
            ssl=ssl_ctx,
            open_timeout=self.timeout,
            close_timeout=5,
        )

        client_key = load_client_key(self.host, self.client_key_path)
        register_payload = {
            "type": "register",
            "id": "register_0",
            "payload": {
                "forcePairing": False,
                "pairingType": "PROMPT",
                "manifest": MANIFEST,
            },
        }
        if client_key:
            register_payload["payload"]["client-key"] = client_key
        else:
            print(f"[lgtv] Pairing request sent to {self.host}.")
            print(">>> PLEASE LOOK AT YOUR TV SCREEN AND CLICK 'ALLOW' TO AUTHORIZE <<<")

        self.ws.send(json.dumps(register_payload))

        # Wait for registered response
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            raw = self.ws.recv(timeout=self.timeout)
            msg = json.loads(raw)
            if msg.get("type") == "registered":
                new_key = msg.get("payload", {}).get("client-key")
                if new_key:
                    save_client_key(self.host, new_key, self.client_key_path)
                return
            elif msg.get("type") == "error":
                raise ConnectionError(f"SSAP Registration failed: {msg.get('error')}")

        raise TimeoutError(f"Pairing timed out on {self.host} after {self.timeout}s.")

    def call(self, uri: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send SSAP request and receive response."""
        self.req_id += 1
        req_id = f"req_{self.req_id}"

        packet = {
            "type": "request",
            "id": req_id,
            "uri": uri,
            "payload": payload or {},
        }
        self.ws.send(json.dumps(packet))

        start_time = time.time()
        while time.time() - start_time < self.timeout:
            raw = self.ws.recv(timeout=self.timeout)
            msg = json.loads(raw)
            if msg.get("id") == req_id:
                return msg.get("payload", {})
            # Ignore unrelated background broadcasts
        raise TimeoutError(f"Request {uri} timed out on {self.host}.")

    def close(self) -> None:
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()


def session(host: str, client_key_path: str = ".lgtv-key.json", mock: bool = False):
    """
    Establish an SSAP session with the TV or create a mock session.
    Usable as a context manager: `with lgtv.session(host) as client:`
    """
    if mock or host == "mock" or os.environ.get("LGTV_MOCK") == "1" or "--offline-mock" in sys.argv:
        return MockSession(host=host or "mock", client_key_path=client_key_path)
    return LGTVSession(host=host, client_key_path=client_key_path)


def call(session_obj, uri: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Module-level call wrapper: lgtv.call(ws, uri, payload) -> dict."""
    if hasattr(session_obj, "call"):
        return session_obj.call(uri, payload)
    raise TypeError(f"Invalid session object: {session_obj}")


def main():
    parser = argparse.ArgumentParser(description="LG webOS SSAP communication client.")
    parser.add_argument("host", nargs="?", default="192.168.1.68", help="TV IP address")
    parser.add_argument("--offline-mock", action="store_true", help="Run with mock responses")
    parser.add_argument("--client-key-path", default=".lgtv-key.json", help="Path to pairing key cache")
    parser.add_argument("--test-info", action="store_true", help="Query and print system info")
    parser.add_argument("--test-apps", action="store_true", help="Query and print launch points")

    args = parser.parse_args()

    try:
        with session(args.host, client_key_path=args.client_key_path, mock=args.offline_mock) as tv:
            info = call(tv, "ssap://system/getSystemInfo")
            print("System Info:", json.dumps(info, indent=2))

            if args.test_apps:
                apps = call(tv, "ssap://com.webos.applicationManager/listLaunchPoints")
                print(f"Launch Points count: {len(apps.get('launchPoints', []))}")
        return 0
    except Exception as exc:
        print(f"Error connecting to TV: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
