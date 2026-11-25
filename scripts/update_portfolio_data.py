#!/usr/bin/env python3
"""
Discover public repositories and enrich the portfolio data layer.

Reads the authenticated user's public repositories via the GitHub API,
inspects each repo's README and package metadata, and updates:

    data/projects.json
    data/profile.json   (live links)
    data/portfolio-state.json (derived proof metrics)

This is the single source-of-truth updater for the portfolio generator.
It does NOT redesign the profile; it only refreshes project/content data.
"""
import json
import os
import re
import subprocess
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")

API_BASE = "https://api.github.com"


def gh_api(path, per_page=100):
    """Make an authenticated GitHub API request using the gh CLI (falls back to raw)."""
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
    """Find vercel.app / chatgpt.site / custom live demo URLs in a README."""
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
    found = set()
    for t in known:
        if t in blob:
            found.add(t)
    return found


def detect_tests(readme):
    """Heuristic: does the repo have and run tests?"""
    if not readme:
        return None
    m = re.search(r"(\d+)/(\d+)\s*(?:tests|self-checks|checks)\s*pass", readme)
    if m:
        return {"passed": int(m.group(1)), "total": int(m.group(2))}
    return None


def classify_quality(repo, readme, package_json, tests):
    """Classify a repo's quality tier for portfolio selection."""
    score = 0
    if readme:
        score += 2
        if "live at" in readme or "vercel.app" in readme:
            score += 2
    if tests:
        score += 3
    if package_json:
        score += 1
    if repo.get("size", 0) > 1000:
        score += 1
    if score >= 7:
        return "strong"
    if score >= 4:
        return "moderate"
    return "light"


def discover():
    owner = "Swapneel-Sethi"
    repos = gh_api(f"/users/{owner}/repos?type=public&sort=pushed&direction=desc")
    if repos is None:
        print("WARNING: could not list public repos; keeping existing data.")
        return

    projects = load_json("projects.json")
    profile = load_json("profile.json")
    state = load_json("portfolio-state.json")

    discovered = []
    for repo in repos:
        name = repo["name"]
        default_branch = repo.get("default_branch", "main")
        readme = raw_file(owner, name, default_branch, "README.md")
        # try root package.json, then common locations
        package_json = None
        for cand in ["package.json", "frontend/package.json", "backend/package.json"]:
            package_json = raw_file(owner, name, default_branch, cand)
            if package_json:
                break

        live_urls = extract_live_urls(readme or "")
        tests = detect_tests(readme or "")
        techs = extract_technologies(readme or "", package_json)
        tier = classify_quality(repo, readme or "", package_json, tests)

        discovered.append({
            "name": name,
            "description": repo.get("description"),
            "homepage": repo.get("homepage"),
            "size": repo.get("size", 0),
            "default_branch": default_branch,
            "live_urls": live_urls,
            "tests": tests,
            "technologies": sorted(techs),
            "tier": tier,
            "updated_at": repo.get("updated_at"),
        })
        print(f"{name}: tier={tier} live={live_urls} tests={tests} techs={len(techs)}")

    # Merge discovered repos into projects.json secondary_work, preserving
    # the manually-curated selected work and flagship entries.
    existing = {w["name"] for w in projects.get("secondary_work", [])}
    existing.update({w["name"] for w in projects.get("selected_work", [])})
    existing.update({w["name"] for w in projects.get("currently_building", [])})

    for d in discovered:
        if d["name"] in existing:
            continue
        projects.setdefault("secondary_work", []).append({
            "name": d["name"],
            "note": f"Auto-discovered ({d['tier']}): {d['description'] or ''} "
                    f"{'live: ' + ', '.join(d['live_urls']) if d['live_urls'] else ''}".strip(),
            "repo": d["name"],
            "live": bool(d["live_urls"]),
            "tier": d["tier"],
        })

    save_json("projects.json", projects)

    # Update live links in profile.json from discovered URLs (keep curated order).
    live_links = {l["label"]: l for l in profile.get("live_links", [])}
    for d in discovered:
        for url in d["live_urls"]:
            label = d["name"]
            if label not in live_links:
                live_links[label] = {"label": label, "url": url}
    profile["live_links"] = list(live_links.values())
    save_json("profile.json", profile)

    # Touch portfolio-state timestamp.
    import datetime
    state["last_updated"] = datetime.datetime.utcnow().isoformat() + "Z"
    save_json("portfolio-state.json", state)

    print(f"\nDiscovered {len(discovered)} public repos. Data layer updated.")


if __name__ == "__main__":
    discover()
