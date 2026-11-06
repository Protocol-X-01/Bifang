"""Rebuild Bifang's editable vector kit and mechanical PNG exports.

Requires fonttools and rsvg-convert. Uses only assets inside this pack.
The optional generated backdrop is kept unchanged and embedded in one layout.
"""
from __future__ import annotations

import base64
import copy
import html
import json
import math
import struct
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
SLATE, WHITE, RED, ORANGE = "#0F172A", "#F7F7F7", "#E63946", "#FF8A3D"
MUTED, LINE = "#94A3B8", "#334155"
FONT = ROOT / "fonts/SpaceGrotesk-variable.ttf"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
SOURCE = ET.parse(ROOT / "source/bifang-symbol-original.svg").getroot()
NODES = list(SOURCE.find(f"{{{NS}}}g"))
RECORDS: list[dict] = []

DEFS = '''<defs>
<linearGradient id="ember" gradientUnits="userSpaceOnUse" x1="70" y1="380" x2="442" y2="30"><stop stop-color="#E63946"/><stop offset="1" stop-color="#FF8A3D"/></linearGradient>
<linearGradient id="ember-reverse" gradientUnits="userSpaceOnUse" x1="442" y1="380" x2="70" y2="30"><stop stop-color="#E63946"/><stop offset="1" stop-color="#FF8A3D"/></linearGradient>
<linearGradient id="word-ember" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#E63946"/><stop offset="1" stop-color="#FF8A3D"/></linearGradient>
<radialGradient id="ambient"><stop stop-color="#E63946" stop-opacity=".15"/><stop offset="1" stop-color="#0F172A" stop-opacity="0"/></radialGradient>
<linearGradient id="backdrop" x2="1" y2="1"><stop stop-color="#090F1B"/><stop offset="1" stop-color="#172238"/></linearGradient>
</defs>'''


@lru_cache(maxsize=4)
def font(weight: int = 700):
    f = instantiateVariableFont(TTFont(FONT), {"wght": weight}, inplace=False)
    return f, f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm


def lettering(value: str, x: float, y: float, size: float, fill: str = WHITE,
              tracking: float = 0, weight: int = 700) -> tuple[str, float]:
    f, glyphs, cmap, units = font(weight)
    scale, cursor, pieces = size / units, 0.0, []
    for char in value:
        name = cmap[ord(char)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(pen)
        if pen.getCommands():
            pieces.append(f'<path transform="translate({cursor:.4f},0)" d="{pen.getCommands()}"/>')
        cursor += f["hmtx"][name][0] + tracking / scale
    width = cursor * scale - (tracking if value else 0)
    return (f'<g aria-label="{html.escape(value)}" fill="{fill}" transform="translate({x},{y}) scale({scale:.7f},-{scale:.7f})">'
            + "".join(pieces) + "</g>"), width


def txt(value, x, y, size, fill=WHITE, tracking=0, weight=700):
    return lettering(value, x, y, size, fill, tracking, weight)[0]


def centered(value, width, y, size, fill=WHITE, tracking=0, weight=700):
    _, advance = lettering(value, 0, 0, size, fill, tracking, weight)
    return txt(value, (width - advance) / 2, y, size, fill, tracking, weight)


def mark(x=0, y=0, size=512, variant="ember-dark"):
    mono = variant in {"white", "black"}
    ink = "#FFFFFF" if variant == "white" else "#000000"
    body = WHITE if variant == "ember-light" else SLATE
    glyph = SLATE if variant == "ember-light" else WHITE
    pieces = []
    for source in NODES:
        node = copy.deepcopy(source)
        node.attrib.pop("filter", None)
        if node.tag.endswith("path"):
            node.attrib.pop("rx", None)
        if mono and node.tag.endswith("circle") and node.get("r") == "2":
            continue
        for key in ("stroke", "fill"):
            current = node.get(key)
            if mono:
                if key == "stroke" and current and current != "none":
                    node.set(key, ink)
                elif key == "fill" and current and current != "none":
                    node.set(key, "none" if current == SLATE else ink)
            else:
                if current == SLATE:
                    node.set(key, body)
                elif current == WHITE:
                    node.set(key, glyph)
        pieces.append(ET.tostring(node, encoding="unicode"))
    return (f'<g transform="translate({x},{y}) scale({size / 512:.8f})">'
            '<g transform="translate(0,52)">' + "".join(pieces) + "</g></g>")


def svg(width, height, body, title="Bifang"):
    return (f'<svg xmlns="{NS}" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="{html.escape(title)}"><title>{html.escape(title)}</title>' + DEFS + body + "</svg>\n")


def write(relative, width, height, body, purpose, render_widths=()):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg(width, height, body, purpose))
    RECORDS.append({"path": relative, "width": width, "height": height, "purpose": purpose, "format": "SVG"})
    for export_width in render_widths:
        name = path.stem + f"-{export_width}.png"
        target = ROOT / "logos/png" / name if relative.startswith("logos/svg/") else path.with_name(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["rsvg-convert", "--width", str(export_width), "--output", str(target), str(path)], check=True)
        png_width, png_height = struct.unpack(">II", target.read_bytes()[16:24])
        RECORDS.append({"path": str(target.relative_to(ROOT)), "width": png_width,
                        "height": png_height, "purpose": purpose, "format": "PNG"})


