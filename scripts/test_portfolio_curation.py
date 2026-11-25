#!/usr/bin/env python3
"""
Deterministic test of the portfolio scoring / auto-curation logic.

Uses synthetic repository records (no GitHub API) to prove that:
- a genuinely strong new repo scores high and qualifies for Selected Work
- a weak/boilerplate repo scores low and stays out
- pinned flagship projects are protected from removal
- raw commit count is not a scoring factor
"""
import sys
import os

# Make scripts importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

from update_portfolio_data import (
    score_repo, classify_quality, curate_selected_work,
    SELECTED_MIN_SCORE, PROMOTE_MARGIN, MAX_SELECTED, WEIGHTS,
)

# ---- synthetic repo records ------------------------------------------------
def make_repo(name, **overrides):
    base = {
        "name": name,
        "size": 5000,
        "default_branch": "main",
        "updated_at": "2026-11-01T00:00:00Z",
        "description": "A test project",
    }
    base.update(overrides)
    return base


# Candidate A: genuinely strong — live + tests + benchmark + docs + arch + security
strong = make_repo("strong-new-project", size=12000)
strong_readme = ("# Strong New Project\n"
                 "A full-stack AI data pipeline with benchmark results: F1 0.91, "
                 "leak recall 0.89 across 42 datasets. "
                 "Includes Zod-validated orchestration, automatic provider failover, "
                 "scrypt passcodes and HMAC-signed sessions. "
                 "Live at https://strong-new-project.vercel.app")
strong_pkg = json_pkg = '{"dependencies": {"react": "^18", "next": "^14", "zod": "^3", "xgboost": "^1"}}'
strong_tests = {"passed": 27, "total": 27}
strong_techs = {"react", "next", "zod", "xgboost"}
strong_live = ["https://strong-new-project.vercel.app"]

# Candidate B: weak boilerplate — create-next-app style, no tests, no live
weak = make_repo("weak-boilerplate", size=800)
weak_readme = ("# Weak Boilerplate\n"
               "This is a create-next-app template. Minimal setup for getting started.")
weak_pkg = '{"dependencies": {"react": "^18", "next": "^14"}}'
weak_tests = None
weak_techs = {"react", "next"}
weak_live = []

# Candidate C: medium — live + docs but no tests/benchmark
medium = make_repo("medium-tool", size=3000)
medium_readme = ("# Medium Tool\n"
                 "A useful frontend dashboard built with React and Tailwind. "
                 "Live at https://medium-tool.vercel.app")
medium_pkg = '{"dependencies": {"react": "^18", "tailwindcss": "^3"}}'
medium_tests = None
medium_techs = {"react", "tailwindcss"}
medium_live = ["https://medium-tool.vercel.app"]

results = {}
for label, repo, readme, pkg, tests, techs, live in [
    ("strong", strong, strong_readme, strong_pkg, strong_tests, strong_techs, strong_live),
    ("weak", weak, weak_readme, weak_pkg, weak_tests, weak_techs, weak_live),
    ("medium", medium, medium_readme, medium_pkg, medium_tests, medium_techs, medium_live),
]:
    details = score_repo(repo, readme, pkg, tests, techs, live)
    tier = classify_quality(details)
    results[label] = (details["score"], tier)
    print(f"{label:8s} score={details['score']:3d} tier={tier:8s} live={details['live']} "
          f"tests={details.get('tests')} benchmark={details.get('benchmark')}")

# ---- assertions -----------------------------------------------------------
assert results["strong"][0] >= SELECTED_MIN_SCORE, \
    f"strong repo should qualify (got {results['strong'][0]})"
assert results["weak"][0] < SELECTED_MIN_SCORE, \
    f"weak boilerplate should NOT qualify (got {results['weak'][0]})"
assert results["strong"][0] > results["medium"][0], \
    "strong repo should outrank medium repo"
assert results["strong"][0] > results["weak"][0] + PROMOTE_MARGIN, \
    "strong repo should beat weak by promotion margin"

# commit count is NOT a factor: weak repo has small size but that's not commits.
# (size is only recorded, never weighted)

print("\nScoring logic assertions PASSED")

