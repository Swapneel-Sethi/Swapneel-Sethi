#!/usr/bin/env python3
"""
Deterministic tests for the Selected Work auto-curation logic.

Uses synthetic repository records (no GitHub API) to prove the curation
policy without touching the live portfolio:

  Test 1 - Pinned projects (EVIDENT, HOLDOUT) survive any candidate.
  Test 2 - Unpinned projects can be displaced by a genuinely stronger repo.
  Test 3 - Promotion margin (15) is enforced; 10-15 above does not displace.
  Test 4 - Missing stored _score does not become a false zero when discovery
           data provides the real score.
  Test 5 - Weak boilerplate repos (score < 75, no live) stay excluded.
  Test 6 - Pinned projects carry real discovery scores and stay protected.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

from update_portfolio_data import (
    score_repo, classify_quality, curate_selected_work,
    SELECTED_MIN_SCORE, PROMOTE_MARGIN, MAX_SELECTED,
)

PASS = 0
FAIL = 0


def check(condition, message):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {message}")
    else:
        FAIL += 1
        print(f"  FAIL: {message}")


# ---- helpers ----------------------------------------------------------------
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


def make_discovered(name, score, live=True, tests=None):
    """Build a discovered repo record with _score_details like the pipeline."""
    return {
        "name": name,
        "description": f"{name} description",
        "homepage": None,
        "size": 5000,
        "default_branch": "main",
        "live_urls": ["https://example.vercel.app"] if live else [],
        "tests": tests,
        "technologies": ["react", "next"],
        "tier": "strong" if score >= 80 else "moderate",
        "score": score,
        "_score_details": {"score": score, "live": live, "tests": tests},
        "updated_at": "2026-11-01T00:00:00Z",
    }


def base_projects():
    """Four selected projects matching the intended live state."""
    return {
        "selected_work": [
            {"id": "evident", "name": "EVIDENT", "index": "01", "accent": "tech",
             "value": "...", "signal": "...", "metric": "3-PROVIDER FAILOVER",
             "url": "evident-olive.vercel.app", "repo": "evident",
             "live": True, "verified": True, "pinned": True, "_score": 83},
            {"id": "holdout", "name": "HOLDOUT", "index": "02", "accent": "studio",
             "value": "...", "signal": "...", "metric": "59 DATASETS",
             "url": "holdout-taupe-iota.vercel.app", "repo": "holdout",
             "live": True, "verified": True, "pinned": True, "_score": 78},
            {"id": "airloom", "name": "AIRLOOM", "index": "03", "accent": "learn",
             "value": "...", "signal": "...", "metric": "13/13 SELF-CHECKS",
             "url": "airloom-brown.vercel.app", "repo": "airloom",
             "live": True, "verified": True, "pinned": False, "_score": 70},
            {"id": "caremesh", "name": "CAREMESH", "index": "04", "accent": "ink",
             "value": "...", "signal": "...", "metric": "19/19 TESTS",
             "url": "caremesh-one.vercel.app", "repo": "caremesh",
             "live": True, "verified": True, "pinned": False, "_score": 60},
        ],
        "what_i_build": [], "currently_building": [],
        "tech_stack": [], "secondary_work": [],
    }


# ---- Test 1: Pinned projects survive ---------------------------------------
print("Test 1: pinned projects (EVIDENT, HOLDOUT) survive any candidate")
projects = base_projects()
discovered = [
    make_discovered("strong-challenger", 99, live=True,
                    tests={"passed": 30, "total": 30}),
]
new_selected, changed, promotions = curate_selected_work(discovered, projects)
repos = {w["repo"] for w in new_selected}
check("evident" in repos, "EVIDENT remains in Selected Work")
check("holdout" in repos, "HOLDOUT remains in Selected Work")
check(len(new_selected) == MAX_SELECTED, "Selected Work maximum remains 4")
# pinned flag still set
pinned = {w["repo"]: w.get("pinned") for w in new_selected}
check(pinned.get("evident") is True, "EVIDENT still pinned")
check(pinned.get("holdout") is True, "HOLDOUT still pinned")

# ---- Test 2: Unpinned projects displaced -----------------------------------
print("\nTest 2: unpinned projects displaced by genuinely stronger repo")
projects = base_projects()
# airloom=70, caremesh=60 (weakest unpinned)
discovered = [
    make_discovered("strong-challenger", 88, live=True,
                    tests={"passed": 25, "total": 25}),
]
new_selected, changed, promotions = curate_selected_work(discovered, projects)
repos = {w["repo"] for w in new_selected}
check("strong-challenger" in repos, "strong challenger entered Selected Work")
check("caremesh" not in repos, "weakest unpinned (CAREMESH) displaced")
check("evident" in repos, "EVIDENT remains")
check("holdout" in repos, "HOLDOUT remains")
check(len(new_selected) == MAX_SELECTED, "Selected Work maximum remains 4")
check(any(p["action"] == "promoted" and p["displaced"] == "caremesh"
            for p in promotions), "promotion recorded with displacement")

# ---- Test 3: Promotion margin enforced -------------------------------------
print("\nTest 3: promotion margin (15) is enforced")
# weakest unpinned caremesh=60; candidate 75 beats by exactly 15 -> no displace
projects = base_projects()
discovered = [make_discovered("marginal-challenger", 75, live=True,
                              tests={"passed": 10, "total": 10})]
new_selected, changed, promotions = curate_selected_work(discovered, projects)
repos = {w["repo"] for w in new_selected}
check("marginal-challenger" not in repos, "candidate +15 exactly does not displace")
check("caremesh" in repos, "caremesh not displaced by marginal candidate")
check(len(promotions) == 0, "no promotion recorded for marginal candidate")

# candidate +10 also does not displace
projects = base_projects()
discovered = [make_discovered("weak-challenger", 70, live=True)]
new_selected, changed, promotions = curate_selected_work(discovered, projects)
repos = {w["repo"] for w in new_selected}
check("weak-challenger" not in repos, "candidate +10 does not displace")
check(len(new_selected) == MAX_SELECTED, "still 4 selected")

# ---- Test 4: Missing stored _score uses discovery score -------------------
print("\nTest 4: missing stored _score uses discovery score, not zero")
# airloom has NO stored _score, discovery score=80 (high)
# caremesh has stored _score=50, discovery score=50
# candidate=85: correct enrichment => weakest=caremesh(50), 85>65 => displace caremesh
# wrong (missing=0) => weakest=airloom(0), 85>15 => displace airloom
projects = base_projects()
# clear airloom's stored score
for w in projects["selected_work"]:
    if w["repo"] == "airloom":
        w["_score"] = None
    if w["repo"] == "caremesh":
        w["_score"] = 50
discovered = [
    make_discovered("airloom", 80, live=True),       # real score 80
    make_discovered("caremesh", 50, live=True),       # real score 50
    make_discovered("strong-challenger", 85, live=True), # candidate >= 75
]
new_selected, changed, promotions = curate_selected_work(discovered, projects)
repos = {w["repo"] for w in new_selected}
check("caremesh" not in repos, "caremesh (real score 50) displaced, not airloom")
check("airloom" in repos, "airloom (real score 80) retained via discovery score")
check("strong-challenger" in repos, "candidate entered Selected Work")

# ---- Test 5: Weak boilerplate excluded -------------------------------------
print("\nTest 5: weak boilerplate repo stays excluded")
projects = base_projects()
weak = make_repo("weak-boilerplate", size=800)
weak_readme = ("# Weak Boilerplate\n"
               "create-next-app template. Minimal setup for getting started.")
weak_pkg = '{"dependencies": {"react": "^18", "next": "^14"}}'
details = score_repo(weak, weak_readme, weak_pkg, None, {"react", "next"}, [])
check(details["score"] < SELECTED_MIN_SCORE, f"weak boilerplate score {details['score']} below {SELECTED_MIN_SCORE}")
check(details["live"] is False, "weak repo has no live deployment")
discovered = [
    make_discovered("weak-boilerplate", details["score"], live=False),
]
new_selected, changed, promotions = curate_selected_work(discovered, projects)
repos = {w["repo"] for w in new_selected}
check("weak-boilerplate" not in repos, "weak boilerplate not added to Selected Work")
check(len(new_selected) == MAX_SELECTED, "still 4 selected")

# ---- Test 6: Pinned projects carry real scores -----------------------------
print("\nTest 6: pinned projects carry real discovery scores and stay protected")
projects = base_projects()
discovered = [
    make_discovered("evident", 83, live=True),
    make_discovered("holdout", 78, live=True),
    make_discovered("airloom", 70, live=True),
    make_discovered("caremesh", 60, live=True),
]
new_selected, changed, promotions = curate_selected_work(discovered, projects)
by_repo = {w["repo"]: w for w in new_selected}
check(by_repo["evident"].get("pinned") is True, "EVIDENT still pinned")
check(by_repo["holdout"].get("pinned") is True, "HOLDOUT still pinned")
check(isinstance(by_repo["evident"].get("_score"), (int, float)),
      "EVIDENT has a real _score")
check(isinstance(by_repo["holdout"].get("_score"), (int, float)),
      "HOLDOUT has a real _score")
check(by_repo["evident"]["_score"] == 83, "EVIDENT score reflects discovery (83)")
check(by_repo["holdout"]["_score"] == 78, "HOLDOUT score reflects discovery (78)")
# pinned still protected even though challenger could otherwise displace
discovered2 = [make_discovered("super-challenger", 99, live=True,
                               tests={"passed": 40, "total": 40})]
new_selected2, _, _ = curate_selected_work(discovered2, projects)
repos2 = {w["repo"] for w in new_selected2}
check("evident" in repos2 and "holdout" in repos2,
      "pinned projects not displaced even by super-challenger (99)")

# ---- summary ----------------------------------------------------------------
print(f"\n{PASS} passed, {FAIL} failed out of {PASS + FAIL} checks")
sys.exit(1 if FAIL else 0)