def asset_image(name, x, y, width, height, view_box=None):
    path = ROOT / "source" / name
    data = base64.b64encode(path.read_bytes()).decode()
    if view_box:
        # Layout viewport shows the complete results block, without the unused
        # terminal area below it. The embedded source pixels remain unchanged.
        return (f'<svg x="{x}" y="{y}" width="{width}" height="{height}" '
                f'viewBox="{view_box}" preserveAspectRatio="xMinYMin meet" overflow="hidden">'
                f'<image width="1960" height="1040" href="data:image/png;base64,{data}"/></svg>')
    image = f'<image x="{x}" y="{y}" width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{data}"/>'
    return image


def backdrop(width, height, generated=False):
    body = f'<rect width="{width}" height="{height}" fill="url(#backdrop)"/>'
    generated_path = ROOT / "backgrounds/ember-atmosphere.png"
    if generated and generated_path.exists():
        data = base64.b64encode(generated_path.read_bytes()).decode()
        body += f'<image width="{width}" height="{height}" preserveAspectRatio="xMidYMid slice" href="data:image/png;base64,{data}"/>'
    else:
        body += f'<ellipse cx="{width * .88}" cy="{height * .18}" rx="{width * .55}" ry="{height * .8}" fill="url(#ambient)"/>'
        for x in range(0, width, 96):
            body += f'<path d="M{x} 0V{height}" stroke="#FFFFFF" stroke-opacity=".018"/>'
        for y in range(0, height, 96):
            body += f'<path d="M0 {y}H{width}" stroke="#FFFFFF" stroke-opacity=".018"/>'
    return body


def brand_heading(x=84, y=70, size=52):
    return mark(x, y - size, size * 1.35) + txt("BIFANG", x + size * 1.65, y, size, tracking=size * .12)


def core_logos():
    for variant in ("ember-dark", "ember-light", "white", "black"):
        write(f"logos/svg/bifang-symbol-{variant}.svg", 512, 512, mark(variant=variant),
              f"Bifang symbol · {variant}", (256, 512, 1024))
        ink = SLATE if variant in {"ember-light", "black"} else WHITE
        if variant == "black": ink = "#000000"
        label, advance = lettering("BIFANG", 250, 141, 120, ink, 9)
        width = math.ceil(advance + 292)
        tagline = txt("BUILD. RUN. VERIFY.", 254, 192, 23, ink, 2.2, 500)
        write(f"logos/svg/bifang-horizontal-{variant}.svg", width, 256,
              mark(14, 8, 228, variant) + label + tagline,
              f"Bifang horizontal lockup · {variant}", (2400,))
    for variant in ("ember-dark", "ember-light"):
        ink = SLATE if variant == "ember-light" else WHITE
        body = mark(260, 20, 480, variant) + centered("BIFANG", 1000, 663, 144, ink, 14)
        body += centered("BUILD. RUN. VERIFY.", 1000, 754, 31, ink, 4, 500)
        write(f"logos/svg/bifang-stacked-{variant}.svg", 1000, 850, body,
              f"Bifang stacked lockup · {variant}", (2048,))
    for name, color in (("ember", "url(#word-ember)"), ("white", "#FFFFFF"), ("black", "#000000")):
        label, width = lettering("BIFANG", 20, 144, 160, color, 13)
        write(f"logos/svg/bifang-wordmark-{name}.svg", math.ceil(width + 40), 188, label,
              f"Bifang outlined wordmark · {name}", (2400,))


