"""Extend the parent brand builder with flat iOS/iPadOS icon artwork.

Python composes SVG/JSON and reads PNG headers only. Raster export and RGB
conversion use rsvg-convert and ImageMagick; importing this module builds nothing.
"""
from __future__ import annotations

import json
import shutil
import struct
import subprocess


def _record_png(b, destination, pixels, purpose):
    with destination.open("rb") as image:
        header = image.read(26)
    if len(header) != 26 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"Invalid PNG header: {destination}")
    width, height, depth, color_type = struct.unpack(">IIBB", header[16:26])
    if (width, height, depth, color_type) != (pixels, pixels, 8, 2):
        raise ValueError(f"Expected {pixels}px square, 8-bit RGB PNG without alpha: {destination}")
    b.RECORDS.append({
        "path": destination.relative_to(b.ROOT).as_posix(),
        "width": width,
        "height": height,
        "purpose": purpose,
        "format": "PNG",
    })


def _export_rgb_png(b, master, destination, pixels, background, purpose, grayscale=False):
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = subprocess.run(
        ["rsvg-convert", "--width", str(pixels), "--height", str(pixels), str(master)],
        capture_output=True, check=True,
    )
    command = ["magick", "PNG:-"]
    if grayscale:
        command += ["-colorspace", "Gray"]
    command += [
        "-colorspace", "sRGB", "-background", background,
        "-alpha", "remove", "-alpha", "off", "-depth", "8", "-type", "TrueColor",
        "-strip", "-define", "png:exclude-chunk=date,time",
        f"PNG24:{destination}",
    ]
    subprocess.run(command, input=rendered.stdout, check=True)
    _record_png(b, destination, pixels, purpose)


def _copy_png(b, source, destination, pixels, purpose):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    _record_png(b, destination, pixels, purpose)


def _write_catalog(directory, images):
    directory.mkdir(parents=True, exist_ok=True)
    contents = {"images": images, "info": {"author": "xcode", "version": 1}}
    (directory / "Contents.json").write_text(
        json.dumps(contents, indent=2) + "\n", encoding="utf-8",
    )


def build_mobile_apple(b):
    """Register Apple artwork with the parent and write two alternative icon sets."""
    root = b.ROOT / "mobile/apple"
    modern = root / "AppIcon.appiconset"
    legacy = root / "AppIcon-AllSizes.appiconset"
    masters = {}
    modern_images = []

    for appearance, background, variant in (
        ("any", b.WHITE, "ember-light"),
        ("dark", b.SLATE, "ember-dark"),
        ("tinted", b.WHITE, "black"),
    ):
        stem = f"bifang-ios-{appearance}"
        relative = f"mobile/apple/masters/{stem}.svg"
        # Match the existing avatar placement; the full-square background has no mask.
        body = f'<rect width="1024" height="1024" fill="{background}"/>'
        body += b.mark(72, 62, 880, variant)
        purpose = f"Bifang iOS / iPadOS app icon · {appearance} · opaque square"
        b.write(relative, 1024, 1024, body, purpose)
        master = b.ROOT / relative
        png = master.with_name(f"{stem}-1024.png")
        _export_rgb_png(b, master, png, 1024, background, purpose,
                        grayscale=appearance == "tinted")
        masters[appearance] = (master, png, background)

        _copy_png(b, png, modern / png.name, 1024, purpose + " · Single Size catalog")
        slot = {
            "filename": png.name,
            "idiom": "universal",
            "platform": "ios",
            "size": "1024x1024",
        }
        if appearance != "any":
            slot["appearances"] = [{"appearance": "luminosity", "value": appearance}]
        modern_images.append(slot)
    _write_catalog(modern, modern_images)

    # Point sizes and display scales are distinct from the physical PNG dimensions.
    slots = [
        (idiom, points, scale)
        for idiom, point_sizes, scales in (
            ("iphone", (20, 29, 40, 60), (2, 3)),
            ("ipad", (20, 29, 40, 76), (1, 2)),
        )
        for points in point_sizes
        for scale in scales
    ]
    slots += [("ipad", 83.5, 2), ("ios-marketing", 1024, 1)]
    legacy_images = []
    exported_sizes = {}
    master, png, background = masters["any"]
    for idiom, points, scale in slots:
        pixels = int(points * scale)
        filename = f"bifang-ios-any-{pixels}.png"
        if pixels not in exported_sizes:
            destination = legacy / filename
            purpose = f"Bifang iOS / iPadOS app icon · Any · All Sizes · {pixels}px"
            if pixels == 1024:
                _copy_png(b, png, destination, pixels, purpose)
            else:
                _export_rgb_png(b, master, destination, pixels, background, purpose)
            exported_sizes[pixels] = filename
        legacy_images.append({
            "filename": exported_sizes[pixels],
            "idiom": idiom,
            "size": f"{points}x{points}",
            "scale": f"{scale}x",
        })
    _write_catalog(legacy, legacy_images)
