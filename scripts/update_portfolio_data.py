#!/usr/bin/env python3
"""
Discover public repositories, score them, and auto-curate the portfolio data layer.

Reads the authenticated user's public repositories via the GitHub API,
inspects each repo's README and package metadata, computes a portfolio quality
score (never based on raw commit count), and updates:

    data/projects.json        selected_work / secondary_work curation
    data/profile.json         live links
    data/portfolio-state.json derived proof metrics + scores

Curation rules (conservative):
- Selected Work max size: 4
- A repo enters Selected Work only if: score >= SELECTED_MIN_SCORE,
  has a live deployment, and (there is an open unpinned slot OR it beats the
  weakest unpinned selected project by PROMOTE_MARGIN points).
- Pinned (flagship) projects are never auto-removed.
- Raw commit count is NOT a scoring factor.
"""
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")

API_BASE = "https://api.github.com"

# ---- scoring thresholds -----------------------------------------------------
SELECTED_MIN_SCORE = 75        # minimum to be considered for Selected Work
PROMOTE_MARGIN = 15            # must beat weakest unpinned selected by this much
MAX_SELECTED = 4               # card grid fits exactly 4

# Scoring weights (sum to 100). Raw commit count is intentionally absent.
WEIGHTS = {
    "live": 25,        # has a verifiable live deployment
    "docs": 15,        # substantive README
    "tests": 20,       # test suite with pass/total
    "benchmark": 15,   # quantified benchmark / metric evidence
    "architecture": 10,# design system / orchestrator / failover / pipeline
    "security": 5,     # auth / sessions / authorization / audit
    "relevance": 10,   # real product work, not tutorial/boilerplate
}