def icons():
    for name, bg, variant in (("slate", SLATE, "ember-dark"), ("cloud", WHITE, "ember-light")):
        body = f'<rect width="1024" height="1024" rx="220" fill="{bg}"/>' + mark(72, 62, 880, variant)
        write(f"icons/bifang-avatar-{name}.svg", 1024, 1024, body,
              f"Bifang avatar · {name}", (512, 1024))
    micro = (f'<rect width="32" height="32" rx="7" fill="{SLATE}"/>'
             f'<path d="M10 11C4 9 5 3 9 6L11 10M22 11C28 9 27 3 23 6L21 10" fill="none" stroke="{ORANGE}" stroke-width="1.8" stroke-linecap="round"/>'
             f'<path d="M12 12H20V24H12Z" fill="none" stroke="{RED}" stroke-width="1.5"/>'
             '<path d="M14.5 16L17.5 19M17.5 16L14.5 19" stroke="#F7F7F7" stroke-width="1.4" stroke-linecap="round"/>'
             f'<path d="M16 24V28M14 28H18" stroke="{ORANGE}" stroke-width="1.6" stroke-linecap="round"/>'
             f'<ellipse cx="16" cy="8" rx="2" ry="1.5" fill="{ORANGE}"/>')
    write("icons/favicon.svg", 32, 32, micro, "Bifang simplified favicon", (16, 32, 48, 64, 180, 192))
    subprocess.run(["magick", str(ROOT / "icons/favicon-16.png"),
                    str(ROOT / "icons/favicon-32.png"), str(ROOT / "icons/favicon-48.png"),
                    str(ROOT / "icons/favicon.ico")], check=True)
    RECORDS.append({"path": "icons/favicon.ico", "width": 48, "height": 48,
                    "sizes": [16, 32, 48], "purpose": "Multi-resolution browser favicon", "format": "ICO"})


