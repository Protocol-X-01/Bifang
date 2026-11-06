"""Android brand assets; called by the parent brand-pack builder, never on import.

No application sources, captures, platform badges, or existing exports are used.
SVG rasterization and PNG format conversion are delegated to native tools.
"""
from __future__ import annotations

import re
import struct
import subprocess
from xml.etree import ElementTree as ET

ANDROID = "http://schemas.android.com/apk/res/android"
AAPT = "http://schemas.android.com/aapt"
CANVAS = 1080
MARK_SIZE = 672
MARK_OFFSET = (CANVAS - MARK_SIZE) / 2
SAFE_INSET = 210
SAFE_RADIUS = 330
BASE = "mobile/android"
DENSITIES = (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192))


def _number(value):
    return f"{float(value):.8f}".rstrip("0").rstrip(".") or "0"


def _path_data(node):
    kind = node.tag.rsplit("}", 1)[-1]
    if kind == "path":
        return node.attrib["d"]
    if kind not in {"ellipse", "circle"}:
        raise ValueError(f"Unsupported original symbol element: {kind}")
    cx, cy = float(node.get("cx", 0)), float(node.get("cy", 0))
    rx = float(node.attrib["r"] if kind == "circle" else node.attrib["rx"])
    ry = rx if kind == "circle" else float(node.attrib["ry"])
    if rx <= 0 or ry <= 0:
        raise ValueError("The original symbol must retain positive ellipse/circle radii")
    left, right, y = _number(cx - rx), _number(cx + rx), _number(cy)
    # Two half-arcs reproduce the source ellipse/circle; no polygon approximation.
    return (f"M{left},{y} A{_number(rx)},{_number(ry)} 0,1,0 {right},{y} "
            f"A{_number(rx)},{_number(ry)} 0,1,0 {left},{y} Z")


def _mark(b, variant="ember-dark", x=MARK_OFFSET, y=MARK_OFFSET, size=MARK_SIZE):
    wrapper = ET.fromstring(f'<svg xmlns="{b.NS}">{b.mark(x, y, size, variant)}</svg>')
    group = wrapper[0]
    originals = [node for node in b.NODES if node.tag.rsplit("}", 1)[-1] == "ellipse"]
    ellipses = list(group.iter(f"{{{b.NS}}}ellipse"))
    if len(originals) != len(ellipses):
        raise ValueError("The mobile symbol must retain every original ellipse")
    for source, target in zip(originals, ellipses):
        if any(target.get(attribute) != source.get(attribute)
               for attribute in ("cx", "cy", "rx", "ry")):
            raise ValueError("b.mark must preserve the original ellipse geometry")
    return group


def _svg_mark(b, **options):
    return ET.tostring(_mark(b, **options), encoding="unicode")


def _gradient(b, name):
    svg = ET.fromstring(f'<svg xmlns="{b.NS}">{b.DEFS}</svg>')
    gradient = next((node for node in svg.iter(f"{{{b.NS}}}linearGradient")
                     if node.get("id") == name), None)
    if gradient is None or gradient.get("gradientUnits") != "userSpaceOnUse":
        raise ValueError(f"Unverifiable symbol stroke gradient: {name}")
    native = ET.Element("gradient", {
        f"{{{ANDROID}}}type": "linear",
        f"{{{ANDROID}}}tileMode": "clamp",
        **{f"{{{ANDROID}}}{native_name}": gradient.attrib[svg_name]
           for native_name, svg_name in (("startX", "x1"), ("startY", "y1"),
                                         ("endX", "x2"), ("endY", "y2"))},
    })
    for stop in gradient:
        offset = stop.get("offset", "0")
        number = float(offset.rstrip("%")) / (100 if offset.endswith("%") else 1)
        ET.SubElement(native, "item", {
            f"{{{ANDROID}}}offset": _number(number),
            f"{{{ANDROID}}}color": stop.attrib["stop-color"],
        })
    return native


