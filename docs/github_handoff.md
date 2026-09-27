# GitHub handoff and acceptance

After all local checks and an isolated fresh-checkout replay pass:

```bash
gh auth status
gh auth login --hostname github.com --git-protocol https --web
gh repo create futures-strategy-audit --public --source . --remote origin --push
gh workflow run replication.yml --ref main
gh run list --workflow replication.yml --branch main --limit 1
gh run watch RUN_ID --exit-status
gh run download RUN_ID --name futures-replication-report
git fetch origin main
```

Authentication is a real gate. A repository URL, green workflow, artifact, or push-back must not be claimed before it is observed.

Acceptance requires one `completed/success` manual run whose steps show dependency install, tests, security scan, clean official-data acquisition, all three full backtests, report/output validation, artifact upload, and result commit/push. The downloaded artifact must contain the same metrics and report as the pushed result commit on `origin/main`.

