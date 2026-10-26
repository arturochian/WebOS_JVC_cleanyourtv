#!/usr/bin/env python3
"""
tools/generate_icons.py - Cross-platform webOS icon generator for Windows

Generates webOS required icon resolutions:
- app/icon.png: 80x80 pixels (tile / switcher)
- app/largeIcon.png: 130x130 pixels (app manager / dock)

Engines:
1. Pillow (PIL) - Primary high-quality Lanczos downsampler.
2. Windows .NET System.Drawing - Fallback via PowerShell on Windows.
3. Pure-Python PNG writer - Zero external dependency fallback.
"""

import argparse
import os
import struct
import subprocess
import sys
import zlib


def resize_with_pillow(source_path: str, output_path: str, size: tuple[int, int]) -> bool:
    """Resize image using Pillow."""
    try:
        from PIL import Image

        with Image.open(source_path) as img:
            # Convert to RGBA for consistent PNG formatting
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            # High quality downsampling
            resample = getattr(Image.Resampling, "LANCZOS", getattr(Image, "LANCZOS", Image.BILINEAR))
            resized = img.resize(size, resample=resample)
            resized.save(output_path, "PNG", optimize=True)
            return True
    except Exception as exc:
        print(f"[generate_icons] Pillow engine failed: {exc}", file=sys.stderr)
        return False


def resize_with_dotnet(source_path: str, output_path: str, size: tuple[int, int]) -> bool:
    """Fallback: Resize image using Windows .NET System.Drawing via PowerShell."""
    if sys.platform != "win32":
        return False

    w, h = size
    abs_src = os.path.abspath(source_path).replace("'", "''")
    abs_out = os.path.abspath(output_path).replace("'", "''")

    ps_script = f"""
Add-Type -AssemblyName System.Drawing
$src = [System.Drawing.Image]::FromFile('{abs_src}')
$bmp = New-Object System.Drawing.Bitmap {w}, {h}
$graph = [System.Drawing.Graphics]::FromImage($bmp)
$graph.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$graph.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
$graph.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$graph.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
$graph.DrawImage($src, 0, 0, {w}, {h})
$bmp.Save('{abs_out}', [System.Drawing.Imaging.ImageFormat]::Png)
$graph.Dispose()
$bmp.Dispose()
$src.Dispose()
"""
    try:
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        print(f"[generate_icons] .NET fallback stderr: {res.stderr}", file=sys.stderr)
    except Exception as exc:
        print(f"[generate_icons] .NET fallback execution failed: {exc}", file=sys.stderr)

    return False


def create_solid_png(output_path: str, size: tuple[int, int], color: tuple[int, int, int, int] = (20, 24, 34, 255)) -> bool:
    """Pure-Python minimal valid RGBA PNG writer (last-resort safety fallback)."""
    try:
        width, height = size
        # PNG signature
        png_data = bytearray(b"\x89PNG\r\n\x1a\n")

        # IHDR chunk
        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        png_data += struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)

        # Raw scanlines with filter byte 0 (None)
        raw_rows = []
        row_bytes = bytes([0] + list(color) * width)
        for _ in range(height):
            raw_rows.append(row_bytes)
        compressed = zlib.compress(b"".join(raw_rows))

        # IDAT chunk
        png_data += struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)

        # IEND chunk
        png_data += struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)

        with open(output_path, "wb") as f:
            f.write(png_data)
        return True
    except Exception as exc:
        print(f"[generate_icons] Pure-Python fallback failed: {exc}", file=sys.stderr)
        return False


def resize_image(source_path: str, output_path: str, size: tuple[int, int]) -> bool:
    """Attempt resizing using Pillow, then .NET System.Drawing, then pure-Python."""
    # 1. Primary: Pillow
    if resize_with_pillow(source_path, output_path, size):
        return True

    # 2. Fallback: Windows .NET
    if resize_with_dotnet(source_path, output_path, size):
        return True

    # 3. Fallback: Pure Python minimal PNG
    print(f"[generate_icons] Warning: Falling back to pure-Python PNG writer for {output_path}", file=sys.stderr)
    return create_solid_png(output_path, size)


def generate_icons(source_path: str | None = None, output_dir: str | None = None, force: bool = False) -> dict[str, str]:
    """
    Generate 80x80 icon.png and 130x130 largeIcon.png from source image.
    Returns dict mapping icon name to output file path.
    Raises FileNotFoundError if source is missing.
    """
    if source_path is None:
        if os.path.exists("assets/icon.jpg"):
            source_path = "assets/icon.jpg"
        elif os.path.exists("assets/icon.png"):
            source_path = "assets/icon.png"
        else:
            source_path = "assets/icon.jpg"

    if output_dir is None:
        output_dir = "app"

    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source image '{source_path}' not found.")

    os.makedirs(output_dir, exist_ok=True)

    icon_path = os.path.join(output_dir, "icon.png")
    large_icon_path = os.path.join(output_dir, "largeIcon.png")

    targets = [
        (icon_path, (80, 80)),
        (large_icon_path, (130, 130)),
    ]

    results = {}
    for path, size in targets:
        if os.path.exists(path) and not force:
            # Overwrite to ensure freshness if source is newer or always update
            pass
        success = resize_image(source_path, path, size)
        if not success:
            raise RuntimeError(f"Failed to generate icon at {path}")
        results[os.path.basename(path)] = path
        print(f"Generated {path} ({size[0]}x{size[1]})")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate webOS icons (80x80 icon.png and 130x130 largeIcon.png).")
    parser.add_argument("--source", "-s", default=None, help="Path to source icon image (default: assets/icon.jpg)")
    parser.add_argument("--output-dir", "-o", default=None, help="Directory to save generated icons (default: app)")
    parser.add_argument("--force", "-f", action="store_true", help="Force regenerate icons even if they exist")

    args = parser.parse_args()

    try:
        generate_icons(source_path=args.source, output_dir=args.output_dir, force=args.force)
        return 0
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Error generating icons: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