def promos():
    body = backdrop(1920, 1080) + brand_heading(88, 143, 54)
    for word, y, color in (("BUILD.", 370, WHITE), ("RUN.", 529, WHITE), ("VERIFY.", 688, ORANGE)):
        body += txt(word, 96, y, 146, color, 2)
    body += txt("A coding workspace", 102, 816, 36, "#CBD5E1", 0, 400)
    body += txt("that shows its work.", 102, 869, 36, "#CBD5E1", 0, 400)
    body += asset_image("bifang-desktop-ide.png", 770, 180, 1090, 755)
    body += txt("DESKTOP / TERMINAL / COMPANION", 100, 1000, 24, MUTED, 3, 500)
    write("thumbnails/youtube-coding-demo.svg", 1920, 1080, body, "Coding demo thumbnail", (1920,))

    body = backdrop(1920, 1080) + brand_heading(88, 143, 54)
    for word, y, color in (("A PATCH.", 372, WHITE), ("YOU CAN", 525, WHITE), ("VERIFY.", 678, ORANGE)):
        body += txt(word, 96, y, 132, color, 0)
    body += txt("Inspect. Approve. Run checks.", 101, 807, 32, "#CBD5E1", 0, 400)
    body += txt("Then choose what to keep.", 101, 858, 32, "#CBD5E1", 0, 400)
    body += '<rect x="960" y="255" width="840" height="512" rx="24" fill="#111C30" stroke="#334155"/>'
    body += txt("5 ORIGINAL CHECKS", 1008, 337, 32, MUTED, 2, 500)
    body += txt("PASS", 1002, 478, 130, "#22C55E", 3)
    body += asset_image("bifang-tests-passing.png", 1008, 543, 744, 165, "0 0 1960 385")
    body += txt("BUILD. RUN. VERIFY.", 100, 1000, 25, MUTED, 3, 500)
    write("thumbnails/youtube-reviewed-patch.svg", 1920, 1080, body, "Reviewed-patch thumbnail", (1920,))

    body = backdrop(1920, 1080, generated=True) + brand_heading(88, 143, 54)
    body += txt("CODE WITH", 100, 464, 106, WHITE, 1)
    body += txt("BIFANG.", 93, 621, 152, ORANGE, 4)
    body += txt("Build. Run. Verify.", 102, 734, 44, "#CBD5E1", 0, 500)
    body += txt("OPEN-SOURCE CODING WORKSPACE", 100, 1000, 24, MUTED, 3, 500)
    body += mark(1080, 210, 690)
    write("thumbnails/youtube-brand.svg", 1920, 1080, body, "Brand thumbnail", (1920,))

    for width, height, name in ((1200, 630, "social-preview"), (1584, 396, "profile-banner")):
        body = backdrop(width, height)
        if height > 400:
            body += brand_heading(58, 130, 62) + txt("Build. Run.", 64, 295, 68)
            body += txt("Verify.", 64, 377, 68, ORANGE)
            body += txt("A coding workspace that shows its work.", 67, 470, 25, "#CBD5E1", 0, 400)
            body += mark(750, 112, 410)
            body += txt("github.com/Protocol-X-01/Bifang", 67, 573, 22, MUTED, 1, 500)
        else:
            body += mark(105, 38, 320) + txt("BIFANG", 474, 185, 100, WHITE, 11)
            body += txt("BUILD. RUN. VERIFY.", 484, 254, 29, ORANGE, 4, 500)
        write(f"social/{name}.svg", width, height, body, name.replace("-", " ").title(), (width,))

    body = backdrop(1080, 1080) + brand_heading(64, 134, 54) + mark(284, 220, 512)
    body += centered("Build. Run.", 1080, 847, 92)
    body += centered("Verify.", 1080, 957, 92, ORANGE)
    write("social/square-post.svg", 1080, 1080, body, "Square social post", (1080,))

    body = backdrop(1080, 1920) + brand_heading(70, 155, 66) + mark(230, 340, 620)
    for word, y, color in (("BUILD.", 1155, WHITE), ("RUN.", 1300, WHITE), ("VERIFY.", 1445, ORANGE)):
        body += centered(word, 1080, y, 125, color, 2)
    body += centered("Desktop. Terminal. Companion.", 1080, 1625, 34, "#CBD5E1", 0, 400)
    body += centered("github.com/Protocol-X-01/Bifang", 1080, 1735, 23, MUTED, 0, 500)
    write("social/vertical-story.svg", 1080, 1920, body, "Vertical story / reel cover", (1080,))

    body = backdrop(2560, 1440) + mark(605, 548, 310)
    body += txt("BIFANG", 972, 716, 124, WHITE, 13)
    body += txt("BUILD. RUN. VERIFY.", 981, 799, 33, ORANGE, 5, 500)
    write("social/youtube-channel-banner.svg", 2560, 1440, body,
          "YouTube channel banner · centered logo safe area", (2560,))
    guides = (body + '<rect x="508" y="509" width="1544" height="422" fill="none" stroke="#F7F7F7" stroke-width="2" stroke-dasharray="12 8"/>'
              + txt("CENTERED LOGO / TEXT SAFE AREA — GUIDE ONLY", 525, 486, 24, WHITE, 1, 500))
    write("guide/youtube-banner-safe-area.svg", 2560, 1440, guides,
          "YouTube banner crop guide · not an upload asset", (1280,))


