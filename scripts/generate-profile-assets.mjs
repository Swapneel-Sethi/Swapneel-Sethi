// Refreshes every live number on the profile from the GitHub API:
//   - the five <text id="..."> nodes in assets/profile-card.svg
//   - the activity block in README.md between the activity markers
// Everything else in both files is hand-authored and left untouched.
import { readFile, writeFile } from "node:fs/promises";

const LOGIN = "Swapneel-Sethi";
const TOKEN = process.env.GITHUB_TOKEN;
if (!TOKEN) throw new Error("GITHUB_TOKEN is required");

const headers = {
  Authorization: `Bearer ${TOKEN}`,
  Accept: "application/vnd.github+json",
  "User-Agent": "profile-card-refresh",
};

async function get(path) {
  const res = await fetch(`https://api.github.com${path}`, { headers });
  if (!res.ok) throw new Error(`${path} -> ${res.status} ${await res.text()}`);
  return res.json();
}

const user = await get(`/users/${LOGIN}`);

const graph = await fetch("https://api.github.com/graphql", {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({
    query:
      "query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}",
    variables: { login: LOGIN },
  }),
}).then((r) => r.json());
if (graph.errors) throw new Error(JSON.stringify(graph.errors));

const calendar = graph.data.user.contributionsCollection.contributionCalendar;
const total = calendar.totalContributions;
const days = calendar.weeks.flatMap((w) => w.contributionDays);

const values = {
  "stat-repos": user.public_repos,
  "stat-contrib": total,
  "stat-followers": user.followers,
  "stat-since": new Date(user.created_at).getUTCFullYear(),
  stamp: new Date().toISOString().slice(0, 7).replace("-", "."),
};

async function refreshSvg() {
  const file = new URL("../assets/profile-card.svg", import.meta.url);
  const before = await readFile(file, "utf8");
  let after = before;

  for (const [id, value] of Object.entries(values)) {
    const pattern = new RegExp(`(<text id="${id}"[^>]*>)[^<]*(</text>)`);
    if (!pattern.test(after)) throw new Error(`missing <text id="${id}"> in profile-card.svg`);
    after = after.replace(pattern, `$1${value}$2`);
  }

  if (after === before) return false;
  await writeFile(file, after);
  return true;
}

async function refreshActivity() {
  const file = new URL("../README.md", import.meta.url);
  const source = await readFile(file, "utf8");
  const start = "<!--activity:start-->";
  const end = "<!--activity:end-->";
  const from = source.indexOf(start);
  const to = source.indexOf(end);
  if (from === -1 || to === -1) throw new Error("activity markers missing from README.md");

  const byMonth = new Map();
  for (const day of days) {
    if (!day.contributionCount) continue;
    const key = day.date.slice(0, 7);
    const entry = byMonth.get(key) ?? { days: 0, sum: 0 };
    entry.days += 1;
    entry.sum += day.contributionCount;
    byMonth.set(key, entry);
  }

  const label = (key) =>
    new Date(`${key}-01T00:00:00Z`).toLocaleString("en-US", {
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    });

  const entries = [...byMonth.entries()].sort(([a], [b]) => a.localeCompare(b));
  const activeDays = entries.reduce((sum, [, e]) => sum + e.days, 0);

  const block = [
    `**${total} public contributions in the last 12 months.** The card above is generated from the GitHub API; the breakdown below is the same data, by month.`,
    "",
    "| Month | Active days | Contributions |",
    "| :--- | ---: | ---: |",
    ...entries.map(([key, e]) => `| ${label(key)} | ${e.days} | ${e.sum} |`),
    `| **Total** | **${activeDays}** | **${total}** |`,
  ].join("\n");

  const next = `${source.slice(0, from + start.length)}\n${block}\n${source.slice(to)}`;
  if (next === source) return false;
  await writeFile(file, next);
  return true;
}

const [svg, readme] = [await refreshSvg(), await refreshActivity()];
console.log(svg || readme ? `profile refreshed: ${JSON.stringify(values)}` : "profile already current");
