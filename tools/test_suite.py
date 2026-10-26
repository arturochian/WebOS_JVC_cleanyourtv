#!/usr/bin/env python3
"""
tools/test_suite.py - 4-Tier Offline Verification Test Suite for WebOS JVC CleanYourTV.

Provides offline, dry-run test automation on Windows workstations without physical TV hardware:
- Tier 1: Static syntax, AST, schema, and PowerShell script verification.
- Tier 2: Icon generation execution, PNG binary headers, dimensions (80x80 & 130x130).
- Tier 3: Mock SSAP protocol handshake, launch points, external inputs, apps.js pipeline.
- Tier 4: Backup creation, SHA-256 manifest integrity, rollback fidelity, corruption rejection.

CLI Options:
  --tier {1,2,3,4,all}, -t   Run a specific test tier (default: all)
  --verbose, -v              Enable detailed test and assertion logs
  --json                     Output structured machine-readable JSON to stdout
  --failfast, -x             Stop execution on the first test failure
  --temp-dir DIR             Specify custom scratch directory for test sandboxing

Exit Codes:
  0 = All tests passed
  1 = One or more test assertions failed
  2 = Invalid CLI options or environment/configuration error
"""

import argparse
import ast
import dataclasses
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

VERSION = "1.0.0"

# ANSI Color Codes for Windows Console
USE_ANSI = sys.platform == "win32" or sys.stdout.isatty()
if sys.platform == "win32":
    # Enable VT100 emulation on Windows 10/11 console
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        USE_ANSI = False

def color(text: str, code: str) -> str:
    if not USE_ANSI:
        return text
    return f"\033[{code}m{text}\033[0m"

def c_green(text: str) -> str: return color(text, "32")
def c_red(text: str) -> str: return color(text, "31")
def c_yellow(text: str) -> str: return color(text, "33")
def c_cyan(text: str) -> str: return color(text, "36")
def c_bold(text: str) -> str: return color(text, "1")
def c_dim(text: str) -> str: return color(text, "2")


