import json, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

root = Path(".")
readme = root.joinpath("README.md").read_text(encoding="utf-8")
cards_dir = root.joinpath("cards")

# 1. Every card referenced by README must exist.
referenced = sorted(set(re.findall(r'./cards/([^"\\\s]+\.svg)', readme)))
missing = [c for c in referenced if not cards_dir.joinpath(c).exists()]
if missing:
    print(f"MISSING referenced cards: {missing}")
    sys.exit(1)
print(f"referenced cards present: {len(referenced)} -> {referenced}")

# 2. Each SVG must be well-formed XML.
svgs = list(cards_dir.glob("*.svg"))
for svg in svgs:
    try:
        ET.parse(svg)
    except ET.ParseError as e:
        print(f"INVALID SVG {svg.name}: {e}")
        sys.exit(1)
print(f"valid SVGs: {len(svgs)}")

# 3. No stale cards may be present.
stale = {"heatmap.svg", "activity.svg", "build.svg", "brand.svg", "learn.svg",
         "repo-caremesh.svg", "repo-mule-detection.svg", "repo-plagiarism-checker.svg",
         "title-coding-dark.svg", "title-coding-light.svg"}
present_stale = [c for c in stale if cards_dir.joinpath(c).exists()]
if present_stale:
    print(f"STALE cards still present: {present_stale}")
    sys.exit(1)
print("no stale cards present")

# 4. Data layer files must exist.
for f in ["data/profile.json", "data/projects.json", "data/portfolio-state.json"]:
    if not root.joinpath(f).exists():
        print(f"MISSING data file: {f}")
        sys.exit(1)
print("data layer complete")

# 5. Confirm no stale GENERATION targets in active pipeline files.
#    Exclusion-set mentions are fine; write()/def targets for stale cards are not.
stale_targets = ["heatmap", "activity", "build.svg", "brand.svg", "learn.svg",
                 "repo-caremesh", "repo-mule-detection", "repo-plagiarism-checker",
                 "title-coding", "fetch_contributions"]
pipeline_files = ["README.md", "scripts/render_readme_cards.py",
                  "scripts/update_portfolio_data.py",
                  ".github/workflows/update-portfolio.yml"]
for pf in pipeline_files:
    content = root.joinpath(pf).read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        stripped = line.strip()
        # skip comment lines and exclusion-set lines that merely name stale cards
        if stripped.startswith("#"):
            continue
        if "stale" in stripped and ("={" in stripped or "in stale" in stripped):
            continue
        for term in stale_targets:
            # flag only genuine generation/write/def targets
            if (f'write("{term}' in line or f"write('{term}" in line
                    or f'def {term}' in line or f'def {term}(' in line
                    or term == "fetch_contributions" and "fetch_contributions" in line):
                print(f"STALE GENERATION TARGET '{term}' found in {pf}: {stripped}")
                sys.exit(1)
print("no stale generation targets in active pipeline files")

print("\nALL VALIDATIONS PASSED")