def gh_api(path, per_page=100):
    """Make a GitHub API request via the gh CLI (authenticated)."""
    try:
        out = subprocess.run(
            ["gh", "api", f"{path}?per_page={per_page}", "--jq", "."],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


def raw_file(owner, repo, ref, path):
    """Fetch a file's raw content from GitHub."""
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    try:
        req = Request(url, headers={"Accept": "application/vnd.github.raw+json", "User-Agent": "portfolio-bot"})
        with urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        if e.code == 404:
            return None
        raise
    except URLError:
        return None


def load_json(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def save_json(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def extract_live_urls(readme):
    """Find verifiable live demo URLs in a README."""
    urls = set()
    for m in re.finditer(r"https://(?:[a-z0-9-]+\.)?(?:vercel\.app|chatgpt\.site|netlify\.app|github\.io)/[^\s\)\"\']*", readme):
        urls.add(m.group(0).rstrip(".,)"))
    return sorted(urls)


def extract_technologies(readme, package_json):
    """Gather technology signals from package.json deps and README mentions."""
    tech = set()
    if package_json:
        try:
            pj = json.loads(package_json)
            deps = {**pj.get("dependencies", {}), **pj.get("devDependencies", {})}
            tech.update(deps.keys())
        except json.JSONDecodeError:
            pass
    known = {
        "react", "next", "typescript", "tailwind", "three.js", "three", "recharts",
        "node", "fastapi", "supabase", "firebase", "gemini", "groq", "mistral",
        "xgboost", "scikit-learn", "pandas", "vercel", "docker", "redis", "postgres",
        "deck.gl", "d3", "leaflet", "chart.js", "framer-motion", "zustand", "vitest",
        "jest", "playwright", "react-query", "zod"
    }
    blob = (readme or "").lower() + " " + " ".join(tech).lower()
    return {t for t in known if t in blob}


def detect_tests(readme):
    """Heuristic: does the repo have and report a passing test suite?"""
    if not readme:
        return None
    m = re.search(r"(\d+)/(\d+)\s*(?:tests|self-checks|checks)\s*pass", readme)
    if m:
        return {"passed": int(m.group(1)), "total": int(m.group(2))}
    m2 = re.search(r"npm test.*passed|tests?\s*passed", readme, re.I)
    if m2:
        return {"passed": 1, "total": 1}
    return None


def score_repo(repo, readme, package_json, tests, techs, live_urls):
    """Score a repository 0-100 across evidence dimensions. Never commit count."""
    score = 0
    details = {}

    # --- live deployment (25) -----------------------------------------------
    live = bool(live_urls)
    score += WEIGHTS["live"] if live else 0
    details["live"] = live
    details["live_urls"] = live_urls

    # --- documentation (15) -------------------------------------------------
    docs = bool(readme and len(readme) > 600)
    score += WEIGHTS["docs"] if docs else 0
    details["docs"] = docs

    # --- testing (20) -------------------------------------------------------
    test_ratio = 0.0
    if tests and tests["total"]:
        test_ratio = tests["passed"] / tests["total"]
    score += int(WEIGHTS["tests"] * test_ratio)
    details["tests"] = tests
    details["test_ratio"] = round(test_ratio, 2)

    # --- benchmark evidence (15) --------------------------------------------
    benchmark = bool(
        readme and re.search(r"(F1|recall|precision|benchmark|0\.\d{3}|datasets)", readme or "", re.I)
    )
    score += WEIGHTS["benchmark"] if benchmark else 0
    details["benchmark"] = benchmark

    # --- architecture evidence (10) -----------------------------------------
    architecture = bool(
        readme and re.search(
            r"(architecture|orchestrator|failover|audit trail|pipeline|force graph|state machine)",
            readme or "", re.I,
        )
    )
    score += WEIGHTS["architecture"] if architecture else 0
    details["architecture"] = architecture

    # --- security evidence (5) ----------------------------------------------
    security = bool(
        readme and re.search(
            r"(scrypt|HMAC|authorization|session|audit|passcode|httpOnly)",
            readme or "", re.I,
        )
    )
    score += WEIGHTS["security"] if security else 0
    details["security"] = security

    # --- internship relevance (10) ------------------------------------------
    # Real product work, not create-next-app boilerplate / tutorial.
    boilerplate = bool(
        readme and re.search(
            r"(create-next-app|boilerplate|template|getting started|minimal setup)",
            readme or "", re.I,
        )
    )
    relevance = not boilerplate and bool(readme)
    score += WEIGHTS["relevance"] if relevance else 0
    details["relevance"] = relevance

    # --- recency bonus (bonus, not primary) ---------------------------------
    recency = 0
    updated = repo.get("updated_at")
    if updated:
        try:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - dt).days
            if days < 90:
                recency = 3
            elif days < 365:
                recency = 1
        except Exception:
            pass
    score += recency
    details["recency_bonus"] = recency

    details["score"] = min(score, 100)
    details["technologies"] = sorted(techs)
    details["size"] = repo.get("size", 0)
    details["default_branch"] = repo.get("default_branch", "main")
    return details


def classify_quality(details):
    """Map a score to a quality tier."""
    s = details["score"]
    if s >= 80:
        return "strong"
    if s >= 60:
        return "moderate"
    return "light"


def curate_selected_work(discovered, projects):
    """
    Auto-curate selected_work.

    Returns (selected_work, changed, promotion_candidates).
    Pinned projects are protected from auto-removal.
    Existing unpinned selected projects are carried over unless displaced.
    """
    max_selected = MAX_SELECTED
    current = projects.get("selected_work", [])

    pinned_selected = [w for w in current if w.get("pinned")]
    unpinned_current = [w for w in current if not w.get("pinned")]
    pinned_repos = {w["repo"] for w in pinned_selected}

    # Build candidate list from discovered repos (not already pinned/selected).
    candidates = []
    for d in discovered:
        name = d["name"]
        if name in pinned_repos:
            continue  # pinned flagships stay where they are
        details = d.get("_score_details", {})
        score = details.get("score", 0)
        live = details.get("live", False)
        if score >= SELECTED_MIN_SCORE and live:
            candidates.append((score, name, d, details))

    candidates.sort(key=lambda x: x[0], reverse=True)

    # Start with ALL current selected (pinned + unpinned carried over).
    new_selected = list(current)

    # Enrich existing selected projects with freshly computed discovery scores.
    # Use the freshly computed score whenever the repo was discoverable; only
    # fall back to the stored _score if the repo was not discovered. This
    # prevents a missing stored _score from being treated as zero and making
    # an ordinary candidate look artificially superior.
    discovered_by_name = {d["name"]: d for d in discovered}
    for w in new_selected:
        disc = discovered_by_name.get(w["repo"])
        if disc is not None:
            disc_score = disc.get("_score_details", {}).get("score")
            if disc_score is not None:
                w["_score"] = disc_score
        # else: keep the stored _score (fallback)

    # Count empty non-pinned slots.
    non_pinned_count = len([w for w in new_selected if not w.get("pinned")])
    open_slots = max_selected - len(pinned_selected) - non_pinned_count
    # (open_slots >= 0 normally; clamp just in case)
    open_slots = max(open_slots, 0)

    # Top candidates fill empty non-pinned slots.
    promotion_candidates = []
    for score, name, d, details in candidates:
        if open_slots <= 0:
            break
        # skip if this repo is already selected (unpinned)
        if any(w["repo"] == name for w in new_selected):
            continue
        entry = build_selected_entry(name, d, details)
        new_selected.append(entry)
        open_slots -= 1
        promotion_candidates.append({"name": name, "score": score, "action": "added"})

    # Try to displace the weakest UNPINNED selected project if a candidate
    # meaningfully outranks it (conservative margin).
    unpinned_selected = [w for w in new_selected if not w.get("pinned")]
    if unpinned_selected and candidates:
        weakest = min(unpinned_selected, key=lambda w: w.get("_score", 0))
        best_candidate = candidates[0]
        # skip if best candidate is already selected
        if not any(w["repo"] == best_candidate[1] for w in new_selected):
            if best_candidate[0] > weakest.get("_score", 0) + PROMOTE_MARGIN:
                new_selected = [w for w in new_selected if w["repo"] != weakest["repo"]]
                entry = build_selected_entry(best_candidate[1], best_candidate[2], best_candidate[3])
                new_selected.append(entry)
                promotion_candidates.append(
                    {"name": best_candidate[1], "score": best_candidate[0],
                     "action": "promoted", "displaced": weakest["repo"]}
                )

    # Sort final selection: pinned first, then by score desc.
    def sort_key(w):
        return (0 if w.get("pinned") else 1, -w.get("_score", 0))
    new_selected.sort(key=sort_key)

    # Re-index numbers and trim to max_selected.
    for i, w in enumerate(new_selected[:max_selected]):
        w["index"] = f"{i + 1:02d}"
    new_selected = new_selected[:max_selected]

    changed = _selected_changed(current, new_selected)
    return new_selected, changed, promotion_candidates


def build_selected_entry(repo_name, d, details):
    """Build a selected_work entry from a discovered repo record."""
    readme = d.get("readme") or ""
    # Derive a short value prop from the README's first meaningful lines or description.
    desc = d.get("description") or ""
    value = desc or f"{repo_name}: a shipped engineering project."
    signal = ", ".join(details.get("technologies", [])[:4]) or "engineered system"
    metric = ""
    if details.get("tests"):
        metric = f"{details['tests']['passed']}/{details['tests']['total']} TESTS"
    elif details.get("benchmark"):
        metric = "VERIFIED METRICS"
    elif details.get("live"):
        metric = "LIVE DEPLOYMENT"

    live_urls = details.get("live_urls") or []
    url = live_urls[0] if live_urls else f"{repo_name}.vercel.app"

    return {
        "id": repo_name,
        "name": repo_name.replace("-", " ").replace("_", " ").title(),
        "index": "00",
        "accent": _accent_for(details.get("technologies", [])),
        "value": value,
        "signal": signal,
        "metric": metric,
        "url": url,
        "repo": repo_name,
        "live": bool(live_urls),
        "verified": bool(details.get("tests") or details.get("benchmark")),
        "pinned": False,
        "_score": details.get("score", 0),
    }


def _accent_for(technologies):
    techs = set(t.lower() for t in technologies)
    if techs & {"three.js", "three", "deck.gl", "d3"}:
        return "studio"
    if techs & {"gemini", "groq", "mistral", "xgboost", "scikit-learn", "pandas"}:
        return "learn"
    return "tech"


def _selected_changed(old, new):
    old_keys = {w["repo"] for w in old}
    new_keys = {w["repo"] for w in new}
    return old_keys != new_keys


def discover():
    owner = "Swapneel-Sethi"
    repos = gh_api(f"/users/{owner}/repos?type=public&sort=pushed&direction=desc")
    if repos is None:
        print("WARNING: could not list public repos; keeping existing data.")
        return

    projects = load_json("projects.json")
    profile = load_json("profile.json")
    state = load_json("portfolio-state.json")

    # Preserve existing pinned status + curated content for selected_work.
    existing_selected = projects.get("selected_work", [])
    pinned_map = {w["repo"]: w.get("pinned", False) for w in existing_selected}
    curated_by_repo = {w["repo"]: w for w in existing_selected}

    discovered = []
    for repo in repos:
        name = repo["name"]
        default_branch = repo.get("default_branch", "main")
        readme = raw_file(owner, name, default_branch, "README.md")
        package_json = None
        for cand in ["package.json", "frontend/package.json", "backend/package.json"]:
            package_json = raw_file(owner, name, default_branch, cand)
            if package_json:
                break

        live_urls = extract_live_urls(readme or "")
        tests = detect_tests(readme or "")
        techs = extract_technologies(readme or "", package_json)
        details = score_repo(repo, readme, package_json, tests, techs, live_urls)
        tier = classify_quality(details)

        discovered.append({
            "name": name,
            "description": repo.get("description"),
            "homepage": repo.get("homepage"),
            "size": repo.get("size", 0),
            "default_branch": default_branch,
            "live_urls": live_urls,
            "tests": tests,
            "technologies": details["technologies"],
            "tier": tier,
            "score": details["score"],
            "_score_details": details,
            "updated_at": repo.get("updated_at"),
        })
        print(f"{name}: score={details['score']} tier={tier} live={details.get('live', False)} tests={tests}")

    # ---- auto-curate selected_work -----------------------------------------
    selected_work, changed, promotion_candidates = curate_selected_work(discovered, projects)

    # Re-apply pinned status + preserve human-curated text where repo unchanged.
    for w in selected_work:
        if w["repo"] in pinned_map:
            w["pinned"] = pinned_map[w["repo"]]
        if w["repo"] in curated_by_repo:
            cur = curated_by_repo[w["repo"]]
            for k in ("value", "signal", "metric", "url", "verified", "pinned"):
                if k in cur:
                    w[k] = cur[k]

    projects["selected_work"] = selected_work

    # ---- refresh secondary_work with newly discovered repos ----------------
    existing_names = {
        w["name"] for w in projects.get("secondary_work", [])
    }
    existing_names.update({w["name"] for w in selected_work})
    existing_names.update({w["name"] for w in projects.get("currently_building", [])})

    for d in discovered:
        if d["name"] in existing_names:
            continue
        projects.setdefault("secondary_work", []).append({
            "name": d["name"],
            "note": f"Auto-discovered ({d['tier']}, score {d['score']}): "
                    f"{d['description'] or ''} "
                    f"{'live: ' + ', '.join(d['live_urls']) if d['live_urls'] else ''}".strip(),
            "repo": d["name"],
            "live": bool(d["live_urls"]),
            "tier": d["tier"],
            "score": d["score"],
        })

    save_json("projects.json", projects)

    # ---- update live links in profile.json ---------------------------------
    live_links = {l["label"]: l for l in profile.get("live_links", [])}
    for d in discovered:
        for url in d["live_urls"]:
            label = d["name"]
            if label not in live_links:
                live_links[label] = {"label": label, "url": url}
    profile["live_links"] = list(live_links.values())
    save_json("profile.json", profile)

    # ---- update portfolio-state --------------------------------------------
    state["last_updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state["selected_work_scores"] = {w["repo"]: w.get("_score", 0) for w in selected_work}
    state["promotion_candidates"] = promotion_candidates
    save_json("portfolio-state.json", state)

    print(f"\nDiscovered {len(discovered)} public repos.")
    print(f"Selected work: {[w['repo'] for w in selected_work]}")
    if promotion_candidates:
        print(f"Promotion candidates: {promotion_candidates}")
    print("Data layer updated.")


if __name__ == "__main__":
    discover()