def overview():
    body = '<rect width="1800" height="2050" fill="#0A101C"/>'
    body += txt("BIFANG / BRAND PACK", 72, 116, 48, WHITE, 4)
    body += txt("Build. Run. Verify.", 74, 172, 27, MUTED, 1, 400)
    for index, (variant, bg) in enumerate((("ember-dark", SLATE), ("ember-light", WHITE), ("white", "#15213A"), ("black", "#E8EBF0"))):
        x = 72 + index * 420
        body += f'<rect x="{x}" y="234" width="396" height="388" rx="18" fill="{bg}"/>'
        body += mark(x + 66, 252, 264, variant)
        body += txt(variant.upper(), x + 30, 587, 18, SLATE if index in {1, 3} else WHITE, 2, 500)
    body += txt("VECTOR LOCKUPS / OUTLINED LETTERING", 74, 710, 22, MUTED, 2, 500)
    label, _ = lettering("BIFANG", 355, 880, 132, WHITE, 14)
    body += mark(82, 734, 250) + label + txt("BUILD. RUN. VERIFY.", 363, 944, 26, ORANGE, 4, 500)
    colors = [("DEEP SLATE", SLATE), ("CLOUD WHITE", WHITE), ("BIFANG RED", RED), ("FLAME ORANGE", ORANGE)]
    for index, (name, color) in enumerate(colors):
        x = 76 + index * 420
        body += f'<rect x="{x}" y="1040" width="360" height="100" rx="8" fill="{color}"/>'
        body += txt(name, x, 1186, 17, MUTED, 1, 500) + txt(color, x, 1225, 22, WHITE, 1, 500)
    body += txt("THUMBNAILS / READY TO USE + EDITABLE SVG", 74, 1333, 23, MUTED, 2, 500)
    for index, name in enumerate(("youtube-coding-demo-1920.png", "youtube-reviewed-patch-1920.png", "youtube-brand-1920.png")):
        path = ROOT / "thumbnails" / name
        data = base64.b64encode(path.read_bytes()).decode()
        x = 72 + index * 562
        body += f'<image x="{x}" y="1390" width="535" height="301" href="data:image/png;base64,{data}"/>'
    body += txt("SVG + PNG / TRANSPARENT + MONO / SOCIAL + VIDEO", 74, 1802, 27, WHITE, 1, 500)
    body += txt("Keep the mark consistent. Let the project speak.", 75, 1860, 28, MUTED, 0, 400)
    write("guide/brand-board.svg", 1800, 2050, body, "Bifang brand pack overview", (1800,))


