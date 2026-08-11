---
name: b4-iterate
description: Iterate on a b4-managed kernel patch series posted to lore.kernel.org. Fetches the complete mail thread for the last posted revision, studies every review comment, implements only what was agreed, keeps open questions open, build-tests every touched file, squashes changes into the right patches with fixup+autosquash, and writes a per-patch changelog into the b4 cover letter. Use when a patch series sent with b4 has review feedback that needs to be addressed for the next revision.
compatibility: Requires b4 >= 0.14, git, python3, and network access to lore.kernel.org (or a local Maildir mirror).
---

# b4 Series Iteration

Iterate on a `b4 prep` owned patch series: retrieve the full lore
discussion, agree on a plan, implement, verify, and re-roll the series
for the next revision.

## Prerequisites

- The current branch is a `b4 prep` branch (`b4 prep --show-info` works)
- Working tree is clean (no staged/unstaged changes)
- `b4` and `git` available; `python3` for the thread renderer

## Hard rules

These are non-negotiable. Violating them destroys the user's trust and
sometimes their branch.

1. **NEVER commit, amend, rebase, or reset anything before the user has
   explicitly approved the changes.** All edits stay uncommitted in the
   working tree so the user can review them with their own tooling.
   "Review approved", "go ahead with the plan" or similar is required.
   No silent squashing.
