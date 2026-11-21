"""
Build assets/portrait.svg: the terminal-window panel that sits on the right of the
hero card (same 840 x 880 frame as the reference design).

Two modes, picked from the source image itself:

  pixel  -- a flat, low-colour avatar (GitHub identicons and similar). The 5 x 5
            block grid is redrawn as crisp vector squares, so it stays sharp at any
            size and never resamples into mush.
  ascii  -- a photograph. It is converted with a character ramp and "typed" in,
            row by row (the reference behaviour).

Drop a photo in as assets/avatar.png (square, face centred) and re-run to get the
ASCII portrait; the frame, status line and timings stay identical.

    python scripts/make_portrait_svg.py [source.png] [out.svg]
"""
from PIL import Image, ImageEnhance
import collections
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "assets", "avatar.png")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "assets", "portrait.svg")

PAD = 20
TITLEBAR_H = 30
STATUS_H = 30
ART = 800                       # art area, square
CANVAS_W = ART + PAD * 2
CANVAS_H = TITLEBAR_H + ART + STATUS_H + PAD

BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
TITLE_TEXT = "#7d8590"
INK = "#c9d1d9"
NAME = "Swapneel Sethi"
HANDLE = "swapneel"

STATIC = bool(os.environ.get("STATIC"))

src = Image.open(SRC).convert("RGB")
W0, H0 = src.size


def flat_palette(im, limit=3):
    """Return the dominant colours if the image is essentially flat artwork."""
    small = im.resize((64, 64), Image.NEAREST)
    counts = collections.Counter(small.getdata())
    total = sum(counts.values())
    top = [c for c, n in counts.most_common(limit) if n / total > 0.02]
    # how much of the image is covered by those few colours?
    covered = sum(n for c, n in counts.items() if min(
        sum(abs(a - b) for a, b in zip(c, t)) for t in top) < 24) / total
    return top if len(top) <= 3 and covered > 0.985 else None


def pixel_art(im, colors):
    """Redraw a 5 x 5 identicon-style grid as vector squares, monochrome like the
    reference's character portrait: light marks on the dark panel."""
    bg = max(colors, key=lambda c: sum(c))                      # lightest = background
    ink = [c for c in colors if c != bg]
    style = os.environ.get("PORTRAIT_STYLE", "mono")
    fill = ("#%02x%02x%02x" % ink[0]) if (style == "avatar" and ink) else INK
    margin = round(W0 / 12)                                     # GitHub identicons: 1/12 border
    grid = 5
    cell = (W0 - 2 * margin) / grid
    px = im.load()

    # read the grid from cell centres so anti-aliased edges never matter
    cells = []
    for r in range(grid):
        for c in range(grid):
            x = int(margin + (c + 0.5) * cell)
            y = int(margin + (r + 0.5) * cell)
            sample = px[min(x, W0 - 1), min(y, H0 - 1)]
            if sum(abs(a - b) for a, b in zip(sample, bg)) > 90:
                cells.append((r, c))

    size = ART / grid
    glyph = size * grid - 32          # keep the marks off the window chrome
    step = glyph / grid
    offset = (ART - glyph) / 2
    art = []
    for i, (r, c) in enumerate(cells):
        klass = "" if STATIC else ' class="px"'
        art.append(
            f'<rect{klass} style="animation-delay:{0.35 + i * 0.06:.2f}s" '
            f'x="{offset + c * step:.2f}" y="{offset + r * step:.2f}" width="{step:.2f}" height="{step:.2f}" '
            f'fill="{fill}"/>'
        )
    css = (".px{opacity:0;transform-box:fill-box;transform-origin:center;"
           "animation:blockin .45s cubic-bezier(.2,.8,.2,1) both}"
           "@keyframes blockin{0%{opacity:0;transform:scale(.55)}100%{opacity:1;transform:none}}"
           "@media (prefers-reduced-motion: reduce){.px{animation:none!important;opacity:1!important;transform:none!important}}")
    return art, css


