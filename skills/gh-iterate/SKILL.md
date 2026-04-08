---
name: gh-iterate
description: Iterate on a GitHub pull request by reading all review comments, understanding what was discussed, and creating an action plan. Implements agreed-upon changes as fixup commits rebased into the correct original commits, and flags open/unresolved discussions. Use when a PR has review feedback that needs to be addressed.
---

# GitHub PR Iteration

Read review comments on a GitHub PR, build a plan, implement agreed
changes, and surface unresolved discussions — all using the `gh` CLI.

## Prerequisites

- `gh` CLI must be installed and authenticated (`gh auth status`)
- The repo must have a GitHub remote
- The repo must be in a clean state. No staged or unstaged changes

## Workflow

### 1. Determine last push timestamp

Before reading comments, establish when the PR branch was last
pushed or force-pushed. This is the baseline for filtering comments.

```bash
# Get {owner}/{repo} from git remote
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')

# Get head commit SHA and its committer date as initial baseline
HEAD_SHA=$(gh api repos/$OWNER_REPO/pulls/<number> --jq '.head.sha')
LAST_PUSH=$(gh api repos/$OWNER_REPO/git/commits/$HEAD_SHA --jq '.committer.date')

# Check for force-push events — use the latest one if any exist
FORCE_PUSH=$(gh api repos/$OWNER_REPO/issues/<number>/timeline --paginate \
  --jq '[.[] | select(.event == "head_ref_force_pushed") | .created_at] | last // empty')

if [ -n "$FORCE_PUSH" ]; then
  LAST_PUSH="$FORCE_PUSH"
fi

echo "Last push: $LAST_PUSH"
```

**Detect previous local iterations:** Compare the local HEAD
against the remote PR HEAD. If they differ, a previous iteration
was applied locally but not yet pushed. Identify which files were
already touched so those comments can be marked **Resolved**:

```bash
LOCAL_HEAD=$(git rev-parse HEAD)
if [ "$LOCAL_HEAD" != "$HEAD_SHA" ]; then
  # Files already modified by a previous local iteration
  ALREADY_TOUCHED=$(git diff --name-status $HEAD_SHA HEAD)
  echo "Previous iteration detected. Files already touched:"
  echo "$ALREADY_TOUCHED"
fi
```

In step 3, any comment whose `path` appears in the already-touched
list should be classified as **Resolved** (addressed by previous
iteration) rather than **Agreed**, unless the comment is about
something other than what was changed.

**Note:** Use `--name-status` (not `--name-only`) so renames
(`R` status) are visible. When a file was renamed, both the old
and new path should be considered "touched".

### 2. Check CI status

Check for CI failures on the PR:

```bash
gh pr checks <number>
```

Classify each check as **pass**, **fail**, or **pending**.

For failed GitHub Actions checks, try to fetch logs:

```bash
# Extract the run ID from the check URL and view failed logs
gh run view <run-id> --log-failed 2>&1 | tail -50
```

For failed Azure DevOps checks, extract the build URL from the
`gh pr checks` output and use the public REST API to fetch logs:

```bash
# Parse org, project, and buildId from the Azure DevOps check URL
# URL pattern: https://dev.azure.com/{org}/{project}/_build/results?buildId={id}
AZDO_BASE="https://dev.azure.com/{org}/{project}"
BUILD_ID="<buildId>"

# Get the timeline to find failed tasks and their log IDs
curl -s "$AZDO_BASE/_apis/build/builds/$BUILD_ID/timeline?api-version=7.0" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
for r in data.get('records', []):
    if r.get('result') == 'failed' and r.get('log'):
        print(f'{r[\"name\"]:60s} logId={r[\"log\"][\"id\"]} type={r[\"type\"]}')
"

# Fetch the build task log and grep for errors/warnings
curl -s "$AZDO_BASE/_apis/build/builds/$BUILD_ID/logs/<logId>?api-version=7.0" \
  | grep -i 'error\|warning.*C[0-9]'
```

Note: This works for public Azure DevOps projects without
authentication. For private projects, the user will need to
review the logs manually via the URLs.

Include CI failures in the plan (step 4) so the user is aware.
If a failure is clearly related to code in the PR (e.g. a
compile error or unused variable warning), include it as an
actionable item. If it's an infrastructure or flaky test issue,
flag it as informational.

### 3. Gather and classify comments

Fetch all comments and classify them by freshness relative to the
last push.

```bash
# Inline review comments with outdated detection
gh api repos/$OWNER_REPO/pulls/<number>/comments --paginate --jq '.[] | {
  user: .user.login,
  created_at: .created_at,
  path: .path,
  line: (.line // .original_line),
  commit_id: .commit_id[0:8],
  original_commit_id: .original_commit_id[0:8],
  outdated: (.commit_id != .original_commit_id or .position == null),
  body: .body
}'

# Top-level PR comments (issue-level, includes author replies)
gh api repos/$OWNER_REPO/issues/<number>/comments --paginate --jq '.[] | {
  user: .user.login,
  created_at: .created_at,
  body: .body
}'

# Review-level comments (summary body submitted with each review)
gh api repos/$OWNER_REPO/pulls/<number>/reviews --paginate --jq '.[] | {
  user: .user.login,
  state: .state,
  submitted_at: .submitted_at,
  body: .body
} | select(.body != "" and .body != null)'
```

**Freshness categories** (applied to each comment):

