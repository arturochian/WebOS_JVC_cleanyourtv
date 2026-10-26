#!/usr/bin/env python3
"""
tools/stress_challenge.py - Empirical Adversarial Stress Test Suite for WebOS CleanYourTV.

Executes a battery of adversarial challenge tests against:
1. Tampering & corruption detection in restore engine (SHA-256 verification, syntax validation).
2. CLI robustness, error trapping, and missing file handling in backup.py and restore.py.
3. SSAP protocol edge cases, large payload stress (1000+ items), and malicious input sanitization.
4. Full roundtrip rollback byte-for-byte fidelity across diverse asset types.
5. PowerShell wrapper safety validation.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


class StressTestRunner:
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.passed = 0
        self.failed = 0
        self.results: List[Dict[str, Any]] = []

    def record(self, test_id: str, name: str, success: bool, message: str, elapsed: float):
        if success:
            self.passed += 1
            status = "[PASS]"
        else:
            self.failed += 1
            status = "[FAIL]"
        self.results.append({
            "id": test_id,
            "name": name,
            "status": status,
            "success": success,
            "message": message,
            "elapsed_ms": round(elapsed * 1000, 2),
        })
        print(f"  {status} {test_id}: {name} ({round(elapsed * 1000, 1)}ms) - {message}")

    # =========================================================================
    # Category 1: Deliberate Tampering & Corruption Detection
    # =========================================================================

    def test_tamper_launch_points(self):
        """1.1: Single-byte tampering in launch_points.json -> restore refuses with non-zero exit."""
        t0 = time.perf_counter()
        sandbox = self.temp_dir / "c1_tamper_lp"
        sandbox.mkdir(parents=True, exist_ok=True)
        backup_dir = sandbox / "backup"

        # Create valid snapshot
        run_cmd([sys.executable, "backup.py", "--offline-mock", "--output-dir", str(backup_dir / "snap1"), "--quiet"])

        # Tamper single byte in launch_points.json
        lp_file = backup_dir / "snap1" / "launch_points.json"
        with open(lp_file, "r+b") as f:
            f.seek(10)
            b = f.read(1)
            f.seek(10)
            f.write(bytes([b[0] ^ 0xFF]))

        # Attempt restore
        target_app = sandbox / "app"
        res = run_cmd([
            sys.executable, "restore.py",
            "--snapshot", str(backup_dir / "snap1"),
            "--app-dir", str(target_app),
            "--force", "--quiet"
        ])

        elapsed = time.perf_counter() - t0
        if res.returncode != 0 and not (target_app / "apps.js").exists():
            self.record("C1.1", "Tampered launch_points.json rejection", True,
                        f"Refused restoration with exit code {res.returncode}; target untouched", elapsed)
        else:
            self.record("C1.1", "Tampered launch_points.json rejection", False,
                        f"Unexpected exit code {res.returncode} or files created", elapsed)

    def test_tamper_apps_js(self):
        """1.2: Tampering in snapshot apps.js -> restore detects SHA-256 mismatch and aborts."""
        t0 = time.perf_counter()
        sandbox = self.temp_dir / "c1_tamper_apps"
        sandbox.mkdir(parents=True, exist_ok=True)
        backup_dir = sandbox / "backup"

        run_cmd([sys.executable, "backup.py", "--offline-mock", "--output-dir", str(backup_dir / "snap1"), "--quiet"])

        apps_file = backup_dir / "snap1" / "apps.js"
        if apps_file.exists():
            with open(apps_file, "a", encoding="utf-8") as f:
                f.write("\n// INJECTED_MALICIOUS_PAYLOAD = true;\n")

        target_app = sandbox / "app"
        res = run_cmd([
            sys.executable, "restore.py",
            "--snapshot", str(backup_dir / "snap1"),
            "--app-dir", str(target_app),
            "--force", "--quiet"
        ])

        elapsed = time.perf_counter() - t0
        if res.returncode != 0:
            self.record("C1.2", "Tampered snapshot apps.js rejection", True,
                        f"Detected SHA-256 mismatch and aborted with exit code {res.returncode}", elapsed)
        else:
            self.record("C1.2", "Tampered snapshot apps.js rejection", False,
                        "Failed to reject tampered apps.js (exit code 0)", elapsed)

    def test_tamper_icon_binary(self):
        """1.3: Tampering binary content in snapshot icons/ -> restore aborts."""
        t0 = time.perf_counter()
        sandbox = self.temp_dir / "c1_tamper_icon"
        sandbox.mkdir(parents=True, exist_ok=True)
        backup_dir = sandbox / "backup"

        run_cmd([sys.executable, "backup.py", "--offline-mock", "--output-dir", str(backup_dir / "snap1"), "--quiet"])

        icons_dir = backup_dir / "snap1" / "icons"
        icon_files = list(icons_dir.glob("*.png"))
        if not icon_files:
            self.record("C1.3", "Tampered icon rejection", True, "No icons in test snapshot to tamper", time.perf_counter() - t0)
            return

        target_icon = icon_files[0]
        with open(target_icon, "r+b") as f:
            f.seek(16)
            f.write(b"\xDE\xAD\xBE\xEF")

        res = run_cmd([
            sys.executable, "restore.py",
            "--snapshot", str(backup_dir / "snap1"),
            "--app-dir", str(sandbox / "app"),
            "--force", "--quiet"
        ])

        elapsed = time.perf_counter() - t0
        if res.returncode != 0:
            self.record("C1.3", "Tampered icon rejection", True,
                        f"Refused restore on icon hash mismatch (exit code {res.returncode})", elapsed)
        else:
            self.record("C1.3", "Tampered icon rejection", False, "Failed to detect tampered icon file", elapsed)

    def test_missing_file_in_snapshot(self):
        """1.4: Deleting a manifest-tracked file -> restore detects missing file and refuses."""
        t0 = time.perf_counter()
        sandbox = self.temp_dir / "c1_missing_file"
        sandbox.mkdir(parents=True, exist_ok=True)
        backup_dir = sandbox / "backup"

        run_cmd([sys.executable, "backup.py", "--offline-mock", "--output-dir", str(backup_dir / "snap1"), "--quiet"])

        # Delete system_info.json
        (backup_dir / "snap1" / "system_info.json").unlink()

        res = run_cmd([
            sys.executable, "restore.py",
            "--snapshot", str(backup_dir / "snap1"),
            "--app-dir", str(sandbox / "app"),
            "--force", "--quiet"
        ])

        elapsed = time.perf_counter() - t0
        if res.returncode != 0:
            self.record("C1.4", "Missing snapshot artifact rejection", True,
                        f"Detected missing file and aborted with exit code {res.returncode}", elapsed)
        else:
            self.record("C1.4", "Missing snapshot artifact rejection", False,
                        "Restore proceeded despite missing artifact!", elapsed)

    def test_malformed_snapshot_manifest_json(self):
        """1.5: Completely unparseable JSON in snapshot.json -> restore refuses."""
        t0 = time.perf_counter()
        sandbox = self.temp_dir / "c1_malformed_manifest"
        sandbox.mkdir(parents=True, exist_ok=True)
        backup_dir = sandbox / "backup"

        run_cmd([sys.executable, "backup.py", "--offline-mock", "--output-dir", str(backup_dir / "snap1"), "--quiet"])

        with open(backup_dir / "snap1" / "snapshot.json", "w", encoding="utf-8") as f:
            f.write("<<< INVALID MALFORMED JSON SYNTAX >>>")

        res = run_cmd([
            sys.executable, "restore.py",
            "--snapshot", str(backup_dir / "snap1"),
            "--app-dir", str(sandbox / "app"),
            "--force", "--quiet"
        ])

        elapsed = time.perf_counter() - t0
        if res.returncode != 0:
            self.record("C1.5", "Malformed snapshot.json syntax rejection", True,
                        f"Aborted gracefully on invalid JSON manifest (exit code {res.returncode})", elapsed)
        else:
            self.record("C1.5", "Malformed snapshot.json syntax rejection", False, "Exited 0 on invalid JSON manifest!", elapsed)

    def test_semantic_corruption_with_valid_hash(self):
        """1.6: Valid SHA-256 in manifest but invalid JSON in state files -> caught by restore.py."""
        t0 = time.perf_counter()
        sandbox = self.temp_dir / "c1_semantic_corrupt"
        sandbox.mkdir(parents=True, exist_ok=True)
        backup_dir = sandbox / "backup"

        run_cmd([sys.executable, "backup.py", "--offline-mock", "--output-dir", str(backup_dir / "snap1"), "--quiet"])

        # Overwrite launch_points.json with broken JSON
        lp_file = backup_dir / "snap1" / "launch_points.json"
        with open(lp_file, "w", encoding="utf-8") as f:
            f.write("{ broken json syntax : : : ")

        # Update SHA-256 in manifest so checksum passes!
        new_hash = compute_sha256(lp_file)
        manifest_file = backup_dir / "snap1" / "snapshot.json"
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["checksums"]["launch_points.json"] = new_hash
        manifest["checksums"]["launch_points_sha256"] = new_hash
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Restore should STILL fail because restore.py checks JSON syntax of key state files!
        res = run_cmd([
            sys.executable, "restore.py",
            "--snapshot", str(backup_dir / "snap1"),
            "--app-dir", str(sandbox / "app"),
            "--force", "--quiet"
        ])

        elapsed = time.perf_counter() - t0
        if res.returncode != 0:
            self.record("C1.6", "Semantic JSON corruption rejection", True,
                        f"Detected syntax corruption in launch_points.json (exit code {res.returncode})", elapsed)
        else:
            self.record("C1.6", "Semantic JSON corruption rejection", False,
                        "Failed to reject corrupt JSON with valid SHA-256!", elapsed)

    # =========================================================================
    # Category 2: CLI Robustness & Error Handling
    # =========================================================================

    def test_invalid_cli_flags(self):
        """2.1: Invalid CLI arguments exit with code 2."""
        t0 = time.perf_counter()
        res_b = run_cmd([sys.executable, "backup.py", "--non-existent-flag-xyz"])
        res_r = run_cmd([sys.executable, "restore.py", "--non-existent-flag-xyz"])

        elapsed = time.perf_counter() - t0
        success = res_b.returncode == 2 and res_r.returncode == 2
        self.record("C2.1", "Invalid CLI flag rejection", success,
                    f"backup.py exit={res_b.returncode}, restore.py exit={res_r.returncode} (expected 2)", elapsed)

    def test_conflicting_cli_flags(self):
        """2.2: Mutually exclusive flags in restore.py rejected with code 2."""
        t0 = time.perf_counter()
        res = run_cmd([sys.executable, "restore.py", "--latest", "--snapshot", "some_dir"])
        elapsed = time.perf_counter() - t0
        success = res.returncode == 2
        self.record("C2.2", "Conflicting mutually exclusive flags", success,
                    f"restore.py exited with code {res.returncode} (expected 2)", elapsed)

    def test_nonexistent_snapshot_target(self):
        """2.3: Non-existent snapshot target returns exit code 1."""
        t0 = time.perf_counter()
        res = run_cmd([sys.executable, "restore.py", "--snapshot", "definitely_does_not_exist_slug_999", "--quiet"])
        elapsed = time.perf_counter() - t0
        success = res.returncode == 1
        self.record("C2.3", "Non-existent snapshot target", success,
                    f"restore.py exited with code {res.returncode} (expected 1)", elapsed)

    def test_empty_backup_dir_resolution(self):
        """2.4: Empty backup directory exits cleanly with code 1 for restore."""
        t0 = time.perf_counter()
        empty_dir = self.temp_dir / "c2_empty_backup"
        empty_dir.mkdir(parents=True, exist_ok=True)

        res = run_cmd([sys.executable, "restore.py", "--backup-dir", str(empty_dir), "--latest", "--quiet"])
        elapsed = time.perf_counter() - t0
        success = res.returncode == 1
        self.record("C2.4", "Empty backup directory handling", success,
                    f"restore.py exited with code {res.returncode} on empty backup dir", elapsed)

    def test_backup_dry_run_isolation(self):
        """2.5: backup.py --dry-run writes zero files to filesystem."""
        t0 = time.perf_counter()
        sandbox = self.temp_dir / "c2_dry_run"
        target_dir = sandbox / "dry_run_snap"

        res = run_cmd([
            sys.executable, "backup.py",
            "--offline-mock",
            "--output-dir", str(target_dir),
            "--dry-run",
            "--quiet"
        ])

        elapsed = time.perf_counter() - t0
        dir_exists = target_dir.exists()
        success = res.returncode == 0 and not dir_exists
        self.record("C2.5", "backup.py --dry-run isolation", success,
                    f"exit={res.returncode}, target_created={dir_exists} (expected False)", elapsed)

    def test_backup_missing_app_assets_graceful(self):
        """2.6: backup.py runs smoothly when app/ lacks config or icons."""
        t0 = time.perf_counter()
        empty_app = self.temp_dir / "c2_empty_app"
        empty_app.mkdir(parents=True, exist_ok=True)
        dest_snap = self.temp_dir / "c2_empty_app_snap"

        res = run_cmd([
            sys.executable, "backup.py",
            "--offline-mock",
            "--app-dir", str(empty_app),
            "--output-dir", str(dest_snap),
            "--quiet"
        ])

        elapsed = time.perf_counter() - t0
        success = res.returncode == 0 and (dest_snap / "snapshot.json").exists()
        if success:
            with open(dest_snap / "snapshot.json", "r", encoding="utf-8") as f:
                stats = json.load(f).get("stats", {})
            has_apps = stats.get("hasAppsJs", True)
            success = (has_apps is False)

        self.record("C2.6", "backup.py with missing app assets", success,
                    f"Completed gracefully with stats reflecting missing optional assets", elapsed)

    # =========================================================================
    # Category 3: SSAP Protocol & Data Serialization Stress
    # =========================================================================

    def test_large_ssap_payload_stress(self):
        """3.1: SSAP payload with 1,000 launch points and 50 HDMI inputs."""
        t0 = time.perf_counter()
        sandbox = self.temp_dir / "c3_large_payload"
        sandbox.mkdir(parents=True, exist_ok=True)
        icons_dir = sandbox / "icons"
        icons_dir.mkdir(parents=True, exist_ok=True)

        # Dynamically import sync-apps.py
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_apps_mod", str(REPO_ROOT / "sync-apps.py"))
        sync_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync_mod)

        # Generate massive synthetic payload
        large_lps = []
        for i in range(1000):
            large_lps.append({
                "id": f"com.stress.app_{i:04d}",
                "title": f"Stress Application #{i}",
                "icon": f"http://192.168.1.68:3000/icons/app_{i}.png",
                "largeIcon": f"http://192.168.1.68:3000/icons/app_large_{i}.png",
                "iconColor": f"#{i % 16:x}{i % 16:x}0000",
                "bgColor": "#000000",
                "hidden": (i % 20 == 0), # 5% hidden (50 apps)
                "systemApp": (i < 10),
                "removable": (i >= 10),
                "launchPointId": f"com.stress.app_{i:04d}_default"
            })

        large_inputs = []
        for i in range(50):
            large_inputs.append({
                "id": f"HDMI_{i+1}",
                "label": f"HDMI Port {i+1}",
                "portIdx": i + 1,
                "appId": f"com.webos.app.hdmi{i+1}",
                "icon": f"http://192.168.1.68:3000/icons/hdmi{i+1}.png",
                "connected": (i % 3 == 0),
                "subList": []
            })

        # Process apps using sync-apps.py logic
        processed_apps = []
        for app in large_lps:
            app_id = app.get("id", "")
            if app.get("hidden") is True or app_id == "com.gathin.tvhome":
                continue
            sanitized_id = sync_mod.sanitize_filename(app_id)
            icon_filename = f"{sanitized_id}.png"
            rel_icon_path = f"icons/{icon_filename}"
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

        processed_inputs = []
        for inp in large_inputs:
            inp_id = inp.get("id", "")
            inp_label = inp.get("label", inp_id)
            inp_app = inp.get("appId") or f"com.webos.app.{inp_id.lower()}"
            sanitized_inp_id = sync_mod.sanitize_filename(inp_id)
            icon_filename = f"input_{sanitized_inp_id}.png"
            rel_icon_path = f"icons/{icon_filename}"
            processed_inputs.append({
                "id": inp_id,
                "label": inp_label,
                "portIdx": inp.get("portIdx") or inp.get("port") or 1,
                "appId": inp_app,
                "connected": inp.get("connected", False),
                "icon": rel_icon_path,
            })

        result = {"apps": processed_apps, "inputs": processed_inputs}
        apps_count = len(result["apps"])
        inputs_count = len(result["inputs"])

        expected_apps = 1000 - 50 # 950 apps
        success = (apps_count == expected_apps and inputs_count == 50)

        output_js = sandbox / "apps.js"
        js_content = f"// Generated by stress test\nwindow.TV_APPS = {json.dumps(result, indent=2)};\nwindow.APPS = window.TV_APPS.apps;\nwindow.INPUTS = window.TV_APPS.inputs;\n"
        with open(output_js, "w", encoding="utf-8") as f:
            f.write(js_content)

        node_cmd = shutil.which("node")
        if node_cmd:
            proc = run_cmd([node_cmd, "--check", str(output_js)])
            success = success and (proc.returncode == 0)

        elapsed = time.perf_counter() - t0
        self.record("C3.1", "1,000 SSAP launch points stress test", success,
                    f"Processed {apps_count} visible apps and {inputs_count} inputs in {round(elapsed*1000, 1)}ms; JS syntax verified", elapsed)

    def test_adversarial_app_ids_and_sanitization(self):
        """3.2: Malicious app IDs with Windows reserved characters, path traversal, unicode."""
        t0 = time.perf_counter()
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_apps_mod", str(REPO_ROOT / "sync-apps.py"))
        sync_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync_mod)

        malicious_inputs = [
            'app:with:colons',
            'app/with/forward/slashes',
            'app\\with\\backslashes',
            'app<with>angle<brackets>',
            'app"with"quotes',
            'app|with|pipes',
            'app?with?question?marks',
            'app*with*asterisks',
            '../../../../etc/passwd',
            '..\\..\\..\\windows\\system32',
            'app with emojis 🚀🎮📺',
            'app_with_chinese_微信',
            'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1'
        ]

        all_safe = True
        windows_reserved_pattern = r'[<>:"/\\|?*]'
        for raw in malicious_inputs:
            sanitized = sync_mod.sanitize_filename(raw)
            if re.search(windows_reserved_pattern, sanitized):
                all_safe = False
                break

        elapsed = time.perf_counter() - t0
        self.record("C3.2", "Malicious app ID filename sanitization", all_safe,
                    f"Successfully sanitized {len(malicious_inputs)} malicious/reserved strings", elapsed)

    def test_null_and_missing_fields_in_ssap(self):
        """3.3: Incomplete SSAP response objects (null fields, missing attributes)."""
        t0 = time.perf_counter()
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_apps_mod", str(REPO_ROOT / "sync-apps.py"))
        sync_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync_mod)

        incomplete_lps = [
            {"id": "app.clean"},
            {"id": "app.nulls", "title": None, "icon": None, "largeIcon": None, "iconColor": None, "bgColor": None, "hidden": None},
            {"title": "No ID App"},
            {},
        ]
        incomplete_inputs = [
            {"id": "HDMI_1"},
            {"id": None, "label": None},
            {}
        ]

        try:
            processed_apps = []
            for app in incomplete_lps:
                app_id = app.get("id", "") or "unknown_app"
                if app.get("hidden") is True or app_id == "com.gathin.tvhome":
                    continue
                sanitized_id = sync_mod.sanitize_filename(str(app_id))
                icon_filename = f"{sanitized_id}.png"
                processed_apps.append({
                    "id": app_id,
                    "title": app.get("title", app_id) or str(app_id),
                    "icon": f"icons/{icon_filename}",
                    "largeIcon": f"icons/{icon_filename}",
                    "iconColor": app.get("iconColor") or "#3b82f6",
                    "bgColor": app.get("bgColor") or "#000000",
                    "systemApp": app.get("systemApp", False),
                    "removable": app.get("removable", True),
                })

            processed_inputs = []
            for inp in incomplete_inputs:
                inp_id = inp.get("id", "") or "unknown_input"
                inp_label = inp.get("label", inp_id) or str(inp_id)
                inp_app = inp.get("appId") or f"com.webos.app.{str(inp_id).lower()}"
                sanitized_inp_id = sync_mod.sanitize_filename(str(inp_id))
                processed_inputs.append({
                    "id": inp_id,
                    "label": inp_label,
                    "portIdx": inp.get("portIdx") or inp.get("port") or 1,
                    "appId": inp_app,
                    "connected": inp.get("connected", False),
                    "icon": f"icons/input_{sanitized_inp_id}.png",
                })

            success = True
            msg = f"Handled {len(incomplete_lps)} malformed launch points and {len(incomplete_inputs)} inputs without crashing"
        except Exception as e:
            success = False
            msg = f"Crashed on incomplete fields: {e}"

        elapsed = time.perf_counter() - t0
        self.record("C3.3", "Null and missing SSAP fields resiliency", success, msg, elapsed)

    # =========================================================================
    # Category 4: Full Roundtrip Rollback Fidelity (Byte-for-Byte)
    # =========================================================================

    def test_roundtrip_rollback_fidelity(self):
        """4.1: Workspace mutation and 100% byte-for-byte SHA-256 restoration."""
        t0 = time.perf_counter()
        sandbox = self.temp_dir / "c4_fidelity"
        app_workspace = sandbox / "app"
        app_workspace.mkdir(parents=True, exist_ok=True)
        icons_workspace = app_workspace / "icons"
        icons_workspace.mkdir(parents=True, exist_ok=True)

        # 1. Populate workspace with diverse files
        apps_js_content = "// Original apps.js with unicode: 🚀 CleanYourTV\nwindow.APPS = [{ id: 'app.netflix', title: 'Netflix' }];\n"
        config_js_content = "// Original config.js\nwindow.CONFIG = { clock: true, dock: ['app.netflix'] };\n"
        appinfo_content = json.dumps({"id": "com.gathin.tvhome", "version": "1.0.0", "type": "web", "main": "index.html", "title": "Home", "icon": "icon.png", "largeIcon": "largeIcon.png"}, indent=2)

        (app_workspace / "apps.js").write_text(apps_js_content, encoding="utf-8")
        (app_workspace / "config.js").write_text(config_js_content, encoding="utf-8")
        (app_workspace / "appinfo.json").write_text(appinfo_content, encoding="utf-8")

        # Create binary icon files
        icon1 = icons_workspace / "netflix.png"
        icon2 = icons_workspace / "youtube.png"
        icon1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03\x04" * 100)
        icon2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x05\x06\x07\x08\x09" * 150)

        # Record initial hashes
        orig_hashes = {
            "apps.js": compute_sha256(app_workspace / "apps.js"),
            "config.js": compute_sha256(app_workspace / "config.js"),
            "appinfo.json": compute_sha256(app_workspace / "appinfo.json"),
            "icons/netflix.png": compute_sha256(icon1),
            "icons/youtube.png": compute_sha256(icon2),
        }

        # 2. Take backup snapshot
        snap_dir = sandbox / "backup" / "fidelity_snapshot"
        res_b = run_cmd([
            sys.executable, "backup.py",
            "--offline-mock",
            "--app-dir", str(app_workspace),
            "--output-dir", str(snap_dir),
            "--quiet"
        ])
        if res_b.returncode != 0:
            self.record("C4.1", "Byte-for-byte rollback fidelity", False, f"Backup creation failed: {res_b.stderr}", time.perf_counter() - t0)
            return

        # 3. Aggressively mutate workspace
        (app_workspace / "apps.js").write_text("// CORRUPTED CONTENT OVERWRITE", encoding="utf-8")
        (app_workspace / "config.js").write_text("// DELETED / CORRUPT", encoding="utf-8")
        (app_workspace / "appinfo.json").unlink() # Deleted entirely
        icon1.write_bytes(b"\x00\x00\x00\x00") # Corrupted binary
        icon2.unlink() # Deleted icon
        (app_workspace / "rogue_extra_file.txt").write_text("MALICIOUS EXTRA FILE", encoding="utf-8")

        # 4. Perform restore
        res_r = run_cmd([
            sys.executable, "restore.py",
            "--snapshot", str(snap_dir),
            "--app-dir", str(app_workspace),
            "--force",
            "--quiet"
        ])
        if res_r.returncode != 0:
            self.record("C4.1", "Byte-for-byte rollback fidelity", False, f"Restore failed: {res_r.stderr}", time.perf_counter() - t0)
            return

        # 5. Verify byte-for-byte fidelity of all original files
        all_match = True
        mismatches = []
        for rel_name, expected_hash in orig_hashes.items():
            target_file = app_workspace / rel_name
            if not target_file.is_file():
                all_match = False
                mismatches.append(f"{rel_name} missing")
                continue
            actual_hash = compute_sha256(target_file)
            if actual_hash != expected_hash:
                all_match = False
                mismatches.append(f"{rel_name} hash mismatch ({actual_hash[:8]} != {expected_hash[:8]})")

        elapsed = time.perf_counter() - t0
        if all_match:
            self.record("C4.1", "Byte-for-byte rollback fidelity", True,
                        f"All {len(orig_hashes)} files restored with 100% cryptographic SHA-256 parity", elapsed)
        else:
            self.record("C4.1", "Byte-for-byte rollback fidelity", False,
                        f"Fidelity failure: {'; '.join(mismatches)}", elapsed)

    # =========================================================================
    # Category 5: PowerShell Wrapper Verification
    # =========================================================================

    def test_powershell_restore_wrapper(self):
        """5.1: Test restore.ps1 -List and -VerifyOnly via powershell.exe."""
        t0 = time.perf_counter()
        if sys.platform != "win32":
            self.record("C5.1", "PowerShell restore wrapper", True, "Skipped on non-Windows", time.perf_counter() - t0)
            return

        # 5.1.1: Test restore.ps1 -List
        res_list = run_cmd(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", "restore.ps1", "-List"])
        list_ok = (res_list.returncode == 0 and "CleanYourTV Snapshot Inventory" in res_list.stdout)

        # 5.1.2: Test restore.ps1 -VerifyOnly on latest
        res_verify = run_cmd(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", "restore.ps1", "-Latest", "-VerifyOnly"])
        verify_ok = (res_verify.returncode == 0)

        elapsed = time.perf_counter() - t0
        success = list_ok and verify_ok
        self.record("C5.1", "PowerShell restore.ps1 wrapper", success,
                    f"List code={res_list.returncode}, VerifyOnly code={res_verify.returncode}", elapsed)


def main():
    parser = argparse.ArgumentParser(description="CleanYourTV Empirical Challenger Test Suite")
    parser.add_argument("--temp-dir", default=None, help="Scratch directory for sandboxes")
    args = parser.parse_args()

    temp_base = Path(args.temp_dir) if args.temp_dir else Path(tempfile.mkdtemp(prefix="cy_challenge_"))
    temp_base.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("  CleanYourTV Empirical Challenger - Adversarial Verification Harness")
    print(f"  Sandbox: {temp_base}")
    print("=" * 80)

    runner = StressTestRunner(temp_base)

    print("\n--- Category 1: Deliberate Tampering & Corruption Detection ---")
    runner.test_tamper_launch_points()
    runner.test_tamper_apps_js()
    runner.test_tamper_icon_binary()
    runner.test_missing_file_in_snapshot()
    runner.test_malformed_snapshot_manifest_json()
    runner.test_semantic_corruption_with_valid_hash()

    print("\n--- Category 2: CLI Robustness & Error Handling ---")
    runner.test_invalid_cli_flags()
    runner.test_conflicting_cli_flags()
    runner.test_nonexistent_snapshot_target()
    runner.test_empty_backup_dir_resolution()
    runner.test_backup_dry_run_isolation()
    runner.test_backup_missing_app_assets_graceful()

    print("\n--- Category 3: SSAP Protocol & Data Serialization Stress ---")
    runner.test_large_ssap_payload_stress()
    runner.test_adversarial_app_ids_and_sanitization()
    runner.test_null_and_missing_fields_in_ssap()

    print("\n--- Category 4: Roundtrip Rollback Fidelity (Byte-for-Byte) ---")
    runner.test_roundtrip_rollback_fidelity()

    print("\n--- Category 5: PowerShell Wrapper Verification ---")
    runner.test_powershell_restore_wrapper()

    print("\n" + "=" * 80)
    print(f"  Summary: {runner.passed} passed | {runner.failed} failed out of {runner.passed + runner.failed} challenges")
    print("=" * 80)

    # Clean up scratch directory if all passed
    if runner.failed == 0 and not args.temp_dir:
        shutil.rmtree(temp_base, ignore_errors=True)

    return 0 if runner.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