def ascii_art(im):
    """Character-ramp conversion, printed top to bottom like the reference."""
    COLS = int(os.environ.get("COLS", 160))
    RAMP = " .`:-=+*cs#%@"        # bright(sparse) -> dark(dense)
    WHITE_FLOOR = 0.80
    CELL_W = ART / COLS
    CELL_H = CELL_W * 15 / 8
    ROWS = max(1, round(COLS * (H0 / W0) * (CELL_W / CELL_H)))
    ART_H = ROWS * CELL_H

    g = im.convert("L")
    g = ImageEnhance.Brightness(g).enhance(1.0)
    g = ImageEnhance.Contrast(g).enhance(1.05)
    g = g.resize((COLS, ROWS), Image.LANCZOS)
    px = g.load()

    rows = []
    for y in range(ROWS):
        chars = []
        for x in range(COLS):
            lum = pow(px[x, y] / 255.0, 1.18)
            if lum >= WHITE_FLOOR:
                chars.append(" ")
                continue
            idx = max(0, min(len(RAMP) - 1, int((1.0 - lum) * (len(RAMP) - 1) + 0.5)))
            chars.append(RAMP[idx])
        rows.append("".join(chars))

    row_dur = 5.8 / ROWS
    font_size = CELL_H * 0.86
    top = (ART - ART_H) / 2
    art, css = [], ""
    for ry, line in enumerate(rows):
        y = top + ry * CELL_H + CELL_H * 0.74
        text = (f'<text xml:space="preserve" x="0" y="{y:.1f}" fill="{INK}" '
                f'font-size="{font_size:.2f}" textLength="{ART}" lengthAdjust="spacing">{html.escape(line)}</text>')
        if STATIC:
            art.append(text)
            continue
        row_y = top + ry * CELL_H
        art.append(
            f'<clipPath id="r{ry}"><rect x="0" y="{row_y:.2f}" height="{CELL_H:.2f}" width="0">'
            f'<animate attributeName="width" from="0" to="{ART}" begin="{ry * row_dur:.3f}s" '
            f'dur="{row_dur:.3f}s" fill="freeze"/></rect></clipPath>'
        )
        art.append(f'<g clip-path="url(#r{ry})">{text}</g>')
    return art, css


palette = flat_palette(src)
forced = os.environ.get("PORTRAIT_MODE", "").strip().lower()
if forced == "ascii" or (not forced and not palette):
    art, css = ascii_art(src)
    mode = "ascii"
else:
    art, css = pixel_art(src, palette)
    mode = "pixel"

art_top = TITLEBAR_H + (ART - int(ART)) / 2 + 0  # art area starts right under the chrome

parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
    f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" font-family="ui-monospace, SFMono-Regular, '
    f'Menlo, Consolas, monospace">',
    f'<style>{css}</style>',
    '<defs>'
    f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/>'
    '</linearGradient></defs>',
    f'<rect width="{CANVAS_W}" height="{CANVAS_H}" rx="12" fill="url(#bg)"/>',
    f'<rect x="0.5" y="0.5" width="{CANVAS_W-1}" height="{CANVAS_H-1}" rx="12" '
    f'fill="none" stroke="{FRAME}" stroke-width="1"/>',
    f'<line x1="0" y1="{TITLEBAR_H}" x2="{CANVAS_W}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>',
]
for i, dotcol in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
    parts.append(f'<circle cx="{PAD + i*16}" cy="{TITLEBAR_H/2}" r="5" fill="{dotcol}"/>')
parts.append(f'<text x="{CANVAS_W/2}" y="{TITLEBAR_H/2 + 4}" fill="{TITLE_TEXT}" font-size="12" '
             f'text-anchor="middle">{HANDLE}@github: ~$ ./portrait.sh</text>')

parts.append(f'<g transform="translate({PAD} {TITLEBAR_H})">{"".join(art)}</g>')

status_line_y = TITLEBAR_H + ART
status_y = status_line_y + 20
parts.append(f'<line x1="0" y1="{status_line_y}" x2="{CANVAS_W}" y2="{status_line_y}" stroke="{FRAME}"/>')
parts.append(f'<text x="{PAD}" y="{status_y}" fill="{TITLE_TEXT}" font-size="13">'
             f'{HANDLE}@github:~$ whoami <tspan fill="{INK}">{NAME}</tspan></text>')
status_chars = len(f"{HANDLE}@github:~$ whoami {NAME} ")
parts.append(f'<rect x="{PAD + status_chars * 13 * 0.6:.1f}" y="{status_y - 12}" width="8" height="14" fill="{INK}">'
             f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" '
             f'dur="1s" repeatCount="indefinite"/></rect>')
parts.append("</svg>")

svg = "".join(parts)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(svg)
print(f"wrote {OUT} ({len(svg)} bytes, {mode} mode, {CANVAS_W} x {CANVAS_H})")
