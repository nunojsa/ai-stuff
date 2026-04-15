---
name: git-rewrite-commits
description: Interactively rewrite git commit messages for a range of commits. Examines each commit's diff, proposes a meaningful message body while preserving the subject line and trailers (Signed-off-by, etc.), and amends after user approval. Use when commit messages need to be improved, expanded, or standardized across a series.
---

# Git Rewrite Commits

Rewrite commit messages for a range of N commits, one at a time with
user review before each amend.

## Workflow

1. `git format-patch -<N-1> --output-directory=temp_reword` to save
   all commits after the first (already amended) one
2. `git reset --hard HEAD~<N-1>` to go back
3. For each patch in order:
   - `git am temp_reword/<patch>`
   - `git show --stat` and `git diff HEAD^..HEAD` to understand the change
   - Propose a new commit message body:
     - Keep the original subject line (see Rules below)
     - Add a meaningful body explaining *what* changed and *why*
     - Preserve all trailers (Signed-off-by, Reviewed-by, etc.)
     - Be concise but informative
   - Present the full proposed message to the user
   - Wait for user approval or requested changes
   - On approval: `git commit --amend -m "<new message>"`
4. After all commits: `rm -rf temp_reword`

## Rules

- **Never amend without user approval**
- **Subject line:** Do not change it unless the user explicitly asks.
  If asked to rewrite the subject, follow the project's existing style.
  Check the style with `git log --oneline -- <file>` on files touched
  by the commit.
- **Trailers:** Keep all existing trailers intact and at the end of
  the message. If there is no `Signed-off-by:` tag, one must be added.
  In that case use `git commit --amend -s -m "<new message>"` so
  git adds the trailer automatically.
- The body should explain what the commit does and why, not just
  repeat the diff
- Be concise — no need to describe every line changed
- If multiple commits share the same pattern (e.g. converting
  different files to the same API), the messages can follow a
  consistent template
- Use `git show --stat` for overview and read the full diff when
  needed to understand the change

## Usage Examples

```
User: "Reword the last 10 commits with proper messages"
User: "Add commit message bodies to commits X through Y"
User: "Improve commit messages for this patch series"
User: "Rewrite subjects and bodies for the last 5 commits"
```