def _vector(b, monochrome=False, background=False):
    root = ET.Element("vector", {
        f"{{{ANDROID}}}width": "108dp",
        f"{{{ANDROID}}}height": "108dp",
        f"{{{ANDROID}}}viewportWidth": str(CANVAS),
        f"{{{ANDROID}}}viewportHeight": str(CANVAS),
    })
    if background:
        ET.SubElement(root, "path", {
            f"{{{ANDROID}}}pathData": "M0,0 H1080 V1080 H0 Z",
            f"{{{ANDROID}}}fillColor": "@color/bifang_slate",
        })
        return root
    outer = ET.SubElement(root, "group", {
        f"{{{ANDROID}}}translateX": _number(MARK_OFFSET),
        f"{{{ANDROID}}}translateY": _number(MARK_OFFSET),
        f"{{{ANDROID}}}scaleX": _number(MARK_SIZE / 512),
        f"{{{ANDROID}}}scaleY": _number(MARK_SIZE / 512),
    })
    inner = ET.SubElement(outer, "group", {f"{{{ANDROID}}}translateY": "52"})
    # SVG and native variants share b.mark's original geometry and colour handling.
    prepared = _mark(b, variant="white" if monochrome else "ember-dark")
    for index, source in enumerate(prepared[0]):
        if source.get("transform"):
            raise ValueError("A new per-node transform requires explicit native translation")
        node = ET.SubElement(inner, "path", {
            f"{{{ANDROID}}}name": f"bifang_part_{index}",
            f"{{{ANDROID}}}pathData": _path_data(source),
        })
        for source_name, native_name in (("fill", "fillColor"), ("stroke", "strokeColor")):
            paint = source.get(source_name, "none")
            if paint.startswith("url("):
                match = re.fullmatch(r"url\(#([A-Za-z0-9_-]+)\)", paint)
                if match is None:
                    raise ValueError(f"Unsupported mobile paint: {paint}")
                attribute = ET.SubElement(node, f"{{{AAPT}}}attr",
                                          {"name": f"android:{native_name}"})
                attribute.append(_gradient(b, match.group(1)))
            else:
                node.set(f"{{{ANDROID}}}{native_name}", "#00000000" if paint == "none" else paint)
        for source_name, native_name in (("stroke-width", "strokeWidth"),
                                         ("stroke-linecap", "strokeLineCap"),
                                         ("stroke-linejoin", "strokeLineJoin")):
            if source.get(source_name):
                node.set(f"{{{ANDROID}}}{native_name}", source.attrib[source_name])
    return root


def _xml(b, relative, element, purpose=None):
    ET.register_namespace("android", ANDROID)
    ET.register_namespace("aapt", AAPT)
    ET.indent(element, space="    ")
    path = b.ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n'
                    + ET.tostring(element, encoding="unicode") + "\n", encoding="utf-8")
    if purpose is not None:
        if element.tag != "vector":
            raise ValueError("Only native vector artwork belongs in the artwork index")
        b.RECORDS.append({
            "path": relative, "width": int(element.attrib[f"{{{ANDROID}}}width"][:-2]),
            "height": int(element.attrib[f"{{{ANDROID}}}height"][:-2]),
            "dimension_unit": "dp", "viewport_width": CANVAS, "viewport_height": CANVAS,
            "purpose": purpose, "format": "XML", "artwork_type": "Android VectorDrawable",
        })


def _png(b, source, relative, size, purpose, play=False):
    target = b.ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsvg-convert", "--width", str(size), "--height", str(size),
                    "--output", str(target), str(b.ROOT / source)], check=True)
    if play:
        subprocess.run(["magick", str(target), "-colorspace", "sRGB", "-depth", "8",
                        "-strip", "-define", "png:include-chunk=sRGB",
                        "-define", "png:exclude-chunk=date,time", "PNG32:" + str(target)], check=True)
    header = target.read_bytes()[:33]
    if len(header) != 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"Invalid exported PNG: {relative}")
    width, height = struct.unpack(">II", header[16:24])
    if (width, height) != (size, size):
        raise ValueError(f"Unexpected exported dimensions: {relative}")
    if play and (header[24:26] != bytes((8, 6)) or target.stat().st_size > 1024 * 1024):
        raise ValueError("Play artwork must be 512-square, 8-bit RGBA and at most 1024 KiB")
    b.RECORDS.append({"path": relative, "width": width, "height": height,
                      "purpose": purpose, "format": "PNG"})


def _assert_safe_alpha(b, relative):
    # Inspection only. Neither operation replaces or edits the foreground asset.
    path = str(b.ROOT / relative)
    result = subprocess.run(["magick", path, "-alpha", "extract", "-threshold", "0",
                             "-format", "%@", "info:"], check=True, capture_output=True, text=True)
    match = re.fullmatch(r"(\d+)x(\d+)\+(\d+)\+(\d+)", result.stdout.strip())
    if match is None:
        raise ValueError("Unable to measure foreground alpha")
    width, height, x, y = map(int, match.groups())
    if (not width or not height or x < SAFE_INSET or y < SAFE_INSET
            or x + width > CANVAS - SAFE_INSET or y + height > CANVAS - SAFE_INSET):
        raise ValueError("Adaptive foreground exceeds the central 66dp square")
    result = subprocess.run([
        "magick", path, "-alpha", "extract", "(", "-size", "1080x1080", "xc:white",
        "-fill", "black", "-draw", "circle 540,540 870,540", ")",
        "-compose", "Multiply", "-composite", "-format", "%[fx:maxima]", "info:",
    ], check=True, capture_output=True, text=True)
    if float(result.stdout.strip()) != 0:
        raise ValueError("Adaptive foreground exceeds the central 66dp circle")
    return x, y, x + width, y + height


