# CI workflows

These are the upstream GitHub Actions workflows, adapted for this repo's
`master` default branch. They are vendored here — not under
`.github/workflows/` — because the automation account that pushes changes
lacks the OAuth `workflow` scope, so pushes that modify `.github/workflows/`
are rejected.

To activate CI/CD, copy the workflows into place (any maintainer's own GitHub
auth has the scope, including the GitHub web UI "Add file" flow):

```bash
mkdir -p .github/workflows
cp ci/workflows/*.yml .github/workflows/
git add .github/workflows && git commit -m "Enable CI workflows" && git push
```

Then enable GitHub Pages (Settings → Pages → deploy from branch `gh-pages`)
for the site deploy in `build.yml`. `build.yml` uses the automatic
`GITHUB_TOKEN` for the GitHub metadata refresh, so no extra secrets are
needed.
