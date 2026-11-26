import json, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

root = Path(".")
readme = root.joinpath("README.md").read_text(encoding="utf-8")
cards_dir = root.joinpath("cards")

# ---- load data layer -------------------------------------------------------
projects = json.load(open(root.joinpath("data/projects.json"), encoding="utf-8"))
profile = json.load(open(root.joinpath("data/profile.json"), encoding="utf-8"))
state = json.load(open(root.joinpath("data/portfolio-state.json"), encoding="utf-8"))
selected_work = projects["selected_work"]

# 1. Every card referenced by README must exist.
referenced = sorted(set(re.findall(r'./cards/([^"\\\s]+\.svg)', readme)))
missing = [c for c in referenced if not cards_dir.joinpath(c).exists()]
if missing:
    print(f"MISSING referenced cards: {missing}")
    sys.exit(1)
print(f"referenced cards present: {len(referenced)}")

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

# 5. Selected Work consistency checks.
# 5a. README Selected Work section must reference exactly the selected_work repos.
readme_repos = set(re.findall(r'https://github.com/Swapneel-Sethi/([^/\s\)]+)', readme))
selected_repos = {w["repo"] for w in selected_work}
readme_selected_cards = set(re.findall(r'./cards/work-([a-z0-9-]+)\.svg', readme))
# work-card ids should match selected_work ids.
expected_work_cards = {w["id"] for w in selected_work}
if readme_selected_cards != expected_work_cards:
    print(f"SELECTED WORK CARD MISMATCH: readme={readme_selected_cards} data={expected_work_cards}")
    sys.exit(1)
print(f"selected work cards match data: {expected_work_cards}")

# 5b. Every selected project has a live URL and a matching card.
for w in selected_work:
    card_path = cards_dir.joinpath(f"work-{w['id']}.svg")
    if not card_path.exists():
        print(f"MISSING card for selected project {w['repo']}: {card_path}")
        sys.exit(1)
    if not w.get("url"):
        print(f"SELECTED PROJECT {w['repo']} has no live URL")
        sys.exit(1)
print(f"all {len(selected_work)} selected projects have cards and live URLs")

# 5d. Pinned status: README shows [PINNED] only for pinned projects.
pinned_names = {w["name"] for w in selected_work if w.get("pinned")}
unpinned_names = {w["name"] for w in selected_work if not w.get("pinned")}
for name in pinned_names:
    if f"{name} [PINNED]" not in readme:
        print(f"PINNED PROJECT {name} missing [PINNED] tag in README")
        sys.exit(1)
for name in unpinned_names:
    if f"{name} [PINNED]" in readme:
        print(f"UNPINNED PROJECT {name} incorrectly shows [PINNED] tag in README")
        sys.exit(1)
print(f"pinned status correct: pinned={pinned_names} unpinned={unpinned_names}")

# 5e. selected-work state contains real scores when discovery data available.
state_scores = state.get("selected_work_scores", {})
for w in selected_work:
    repo = w["repo"]
    if repo not in state_scores:
        print(f"SELECTED WORK {repo} missing from portfolio-state scores")
        sys.exit(1)
    score = state_scores[repo]
    if not isinstance(score, (int, float)) or score <= 0:
        print(f"SELECTED WORK {repo} has non-positive score {score}")
        sys.exit(1)
print(f"selected-work state has real scores: {state_scores}")

# 5c. README links section should contain all live links.
for l in profile.get("live_links", []):
    if l["url"] not in readme:
        print(f"LIVE LINK MISSING FROM README: {l['label']} -> {l['url']}")
        sys.exit(1)
print("all profile live links present in README")

# 6. No stale cards may be regenerated.
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
        if stripped.startswith("#"):
            continue
        if "stale" in stripped and ("={" in stripped or "in stale" in stripped):
            continue
        for term in stale_targets:
            if (f'write("{term}' in line or f"write('{term}" in line
                    or f'def {term}' in line or f'def {term}(' in line
                    or term == "fetch_contributions" and "fetch_contributions" in line):
                print(f"STALE GENERATION TARGET '{term}' found in {pf}: {stripped}")
                sys.exit(1)
print("no stale generation targets in active pipeline files")

print("\nALL VALIDATIONS PASSED")
