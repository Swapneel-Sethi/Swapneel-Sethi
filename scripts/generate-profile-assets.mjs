// Refreshes the live numbers on assets/profile-card.svg from the GitHub API.
// Only the five <text id="..."> nodes are touched, so the design stays hand-authored.
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
    query: "query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{totalContributions}}}}",
    variables: { login: LOGIN },
  }),
}).then((r) => r.json());
if (graph.errors) throw new Error(JSON.stringify(graph.errors));

const values = {
  "stat-repos": user.public_repos,
  "stat-contrib": graph.data.user.contributionsCollection.contributionCalendar.totalContributions,
  "stat-followers": user.followers,
  "stat-since": new Date(user.created_at).getUTCFullYear(),
  stamp: new Date().toISOString().slice(0, 7).replace("-", "."),
};

const file = new URL("../assets/profile-card.svg", import.meta.url);
const before = await readFile(file, "utf8");
let after = before;

for (const [id, value] of Object.entries(values)) {
  const pattern = new RegExp(`(<text id="${id}"[^>]*>)[^<]*(</text>)`);
  if (!pattern.test(after)) throw new Error(`missing <text id="${id}"> in profile-card.svg`);
  after = after.replace(pattern, `$1${value}$2`);
}

if (after === before) {
  console.log("profile card already current");
} else {
  await writeFile(file, after);
  console.log("profile card updated:", values);
}
