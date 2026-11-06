"""Brand-only mobile artwork; call after the Apple and Android generators.

Uses the pack's unchanged mark, local outlined type and native SVG/PNG exporter.
These covers and icon previews are artwork, not screens or platform-support proof.
"""
from __future__ import annotations

import base64
import math


def build_mobile_promos(b):
    """Append four covers, three family lockups and one portable mobile board."""
    slate, white, orange = b.SLATE, b.WHITE, b.ORANGE

    def rule(x1, y, x2, opacity=.16):
        return f'<path d="M{x1} {y}H{x2}" stroke="{white}" stroke-opacity="{opacity}"/>'

    def eyebrow(value, x, y, size=22):
        return b.txt(value, x, y, size, orange, size * .13, 500)

    def cover(w, h, number):
        margin = w * .10
        landscape, tablet = w > h, w / h > .65
        body = b.backdrop(w, h) + f'<rect width="{w}" height="{h}" fill="{slate}" opacity=".35"/>'
        body += b.brand_heading(margin, h * .105, min(w * .048, 100))
        body += rule(margin, h * .17, w - margin)
        body += eyebrow("THE BIFANG FAMILY", margin, h * .208, w * .018)
        body += b.txt(number, w - margin - w * .037, h * .208, w * .019, white, 1, 500)
        if landscape:
            size = w * .39
            body += b.mark(w - margin - size, h * .285, size)
            for word, y, ink in (("BUILD.", .46, white), ("RUN.", .59, white), ("VERIFY.", .72, orange)):
                body += b.txt(word, margin, h * y, w * .080, ink, w * .0015)
            body += f'<path d="M{w * .48} {h * .33}V{h * .79}" stroke="{white}" stroke-opacity=".10"/>'
        elif tablet:
            size = w * .62
            body += b.mark((w - size) / 2, h * .215, size)
            body += b.centered("Build. Run.", w, h * .78, w * .087, white, 1)
            body += b.centered("Verify.", w, h * .866, w * .10, orange, 1)
        else:
            size = w * .78
            body += b.mark((w - size) / 2, h * .245, size)
            for word, y, ink in (("BUILD.", .735, white), ("RUN.", .80, white), ("VERIFY.", .865, orange)):
                body += b.txt(word, margin, h * y, w * .135, ink, w * .002)
        body += rule(margin, h * .902, w - margin)
        body += b.centered("COMPANION / TERMINAL / IDE", w, h * .938, w * .020, white, w * .0016, 500)
        return body

    covers = []
    specs = ((1290, 2796, "phone-portrait", "PHONE PORTRAIT"),
             (1080, 2400, "android-phone", "ANDROID PHONE"),
             (2048, 2732, "tablet-portrait", "TABLET PORTRAIT"),
             (2732, 2048, "tablet-landscape", "TABLET LANDSCAPE"))
    for index, (w, h, name, label) in enumerate(specs, 1):
        path = f"promos/mobile/bifang-{name}-{w}x{h}.svg"
        body = cover(w, h, f"0{index}")
        b.write(path, w, h, body, f"Bifang {label.lower()} brand cover; promotional artwork only", (w,))
        covers.append((path[:-4] + f"-{w}.png", w, h, body, label))

    lockups = []
    for family in ("Companion", "Terminal", "IDE"):
        word, advance = b.lettering("BIFANG", 310, 142, 98, white, 8)
        family_x = 310 + advance + 100
        label, family_width = b.lettering(family, family_x, 142, 55, white, 0, 500)
        width = math.ceil(family_x + family_width + 64)
        body = b.mark(14, 10, 248) + word + label
        body += f'<path d="M{family_x - 50} 86V151" stroke="{orange}" stroke-width="2"/>'
        body += b.txt("BUILD. RUN. VERIFY.", 316, 210, 24, orange, 3, 500)
        stem = f"bifang-family-{family.lower()}-horizontal"
        b.write(f"logos/svg/{stem}.svg", width, 280, body,
                f"Bifang {family} family lockup; outlined lettering", (2400,))
        lockups.append((f"logos/png/{stem}-2400.png", width, 280, body))

    def picture(relative, x, y, w, h, fallback, view_w, view_h):
        path = (b.ROOT / relative).resolve() if relative else None
        if path and path.is_relative_to(b.ROOT.resolve()) and path.is_file():
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            return (f'<image x="{x}" y="{y}" width="{w}" height="{h}" '
                    f'preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{data}"/>')
        return (f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 {view_w} {view_h}" '
                f'preserveAspectRatio="xMidYMid meet" overflow="hidden">{fallback}</svg>')

    def native_icon(words):
        preferred = "mobile/apple/masters/bifang-ios-any-1024.png" if "apple" in words else "mobile/android/bifang-google-play-512.png"
        if (b.ROOT / preferred).is_file():
            return preferred
        choices = []
        for record in b.RECORDS:
            path = record.get("path", "")
            if (record.get("format") == "PNG" and record.get("width") == record.get("height")
                    and any(word in path.lower() for word in words)
                    and not any(word in path.lower() for word in ("foreground", "background", "monochrome", "guide", "safe-area", "mask-preview", "tinted"))
                    and path.endswith(".png") and (b.ROOT / path).is_file()):
                choices.append(record)
        return max(choices, key=lambda r: (r["width"], r["path"]))["path"] if choices else None

    board = b.backdrop(1800, 2220)
    board += b.txt("BIFANG / MOBILE ART", 92, 132, 54, white, 3)
    board += b.txt("The same bird. A wider canvas.", 95, 192, 28, white, 0, 400)
    board += rule(92, 242, 1708)
    board += eyebrow("01 / APP ICONS", 94, 304, 20)
    tiles = ((92, "APPLE", native_icon(("apple", "ios", "ipad")), "ember-light"),
             (650, "ANDROID", native_icon(("android",)), "ember-dark"),
             (1208, "ORIGINAL", None, "ember-dark"))
    for x, label, image, variant in tiles:
        board += f'<rect x="{x}" y="346" width="500" height="294" rx="18" fill="{slate}" stroke="{white}" stroke-opacity=".13"/>'
        bg = white if variant == "ember-light" else slate
        fallback = f'<rect width="1024" height="1024" rx="210" fill="{bg}"/>' + b.mark(72, 62, 880, variant)
        if label == "ORIGINAL":
            fallback = b.mark(72, 62, 880)
        board += picture(image, x + 20, 376, 224, 224, fallback, 1024, 1024)
        board += b.txt(label, x + 267, 447, 24, white, 2)
        board += b.txt("ONE BIRD / ONE LEG" if label == "ORIGINAL" else "APP ICON", x + 267, 486, 14, orange, 1, 500)
        board += b.txt("UNCHANGED MARK" if label == "ORIGINAL" else
                       ("LOCAL EXPORT" if image else "VECTOR PREVIEW"), x + 267, 544, 14, white, 1, 500)
    board += eyebrow("02 / APP-FAMILY LOCKUPS", 94, 724, 20)
    for x, (path, w, h, body) in zip((92, 650, 1208), lockups):
        board += picture(path, x, 765, 500, 120, body, w, h)
    board += rule(92, 929, 1708)
    board += eyebrow("03 / PORTRAIT TO LANDSCAPE", 94, 994, 20)
    for x, preview_w, (path, w, h, body, label) in zip((92, 425, 770, 1190), (285, 285, 360, 518), covers):
        preview_h = preview_w * h / w
        board += picture(path, x, 1046, preview_w, preview_h, body, w, h)
        board += b.txt(label, x, 1084 + preview_h, 16, white, 1, 500)
        board += b.txt(f"{w} x {h}", x, 1116 + preview_h, 16, orange, 1, 500)
    board += rule(92, 1830, 1708)
    board += eyebrow("04 / COMPOSITION NOTES", 94, 1895, 20)
    board += b.txt("Give the mark room to breathe.", 94, 1960, 30, white, 0, 500)
    board += b.txt("Keep essential copy within the generous inset.", 94, 2010, 22, white, 0, 400)
    board += b.txt("Consistent type. Distinctive silhouettes.", 94, 2050, 22, white, 0, 400)
    board += b.txt("PHONE / TABLET / BOTH ORIENTATIONS", 1000, 1958, 20, orange, 1.5, 500)
    board += b.txt("Ready for your next announcement.", 1000, 2005, 21, white, 0, 400)
    board += b.txt("SPACE GROTESK OUTLINES / ORIGINAL SYMBOL GEOMETRY", 94, 2150, 17, white, 1, 500)
    for index, color in enumerate((slate, white, b.RED, orange)):
        board += f'<rect x="{1508 + index * 50}" y="2125" width="36" height="36" rx="5" fill="{color}" stroke="{white}" stroke-opacity=".2"/>'
    b.write("guide/mobile-brand-board.svg", 1800, 2220, board,
            "Bifang phone and tablet asset overview", (1800,))