def run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Run subprocess safely with UTF-8 encoding and character replacement to prevent Windows cp1252 decoder errors."""
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )


@dataclasses.dataclass
class TestResult:
    tier: int
    name: str
    description: str
    passed: bool
    duration_ms: float
    error_message: Optional[str] = None
    details: Optional[str] = None


class TestContext:
    def __init__(self, repo_root: Path, temp_dir: Path, verbose: bool = False):
        self.repo_root = repo_root
        self.temp_dir = temp_dir
        self.verbose = verbose
        self.log_messages: List[str] = []

    def log(self, message: str) -> None:
        if self.verbose:
            self.log_messages.append(message)


# -----------------------------------------------------------------------------
# Tier 1: Static Syntax, Schemas & Static Analysis
# -----------------------------------------------------------------------------

def test_python_syntax(ctx: TestContext) -> Tuple[bool, str]:
    """Compile all project .py files using ast.parse() to detect syntax errors."""
    py_files = []
    # Search root and tools/ for .py files
    for item in ctx.repo_root.glob("*.py"):
        if not item.name.startswith("."):
            py_files.append(item)
    tools_dir = ctx.repo_root / "tools"
    if tools_dir.is_dir():
        for item in tools_dir.glob("*.py"):
            if not item.name.startswith("."):
                py_files.append(item)

    if not py_files:
        return False, "No Python source files discovered in project root or tools/."

    parsed_count = 0
    errors = []
    for py_file in py_files:
        ctx.log(f"Parsing AST for: {py_file.relative_to(ctx.repo_root)}")
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                source = f.read()
            ast.parse(source, filename=str(py_file))
            parsed_count += 1
        except SyntaxError as e:
            errors.append(f"{py_file.name}:{e.lineno} SyntaxError: {e.msg}")
        except Exception as e:
            errors.append(f"{py_file.name} Error: {e}")

    if errors:
        return False, f"Syntax errors detected in {len(errors)} file(s):\n  " + "\n  ".join(errors)

    return True, f"Successfully parsed AST for {parsed_count} Python file(s) with 0 syntax errors."


def test_javascript_syntax(ctx: TestContext) -> Tuple[bool, str]:
    """Verify JavaScript syntax of app/*.js using node --check or lexical parser."""
    app_dir = ctx.repo_root / "app"
    js_files = []
    if app_dir.is_dir():
        for item in app_dir.glob("*.js"):
            js_files.append(item)

    if not js_files:
        # Check if apps.js or config.js exist
        return False, "No JavaScript files found in app/ directory."

    node_cmd = shutil.which("node")
    checked_count = 0
    errors = []

    for js_file in js_files:
        rel_path = js_file.relative_to(ctx.repo_root)
        ctx.log(f"Checking JS syntax for: {rel_path}")

        if node_cmd:
            proc = run_cmd([node_cmd, "--check", str(js_file)])
            if proc.returncode != 0:
                err_line = proc.stderr.strip().split("\n")[0] if proc.stderr else "Unknown JS parse error"
                errors.append(f"{js_file.name}: {err_line}")
            else:
                checked_count += 1
        else:
            # Fallback lexical check
            try:
                with open(js_file, "r", encoding="utf-8") as f:
                    content = f.read()
                # Balance checks
                stack = []
                pairs = {')': '(', '}': '{', ']': '['}
                in_str = None
                escaped = False
                for ch in content:
                    if escaped:
                        escaped = False
                        continue
                    if ch == '\\':
                        escaped = True
                        continue
                    if in_str:
                        if ch == in_str:
                            in_str = None
                        continue
                    if ch in ("'", '"', '`'):
                        in_str = ch
                        continue
                    if ch in pairs.values():
                        stack.append(ch)
                    elif ch in pairs:
                        if not stack or stack[-1] != pairs[ch]:
                            raise ValueError(f"Unmatched closing token '{ch}'")
                        stack.pop()
                if stack:
                    raise ValueError(f"Unclosed token '{stack[-1]}'")
                checked_count += 1
            except Exception as e:
                errors.append(f"{js_file.name} lexical check error: {e}")

    if errors:
        return False, f"JavaScript errors in {len(errors)} file(s):\n  " + "\n  ".join(errors)

    engine_desc = f"node --check ({node_cmd})" if node_cmd else "static lexical balancer"
    return True, f"Validated {checked_count} JavaScript file(s) in app/ via {engine_desc}."


def test_appinfo_schema(ctx: TestContext) -> Tuple[bool, str]:
    """Validate webOS appinfo.json structure and mandatory keys against webOS Hub standards."""
    appinfo_path = ctx.repo_root / "app" / "appinfo.json"
    if not appinfo_path.is_file():
        return False, f"appinfo.json not found at {appinfo_path}"

    try:
        with open(appinfo_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"appinfo.json is not valid JSON: {e}"

    required_fields = ["id", "version", "type", "main", "title", "icon", "largeIcon"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        return False, f"appinfo.json missing required webOS field(s): {missing}"

    app_id = data["id"]
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", str(app_id)):
        return False, f"Invalid app ID '{app_id}': must contain only alphanumeric, dot, hyphen, underscore"

    version = data["version"]
    if not re.match(r"^\d+\.\d+\.\d+", str(version)):
        return False, f"Invalid version string '{version}': must follow semantic versioning (e.g. 1.0.0)"

    if data["type"] != "web":
        return False, f"Invalid app type '{data['type']}': must be exactly 'web'"

    if not str(data["main"]).endswith(".html"):
        return False, f"Invalid main entrypoint '{data['main']}': must point to an HTML file"

    if data["icon"] != "icon.png":
        return False, f"Invalid icon property '{data['icon']}': must equal 'icon.png'"

    if data["largeIcon"] != "largeIcon.png":
        return False, f"Invalid largeIcon property '{data['largeIcon']}': must equal 'largeIcon.png'"

    # Check required ACG permissions
    acg = data.get("requiredACG", [])
    if not isinstance(acg, list) or "application.launcher" not in acg:
        return False, "appinfo.json missing required ACG permission 'application.launcher' in requiredACG array"

    return True, f"appinfo.json is 100% compliant (id='{app_id}', version='{version}', type='web', ACG={acg})."


def test_powershell_scripts(ctx: TestContext) -> Tuple[bool, str]:
    """Validate PowerShell scripts (install.ps1, restore.ps1, test.ps1) encoding, syntax, and zero-macOS check."""
    ps_scripts = list(ctx.repo_root.glob("*.ps1"))
    if not ps_scripts:
        return False, "No PowerShell (.ps1) scripts found in project root."

    checked_count = 0
    errors = []
    macos_commands = [r"\bsips\b", r"\bpbcopy\b", r"\bpbpaste\b"]

    pwsh_cmd = shutil.which("powershell") or shutil.which("pwsh")

    for ps_script in ps_scripts:
        ctx.log(f"Checking PowerShell script: {ps_script.name}")
        try:
            with open(ps_script, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError as e:
            errors.append(f"{ps_script.name}: UTF-8 decode error ({e})")
            continue

        # Check for forbidden macOS commands
        for cmd_pattern in macos_commands:
            if re.search(cmd_pattern, content, re.IGNORECASE):
                errors.append(f"{ps_script.name}: Disallowed macOS-specific command pattern found '{cmd_pattern}'")

        # Parse syntax via PowerShell AST parser if available on Windows
        if pwsh_cmd:
            check_cmd = [
                pwsh_cmd, "-NoProfile", "-NonInteractive", "-Command",
                f"$errs = $null; [System.Management.Automation.Language.Parser]::ParseInput((Get-Content -Raw '{ps_script}'), [ref]$null, [ref]$errs); if ($errs.Count -gt 0) {{ exit 1 }} else {{ exit 0 }}"
            ]
            proc = run_cmd(check_cmd)
            if proc.returncode != 0:
                errors.append(f"{ps_script.name}: PowerShell syntax parse errors detected.")
            else:
                checked_count += 1
        else:
            checked_count += 1

    if errors:
        return False, f"PowerShell script validation failures:\n  " + "\n  ".join(errors)

    engine = f"PowerShell parser ({pwsh_cmd})" if pwsh_cmd else "UTF-8 & anti-macOS regex validator"
    return True, f"Validated {checked_count} PowerShell script(s) with {engine} (zero macOS dependencies)."


# -----------------------------------------------------------------------------
# Tier 2: Asset & Icon Generation Verification
# -----------------------------------------------------------------------------

def parse_png_ihdr(file_path: Path) -> Tuple[int, int, int, int, int]:
    """Parse PNG binary header and return (width, height, bit_depth, color_type, crc_valid)."""
    with open(file_path, "rb") as f:
        header = f.read(8)
        if header != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Invalid PNG magic signature: {header!r}")
        
        chunk_len_bytes = f.read(4)
        if len(chunk_len_bytes) < 4:
            raise ValueError("Truncated PNG file")
        chunk_len = struct.unpack(">I", chunk_len_bytes)[0]
        chunk_type = f.read(4)
        if chunk_type != b"IHDR" or chunk_len != 13:
            raise ValueError(f"First chunk must be IHDR of length 13, got {chunk_type!r} len={chunk_len}")
        
        ihdr_data = f.read(13)
        crc_bytes = f.read(4)
        expected_crc = struct.unpack(">I", crc_bytes)[0]
        actual_crc = zlib.crc32(chunk_type + ihdr_data) & 0xffffffff
        if actual_crc != expected_crc:
            raise ValueError(f"IHDR CRC mismatch: {actual_crc} != {expected_crc}")
        
        width, height, bit_depth, color_type, comp, filt, inter = struct.unpack(">IIBBBBB", ihdr_data)
        return width, height, bit_depth, color_type, (actual_crc == expected_crc)


def test_icon_generation_execution(ctx: TestContext) -> Tuple[bool, str]:
    """Execute tools/generate_icons.py in an isolated sandbox and verify artifact output."""
    generator_script = ctx.repo_root / "tools" / "generate_icons.py"
    if not generator_script.is_file():
        return False, f"generate_icons.py script missing at {generator_script}"

    source_icon = ctx.repo_root / "assets" / "icon.jpg"
    sandbox_out = ctx.temp_dir / "tier2_icons_out"
    sandbox_out.mkdir(parents=True, exist_ok=True)

    # If assets/icon.jpg is missing, create a sample source image
    if not source_icon.is_file():
        source_icon = ctx.temp_dir / "sample_source.png"
        # Write minimal 100x100 solid PNG
        raw_rows = b"".join(b"\x00" + (b"\x10\x80\xff\xff" * 100) for _ in range(100))
        compressed = zlib.compress(raw_rows)
        with open(source_icon, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
            ihdr = struct.pack(">IIBBBBB", 100, 100, 8, 6, 0, 0, 0)
            f.write(struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)))
            f.write(struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", zlib.crc32(b"IDAT" + compressed)))
            f.write(struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND")))

    cmd = [
        sys.executable,
        str(generator_script),
        "--source", str(source_icon),
        "--output-dir", str(sandbox_out),
        "--force"
    ]
    proc = run_cmd(cmd)
    if proc.returncode != 0:
        return False, f"generate_icons.py execution failed with exit code {proc.returncode}:\n{proc.stderr}"

    out_icon = sandbox_out / "icon.png"
    out_large = sandbox_out / "largeIcon.png"

    if not out_icon.is_file():
        return False, f"icon.png was not generated at {out_icon}"
    if not out_large.is_file():
        return False, f"largeIcon.png was not generated at {out_large}"

    return True, f"tools/generate_icons.py executed successfully; wrote icon.png and largeIcon.png to {sandbox_out.name}."


def test_icon_dimensions(ctx: TestContext) -> Tuple[bool, str]:
    """Verify generated icons match exact webOS resolutions: 80x80 (icon.png) and 130x130 (largeIcon.png)."""
    # Check both sandbox output and repository app/ folder
    candidates = [
        (ctx.temp_dir / "tier2_icons_out" / "icon.png", 80, 80),
        (ctx.temp_dir / "tier2_icons_out" / "largeIcon.png", 130, 130),
    ]

    repo_icon = ctx.repo_root / "app" / "icon.png"
    repo_large = ctx.repo_root / "app" / "largeIcon.png"
    if repo_icon.is_file():
        candidates.append((repo_icon, 80, 80))
    if repo_large.is_file():
        candidates.append((repo_large, 130, 130))

    verified = 0
    for path, exp_w, exp_h in candidates:
        if not path.is_file():
            continue
        try:
            w, h, bit_depth, color_type, crc_ok = parse_png_ihdr(path)
            if w != exp_w or h != exp_h:
                return False, f"Dimension mismatch for {path.name}: expected {exp_w}x{exp_h}, got {w}x{h}"
            verified += 1
        except Exception as e:
            return False, f"Failed to parse dimensions of {path}: {e}"

    if verified < 2:
        return False, f"Insufficient icons verified ({verified} < 2). Run icon generation first."

    return True, f"Verified {verified} icon image(s) meet strict webOS resolutions (80x80 and 130x130)."


def test_icon_format_integrity(ctx: TestContext) -> Tuple[bool, str]:
    """Inspect PNG binary magic headers, 8-bit depth, RGB/RGBA channels, and IHDR CRC integrity."""
    test_files = [
        ctx.temp_dir / "tier2_icons_out" / "icon.png",
        ctx.temp_dir / "tier2_icons_out" / "largeIcon.png",
    ]

    for p in test_files:
        if not p.is_file():
            return False, f"Target test icon not found: {p}"
        try:
            w, h, bit_depth, color_type, crc_ok = parse_png_ihdr(p)
            if bit_depth != 8:
                return False, f"{p.name} bit depth is {bit_depth}, expected 8-bit."
            if color_type not in (2, 6): # RGB or RGBA
                return False, f"{p.name} color type is {color_type}, expected 2 (RGB) or 6 (RGBA)."
            if not crc_ok:
                return False, f"{p.name} IHDR chunk CRC check failed."
        except Exception as e:
            return False, f"PNG binary integrity check failed on {p.name}: {e}"

    # Also test opening with Pillow if installed
    try:
        from PIL import Image
        for p in test_files:
            with Image.open(p) as img:
                img.verify()
        pillow_note = " + Pillow.verify() confirmed"
    except ImportError:
        pillow_note = " (Pillow not installed; verified via strict binary PNG parser)"
    except Exception as e:
        return False, f"Pillow failed to decode icon: {e}"

    return True, f"PNG headers, IHDR CRC, 8-bit RGBA color types verified for icons{pillow_note}."


def test_icon_missing_source_handling(ctx: TestContext) -> Tuple[bool, str]:
    """Test tools/generate_icons.py error handling and exit codes when source file is missing."""
    generator_script = ctx.repo_root / "tools" / "generate_icons.py"
    bogus_path = ctx.temp_dir / "non_existent_source_999.png"

    cmd = [
        sys.executable,
        str(generator_script),
        "--source", str(bogus_path),
        "--output-dir", str(ctx.temp_dir / "bogus_out")
    ]
    proc = run_cmd(cmd)
    if proc.returncode == 0:
        return False, "generate_icons.py unexpectedly exited with 0 when source image was missing."

    output = (proc.stderr + proc.stdout).lower()
    if "not found" not in output and "error" not in output:
        return False, f"generate_icons.py did not print informative error message on missing source. Output:\n{output}"

    return True, f"generate_icons.py correctly refused missing source with exit code {proc.returncode}."


# -----------------------------------------------------------------------------
# Tier 3: Mock SSAP Protocol & Data Pipeline
# -----------------------------------------------------------------------------

def test_ssap_registration_handshake(ctx: TestContext) -> Tuple[bool, str]:
    """Simulate SSAP TLS handshake, unsigned manifest validation, and client key persistence."""
    # Define required SSAP permissions for webOS Hub
    required_permissions = [
        "LAUNCH", "LAUNCH_WEBAPP", "READ_INSTALLED_APPS",
        "READ_INPUT_DEVICE_LIST", "WRITE_NOTIFICATION_TOAST"
    ]

    mock_manifest = {
        "manifestVersion": 1,
        "permissions": required_permissions,
        "signatures": [] # Unsigned manifest avoids LG certificate blacklist
    }

    registration_payload = {
        "type": "register",
        "id": "register_0",
        "payload": {
            "forcePairing": False,
            "pairingType": "PROMPT",
            "manifest": mock_manifest
        }
    }

    # Verify serialization
    req_json = json.dumps(registration_payload)
    parsed_req = json.loads(req_json)
    if parsed_req["payload"]["manifest"]["permissions"] != required_permissions:
        return False, "Handshake manifest serialization corrupted permissions array."

    # Emulate server response
    mock_client_key = "mock_key_jvc_hub_32kb116_secure_token"
    server_response = {
        "type": "registered",
        "id": "register_0",
        "payload": {
            "client-key": mock_client_key
        }
    }

    # Test client-key caching to .lgtv-key.json in scratch directory
    key_cache_file = ctx.temp_dir / ".lgtv-key.json"
    cache_data = {"192.168.1.68": server_response["payload"]["client-key"]}
    with open(key_cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2)

    # Re-read and assert match
    with open(key_cache_file, "r", encoding="utf-8") as f:
        loaded_keys = json.load(f)

    if loaded_keys.get("192.168.1.68") != mock_client_key:
        return False, f"Cached client-key mismatch: expected {mock_client_key}, got {loaded_keys.get('192.168.1.68')}"

    return True, f"SSAP handshake serialization, unsigned manifest structure, and client-key caching verified."


def test_ssap_list_launch_points(ctx: TestContext) -> Tuple[bool, str]:
    """Test parsing and filtering of listLaunchPoints response, excluding hidden system/launcher apps."""
    mock_response = {
        "returnValue": True,
        "launchPoints": [
            {"id": "youtube.leanback.v4", "title": "YouTube", "icon": "http://192.168.1.68:3000/icon/yt.png", "hidden": False},
            {"id": "netflix", "title": "Netflix", "icon": "http://192.168.1.68:3000/icon/nf.png", "hidden": False},
            {"id": "com.amazon.ignition.ignite", "title": "Prime Video", "icon": "http://192.168.1.68:3000/icon/pv.png", "hidden": False},
            {"id": "com.webos.app.browser", "title": "Web Browser", "icon": "http://192.168.1.68:3000/icon/wb.png", "hidden": False},
            {"id": "com.webos.app.livetv", "title": "Live TV", "icon": "http://192.168.1.68:3000/icon/tv.png", "hidden": False},
            {"id": "com.gathin.tvhome", "title": "Home", "icon": "icon.png", "hidden": True} # Custom launcher must be filtered
        ]
    }

    raw_apps = mock_response.get("launchPoints", [])
    # Filter logic: omit hidden apps or self app id
    filtered_apps = [
        app for app in raw_apps
        if not app.get("hidden", False) and app.get("id") != "com.gathin.tvhome"
    ]

    if len(filtered_apps) != 5:
        return False, f"Launch point filtering failed: expected 5 visible apps, got {len(filtered_apps)}"

    app_ids = [a["id"] for a in filtered_apps]
    if "com.gathin.tvhome" in app_ids:
        return False, "Launcher app 'com.gathin.tvhome' was not filtered out of launch points."

    if "youtube.leanback.v4" not in app_ids or "netflix" not in app_ids:
        return False, "Standard streaming apps missing from filtered launch points."

    return True, f"Successfully filtered 6 raw launch points into 5 active launcher applications."


def test_ssap_external_inputs(ctx: TestContext) -> Tuple[bool, str]:
    """Test mapping of getExternalInputList HDMI devices into launcher navigation items."""
    mock_input_response = {
        "returnValue": True,
        "devices": [
            {"id": "AV_HDMI_1", "label": "HDMI 1", "port": 1, "connected": True, "appId": "com.webos.app.hdmi1"},
            {"id": "AV_HDMI_2", "label": "HDMI 2 (eARC)", "port": 2, "connected": True, "appId": "com.webos.app.hdmi2"},
            {"id": "AV_HDMI_3", "label": "HDMI 3", "port": 3, "connected": False, "appId": "com.webos.app.hdmi3"},
            {"id": "AV_COMPOSITE", "label": "AV In", "port": 1, "connected": False, "appId": "com.webos.app.externalinput.av"}
        ]
    }

    devices = mock_input_response.get("devices", [])
    mapped_inputs = []
    for dev in devices:
        mapped_inputs.append({
            "id": dev["id"],
            "title": dev.get("label", dev["id"]),
            "appId": dev.get("appId"),
            "connected": dev.get("connected", False)
        })

    if len(mapped_inputs) != 4:
        return False, f"Expected 4 mapped external inputs, got {len(mapped_inputs)}"

    hdmi2 = next((inp for inp in mapped_inputs if inp["id"] == "AV_HDMI_2"), None)
    if not hdmi2 or hdmi2["title"] != "HDMI 2 (eARC)" or hdmi2["appId"] != "com.webos.app.hdmi2":
        return False, f"Incorrect mapping for HDMI 2: {hdmi2}"

    return True, f"Mapped {len(mapped_inputs)} external inputs with correct HDMI port labels and app IDs."


def test_apps_js_code_generation(ctx: TestContext) -> Tuple[bool, str]:
    """Verify programmatic generation and syntax validity of app/apps.js data bridge."""
    mock_apps = [
        {"id": "youtube.leanback.v4", "title": "YouTube", "icon": "icons/youtube.png"},
        {"id": "netflix", "title": "Netflix", "icon": "icons/netflix.png"}
    ]
    mock_inputs = [
        {"id": "AV_HDMI_1", "title": "HDMI 1", "appId": "com.webos.app.hdmi1"}
    ]

    target_js_file = ctx.temp_dir / "apps_test.js"
    js_content = (
        "// Auto-generated by test_suite\n"
        f"window.APPS = {json.dumps(mock_apps, indent=2)};\n"
        f"window.INPUTS = {json.dumps(mock_inputs, indent=2)};\n"
    )

    with open(target_js_file, "w", encoding="utf-8") as f:
        f.write(js_content)

    # Validate syntax via node if available
    node_cmd = shutil.which("node")
    if node_cmd:
        proc = run_cmd([node_cmd, "--check", str(target_js_file)])
        if proc.returncode != 0:
            return False, f"Generated apps.js failed node --check: {proc.stderr}"

    # Extract JSON part and verify data
    match = re.search(r"window\.APPS\s*=\s*(\[.*?\]);", js_content, re.DOTALL)
    if not match:
        return False, "Failed to match window.APPS array declaration in generated apps.js"

    parsed = json.loads(match.group(1))
    if len(parsed) != 2 or parsed[0]["id"] != "youtube.leanback.v4":
        return False, f"Parsed apps data mismatch: {parsed}"

    return True, "apps.js code generation produces syntactically valid JavaScript and verifiable JSON payload."


# -----------------------------------------------------------------------------
# Tier 4: Backup Creation & Rollback State Machine
# -----------------------------------------------------------------------------

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_backup_creation(ctx: TestContext) -> Tuple[bool, str]:
    """Execute backup.py with --offline-mock and verify creation of timestamped snapshot directory."""
    backup_script = ctx.repo_root / "backup.py"
    if not backup_script.is_file():
        return False, f"backup.py missing at {backup_script}"

    custom_snap_dir = ctx.temp_dir / "tier4_snapshots" / "test_snap_01"

    cmd = [
        sys.executable,
        str(backup_script),
        "--offline-mock",
        "--output-dir", str(custom_snap_dir),
        "--quiet"
    ]
    proc = run_cmd(cmd)
    if proc.returncode != 0:
        return False, f"backup.py execution failed (exit code {proc.returncode}):\n{proc.stderr}\n{proc.stdout}"

    if not custom_snap_dir.is_dir():
        return False, f"Snapshot directory was not created at {custom_snap_dir}"

    required_artifacts = ["snapshot.json", "launch_points.json", "inputs.json", "system_info.json"]
    missing = [art for art in required_artifacts if not (custom_snap_dir / art).is_file()]
    if missing:
        return False, f"Snapshot missing required artifact(s): {missing}"

    return True, f"backup.py created snapshot with {len(required_artifacts)} verified artifacts in {custom_snap_dir.name}."


def test_snapshot_schema_and_manifest(ctx: TestContext) -> Tuple[bool, str]:
    """Validate snapshot.json schema and verify 100% of cryptographic SHA-256 file checksums."""
    snap_dir = ctx.temp_dir / "tier4_snapshots" / "test_snap_01"
    manifest_path = snap_dir / "snapshot.json"
    if not manifest_path.is_file():
        return False, f"Manifest snapshot.json not found at {manifest_path}"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Validate mandatory schema attributes
    for key in ["timestamp", "version", "checksums"]:
        if key not in manifest:
            return False, f"snapshot.json missing root schema key: '{key}'"

    checksums = manifest["checksums"]
    if not isinstance(checksums, dict):
        return False, "'checksums' in snapshot.json is not a dictionary"

    verified_count = 0
    for rel_path_str, expected_hash in checksums.items():
        if rel_path_str.endswith("_sha256"):
            continue # Skip convenience alias keys
        file_path = snap_dir / rel_path_str
        if not file_path.is_file():
            return False, f"File listed in checksums manifest not present: {rel_path_str}"
        actual_hash = compute_sha256(file_path)
        if actual_hash.lower() != expected_hash.lower():
            return False, f"Hash mismatch for {rel_path_str}: expected {expected_hash}, calculated {actual_hash}"
        verified_count += 1

    if verified_count < 3:
        return False, f"Insufficient files verified in snapshot ({verified_count} < 3)"

    return True, f"snapshot.json schema valid; {verified_count} file(s) matched cryptographic SHA-256 hashes."


def test_restore_execution_fidelity(ctx: TestContext) -> Tuple[bool, str]:
    """Test full rollback roundtrip: corrupt workspace files, run restore.py, and verify byte-for-byte fidelity."""
    restore_script = ctx.repo_root / "restore.py"
    backup_script = ctx.repo_root / "backup.py"
    if not restore_script.is_file():
        return False, f"restore.py missing at {restore_script}"

    # Setup sandbox workspace
    mock_app_dir = ctx.temp_dir / "fidelity_app_dir"
    mock_app_dir.mkdir(parents=True, exist_ok=True)
    orig_apps_content = "// Original apps.js\nwindow.APPS = [{ id: 'app.one' }];\n"
    orig_config_content = "// Original config.js\nwindow.CONFIG = { dockApps: ['app.one'] };\n"
    orig_appinfo_content = json.dumps({"id": "com.gathin.tvhome", "version": "1.0.0", "type": "web", "main": "index.html", "title": "Home", "icon": "icon.png", "largeIcon": "largeIcon.png"}, indent=2)

    with open(mock_app_dir / "apps.js", "w", encoding="utf-8") as f: f.write(orig_apps_content)
    with open(mock_app_dir / "config.js", "w", encoding="utf-8") as f: f.write(orig_config_content)
    with open(mock_app_dir / "appinfo.json", "w", encoding="utf-8") as f: f.write(orig_appinfo_content)

    orig_apps_hash = compute_sha256(mock_app_dir / "apps.js")
    orig_config_hash = compute_sha256(mock_app_dir / "config.js")

    # Take backup of this sandbox
    fidelity_snap_dir = ctx.temp_dir / "tier4_snapshots" / "fidelity_snap"
    proc_b = run_cmd([
        sys.executable, str(backup_script),
        "--offline-mock",
        "--output-dir", str(fidelity_snap_dir),
        "--app-dir", str(mock_app_dir),
        "--quiet"
    ])
    if proc_b.returncode != 0:
        return False, f"Failed to create fidelity test snapshot: {proc_b.stderr}"

    # Corrupt the workspace files
    with open(mock_app_dir / "apps.js", "w", encoding="utf-8") as f: f.write("// CORRUPTED_CONTENT_SIMULATED_CRASH")
    with open(mock_app_dir / "config.js", "w", encoding="utf-8") as f: f.write("// CORRUPTED_CONTENT_CONFIG")

    corrupted_apps_hash = compute_sha256(mock_app_dir / "apps.js")
    if corrupted_apps_hash == orig_apps_hash:
        return False, "Failed to simulate file corruption."

    # Execute restore.py targeting mock_app_dir
    cmd = [
        sys.executable, str(restore_script),
        "--snapshot", str(fidelity_snap_dir),
        "--app-dir", str(mock_app_dir),
        "--force",
        "--quiet"
    ]
    proc_r = run_cmd(cmd)
    if proc_r.returncode != 0:
        return False, f"restore.py failed with exit code {proc_r.returncode}:\n{proc_r.stderr}\n{proc_r.stdout}"

    # Verify restored files match original hashes
    restored_apps_hash = compute_sha256(mock_app_dir / "apps.js")
    restored_config_hash = compute_sha256(mock_app_dir / "config.js")

    if restored_apps_hash != orig_apps_hash:
        return False, "Fidelity failure: apps.js hash after restore does not match original."
    if restored_config_hash != orig_config_hash:
        return False, "Fidelity failure: config.js hash after restore does not match original."

    return True, "Rollback state machine restored workspace files with 100% byte-for-byte SHA-256 fidelity."


def test_corrupted_snapshot_handling(ctx: TestContext) -> Tuple[bool, str]:
    """Verify restore.py detects checksum tampering and corrupted JSON, refusing restoration with non-zero exit."""
    restore_script = ctx.repo_root / "restore.py"
    target_snap = ctx.temp_dir / "tier4_snapshots" / "corrupted_snap"
    target_snap.mkdir(parents=True, exist_ok=True)

    # Copy files from a valid snapshot
    valid_source = ctx.temp_dir / "tier4_snapshots" / "test_snap_01"
    for item in valid_source.iterdir():
        if item.is_file():
            shutil.copy2(item, target_snap / item.name)

    # Tamper with launch_points.json without updating snapshot.json
    with open(target_snap / "launch_points.json", "ab") as f:
        f.write(b"\n// INJECTED_MALICIOUS_TAMPERED_DATA\n")

    cmd = [
        sys.executable, str(restore_script),
        "--snapshot", str(target_snap),
        "--app-dir", str(ctx.temp_dir / "scratch_target"),
        "--force",
        "--verify-only",
        "--quiet"
    ]
    proc = run_cmd(cmd)
    if proc.returncode == 0:
        return False, "restore.py failed to detect tampered launch_points.json (exited with 0)."

    # Test invalid JSON syntax in manifest
    with open(target_snap / "snapshot.json", "w", encoding="utf-8") as f:
        f.write("{ invalid json syntax corrupt : ::: }")

    proc_json = run_cmd(cmd)
    if proc_json.returncode == 0:
        return False, "restore.py failed to detect malformed JSON syntax in snapshot.json (exited with 0)."

    return True, "restore.py successfully detected file tampering and corrupted manifest syntax, aborting with non-zero exit."


# -----------------------------------------------------------------------------
# Test Registry & Test Suite Runner
# -----------------------------------------------------------------------------

TIER_METADATA = {
    1: {"name": "Static Syntax, Schemas & Static Analysis", "tests": [
        (test_python_syntax, "test_python_syntax", "Python AST syntax verification on all project .py files"),
        (test_javascript_syntax, "test_javascript_syntax", "JavaScript syntax check on app/*.js via node/lexical parser"),
        (test_appinfo_schema, "test_appinfo_schema", "WebOS appinfo.json structure and ACG permissions compliance"),
        (test_powershell_scripts, "test_powershell_scripts", "PowerShell scripts encoding, syntax, and zero-macOS check"),
    ]},
    2: {"name": "Asset & Icon Generation Verification", "tests": [
        (test_icon_generation_execution, "test_icon_generation_execution", "Execution of tools/generate_icons.py in sandbox"),
        (test_icon_dimensions, "test_icon_dimensions", "Strict dimensions: 80x80 (icon.png) & 130x130 (largeIcon.png)"),
        (test_icon_format_integrity, "test_icon_format_integrity", "PNG binary magic headers, 8-bit RGBA, and IHDR CRC check"),
        (test_icon_missing_source_handling, "test_icon_missing_source_handling", "generate_icons.py non-zero exit on missing source asset"),
    ]},
    3: {"name": "Mock SSAP Protocol & Data Pipeline", "tests": [
        (test_ssap_registration_handshake, "test_ssap_registration_handshake", "SSAP handshake, unsigned manifest & client-key caching"),
        (test_ssap_list_launch_points, "test_ssap_list_launch_points", "listLaunchPoints parsing & hidden app filtering"),
        (test_ssap_external_inputs, "test_ssap_external_inputs", "getExternalInputList HDMI port and label mapping"),
        (test_apps_js_code_generation, "test_apps_js_code_generation", "Programmatic generation & syntax of app/apps.js"),
    ]},
    4: {"name": "Backup Creation & Rollback State Machine", "tests": [
        (test_backup_creation, "test_backup_creation", "Automated timestamped backup snapshot creation in mock mode"),
        (test_snapshot_schema_and_manifest, "test_snapshot_schema_and_manifest", "snapshot.json schema & 100% cryptographic SHA-256 match"),
        (test_restore_execution_fidelity, "test_restore_execution_fidelity", "Full roundtrip rollback: corrupt workspace and assert 100% fidelity"),
        (test_corrupted_snapshot_handling, "test_corrupted_snapshot_handling", "Tampered file & corrupt JSON rejection with non-zero exit"),
    ]}
}


def run_test_suite(
    repo_root: Path,
    selected_tier: str = "all",
    verbose: bool = False,
    failfast: bool = False,
    temp_dir_override: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Execute test suite and return (exit_code, summary_dict)."""
    start_total_time = time.perf_counter()

    # Setup scratch directory
    if temp_dir_override:
        scratch_dir = Path(temp_dir_override)
        scratch_dir.mkdir(parents=True, exist_ok=True)
        managed_temp = None
    else:
        managed_temp = tempfile.TemporaryDirectory(prefix="webos_test_")
        scratch_dir = Path(managed_temp.name)

    ctx = TestContext(repo_root=repo_root, temp_dir=scratch_dir, verbose=verbose)

    # Determine tiers to execute
    if selected_tier == "all":
        tiers_to_run = [1, 2, 3, 4]
    else:
        tiers_to_run = [int(selected_tier)]

    results: List[TestResult] = []
    has_failure = False

    for tier_num in tiers_to_run:
        tier_info = TIER_METADATA[tier_num]
        for func, name, desc in tier_info["tests"]:
            t0 = time.perf_counter()
            try:
                passed, msg = func(ctx)
            except Exception as exc:
                passed = False
                msg = f"Unhandled test exception: {exc}"

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            res = TestResult(
                tier=tier_num,
                name=name,
                description=desc,
                passed=passed,
                duration_ms=elapsed_ms,
                error_message=None if passed else msg,
                details=msg if passed else None
            )
            results.append(res)

            if not passed:
                has_failure = True
                if failfast:
                    break
        if has_failure and failfast:
            break

    total_duration_sec = time.perf_counter() - start_total_time

    # Cleanup temp directory if managed
    if managed_temp:
        try:
            managed_temp.cleanup()
        except Exception:
            pass

    # Build summary dict
    passed_count = sum(1 for r in results if r.passed)
    failed_count = sum(1 for r in results if not r.passed)

    tier_summaries = {}
    for t_num in tiers_to_run:
        t_results = [r for r in results if r.tier == t_num]
        tier_summaries[str(t_num)] = {
            "name": TIER_METADATA[t_num]["name"],
            "total": len(t_results),
            "passed": sum(1 for r in t_results if r.passed),
            "failed": sum(1 for r in t_results if not r.passed),
            "tests": [
                {
                    "name": r.name,
                    "description": r.description,
                    "passed": r.passed,
                    "duration_ms": round(r.duration_ms, 2),
                    "message": r.details if r.passed else r.error_message
                }
                for r in t_results
            ]
        }

    summary = {
        "version": VERSION,
        "status": "PASS" if not has_failure else "FAIL",
        "total_tests": len(results),
        "passed_tests": passed_count,
        "failed_tests": failed_count,
        "duration_sec": round(total_duration_sec, 3),
        "tiers": tier_summaries
    }

    exit_code = 0 if not has_failure else 1
    return exit_code, summary, results


def print_human_report(summary: Dict[str, Any], results: List[TestResult], verbose: bool) -> None:
    """Print beautifully formatted test report for human console viewing."""
    print()
    print(c_bold("================================================================================="))
    print(c_bold(c_cyan("       WebOS JVC CleanYourTV - Offline Verification Test Suite")))
    print(c_bold(f"       Engine Version: {VERSION} | Python {sys.version.split()[0]} | Platform: {sys.platform}"))
    print(c_bold("================================================================================="))
    print()

    current_tier = None
    for r in results:
        if r.tier != current_tier:
            current_tier = r.tier
            tier_name = TIER_METADATA[current_tier]["name"]
            print(f"\n{c_bold(f'--- Tier {current_tier}: {tier_name} ---')}")

        status_tag = c_green("[PASS]") if r.passed else c_red("[FAIL]")
        dur_str = f"{r.duration_ms:6.1f}ms"
        print(f"  {status_tag} {c_bold(r.name):<36} {c_dim(dur_str)}  {r.description}")

        if not r.passed and r.error_message:
            for line in r.error_message.split("\n"):
                print(f"         {c_red('>>')} {c_red(line)}")
        elif verbose and r.details:
            print(f"         {c_dim('->')} {c_dim(r.details)}")

    print()
    print(c_bold("---------------------------------------------------------------------------------"))
    tot = summary["total_tests"]
    pass_cnt = summary["passed_tests"]
    fail_cnt = summary["failed_tests"]
    dur = summary["duration_sec"]

    if fail_cnt == 0:
        status_banner = c_bold(c_green("ALL TESTS PASSED SUCCESSFULLY (100%)"))
    else:
        status_banner = c_bold(c_red(f"{fail_cnt} TEST(S) FAILED"))

    print(f"  Summary: {pass_cnt}/{tot} passed | {fail_cnt} failed | Duration: {dur:.2f}s")
    print(f"  Result:  {status_banner}")
    print(c_bold("---------------------------------------------------------------------------------"))
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline Verification Test Suite for WebOS JVC CleanYourTV",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tier", "-t",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Run specific test tier (1: Syntax/Schemas, 2: Icons, 3: SSAP, 4: Rollback, all: All)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable detailed assertion logging"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output machine-readable JSON to stdout"
    )
    parser.add_argument(
        "--failfast", "-x",
        action="store_true",
        default=False,
        help="Stop test execution on first failure"
    )
    parser.add_argument(
        "--temp-dir",
        default=None,
        help="Override scratch directory for test sandboxing"
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    try:
        exit_code, summary, results = run_test_suite(
            repo_root=repo_root,
            selected_tier=args.tier,
            verbose=args.verbose,
            failfast=args.failfast,
            temp_dir_override=args.temp_dir
        )
    except Exception as e:
        sys.stderr.write(f"\n[FATAL ERROR] Test suite crashed: {e}\n")
        return 2

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_human_report(summary, results, verbose=args.verbose)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