| Freshness | Condition | Meaning |
|-----------|-----------|---------|
| **Outdated** | `commit_id != original_commit_id` or `position == null` | Code changed under this comment (likely addressed by a push) — skip unless still relevant |
| **New** | `created_at` > last push timestamp and not outdated | Reviewer commented on the current version — must address |
| **Carried forward** | `created_at` < last push, not outdated | Older comment on unchanged code — still relevant |

**Focus on New and Carried-forward comments. Skip Outdated ones**
(they were likely addressed by the push that made them outdated).

Cross-reference inline comments, review-level summaries, and
top-level replies to understand the full conversation thread for
each piece of feedback. Reviewers often put important context or
overall requests in the review summary body.

### 4. Build and present a plan

Categorise every non-outdated review comment into one of:

| Category | Action |
|----------|--------|
| **Agreed** | Author accepted the suggestion — implement it |
| **Open** | No consensus yet — flag to the user, do not implement |
| **Resolved** | Already addressed in a later commit or reply — skip |
| **Informational** | Question answered, no code change needed — skip |

Also include any CI failures from step 2 as line items in the
plan. Mark code-related failures (compile errors, warnings,
lint issues) as **Agreed** if the fix is obvious, or **Open**
if it needs discussion. Mark infrastructure/flaky failures as
**Informational**.

Present the plan to the user in a table showing freshness, category,
and proposed action. **Wait for confirmation before writing any
code.** The user may reclassify items or add context.

### 5. Implement agreed changes

For each agreed change:

1. **Identify the target commit** — the one that introduced the code
   being changed. Use `git log -S '<symbol>' -- <file>` scoped to
   the PR's commit range, or `git blame`.

2. **Make the edit** in the working tree.

3. **Verify the build** — ask the user for the build command if not
   already known (or look for `Makefile`, `CMakeLists.txt`,
   `package.json`, etc.). Run it to confirm the code compiles.

4. **Show changes to the user for review.**
   Run `git diff` and present the output for the affected files.
   Ask the user to review and confirm. Optionally, suggest the
   user run `/diff-review` (pi-diff-review extension) for a
   richer interactive review experience.
   If changes are requested, go back to step 2. **Only move to the
   next step after the user EXPLICITLY agrees with the changes.**

   **Bypass:** This review step can be skipped ONLY if the user
   explicitly asked for it (e.g. "skip review", "no review",
   "just do it"). Never skip silently.

5. **Group related changes** — if several review comments affect the
   same original commit, implement them together before moving on.

Repeat steps 1–5 for every agreed change. **Do not commit yet** —
all edits stay in the working tree until every change has been
reviewed and approved by the user.

### 6. Save, commit, and rebase

Once all changes are in the working tree and approved:

1. **Save a backup diff** of all uncommitted work as a safety net
   before starting the commit/rebase phase:
   ```bash
   git diff > pr-<number>-iteration.diff
   ```
   If the fixup or rebase goes wrong, the user can restore with
   `git apply pr-<number>-iteration.diff`.

2. **Create fixup commits** — one per target commit. Stage only the
   files that belong to each target:
   ```bash
   git add <files-for-target>
   git commit --fixup=<target-sha>
   ```
   If multiple review comments affect the same original commit,
   combine them into a single fixup.

3. **Rebase:**

   ```bash
   GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash <base>~1
   ```

   Where `<base>` is the oldest commit in the PR. Verify:

   ```bash
   git log --oneline <base-branch>..HEAD   # same count, no fixup! lines
   ```

### 7. Final verification

- Build again after rebase to confirm nothing broke.
- Run `grep` / `rg` to ensure no stale references remain from
  renamed symbols.
- Show the user a summary of what was done and list any open
  discussions that still need resolution.

### 8. Range-diff and changelog

Run a range-diff between the remote PR head and the local tree
to produce a clear summary of all changes:

```bash
BASE_SHA=$(gh api repos/$OWNER_REPO/pulls/<number> --jq '.base.sha')
git range-diff ${BASE_SHA}..${HEAD_SHA} ${BASE_SHA}..HEAD
```

Then check existing PR comments for previous changelog entries
to determine the next version number:

```bash
gh api repos/$OWNER_REPO/issues/<number>/comments \
  --jq '.[] | .body' | grep -i 'changes in v'
```

Compose a changelog message in this format and present it to
the user for copy-pasting into the PR:

```
Changes in vN:
 * <concise description of change, crediting reviewer if suggested>
 * ...
```

Each bullet should be a concise one-liner describing what changed
and why (e.g. reviewer suggestion, CI fix). Credit the reviewer
with `@username` when the change was their suggestion. If a changelog version
number cannot be determined, omit the "in vN" part and just say "Changelog:".

## Rules

- **Never implement changes without presenting the plan first.**
- **Always save a backup diff** (`git diff > pr-<number>-iteration.diff`)
  after all edits are reviewed and approved, but before creating
  fixup commits and rebasing. This is the safety net in case the
  commit/rebase phase goes wrong.
- **One fixup commit per original target commit.** If multiple review
  comments touch the same original commit, combine them.
- **Verify the build** after edits and again after rebase.
- **Flag open discussions** clearly — do not silently skip or
  unilaterally resolve them.
- **Preserve commit structure** — use fixup + autosquash rebase, never
  squash unrelated commits together.
- When deriving `{owner}/{repo}`, parse `git remote -v` for the
  GitHub remote (prefer `origin`).
- **Skip outdated comments** — after a force push, comments where
  `commit_id != original_commit_id` or `position == null` were on
  code that has since changed. Do not act on them unless the user
  explicitly asks.

## Usage Examples

```
User: "Iterate on PR #1417"
User: "Address the review comments on PR #42"
User: "Check PR 100 feedback and fix what's been agreed"
```
