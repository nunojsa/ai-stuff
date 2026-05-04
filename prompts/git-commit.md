---
description: Create a git commit with proper subject, message, and sign-off
argument-hint: "[instructions]"
---

Create a git commit for the currently staged changes (or all changes if nothing is staged).

## Process
1. Run `git diff --cached` (or `git diff` if nothing is staged) to understand the actual changes
2. Run `git log --no-merges --oneline <changed-file-path> | head -20` for each changed file to learn the project's subject line style (prefix, capitalization, etc.)
3. Write the commit message based on the **intent and reasoning**, not a description of the code diff
4. Show me the proposed commit message before committing
5. Commit with `git commit -s` unless explicitly told not to

## Subject Line
- Follow the style from `git log` of the changed files (e.g., `subsystem: component: short description`)
- Use imperative mood ("Fix X", "Add Y", not "Fixed X", "Added Y")
- Keep under 72 characters
- No trailing period

## Message Body
- Explain **why** the change is needed — what problem it fixes or what goal it achieves
- Describe the **root cause** if it's a bug fix
- Do NOT enumerate the code changes line by line — the diff already shows that
- Be concise. Only add detail when the change is non-obvious or tricky
- If there's a small unrelated cleanup bundled in, mention it briefly: "While at it, ..."
- Wrap lines at 72 characters

## Anti-patterns to avoid
- "Changed X to Y in file Z" — that's just restating the diff
- Overly long messages for simple changes
- Missing the "why" — every commit must explain motivation
- Generic subjects like "Fix bug" or "Update code"

## Commit Granularity
- Split changes into logical, self-contained commits (one concern per commit, ideally per file when touching independent files)
- If a single file contains multiple logical changes that need separate commits:
  1. Save the full diff: `git diff <file> > /tmp/<file>-changes.diff`
  2. Reset the file: `git checkout <file>`
  3. Apply one logical change manually, `git add <file>`, commit
  4. Repeat step 3 until all changes are committed
  5. Verify: `git diff <first-commit>~..<last-commit> -- <file>` must match the saved diff. If not, something was lost or duplicated — ask the user for guidance
- When unsure whether to split, ask the user

## Linux Kernel Tree
If the repo appears to be a Linux kernel tree (check with `git log --oneline --author="Linus Torvalds" --grep="^Linux [0-9]\+\.[0-9]\+" --max-count=1`),
also apply the following:
- Add `Fixes: <12-char-hash> ("<subject>")` trailer when fixing a specific prior commit
- Respect trailer ordering: `Co-developed-by` immediately followed by its `Signed-off-by`, then other `Signed-off-by` tags last

$@