2. **NEVER touch the `--- b4-submit-tracking ---` block** in the cover
   letter, including its
   `# This section is used internally by b4 prep for tracking purposes.`
   comment line and the JSON below it. See
   [Cover letter and changelog](#7-cover-letter-and-changelog) for how
   git silently eats that line.
3. **Never invent agreement.** Implement only what the maintainer and
   the author actually agreed on in the thread. Every unresolved
   discussion stays an open question, reported as such.
4. **Ignore bot findings unrelated to the series.** AI reviewers
   (sashiko-bot and friends) report pre-existing issues in the touched
   files. Unless the series *introduced* the problem, or the user says
   otherwise, list it as out-of-scope — do not fix it.
5. **Do not create files inside the repo.** Put mboxes, backups and
   scratch files under `/tmp`. The user's `git status` must stay clean.

## Workflow

### 1. Establish series state

```bash
b4 prep --show-info
```

Record: `cover-subject`, `revision` (the revision being *prepared*, so
the posted one is `revision - 1`), `base-commit`, `start-commit` (the
cover-letter commit when `cover-strategy: commit`), `end-commit`, and
`series-vN:` lines.

```bash
git log --oneline <start-commit>..HEAD
```

With `cover-strategy: commit` the **first** commit of the range is the
cover letter, not a patch. Patch N of the series is the Nth commit
*after* it. Two commits sharing the same subject usually means the cover
subject equals patch 1's subject — do not mistake one for the other.

### 2. Get the complete thread (mandatory)

Try in order and stop at the first success. **If no local mbox of the
full thread for the last posted revision can be obtained, ABORT** and
explain why — reviewing from memory or from the patches alone is not
acceptable.

**a. `b4 dig`**

```bash
b4 dig
```

Depending on the b4 version this may not exist or may silently print
nothing and exit 0. Treat empty output as failure and continue.

**b. Message-IDs from the b4 tracking data** (most reliable)

The cover-letter commit carries the message-ids of every previous
posting:

```bash
git show <start-commit> --no-patch --format='%B' | sed -n '/b4-submit-tracking/,$p'
```

> **Important:** the `history` map is keyed by the *label* used when
> sending, which is not always the true revision. A series can have two
> msgids under `"v1"` (e.g. an `RFC` posting plus a repost mislabeled
> `v1`). **Use the newest msgid** — that is the revision under review —
> and fetch the older ones too when the discussion spans them.

```bash
mkdir -p /tmp/b4-iter                       # b4 mbox -n does NOT create outdir
b4 mbox -o /tmp/b4-iter -n vN-thread <newest-msgid>
```

`b4 mbox` grabs `t.mbox.gz`, i.e. the *whole* thread including replies
from everyone. Sanity check the reported message count.

**c. Local Maildir**

If lore is unreachable, find the msgid locally and feed it to
`b4 mbox -m`:

```bash
grep -rl "<change-id-or-msgid-prefix>" ~/Mail | head
b4 mbox -m <local.mbx> -o /tmp/b4-iter -n vN-thread <msgid>
```

**d. Web search** `https://lore.kernel.org/` for the cover subject, take
the msgid from the URL, then go back to (b).

Confirm the saved mbox and the thread size before moving on.

### 3. Render and read the thread

```bash
scripts/mbox-thread.py /tmp/b4-iter/vN-thread > /tmp/b4-iter/thread.txt
scripts/mbox-thread.py --strip-quotes /tmp/b4-iter/vN-thread > /tmp/b4-iter/replies.txt
```

Read `thread.txt` for the patches themselves and `replies.txt` (quotes
removed, ~3x shorter) for the discussion. Read **every** message; deep
sub-threads often hold the actual conclusion ("Ack", "this needs fixing
in v2", "Needn't bump now").

Note these signals:

- `Reviewed-by:`/`Acked-by:`/`Tested-by:` trailers → collect via
  `b4 trailers -u` (check whether they are already applied locally)
- author replies such as "Yeps! This needs fixing in v2", "Ack",
  "Will do" → **Agreed**
- maintainer questions the author answered with no code change → the
  answer may still belong in the commit message → **Agreed (wording)**
- disagreement with no conclusion, or a suggestion the author pushed
  back on with no reviewer follow-up → **Open**


### 4. CHECKPOINT — plan only, no edits

Present a table and stop. **No file edits, no commits.**

| # | Patch | Source (who/msgid) | Category | Proposed action |
|---|-------|--------------------|----------|-----------------|

Categories: **Agreed** (implement), **Open** (needs the user's
decision), **Informational** (answered, nothing to do),
**Out-of-scope** (pre-existing/bot noise, not introduced by the series).

For each **Open** item, propose a concrete solution but make clear it is
a suggestion. Then wait. The user may reclassify items, drop them, or
answer open questions.

This checkpoint may be skipped only if the user explicitly asked for it
in the prompt (e.g. "skip the checkpoint", "just implement it") — never
skip it silently.

### 5. Implement agreed changes (working tree only)

**Nothing is committed in this step.** Every edit stays uncommitted so
the user can review it with their own tooling (e.g. the `/ide_review`
extension, which hands the review context straight back). Do not dump
`git diff` or paste the changes at the user — they run their own
commands.

For each agreed change:

1. **Find the target patch** — the commit that introduced the code being
   changed. This is bookkeeping for the later fixup only; record it, act
   on it in step 7:
   ```bash
   git log --oneline -S'<symbol>' <start-commit>..HEAD -- <file>
   ```
2. Edit the file in the working tree.
3. Commit-message-only changes: do **not** amend. Write the proposed
   message to `/tmp/b4-iter/msg-<patch>.txt` and report it as a proposal.

When all agreed changes are in place, report what was touched and which
patch each change belongs to, then hand over for review.

**You cannot move on until the review is explicitly accepted.** A
passing build, silence, or a "thanks" is not acceptance — wait for an
explicit "review approved" / "go ahead". If the user requests changes,
rework and hand over for review again.

### 6. Verify (before and after squashing)

Kernel series: cover **every** touched file.

```bash
git diff --stat <start-commit>..HEAD      # the full list of touched files
```

Pick the toolchain **first** — a `.config` regeneration would discard any
symbol you enabled before it.

Assume the arm and arm64 cross toolchains are installed. Prefer the arch of the
existing `.config`; if `.config` is missing or is for another arch, still cross
build for arm64/arm. **x86 is the last resort, only when neither cross compiler
exists:**

```bash
have() { command -v "$1" >/dev/null; }

if   grep -qs '^CONFIG_ARM64=y' .config && have aarch64-linux-gnu-gcc; then
	export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
elif grep -qs '^CONFIG_ARM=y'   .config && have arm-linux-gnueabihf-gcc; then
	export ARCH=arm   CROSS_COMPILE=arm-linux-gnueabihf-
elif have aarch64-linux-gnu-gcc; then
	export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-      # .config regen needed
elif have arm-linux-gnueabihf-gcc; then
	export ARCH=arm   CROSS_COMPILE=arm-linux-gnueabihf-    # .config regen needed
else
	unset ARCH CROSS_COMPILE                                # last resort: native x86
fi
```

In the last three cases the `.config` does not match the chosen `ARCH` (or is
missing), so regenerate it with `make defconfig` first.

Then, **whatever the starting `.config` was** (it can be an arbitrary config the
user left behind), map every touched `.c` to its `CONFIG_*` symbol and check it
is really enabled — a driver that is `not set` is *not* being compiled, and a
matching arch says nothing about which drivers are on:

```bash
./scripts/config --module <SYMBOL>        # or --enable
make olddefconfig
grep -E '^(# )?CONFIG_<SYMBOL>' .config   # verify, do not assume
```

Drivers gated on a platform (e.g. `STM32_DMA3` needs
`ARCH_STM32 || COMPILE_TEST`) may need `CONFIG_COMPILE_TEST=y` to be reachable
at all. If a symbol refuses to stick, its dependencies are unmet — report that
file as not covered instead of pretending it was built.

Build the exact objects, with `W=1`, deleting them first so they really
recompile (`make` on an unchanged tree prints nothing and proves
nothing):

```bash
rm -f $OBJS && make W=1 -j$(nproc) $OBJS
```

Then run the series checks through b4 rather than calling checkpatch by
hand — it uses the right flags and gives a per-patch verdict:

```bash
b4 prep --check
```

Expect `Success: <n>, Warning: 0, Error: 0`. Note that `b4 prep`
subcommands may re-import the branch (`fast-import` in the reflog),
which **changes every commit hash** without changing content — so
re-read hashes from `b4 prep --show-info` afterwards and confirm nothing
moved:

```bash
git diff --stat <old-tip> HEAD    # must be empty
```

**Bisectability:** rebuild the objects at every commit of the range:

```bash
BR=$(git branch --show-current)
for c in $(git rev-list --reverse <start-commit>..HEAD); do
  git checkout -q $c && rm -f $OBJS
  out=$(make W=1 -j$(nproc) $OBJS 2>&1)
  echo "$(echo "$out" | grep -qiE 'error|warning' && echo FAIL || echo OK) $(git log -1 --oneline $c)"
done
git checkout -q $BR
```

Non-kernel projects: ask for the build/test command and run it.

### 7. Squash, then cover letter and changelog

Only after the user approved everything.

```bash
git diff > /tmp/b4-iter/iteration.diff        # safety net, NOT in the repo
git add <files-of-target> && git commit --fixup=<target-sha>   # one per target
GIT_SEQUENCE_EDITOR=true git rebase --autosquash -i <start-commit>
git log --oneline <start-commit>..HEAD        # no 'fixup!' left, count unchanged
```

Rebasing onto `<start-commit>` keeps the cover-letter commit untouched.
Apply approved commit-message rewordings with
`git commit --amend -F /tmp/b4-iter/msg-<patch>.txt` (see the cleanup
warning below). Verify `Reviewed-by:` trailers survived.

**Changelog.** b4 pre-seeds the cover with an `EDITME` changelog block.
Replace those lines — never add a second changelog. Preferred:

```bash
EDITOR=<script-that-rewrites-only-the-changelog> b4 prep --edit-cover
```

b4 owns the tracking block, so it cannot be damaged this way.

> **Trap:** editing the cover via `git rebase --reword`/`git commit -F`
> uses git's default `--cleanup=strip`, which **silently deletes every
> line starting with `#`** — including
> `# This section is used internally by b4 prep for tracking purposes.`
> b4 restores it on the next `b4 prep` run, which rewrites the cover and
> **changes every commit hash**. If you must go through git, use
> `--cleanup=verbatim`:
> ```bash
> git commit --amend --cleanup=verbatim -F /tmp/b4-iter/cover.txt
> ```
> After any cover rewrite, prove nothing else moved:
> ```bash
> git diff --stat <old-tip> <new-tip>    # must be empty
> ```

Changelog format (per patch, newest revision on top, older blocks may be
dropped in favour of the link — ask):

```
Changes in vN:
- Patch 1:
  - <what changed and why>
- Patch X:
  - <what changed and why>
- Link to vN-1: https://patch.msgid.link/<msgid-of-vN-1-cover>
```

Do not bump `revision` by hand; `b4 prep --show-info` already reflects
the revision being prepared.

### 8. Final report

```bash
b4 prep --show-info | grep -E 'revision|needs-editing|start-commit|end-commit'
b4 prep --compare-to vN-1        # range-diff against the posted revision
git status --short               # must be clean
```

`b4 prep --compare-to` knows the previous revisions from the tracking
data, so use it. Only if it fails (e.g. the old revision is not in the
local object store) fall back to a hand-rolled
`git range-diff <base>..<old-tip> <base>..HEAD`.

Report: what was implemented and into which patch, build /
`b4 prep --check` / bisect results, trailers collected, the changelog
written, and the list of **Open** and **Out-of-scope** items. Optionally
suggest `b4 send --dry-run`.

## Reference

- `scripts/mbox-thread.py` — render an mbox as a threaded digest,
  optionally stripping quoted text.

## Usage Examples

```
User: "Iterate on the current b4 patch series"
User: "Iterate on my series, ignore bot findings unrelated to my changes"
User: "Fetch the v2 discussion and tell me what's still open"
```
