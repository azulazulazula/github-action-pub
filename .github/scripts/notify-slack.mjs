const repository = process.env.GITHUB_REPOSITORY;
const token = process.env.GITHUB_TOKEN;
const runId = process.env.TARGET_RUN_ID;
const webhookUrl = process.env.SLACK_WEBHOOK_URL;

if (!repository || !token || !runId || !webhookUrl) {
  throw new Error("GITHUB_REPOSITORY, GITHUB_TOKEN, TARGET_RUN_ID, and SLACK_WEBHOOK_URL are required.");
}

const [owner, repo] = repository.split("/");
if (!owner || !repo) throw new Error("GITHUB_REPOSITORY must use owner/repository format.");

const apiUrl = `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/actions/runs/${encodeURIComponent(runId)}`;
const runResponse = await fetch(apiUrl, {
  headers: {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${token}`,
    "X-GitHub-Api-Version": "2022-11-28",
  },
});

if (!runResponse.ok) {
  throw new Error(`GitHub API request failed: ${runResponse.status} ${await runResponse.text()}`);
}

const run = await runResponse.json();
const status = run.conclusion ?? run.status;
const message = `GitHub Actions: ${status} — ${repository} / ${run.name} (<${run.html_url}|実行結果>)`;

const slackResponse = await fetch(webhookUrl, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text: message }),
});

const slackBody = await slackResponse.text();
if (!slackResponse.ok || slackBody.trim() !== "ok") {
  throw new Error(`Slack webhook request failed: ${slackResponse.status} ${slackBody}`);
}

console.log(`Slack notification sent for workflow run ${run.id}: ${status}`);