def gallery():
    cards = []
    for r in RECORDS:
        if r["format"] != "SVG" or r["path"].startswith("guide/"): continue
        light = any(s in r["path"] for s in ("ember-light", "black", "cloud"))
        if r["path"].startswith("mobile/apple/"):
            kind = "apple"
        elif r["path"].startswith("mobile/android/"):
            kind = "android"
        elif r["path"].startswith("promos/mobile/"):
            kind = "mobile"
        elif r["path"].startswith(("social/", "thumbnails/")):
            kind = "promo"
        else:
            kind = "logos"
        cards.append(f'<article class="card" data-kind="{kind}"><div class="asset {"light" if light else ""}"><img src="{r["path"]}" alt="{html.escape(r["purpose"])}"></div><h3>{html.escape(r["purpose"])}</h3><p>{r["width"]} × {r["height"]} · editable SVG</p><a href="{r["path"]}" download>Download SVG</a></article>')
    font_data = base64.b64encode(FONT.read_bytes()).decode()
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bifang / Brand Pack</title>
<style>@font-face{{font-family:Space;src:url(data:font/ttf;base64,{font_data});font-weight:300 700}}*{{box-sizing:border-box}}body{{margin:0;background:#0A101C;color:#F7F7F7;font-family:Space,system-ui,sans-serif}}main{{max-width:1400px;margin:auto;padding:60px 28px}}.eyebrow{{letter-spacing:.2em;color:#FF8A3D;font-size:12px}}h1{{font-size:clamp(40px,7vw,86px);line-height:1.02;letter-spacing:-.04em;max-width:800px}}.intro{{font-size:20px;line-height:1.65;color:#B6C1D4;max-width:760px}}nav{{display:flex;gap:20px;flex-wrap:wrap;margin:32px 0 56px}}a{{color:#FFAD70}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px}}.card{{background:#101A2D;border:1px solid #253249;border-radius:16px;overflow:hidden;padding-bottom:24px}}.card h3,.card p,.card a{{margin-left:22px;margin-right:22px}}.card p{{color:#94A3B8;font-size:13px}}.asset{{height:240px;display:grid;place-items:center;background:#0F172A;padding:24px}}.asset.light{{background:#F7F7F7}}.asset img{{max-width:100%;max-height:100%;object-fit:contain}}.note{{border-top:1px solid #334155;padding-top:30px;margin-top:52px;color:#94A3B8;line-height:1.7}}</style>
<style>.filters{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:30px}}.filters button{{font:inherit;border:1px solid #334155;border-radius:99px;background:#101A2D;color:#CBD5E1;padding:10px 18px;cursor:pointer}}.filters button[aria-pressed="true"]{{background:#FF8A3D;color:#0F172A;border-color:#FF8A3D}}.card[hidden]{{display:none}}</style>
<main><p class="eyebrow">BIFANG / BRAND PACK / 2026.11</p><h1>Build. Run.<br><span style="color:#FF8A3D">Verify.</span></h1><p class="intro">The working identity, ready to use. Transparent logos, native app icons, phone and tablet covers, social artwork and thumbnails — all in the same ember-and-slate language.</p><nav><a href="guide/brand-board-1800.png">Brand board</a><a href="guide/mobile-brand-board-1800.png">Mobile + tablet board</a><a href="guide/USAGE.md">Usage guide</a><a href="guide/APPLE_ASSETS.md">iPhone + iPad icons</a><a href="guide/ANDROID_ASSETS.md">Android icons</a><a href="logos/png/">Transparent PNGs</a><a href="guide/PROJECT-HANDOFF-CHECKLIST.md">Reuse this checklist</a></nav><div class="filters" aria-label="Filter assets"><button data-filter="all" aria-pressed="true">All assets</button><button data-filter="logos" aria-pressed="false">Logos</button><button data-filter="apple" aria-pressed="false">iPhone + iPad</button><button data-filter="android" aria-pressed="false">Android</button><button data-filter="mobile" aria-pressed="false">Phone + tablet art</button><button data-filter="promo" aria-pressed="false">Social + video</button></div><section class="grid">{"".join(cards)}</section><p class="note">SVG lettering is converted to outlines, so logo files work without installed fonts. Editable sources, platform guides and the Space Grotesk font are included. Keep the single supporting leg visible; use the simplified favicon at tiny sizes.</p></main><script>document.querySelectorAll('.filters button').forEach(button=>button.addEventListener('click',()=>{{document.querySelectorAll('.filters button').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));document.querySelectorAll('.card').forEach(card=>card.hidden=button.dataset.filter!=='all'&&card.dataset.kind!==button.dataset.filter);}}));</script></html>'''
    (ROOT / "START-HERE.html").write_text(page)
    (ROOT / "ASSET-INDEX.json").write_text(json.dumps({"brand": "Bifang", "version": "2026-11-06", "assets": RECORDS}, indent=2) + "\n")


if __name__ == "__main__":
    core_logos()
    icons()
    promos()
    from build_mobile_apple import build_mobile_apple
    from build_mobile_android import build_mobile_android
    from build_mobile_promos import build_mobile_promos

    build_mobile_apple(sys.modules[__name__])
    build_mobile_android(sys.modules[__name__])
    build_mobile_promos(sys.modules[__name__])
    overview()
    gallery()
    print(json.dumps({"brand_pack": str(ROOT), "artwork_files": len(RECORDS), "outlined_lettering": True, "generated_background_used": (ROOT / 'backgrounds/ember-atmosphere.png').exists()}))
