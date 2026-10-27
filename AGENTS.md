# AGENTS.md

Mars is a Python CLI coding agent.

## Working agreements

- Design decisions are made by the author. Agents propose options with evidence; never decide.
- When the user asks a question, answer it first before making edits or running commands.
- When responding to feedback, state whether you agree or disagree before saying what you changed.
- Technical prose only: no emojis in commits, code, or docs.
- Never commit unless the user asks.
- If the user's instructions conflict with any rule in this document, ask for explicit confirmation first.

## Git

- Stage explicit paths; never `git add -A` / `git add .`.
- Never run `git reset --hard`, `git clean -fd`, `git stash`, or `git commit --no-verify`.
- Commit message format: `{feat,fix,docs,refactor,test,chore}: <subject>`, subject in Chinese.
