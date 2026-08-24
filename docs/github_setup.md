# GitHub Setup

This workspace currently has a `.git` directory but no commits and no configured remote.

## What is ready

- generated caches and heavy media are ignored in `.gitignore`
- line endings and binary file handling are defined in `.gitattributes`
- GitHub Actions CI is defined in `.github/workflows/ci.yml`

## Recommended first commit flow

Review the staged surface first. This repo contains source code, profiles, docs, and tests, but should not include large audio/video exports.

```bash
git status --short
git add .
git status --short
git commit -m "Initial commit"
```

## Create the GitHub repository

If you use the GitHub CLI:

```bash
gh repo create electro-analyzer --private --source=. --remote=origin --push
```

Or create an empty repository in GitHub and then connect it manually:

```bash
git remote add origin git@github.com:<your-org-or-user>/electro-analyzer.git
git branch -M main
git push -u origin main
```

## Notes

- If you later decide to version control curated media assets, prefer object storage or Git LFS rather than regular Git history.
- Rotate any Spotify client secrets before publishing if they have been shared outside a secure environment.