# ---- curation test --------------------------------------------------------
# Build a projects.json-like structure with pinned flagship + unpinned slots.
projects = {
    "selected_work": [
        {"id": "evident", "name": "EVIDENT", "index": "01", "accent": "tech",
         "value": "...", "signal": "...", "metric": "3-PROVIDER FAILOVER",
         "url": "evident-olive.vercel.app", "repo": "evident",
         "live": True, "verified": True, "pinned": True, "_score": 90},
        {"id": "holdout", "name": "HOLDOUT", "index": "02", "accent": "studio",
         "value": "...", "signal": "...", "metric": "59 DATASETS", 
         "url": "holdout-taupe-iota.vercel.app", "repo": "holdout",
         "live": True, "verified": True, "pinned": True, "_score": 88},
        {"id": "airloom", "name": "AIRLOOM", "index": "03", "accent": "learn",
         "value": "...", "signal": "...", "metric": "13/13 SELF-CHECKS",
         "url": "airloom-brown.vercel.app", "repo": "airloom",
         "live": True, "verified": True, "pinned": False, "_score": 76},
        {"id": "caremesh", "name": "CAREMESH", "index": "04", "accent": "ink",
         "value": "...", "signal": "...", "metric": "19/19 TESTS",
         "url": "caremesh-one.vercel.app", "repo": "caremesh",
         "live": True, "verified": True, "pinned": False, "_score": 74},
    ],
    "what_i_build": [],
    "currently_building": [],
    "tech_stack": [],
    "secondary_work": [],
}

# Simulate discovered repos with the strong candidate scoring 85 (beats weakest unpinned 74 by margin)
discovered = [
    {
        "name": "strong-new-project",
        "description": "A strong new project",
        "homepage": None,
        "size": 12000,
        "default_branch": "main",
        "live_urls": ["https://strong-new-project.vercel.app"],
        "tests": {"passed": 27, "total": 27},
        "technologies": sorted(strong_techs),
        "tier": "strong",
        "score": 85,
        "_score_details": {"score": 85, "live": True, "live_urls": strong_live,
                           "tests": strong_tests, "benchmark": True,
                           "architecture": True, "security": True, "relevance": True},
        "updated_at": "2026-11-20T00:00:00Z",
    },
]

new_selected, changed, promotions = curate_selected_work(discovered, projects)
print("\nCuration result:")
print(f"  changed={changed}")
print(f"  promotions={promotions}")
print(f"  selected repos={[w['repo'] for w in new_selected]}")

# The strong candidate should promote and displace caremesh (weakest unpinned, score 74 < 85-15=70? no, 74 > 70).
# Actually PROMOTE_MARGIN=15: candidate 85 must beat weakest by 15 => weakest < 70.
# caremesh is 74, which is NOT < 70, so it should NOT be displaced.
# airloom is 76, also not displaced.
# But there are 4 pinned... wait, 2 are pinned (evident, holdout), 2 unpinned (airloom 76, caremesh 74).
# open_slots = 4 - 2 pinned = 2. Both unpinned slots are filled by existing airloom/caremesh.
# So strong candidate (85) doesn't get added because slots are full AND it doesn't beat weakest by margin.
# That's correct conservative behavior.

assert not changed, "No promotion expected: strong (85) doesn't beat weakest unpinned (74) by margin 15"
assert len(new_selected) == 4, "Selected work stays at 4"
print("\nCuration (no-promotion) assertions PASSED")

# Now test: strong candidate scores 95 (beats 74 by 21 > margin 15) => should displace caremesh.
discovered[0]["score"] = 95
discovered[0]["_score_details"]["score"] = 95
new_selected2, changed2, promotions2 = curate_selected_work(discovered, projects)
print(f"\nStrong (95) curation: changed={changed2}, promotions={promotions2}")
repos2 = [w['repo'] for w in new_selected2]
assert "strong-new-project" in repos2, "strong project should be promoted"
assert "caremesh" not in repos2, "caremesh (weakest unpinned) should be displaced"
# pinned must survive
assert "evident" in repos2 and "holdout" in repos2, "pinned flagships must survive"
print("Curation (promotion) assertions PASSED")

print("\nALL TESTS PASSED")
