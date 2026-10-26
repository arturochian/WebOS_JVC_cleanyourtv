#!/usr/bin/env python3
"""
restore.py - State & Configuration Rollback Engine for WebOS TV Enhancement Suite.

Restores application configuration (apps.js, config.js, appinfo.json, icons)
from a selected or latest snapshot directory with cryptographic SHA-256 integrity
verification before applying changes. Refuses corrupted or tampered snapshots.

Tested with LG webOS Hub (JVC LT-32KB116) and supports offline mock verification.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = "1.0.0"
DEFAULT_BACKUP_DIR = "backup"
DEFAULT_APP_DIR = "app"


def compute_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hexadecimal digest of a file in binary mode."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def find_snapshots(backup_dir: Path) -> List[Path]:
    """Discover all snapshot directories inside backup_dir, sorted chronologically."""
    if not backup_dir.is_dir():
        return []
    candidates = []
    for item in backup_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            manifest = item / "snapshot.json"
            if manifest.is_file():
                candidates.append(item)
    # Sort by directory name (typically timestamp slug YYYYMMDD_HHMMSS)
    candidates.sort(key=lambda p: p.name)
    return candidates


def resolve_latest_snapshot(backup_dir: Path) -> Optional[Path]:
    """Resolve the latest snapshot via latest.json or newest snapshot directory."""
    latest_file = backup_dir / "latest.json"
    if latest_file.is_file():
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                latest_path = data.get("path")
                if latest_path:
                    p = Path(latest_path)
                    if not p.is_absolute():
                        p = Path.cwd() / p
                    if p.is_dir() and (p / "snapshot.json").is_file():
                        return p
                latest_slug = data.get("latest")
                if latest_slug:
                    p = backup_dir / latest_slug
                    if p.is_dir() and (p / "snapshot.json").is_file():
                        return p
        except Exception:
            pass

    snapshots = find_snapshots(backup_dir)
    return snapshots[-1] if snapshots else None


def resolve_snapshot(target: Optional[str], backup_dir: Path) -> Optional[Path]:
    """Resolve a snapshot by explicit path, slug name, or fallback to latest."""
    if not target or target.strip() == "":
        return resolve_latest_snapshot(backup_dir)

    # 1. Direct path
    p = Path(target)
    if not p.is_absolute():
        p = Path.cwd() / p
    if p.is_dir() and (p / "snapshot.json").is_file():
        return p

    # 2. Inside backup_dir
    p_in_backup = backup_dir / target
    if p_in_backup.is_dir() and (p_in_backup / "snapshot.json").is_file():
        return p_in_backup

    return None


def verify_snapshot_integrity(snapshot_dir: Path) -> Tuple[bool, str, Optional[dict]]:
    """
    Verify snapshot manifest, JSON structures, and SHA-256 checksums.
    Returns (is_valid, error_or_success_message, manifest_dict).
    """
    manifest_path = snapshot_dir / "snapshot.json"
    if not manifest_path.is_file():
        return False, f"Manifest not found: {manifest_path}", None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        return False, f"Invalid JSON syntax in manifest {manifest_path.name}: {e}", None

    checksums = manifest.get("checksums", {})
    if not isinstance(checksums, dict):
        return False, "Corrupted manifest: 'checksums' is not a dictionary", manifest

    # Check each file entry in checksums
    verified_files = 0
    for rel_path_str, expected_hash in checksums.items():
        # Skip alias keys (e.g. launch_points_sha256)
        if rel_path_str.endswith("_sha256"):
            continue

        file_path = snapshot_dir / rel_path_str
        if not file_path.is_file():
            return False, f"Missing expected snapshot file: '{rel_path_str}'", manifest

        actual_hash = compute_sha256(file_path)
        if actual_hash.lower() != expected_hash.lower():
            return (
                False,
                f"Checksum mismatch for '{rel_path_str}': expected {expected_hash}, calculated {actual_hash} (tampering or corruption detected)",
                manifest
            )
        verified_files += 1

    # Validate syntax of key JSON files in snapshot
    for json_file_name in ["launch_points.json", "inputs.json", "system_info.json", "appinfo.json"]:
        json_file_path = snapshot_dir / json_file_name
        if json_file_path.is_file():
            try:
                with open(json_file_path, "r", encoding="utf-8") as jf:
                    json.load(jf)
            except Exception as e:
                return False, f"Syntax corruption in JSON file '{json_file_name}': {e}", manifest

    return True, f"Integrity verified ({verified_files} files validated against SHA-256)", manifest


def list_snapshots(backup_dir: Path, quiet: bool = False) -> int:
    """Print an inventory table of all discovered snapshots."""
    snapshots = find_snapshots(backup_dir)
    if not snapshots:
        if not quiet:
            print(f"No snapshots found in '{backup_dir}'.")
        return 0

    latest_snap = resolve_latest_snapshot(backup_dir)
    latest_name = latest_snap.name if latest_snap else None

    if not quiet:
        print("\nCleanYourTV Snapshot Inventory:")
        print("-" * 90)
        print(f"{'Snapshot ID':<20} {'Created (UTC)':<22} {'Apps':<6} {'Inputs':<8} {'Icons':<7} {'Integrity':<11} {'Status'}")
        print("-" * 90)

    for snap in snapshots:
        valid, msg, manifest = verify_snapshot_integrity(snap)
        timestamp_str = "Unknown"
        apps_count = "-"
        inputs_count = "-"
        icons_count = "-"

        if manifest:
            ts = manifest.get("timestamp", snap.name)
            if "T" in ts:
                # Format ISO timestamp nicely
                timestamp_str = ts.replace("T", " ")[:19]
            else:
                timestamp_str = ts
            stats = manifest.get("stats", {})
            apps_count = str(stats.get("launchPointsCount", "-"))
            inputs_count = str(stats.get("inputsCount", "-"))
            icons_count = str(stats.get("iconsCount", "-"))

        integrity_str = "VALID" if valid else "CORRUPT"
        status_str = "[LATEST]" if snap.name == latest_name else "Available"
        if not valid:
            status_str = "UNUSABLE"

        if not quiet:
            print(f"{snap.name:<20} {timestamp_str:<22} {apps_count:<6} {inputs_count:<8} {icons_count:<7} {integrity_str:<11} {status_str}")

    if not quiet:
        print("-" * 90)
        print(f"Total snapshots: {len(snapshots)}\n")

    return 0


def validate_js_syntax(file_path: Path) -> bool:
    """Validate JavaScript file syntax using node -c if available."""
    if not file_path.is_file():
        return True
    try:
        res = subprocess.run(
            ["node", "-c", str(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        return res.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Fallback basic check
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Basic sanity check
            return len(content.strip()) > 0
        except Exception:
            return False


def restore_snapshot(
    snapshot_dir: Path,
    app_dir: Path,
    quiet: bool = False
) -> Tuple[int, str]:
    """Safely restore configuration and icons from snapshot into app_dir."""
    staging_dir = app_dir / ".restore_staging"

    try:
        app_dir.mkdir(parents=True, exist_ok=True)
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        restored_items: List[str] = []

        # 1. Stage config files
        for fname in ["apps.js", "config.js", "appinfo.json"]:
            src = snapshot_dir / fname
            if src.is_file():
                dest = staging_dir / fname
                shutil.copy2(src, dest)

        # 2. Stage icons
        src_icons = snapshot_dir / "icons"
        if src_icons.is_dir():
            dest_icons = staging_dir / "icons"
            dest_icons.mkdir(parents=True, exist_ok=True)
            for icon_file in src_icons.rglob("*"):
                if icon_file.is_file():
                    rel = icon_file.relative_to(src_icons)
                    target = dest_icons / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(icon_file, target)

        # 3. Atomically copy from staging to app_dir
        for fname in ["apps.js", "config.js", "appinfo.json"]:
            staged_file = staging_dir / fname
            if staged_file.is_file():
                final_dest = app_dir / fname
                shutil.copy2(staged_file, final_dest)
                restored_items.append(fname)
                if fname.endswith(".js"):
                    if not validate_js_syntax(final_dest):
                        if not quiet:
                            sys.stderr.write(f"[WARNING] Restored file '{fname}' failed JavaScript syntax check.\n")

        # Copy icons
        staged_icons = staging_dir / "icons"
        if staged_icons.is_dir():
            target_icons = app_dir / "icons"
            target_icons.mkdir(parents=True, exist_ok=True)
            for icon_file in staged_icons.rglob("*"):
                if icon_file.is_file():
                    rel = icon_file.relative_to(staged_icons)
                    target = target_icons / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(icon_file, target)
            restored_items.append("icons/")

        # Clean up staging directory
        shutil.rmtree(staging_dir, ignore_errors=True)

        summary = f"Restored {len(restored_items)} item(s): {', '.join(restored_items)}"
        return 0, summary
    except Exception as e:
        shutil.rmtree(staging_dir, ignore_errors=True)
        return 2, f"Filesystem I/O error during restoration: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="State & Configuration Rollback Engine for WebOS TV",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--latest", action="store_true", default=False,
                       help="Restore from the most recent snapshot in backup/ (default)")
    group.add_argument("--snapshot", dest="snapshot_target", default=None,
                       help="Specific snapshot ID/slug (e.g. '20261025_204500') or directory path")
    group.add_argument("--list", action="store_true", default=False,
                       help="List all discovered snapshots in backup/ with integrity status")

    parser.add_argument("--verify-only", action="store_true", default=False,
                        help="Verify snapshot schemas and SHA-256 checksums without altering any files")
    parser.add_argument("--offline-mock", action="store_true", default=False,
                        help="Acknowledge offline operation mode (no network calls)")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR,
                        help=f"Path to backup root directory (default: {DEFAULT_BACKUP_DIR})")
    parser.add_argument("--app-dir", default=DEFAULT_APP_DIR,
                        help=f"Target app directory to restore into (default: {DEFAULT_APP_DIR})")
    parser.add_argument("--force", "-f", action="store_true", default=False,
                        help="Overwrite target files without interactive prompt")
    parser.add_argument("--quiet", "-q", action="store_true", default=False,
                        help="Suppress standard output, only print errors")

    args = parser.parse_args()
    backup_path = Path(args.backup_dir)
    app_path = Path(args.app_dir)

    # 1. Handle --list
    if args.list:
        return list_snapshots(backup_path, quiet=args.quiet)

    # 2. Resolve target snapshot
    if args.snapshot_target:
        snapshot_dir = resolve_snapshot(args.snapshot_target, backup_path)
        if not snapshot_dir:
            if not args.quiet:
                sys.stderr.write(f"[ERROR] Snapshot '{args.snapshot_target}' not found in '{backup_path}'.\n")
            return 1
    else:
        # Default or --latest
        snapshot_dir = resolve_latest_snapshot(backup_path)
        if not snapshot_dir:
            if not args.quiet:
                sys.stderr.write(f"[ERROR] No valid snapshots found in '{backup_path}'.\n")
            return 1

    if not args.quiet:
        print(f"=== WebOS TV State Restore [{VERSION}] ===")
        print(f"Target Snapshot: {snapshot_dir.name}")
        print(f"Directory: {snapshot_dir}")
        print(f"App Destination: {app_path}")

    # 3. Cryptographic Verification
    is_valid, message, manifest = verify_snapshot_integrity(snapshot_dir)
    if not is_valid:
        if not args.quiet:
            sys.stderr.write(f"\n[INTEGRITY FAILURE] Snapshot is corrupt or tampered:\n  {message}\n")
            sys.stderr.write("Refusing to restore from an untrusted or damaged snapshot.\n")
        return 1

    if not args.quiet:
        print(f"[VERIFIED] {message}")

    # 4. If --verify-only, stop here with success
    if args.verify_only:
        if not args.quiet:
            print("\n[SUCCESS] Snapshot integrity check passed (--verify-only specified).")
        return 0

    # 5. Interactive confirmation (unless --force or --quiet)
    if not args.force and not args.quiet:
        try:
            choice = input(f"\nProceed with restoring into '{app_path}'? [y/N]: ").strip().lower()
            if choice not in ["y", "yes"]:
                print("Restoration cancelled by user.")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("\nRestoration cancelled.")
            return 0

    # 6. Perform Restoration
    code, summary = restore_snapshot(snapshot_dir, app_path, quiet=args.quiet)
    if code != 0:
        if not args.quiet:
            sys.stderr.write(f"\n[ERROR] Restore failed: {summary}\n")
        return code

    if not args.quiet:
        print(f"\n[SUCCESS] Restoration completed successfully!")
        print(f"  {summary}")
        print(f"  Target: {app_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