def build_mobile_android(b):
    """Write only mobile/android assets and append artwork to the parent's index."""
    foreground = _svg_mark(b)
    monochrome = _svg_mark(b, variant="white")
    background = f'<rect width="1080" height="1080" fill="{b.SLATE}"/>'
    masters = (
        ("adaptive-foreground", foreground, "Android adaptive foreground · transparent"),
        ("adaptive-background", background, "Android adaptive background · full bleed"),
        ("adaptive-monochrome", monochrome, "Android themed monochrome · white outline"),
    )
    for name, body, purpose in masters:
        b.write(f"{BASE}/bifang-{name}.svg", CANVAS, CANVAS, body, purpose, (CANVAS,))
    alpha_bounds = {
        name: _assert_safe_alpha(b, f"{BASE}/bifang-{name}-1080.png")
        for name in ("adaptive-foreground", "adaptive-monochrome")
    }

    _xml(b, f"{BASE}/res/drawable-v26/ic_bifang_launcher_foreground.xml", _vector(b),
         "Android adaptive foreground · native gradient vector")
    _xml(b, f"{BASE}/res/drawable-v26/ic_bifang_launcher_background.xml",
         _vector(b, background=True), "Android adaptive background · native vector")
    _xml(b, f"{BASE}/res/drawable-v33/ic_bifang_launcher_monochrome.xml",
         _vector(b, monochrome=True), "Android themed monochrome · native vector")

    colors = ET.Element("resources")
    for name, color in (("slate", b.SLATE), ("cloud_white", b.WHITE),
                        ("red", b.RED), ("flame_orange", b.ORANGE)):
        ET.SubElement(colors, "color", {"name": f"bifang_{name}"}).text = color
    _xml(b, f"{BASE}/res/values/bifang_colors.xml", colors)
    for api in (26, 33):
        for name in ("ic_launcher", "ic_launcher_round"):
            adaptive = ET.Element("adaptive-icon")
            for layer, drawable in (
                ("background", "ic_bifang_launcher_background"),
                ("foreground", "ic_bifang_launcher_foreground"),
            ):
                ET.SubElement(adaptive, layer, {f"{{{ANDROID}}}drawable": f"@drawable/{drawable}"})
            if api == 33:
                ET.SubElement(adaptive, "monochrome", {
                    f"{{{ANDROID}}}drawable": "@drawable/ic_bifang_launcher_monochrome",
                })
            _xml(b, f"{BASE}/res/mipmap-anydpi-v{api}/{name}.xml", adaptive)

    legacy_mark = _svg_mark(b, x=60, y=60, size=960)
    for shape, backdrop in (
        ("square", background),
        ("round", f'<circle cx="540" cy="540" r="540" fill="{b.SLATE}"/>'),
    ):
        master = f"{BASE}/bifang-legacy-{shape}.svg"
        # Only the background changes shape; the bird itself is never clipped.
        b.write(master, CANVAS, CANVAS, backdrop + legacy_mark,
                f"Android legacy launcher · {shape}", (512,))
        name = "ic_launcher" if shape == "square" else "ic_launcher_round"
        for density, pixels in DENSITIES:
            _png(b, master, f"{BASE}/res/mipmap-{density}/{name}.png", pixels,
                 f"Android legacy launcher · {shape} · {density}")

    play_master = f"{BASE}/bifang-google-play.svg"
    b.write(play_master, 512, 512,
            f'<rect width="512" height="512" fill="{b.SLATE}"/>'
            + _svg_mark(b, x=32, y=32, size=448),
            "Google Play icon master · full square · no shadow")
    _png(b, play_master, f"{BASE}/bifang-google-play-512.png", 512,
         "Google Play icon · 512px sRGB RGBA PNG · full bleed", play=True)

    masks = {
        "circle": '<circle cx="540" cy="540" r="360"/>',
        "rounded-square": '<rect x="180" y="180" width="720" height="720" rx="160"/>',
        "squircle": ('<path d="M540 180 C830 180 900 250 900 540 '
                     'C900 830 830 900 540 900 C250 900 180 830 180 540 '
                     'C180 250 250 180 540 180Z"/>'),
    }
    for name, mask in masks.items():
        preview = (f'<defs><clipPath id="android-preview-mask">{mask}</clipPath></defs>'
                   f'<g clip-path="url(#android-preview-mask)">{background}{foreground}</g>')
        b.write(f"{BASE}/bifang-mask-preview-{name}.svg", CANVAS, CANVAS, preview,
                f"Android illustrative {name} mask · artwork study, not a device capture", (540,))

    guide = (background + foreground
             + f'<rect x="210" y="210" width="660" height="660" fill="none" '
               f'stroke="{b.WHITE}" stroke-width="2" stroke-dasharray="12 8"/>'
             + f'<circle cx="540" cy="540" r="330" fill="none" stroke="{b.ORANGE}" '
               'stroke-width="2" stroke-dasharray="12 8"/>'
             + b.txt("108 DP / 1080 UNITS", 48, 92, 28, b.WHITE, 2, 500)
             + b.txt("CENTRAL 66 DP SAFE AREA", 48, 1008, 28, b.ORANGE, 2, 500))
    b.write(f"{BASE}/bifang-adaptive-safe-area.svg", CANVAS, CANVAS, guide,
            "Android adaptive safe-area diagram · not a launcher asset", (540,))
    return {"foreground_alpha_bounds": alpha_bounds, "canvas": CANVAS,
            "mark_size": MARK_SIZE, "safe_inset": SAFE_INSET, "safe_radius": SAFE_RADIUS}

