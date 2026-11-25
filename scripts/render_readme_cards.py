#!/usr/bin/env python3
"""
Render the profile README cards as SVGs into cards/.

Data-driven generator for the internship-focused profile architecture:

    HERO → WHAT I BUILD → SELECTED WORK → PROOF → HOW I BUILD
    → CURRENTLY BUILDING → TECH STACK → LINKS

Reads structured portfolio data from data/ and emits ONLY the SVG cards
referenced by README.md:

    cards/hero.svg
    cards/build-*.svg   (products / ai-data / systems)
    cards/proof.svg
    cards/work-*.svg    (evident / holdout / airloom / caremesh)
    cards/how.svg
    cards/building.svg
    cards/stack.svg

Design system: paper, ink, one accent per world (TECH blue, STUDIO red,
LEARN yellow); Instrument Serif display, Geist body, Geist Mono labels.
Fonts are subset WOFFs in fonts/ (SIL OFL).

No contribution-density graphics, no activity charts, no BUILD/BRAND/LEARN
tiles, no old repo cards. Simulated/demo projects are labelled honestly.
"""
import base64
import json
import os
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
OUT = os.environ.get("CARDS_OUT") or os.path.join(ROOT, "cards")
FONTS = os.path.join(ROOT, "fonts")
PORTRAIT = os.environ.get("PORTRAIT_PATH") or os.path.join(ROOT, "assets", "portrait.svg")

# ---- brand tokens -----------------------------------------------------------
PAPER = "#f3f3f1"
PAPER_DEEP = "#e2e2de"
INK = "#111111"
INK_SOFT = "#3a3a3c"
MUTED = "#6e6e73"
RULE = "#dcdcd7"
TECH = "#2f55ff"
STUDIO = "#ef3b2d"
LEARN = "#ffc81a"
W = 880  # full card width, GitHub's README column at 100%

ACCENT_MAP = {"tech": TECH, "studio": STUDIO, "learn": LEARN, "ink": INK}

SERIF = "'Instrument Serif', Georgia, serif"
SANS = "Geist, system-ui, -apple-system, sans-serif"
MONO = "'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

FONT_FILES = {
    "serif": ("Instrument Serif", "normal", 400, "serif-400.woff"),
    "serif-i": ("Instrument Serif", "italic", 400, "serif-italic.woff"),
    "sans": ("Geist", "normal", 400, "geist-400.woff"),
    "sans-b": ("Geist", "normal", 600, "geist-600.woff"),
    "mono": ("Geist Mono", "normal", 400, "geistmono-400.woff"),
}

BASE_CSS = """
@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes pop{0%{opacity:0;transform:scale(.3)}70%{opacity:1;transform:scale(1.15)}100%{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@keyframes nudge{0%,100%{transform:none}50%{transform:translateX(4px)}}
@keyframes nudgeup{0%,100%{transform:none}50%{transform:translate(3px,-3px)}}
@keyframes sheen{0%{transform:translateX(-260px) skewX(-20deg)}22%,100%{transform:translateX(980px) skewX(-20deg)}}
.r{opacity:0;animation:rise .8s cubic-bezier(.2,.7,.2,1) both;transform-box:fill-box}
.f{opacity:0;animation:fade .9s ease-out both}
.g{transform-box:fill-box;transform-origin:bottom;transform:scaleY(0);animation:grow .8s cubic-bezier(.2,.7,.2,1) both}
.p{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .4s ease-out both}
.live{animation:pulse 1.6s ease-in-out infinite}
.n{transform-box:fill-box;animation:nudge 1.8s ease-in-out infinite}
.nu{transform-box:fill-box;animation:nudgeup 1.8s ease-in-out infinite}
.sh{animation:sheen 6s ease-in-out infinite}
@media (prefers-reduced-motion: reduce){.r,.f,.g,.p,.live,.n,.nu{animation:none!important;opacity:1!important;transform:none!important}.sh{display:none}}
"""


def font_face(keys):
    out = []
    for k in keys:
        fam, style, weight, fn = FONT_FILES[k]
        b64 = base64.b64encode(open(os.path.join(FONTS, fn), "rb").read()).decode()
        out.append(
            f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{weight};"
            f"src:url(data:font/woff;base64,{b64}) format('woff')}}"
        )
    return "".join(out)


