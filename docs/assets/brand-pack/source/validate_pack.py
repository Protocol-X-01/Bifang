"""Check delivered artwork and offline links. Pillow is used for inspection only."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NS = "{http://www.w3.org/2000/svg}"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"src", "href"} and value:
                self.paths.append(value)


def main():
    assets = json.loads((ROOT / "ASSET-INDEX.json").read_text())["assets"]
    checks = Counter()
    problems = []
    for item in assets:
        path = ROOT / item["path"]
        if not path.is_file():
            problems.append("Missing: " + item["path"])
            continue
        checks["artwork_files_present"] += 1
        if item["format"] == "SVG":
            tree = ET.parse(path).getroot()
            assert (int(tree.get("width")), int(tree.get("height"))) == (item["width"], item["height"])
            assert not list(tree.iter(NS + "text")), path
            for node in tree.iter():
                for key, value in node.attrib.items():
                    if key in {"href", "{http://www.w3.org/1999/xlink}href"}:
                        assert value.startswith(("data:", "#")), (path, value)
            checks["portable_outlined_svgs"] += 1
        elif item["format"] == "PNG":
            with Image.open(path) as im:
                im.load()
                assert im.size == (item["width"], item["height"]), (path, im.size)
                checks["png_dimensions_and_decode"] += 1
                if item["path"].startswith("logos/png/"):
                    alpha = im.getchannel("A")
                    assert alpha.getextrema() == (0, 255), path
                    box = alpha.getbbox()
                    assert box and box[0] > 0 and box[1] > 0 and box[2] < im.width and box[3] < im.height, (path, box)
                    checks["transparent_logo_with_clear_margins"] += 1
                if item["path"].startswith("thumbnails/"):
                    assert path.stat().st_size < 2_000_000, path
                    checks["thumbnail_under_2mb"] += 1
        elif item["format"] == "ICO":
            with Image.open(path) as im:
                assert im.ico.sizes() == {(16, 16), (32, 32), (48, 48)}
                checks["multi_resolution_ico"] += 1

    for variant in ("ember-dark", "ember-light", "white", "black"):
        tree = ET.parse(ROOT / f"logos/svg/bifang-symbol-{variant}.svg").getroot()
        head = next(node for node in tree.iter(NS + "ellipse") if node.get("cx") == "256")
        assert head.get("rx") == "28" and head.get("ry") == "20", variant
        checks["original_head_ellipse_preserved"] += 1
        with Image.open(ROOT / f"logos/png/bifang-symbol-{variant}-512.png") as im:
            # The supporting leg and foot must survive gradient and mono exports.
            assert im.getchannel("A").crop((238, 393, 274, 443)).getbbox(), variant
            checks["supporting_leg_visible"] += 1

    links = Links()
    links.feed((ROOT / "START-HERE.html").read_text())
    for value in links.paths:
        if value.startswith(("data:", "#", "https:")):
            continue
        assert (ROOT / value).exists(), value
        checks["offline_links_resolve"] += 1

    provenance = json.loads((ROOT / "source/PROVENANCE.json").read_text())
    for font_file in provenance["font"]["files"]:
        data = (ROOT / font_file["path"]).read_bytes()
        blob = b"blob " + str(len(data)).encode() + b"\0" + data
        assert hashlib.sha1(blob).hexdigest() == font_file["git_blob_sha1"]
        checks["font_source_blob_verified"] += 1

    with Image.open(ROOT / "backgrounds/ember-atmosphere.png") as bg:
        background = {"width": bg.width, "height": bg.height, "mode": bg.mode, "pixel_edits": False}
    assert (ROOT / "social/youtube-channel-banner-2560.png").stat().st_size < 6_000_000
    for catalog in sorted((ROOT / "mobile/apple").glob("*.appiconset")):
        entries = json.loads((catalog / "Contents.json").read_text())["images"]
        for entry in entries:
            width, height = (float(value) for value in entry["size"].split("x"))
            scale = float(entry.get("scale", "1x")[:-1])
            with Image.open(catalog / entry["filename"]) as icon:
                assert icon.size == (int(width * scale), int(height * scale)), entry
                assert icon.mode == "RGB" and "transparency" not in icon.info, entry
                if any(a.get("value") == "tinted" for a in entry.get("appearances", [])):
                    red, green, blue = icon.split()
                    assert red.tobytes() == green.tobytes() == blue.tobytes()
                    checks["apple_tinted_neutral_channels"] += 1
            checks["apple_catalog_slot_dimensions_and_no_alpha"] += 1
    for name in ("foreground", "monochrome"):
        with Image.open(ROOT / f"mobile/android/bifang-adaptive-{name}-1080.png") as icon:
            alpha = icon.getchannel("A")
            bounds = alpha.getbbox()
            assert bounds and min(bounds[:2]) >= 210 and max(bounds[2:]) <= 870
            points = ((x, y) for y in range(bounds[1], bounds[3])
                      for x in range(bounds[0], bounds[2]) if alpha.getpixel((x, y)))
            assert max((x + .5 - 540) ** 2 + (y + .5 - 540) ** 2 for x, y in points) <= 330 ** 2
            checks["android_foreground_inside_safe_circle"] += 1
    with Image.open(ROOT / "mobile/android/bifang-google-play-512.png") as icon:
        assert icon.size == (512, 512) and icon.mode == "RGBA"
        assert icon.getchannel("A").getextrema() == (255, 255)
        assert (ROOT / "mobile/android/bifang-google-play-512.png").stat().st_size <= 1024 * 1024
        checks["play_full_square_rgba_icon"] += 1
    assert not problems, problems
    report = {"brand": "Bifang", "edition": "2026-11-06", "status": "passed", "artwork_files": len(assets),
              "checks": dict(checks), "generated_background": background,
              "visual_review": ["Brand board", "Horizontal dark lockup", "48px favicon", "Brand thumbnail", "Coding-demo thumbnail", "Social and banner layouts", "Mobile brand board", "Apple icon master", "Android 48px launcher icon", "Tablet landscape cover"],
              "notes": ["Core logo geometry preserved; gradients, mono strokes and canvas placement repaired.",
                        "PNG transparency checked on logo exports; promo layouts intentionally have backgrounds.",
                        "Visual review describes this delivered edition, not a claim about a deployed app or video thumbnail."]}
    (ROOT / "VALIDATION.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