def svg(w, h, body, fonts, label, extra_css="", left=0, right=0, bottom=12):
    """Card of w x h drawn at x=left inside a transparent canvas, padded so rows tile exactly."""
    if left:
        body = f'<g transform="translate({left:.3f} 0)">{body}</g>'
    w, h = w + left + right, h + bottom
    css = font_face(fonts) + BASE_CSS + extra_css
    if os.environ.get("STATIC"):
        css += ".r,.f,.g,.p,.live,.n,.nu{animation:none!important;opacity:1!important;transform:none!important}.sh{display:none}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}" height="{h}" viewBox="0 0 {w:.3f} {h}" '
        f'role="img" aria-label="{escape(label)}"><title>{escape(label)}</title>'
        f"<style>{css}</style>{body}</svg>"
    )


def write(name, content):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"wrote cards/{name} ({len(content) // 1024} KB)")


def d(s):
    return f'style="animation-delay:{s:.2f}s"'


def wrap(text, n):
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > n:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line] if line else lines


def text_lines(x, y, lines, lh, attrs):
    return "".join(
        f'<text x="{x}" y="{y + i * lh}" {attrs}>{escape(l)}</text>' for i, l in enumerate(lines)
    )


# ---- load data --------------------------------------------------------------
def load_json(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


PROFILE = load_json("profile.json")
PROJECTS = load_json("projects.json")
STATE = load_json("portfolio-state.json")
TOKENS = PROFILE["design_tokens"]


# ---- 1 · hero ---------------------------------------------------------------
def hero():
    h = 420
    eyebrow = PROFILE["tagline"]
    tagline = PROFILE["headline"]
    link = PROFILE["url"]
    s = 0.41
    body = f"""
<defs>
  <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="600" y2="0">
    <stop offset="0" stop-color="{INK}"/><stop offset=".42" stop-color="{INK}"/>
    <stop offset=".5" stop-color="{TECH}"/><stop offset=".58" stop-color="{INK}"/>
    <stop offset="1" stop-color="{INK}"/>
    <animateTransform attributeName="gradientTransform" type="translate" values="-600 0;600 0;600 0"
      keyTimes="0;.45;1" dur="7s" begin="1.6s" repeatCount="indefinite"/>
  </linearGradient>
</defs>
<rect width="{W}" height="{h}" rx="14" fill="{PAPER}"/>
<g class="f" {d(0)}>
  <rect class="live" x="48" y="49" width="8" height="8" rx="2" fill="{TECH}"/>
  <text x="66" y="57" font-family="{MONO}" font-size="12" letter-spacing="1" fill="{MUTED}">{escape(eyebrow)}</text>
</g>
<text class="r" {d(0.15)} x="44" y="190" font-family="{SERIF}" font-size="116" letter-spacing="-2.5" fill="{INK}">{escape(PROFILE['name'].split()[0])}</text>
<text class="r" {d(0.3)} x="44" y="290" font-family="{SERIF}" font-style="italic" font-size="116" letter-spacing="-2.5" fill="url(#shine)">{escape(PROFILE['name'].split()[-1])}</text>
<g class="r" {d(0.55)}>
  {text_lines(48, 338, tagline, 27, f'font-family="{SANS}" font-size="18" fill="{INK_SOFT}"')}
</g>
<g class="f" {d(0.8)}>
  <text x="48" y="396" font-family="{MONO}" font-size="13" fill="{INK}">{escape(link)}</text>
  <text class="nu" x="{48 + len(link) * 8.1 + 6:.0f}" y="396" font-family="{MONO}" font-size="13" fill="{TECH}">&#8599;</text>
</g>
<g transform="translate(520 46) scale({s}) translate(-20 -37)">
  {open(PORTRAIT).read()}
</g>
"""
    write("hero.svg", svg(W, h, body, ["serif", "serif-i", "sans", "mono"],
                          f"{PROFILE['name']}. {PROFILE['role']}. {PROFILE['bio']}"))


# ---- 2 · what I build tiles -------------------------------------------------
TILE_W = W / 3 - 8
TILE_H = 264


def build_tiles():
    for i, tile in enumerate(PROJECTS["what_i_build"]):
        accent = ACCENT_MAP[tile["accent"]]
        body_lines = wrap(tile["body"], 33)
        tag_lines = wrap(tile["tag"], 38)
        headline = "".join(
            f'<text class="r" {d(0.42 + i * 0.08)} x="24" y="{132 + j * 25}" font-family="{SERIF}" '
            f'font-size="24" fill="{INK}">{escape(line)}</text>'
            for j, line in enumerate(tile["headline"])
        )
        body = f"""
<defs><clipPath id="card{i}"><rect width="{TILE_W}" height="{TILE_H}" rx="14"/></clipPath></defs>
<g class="f" {d(0.05)}><rect width="{TILE_W}" height="{TILE_H}" rx="14" fill="{PAPER}"/>
  <rect x="0" y="0" width="{TILE_W}" height="5" fill="{accent}"/></g>
<text class="f" {d(0.2)} x="24" y="40" font-family="{MONO}" font-size="11" letter-spacing="1.4" fill="{MUTED}">{escape(tile['label'])}</text>
<text class="r" {d(0.28)} x="22" y="100" font-family="{SERIF}" font-size="46" fill="{accent}">{escape(tile['num'])}</text>
<text class="f" {d(0.36)} x="{24 + len(tile['num']) * 25}" y="100" font-family="{SANS}" font-size="12" fill="{MUTED}">{escape(tile['unit'])}</text>
{headline}
{text_lines(24, 182, body_lines, 18, f'font-family="{SANS}" font-size="12.5" fill="{INK_SOFT}"')}
{text_lines(24, 240, tag_lines, 13, f'font-family="{MONO}" font-size="9.5" fill="{MUTED}"')}
"""
        left, right = (4 * i, 8 - 4 * i)
        write(f"build-{tile['id']}.svg", svg(TILE_W, TILE_H, body, ["serif", "sans", "mono"],
                                              f"{tile['label']}: {tile['num']} {tile['unit']}. {tile['headline'][0]} {tile['headline'][1]}. {tile['body']}",
                                              left=left, right=right))


# ---- 3 · selected work ------------------------------------------------------
WORK_W = W / 2 - 12
WORK_H = 322


def work_cards():
    for i, work in enumerate(PROJECTS["selected_work"]):
        accent = ACCENT_MAP[work["accent"]]
        value_lines = wrap(work["value"], 48)
        signal_lines = wrap(work["signal"], 56)
        body = f"""
<defs><clipPath id="work{i}"><rect width="{WORK_W}" height="{WORK_H}" rx="14"/></clipPath></defs>
<g clip-path="url(#work{i})">
  <rect width="{WORK_W}" height="{WORK_H}" fill="{PAPER}"/>
  <rect x="0" y="0" width="6" height="{WORK_H}" fill="{accent}"/>
</g>
<g class="f" {d(0.05)}>
  <text x="28" y="38" font-family="{MONO}" font-size="11" letter-spacing="1.2" fill="{MUTED}">{work['index']} / {escape(work['name'])}</text>
  <circle class="live" cx="{WORK_W - 62}" cy="34" r="4" fill="{accent}"/>
  <text x="{WORK_W - 52}" y="38" font-family="{MONO}" font-size="10" letter-spacing="1.2" fill="{MUTED}">LIVE</text>
</g>
<text class="r" {d(0.18)} x="26" y="84" font-family="{SERIF}" font-size="38" letter-spacing="-0.5" fill="{INK}">{escape(work['name'])}</text>
{text_lines(28, 116, value_lines, 19, f'font-family="{SANS}" font-size="13.5" fill="{INK_SOFT}"')}
<rect class="f" {d(0.4)} x="28" y="182" width="{WORK_W - 56}" height="1" fill="{RULE}"/>
<text class="f" {d(0.46)} x="28" y="206" font-family="{MONO}" font-size="9.5" letter-spacing="1.3" fill="{MUTED}">STRONGEST SIGNAL</text>
{text_lines(28, 228, signal_lines, 17, f'font-family="{SANS}" font-size="12" fill="{INK}"')}
<text class="r" {d(0.58)} x="26" y="292" font-family="{MONO}" font-size="10" letter-spacing="0.8" fill="{accent}">{escape(work['metric'])}</text>
<text class="f" {d(0.64)} x="28" y="312" font-family="{MONO}" font-size="9" fill="{MUTED}">{escape(work['url'])}</text>
"""
        left, right = (0, 12) if i % 2 == 0 else (12, 0)
        write(f"work-{work['id']}.svg", svg(WORK_W, WORK_H, body, ["serif", "sans", "mono"],
                                            f"{work['name']}: {work['value']} Strongest signal: {work['signal']} {work['metric']}.",
                                            left=left, right=right))


# ---- 4 · proof strip --------------------------------------------------------
def proof():
    h = 190
    x0, step = 42, 165
    cols = []
    for i, sig in enumerate(STATE["proof_signals"]):
        x = x0 + i * step
        lines = wrap(sig["text"], 22)
        cols.append(
            f'<g class="r" {d(0.2 + i * 0.08)}>'
            f'<text x="{x}" y="100" font-family="{SERIF}" font-size="34" fill="{INK}">{escape(sig["label"])}</text>'
            f'{text_lines(x, 122, lines, 14, f"font-family=\"{SANS}\" font-size=\"11\" fill=\"{MUTED}\"")}'
            f'<text x="{x}" y="158" font-family="{MONO}" font-size="9" letter-spacing="1" fill="{MUTED}">{sig["source"]}</text>'
            f'</g>'
        )
        if i < len(STATE["proof_signals"]) - 1:
            cols.append(f'<rect class="f" {d(0.2)} x="{x + step - 18}" y="62" width="1" height="96" fill="{RULE}"/>')
    body = f"""
<rect width="{W}" height="{h}" rx="14" fill="{PAPER}"/>
<text class="f" {d(0.05)} x="42" y="38" font-family="{MONO}" font-size="11" letter-spacing="1.4" fill="{MUTED}">PROOF, NOT CLAIMS</text>
<text class="f" {d(0.05)} x="{W - 42}" y="38" text-anchor="end" font-family="{MONO}" font-size="9.5" letter-spacing="1" fill="{MUTED}">VERIFIED FROM REPO ARTIFACTS</text>
<rect class="f" {d(0.1)} x="42" y="52" width="{W - 84}" height="1" fill="{RULE}"/>
{''.join(cols)}
"""
    write("proof.svg", svg(W, h, body, ["serif", "sans", "mono"],
                           "Proof: verified portfolio signals derived from repository artifacts."))


# ---- 5 · how I build --------------------------------------------------------
def how():
    h = 246
    STEPS = [
        ("01", "Understand", ["Start with the failure", "mode, not the framework."], "HOLDOUT: LEAKAGE FIRST"),
        ("02", "Design", ["Choose the smallest", "system that survives."], "CAREMESH: NODE, NO UI FRAMEWORK"),
        ("03", "Build", ["Put the model behind", "an interface with a fallback."], "AIRLOOM: RULE FALLBACK"),
        ("04", "Verify", ["Run the suite and", "publish the misses."], "19/19 · 13/13"),
        ("05", "Ship", ["Deploy the real path,", "then link it."], "6 LIVE PRODUCTS"),
    ]
    x0, step = 40, 162
    cols = []
    for i, (num, title, lines, evidence) in enumerate(STEPS):
        x = x0 + i * step
        cols.append(
            f'<g class="r" {d(0.2 + i * 0.09)}>'
            f'<text x="{x}" y="82" font-family="{SERIF}" font-size="30" fill="{TECH if i == 0 else INK}">{num}</text>'
            f'<text x="{x}" y="110" font-family="{SANS}" font-weight="600" font-size="13" fill="{INK}">{escape(title)}</text>'
            f'{text_lines(x, 132, lines, 16, f"font-family=\"{SANS}\" font-size=\"11.5\" fill=\"{INK_SOFT}\"")}'
            f'<text x="{x}" y="214" font-family="{MONO}" font-size="8.5" letter-spacing="0.6" fill="{MUTED}">{escape(evidence)}</text>'
            f'</g>'
        )
    body = f"""
<rect width="{W}" height="{h}" rx="14" fill="{PAPER}"/>
<text class="f" {d(0.05)} x="40" y="38" font-family="{MONO}" font-size="11" letter-spacing="1.4" fill="{MUTED}">HOW I BUILD</text>
<text class="r" {d(0.1)} x="40" y="62" font-family="{SERIF}" font-size="21" font-style="italic" fill="{INK_SOFT}">Five steps, tied to the repos.</text>
<rect class="f" {d(0.1)} x="40" y="72" width="{W - 80}" height="1" fill="{RULE}"/>
{''.join(cols)}
"""
    write("how.svg", svg(W, h, body, ["serif", "serif-i", "sans", "sans-b", "mono"],
                         "How I build: understand, design, build, verify, ship."))


# ---- 6 · currently building -------------------------------------------------
def building():
    h = 236
    rows = []
    for i, item in enumerate(PROJECTS["currently_building"]):
        color = ACCENT_MAP[item["status_accent"]]
        y = 96 + i * 46
        rows.append(
            f'<g class="r" {d(0.2 + i * 0.1)}>'
            f'<rect x="40" y="{y - 12}" width="6" height="6" rx="1.5" fill="{color}"/>'
            f'<text x="56" y="{y - 4}" font-family="{SANS}" font-weight="600" font-size="12.5" fill="{INK}">{escape(item["name"])}</text>'
            f'<text x="228" y="{y - 4}" font-family="{MONO}" font-size="9" letter-spacing="1" fill="{MUTED}">{escape(item["status"])}</text>'
            f'<text x="330" y="{y - 4}" font-family="{SANS}" font-size="11.5" fill="{INK_SOFT}">{escape(item["description"])}</text>'
            f'</g>'
        )
    body = f"""
<rect width="{W}" height="{h}" rx="14" fill="{PAPER}"/>
<text class="f" {d(0.05)} x="40" y="38" font-family="{MONO}" font-size="11" letter-spacing="1.4" fill="{MUTED}">CURRENTLY BUILDING</text>
<text class="r" {d(0.1)} x="40" y="66" font-family="{SERIF}" font-size="24" fill="{INK}">Shipped, then pushed <tspan font-style="italic">further.</tspan></text>
<rect class="f" {d(0.1)} x="40" y="78" width="{W - 80}" height="1" fill="{RULE}"/>
{''.join(rows)}
<text class="f" {d(0.5)} x="40" y="222" font-family="{MONO}" font-size="8.5" letter-spacing="0.6" fill="{MUTED}">STATUSES DESCRIBE THE REPOSITORY, NOT A ROADMAP PROMISE.</text>
"""
    write("building.svg", svg(W, h, body, ["serif", "serif-i", "sans", "sans-b", "mono"],
                             "Currently building: MuleGuard demo live, AERASCAN simulated, The Honest Planner built."))


# ---- 7 · tech stack ---------------------------------------------------------
def stack():
    h = 244
    x0, step = 40, 162
    cols = []
    for i, group in enumerate(PROJECTS["tech_stack"]):
        accent = ACCENT_MAP[group["accent"]]
        x = x0 + i * step
        lines = "".join(
            f'<text x="{x}" y="{94 + j * 20}" font-family="{SANS}" font-size="11.5" fill="{INK_SOFT}">{escape(item)}</text>'
            for j, item in enumerate(group["items"])
        )
        cols.append(
            f'<g class="f" {d(0.15 + i * 0.08)}>'
            f'<text x="{x}" y="64" font-family="{MONO}" font-size="9.5" letter-spacing="1.1" fill="{MUTED}">{escape(group["group"])}</text>'
            f'<rect x="{x}" y="74" width="30" height="2" fill="{accent}"/>'
            f'{lines}</g>'
        )
    body = f"""
<rect width="{W}" height="{h}" rx="14" fill="{PAPER}"/>
<text class="f" {d(0.05)} x="40" y="36" font-family="{MONO}" font-size="11" letter-spacing="1.4" fill="{MUTED}">TECH STACK</text>
{''.join(cols)}
<text class="f" {d(0.55)} x="40" y="226" font-family="{MONO}" font-size="8.5" letter-spacing="0.6" fill="{MUTED}">GROUPED BY WHAT IT DOES, NOT BY HOW MANY BADGES FIT.</text>
"""
    write("stack.svg", svg(W, h, body, ["sans", "mono"],
                           "Tech stack: grouped by what it does, not by how many badges fit."))


def readme_selected_section():
    """Render the Selected Work section of README.md from data/projects.json."""
    works = PROJECTS["selected_work"]
    lines = ["Selected work\n---"]
    for i, w in enumerate(works):
        pinned_tag = " [PINNED]" if w.get("pinned") else ""
        lines.append("")
        lines.append(f"**{w['index']} · {w['name']}{pinned_tag}** — "
                     f"[{w['url']}](https://{w['url']}) · [repo](https://github.com/Swapneel-Sethi/{w['repo']})")
        lines.append(w["value"])
        lines.append(f"Strongest signal: {w['signal'].rstrip('.')}.")
        lines.append(f"**{w['metric']}** — {'live' if w.get('live') else 'repo'}.")
    lines.append("")
    lines.append("Pinned projects are flagship work protected from automatic removal.")
    lines.append("Unpinned projects compete for the remaining Selected Work slots.")
    return "\n".join(lines)


def render_readme():
    """Generate README.md from the data layer (human summary + data-driven sections)."""
    profile = PROFILE
    projects = PROJECTS
    state = STATE

    live_links = profile.get("live_links", [])
    links_md = " &nbsp;/&nbsp; ".join(
        f"[{l['label']}]({l['url']})" for l in live_links
    )

    what_i_build = projects["what_i_build"]
    selected_work = projects["selected_work"]

    # ---- image block (all cards generated from data) -----------------------
    image_lines = [
        '<div align="center">',
        f'<a href="{profile["profile_url"]}"><img src="./cards/hero.svg" width="100%" alt="{escape(profile["bio"])}" /></a>',
        '<div style="display:flex;flex-wrap:wrap;justify-content:center;gap:12px;margin-top:12px">',
    ]
    for t in what_i_build:
        image_lines.append(
            f'<a href="https://github.com/Swapneel-Sethi/{t["repos"][0] if t["repos"] else t["id"]}">'
            f'<img src="./cards/build-{t["id"]}.svg" width="293.333" alt="{escape(t["label"])}: {t["num"]} {t["unit"]} — {t["body"]}" /></a>'
        )
    image_lines.append('</div>')
    image_lines.append(f'<img src="./cards/proof.svg" width="100%" alt="Proof: verified portfolio signals derived from repository artifacts" />')

    # work cards: two per row
    for i in range(0, len(selected_work), 2):
        row = selected_work[i:i + 2]
        row_tags = []
        for w in row:
            row_tags.append(
                f'<a href="https://github.com/Swapneel-Sethi/{w["repo"]}">'
                f'<img src="./cards/work-{w["id"]}.svg" width="440" alt="{escape(w["name"])} — Live: {w["url"]}" /></a>'
            )
        image_lines.append("".join(row_tags))

    image_lines += [
        f'<img src="./cards/how.svg" width="100%" alt="How I build: five steps tied to the repos" />',
        f'<img src="./cards/building.svg" width="100%" alt="Currently building: shipped, then pushed further" />',
        f'<img src="./cards/stack.svg" width="100%" alt="Tech stack grouped by what it does" />',
        '</div>',
    ]

    # ---- human-written summary (data-driven content) -----------------------
    build_blocks = []
    for t in what_i_build:
        build_blocks.append(
            f"**{t['label']}** — {t['num']} {t['unit']}\n"
            f"{t['tag']} — {t['body']}"
        )

    proof_lines = ["Proof, not claims\n---",
                   "",
                   "Every metric below is verified against repository artifacts:"]
    for sig in state["proof_signals"]:
        proof_lines.append(
            f"- **{sig['source']}** — {sig['label']} {sig['text']}."
        )
    proof_lines.append("")
    proof_lines.append("No expert, elite, visionary or world-class language. "
                       "These are implementation facts from the repos.")

    currently = projects["currently_building"]
    building_lines = ["Currently building\n---"]
    for item in currently:
        building_lines.append(
            f"- **{item['name']}** — {item['status']}. {item['description']}"
        )

    stack_lines = ["Tech stack\n---"]
    for group in projects["tech_stack"]:
        stack_lines.append(
            f"- **{group['group']}** — {', '.join(group['items'])}"
        )

    links_lines = ["Links\n---",
                   f"- **GitHub** — github.com/Swapneel-Sethi",
                   f"- **Live work** — {links_md}"]

    parts = [
        f"# {profile['name']}",
        "",
        f"{profile['role']} — {profile['bio']}",
        "",
        "\n".join(image_lines),
        "",
        "## What I build",
        "",
        "\n\n".join(build_blocks),
        "",
        readme_selected_section(),
        "",
        "\n".join(proof_lines),
        "",
        "\n".join(building_lines),
        "",
        "\n".join(stack_lines),
        "",
        "\n".join(links_lines),
        "",
    ]
    readme_path = os.path.join(ROOT, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    with open(readme_path, encoding="utf-8") as f:
        content = f.read()
    print(f"wrote README.md ({len(content) // 1024} KB)")


if __name__ == "__main__":
    hero()
    build_tiles()
    work_cards()
    proof()
    how()
    building()
    stack()
    render_readme()
