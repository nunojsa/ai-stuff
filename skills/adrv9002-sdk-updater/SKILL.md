---
name: adrv9002-sdk-updater
description: Update the adrv9002 IIO driver when a new SDK is available. Follow the exact steps defined in this document.
---

# Adrv9002 SDK Updater

Given a path for the new API SDK, you must follow all the steps defined in here in order to update the code. By the end of the process
the driver needs to be compilable without any warning.

## Prerequisites

- You MUST be under a linux kernel repository. Remember the path to it. From now on, I'll refer to it as linux-path
- The driver linux-path/drivers/iio/adc/navassa/ MUST exist
- Run `git status -- drivers/iio/adc/navassa firmware` from linux-path. Both paths MUST be in a clean git state (no uncommitted changes, no untracked files). If there is ANY dirty state (modified files, staged changes), you MUST abort immediately and ask the user to resolve first. Do NOT proceed under any circumstance — no exceptions, no judgment calls.
- You are given a path for the new API SDK. If only a version is given, use ~/work/adrv9001-sdk.<version>.
  If neither path nor version is given, look for directories matching ~/work/adrv9001-sdk-* and use the one with the
  highest version. The version can be inferred from the directory name. From now on I'll refer to it as sdk-path

## Steps to Update

1. Copy the API code
 * cd sdk-path/adrv9001-sdk/pkg/production/c_src
 * Read the API version from sdk-path/adrv9001-sdk/pkg/production/CHANGELOG.md and remember the version. You'll need it for the commit message!
 * find . -type f -exec dos2unix {} +
 * cp third_party/adi_pmag_macros/adi_pmag_macros.h linux-path/drivers/iio/adc/navassa/third_party/adi_pmag_macros.h
 * cp third_party/jsmn/jsmn.* linux-path/drivers/iio/adc/navassa/third_party/jsmn/
 * cp common/* linux-path/drivers/iio/adc/navassa/common/
 * cp -rf devices/adrv9001/private/* linux-path/drivers/iio/adc/navassa/devices/adrv9001/private/
 * cp -rf devices/adrv9001/public/* linux-path/drivers/iio/adc/navassa/devices/adrv9001/public/
 * Run `git status -- drivers/iio/adc/navassa` from linux-path to check if new untracked source files were added. If so, add them to
   linux-path/drivers/iio/adc/navassa/Makefile
2. Re-apply overwritten local fixes

 After copying the API files, check for local commits that fixed API files since the last SDK update.
 These fixes get overwritten by the copy in step 1 and must be re-applied.

 ### Permanent kernel patches

 The following fixes target third-party code bundled by the SDK that will never be fixed upstream.
 Apply them **unconditionally** after every copy. Include them in the API update commit — do **not**
 create separate commits and do **not** list them as squashed:

 - `third_party/jsmn/jsmn.h`: Replace `#include <stddef.h>` with:
   ```c
   #ifdef __KERNEL__
   #include <linux/types.h>
   #else
   #include <stddef.h>
   #endif
   ```

 ### Squashable fixes

 * Find the last API update commit:
   `LAST_API_UPDATE=$(git log -1 --format='%H' -- drivers/iio/adc/navassa/devices/adrv9001/public/include/adi_adrv9001_version.h)`

 * **Recent fixes**: List commits since then that touched API files:
   ```
   git log --oneline "$LAST_API_UPDATE"..HEAD -- \
       drivers/iio/adc/navassa/common/ \
       drivers/iio/adc/navassa/devices/ \
       drivers/iio/adc/navassa/third_party/
   ```

 * **Previously squashed fixes**: Read the commit message of `$LAST_API_UPDATE`
   (`git log -1 --format='%B' "$LAST_API_UPDATE"`) and look for commits listed as squashed
   in previous updates. Extract their hashes and inspect their diffs too.

 * For each commit found (recent or previously squashed), inspect its diff
   (`git show <hash> -- <api paths>`) and check whether the new SDK reverted the change.
   If so, re-apply it and resolve conflicts if the surrounding code changed.

 * Collect all re-applied commits — they go into the squashed commits list for the API update
   commit message.

 If no commits are found, skip this step.

3. Copy Firmware files
 * cd sdk-path/adrv9001-sdk/pkg/prototype/resources
 * cp Adi.Adrv9001.Firmware/Navassa_EvaluationFw* linux-path/firmware/Navassa_EvaluationFw.bin
 * From the step above, infer the firmware version from the original file name and remember it for the commit message!
 * cp Adi.Adrv9001.GainTables/public/RxGainTable_GainCompensated_*.csv linux-path/firmware/RxGainTable_GainCompensated.csv
 * cp Adi.Adrv9001.GainTables/public/RxGainTable_[0-9]*.csv linux-path/firmware/RxGainTable.csv
 * cp Adi.Adrv9001.GainTables/public/TxAttenTable_*.csv linux-path/firmware/TxAttenTable.csv
 * cp Adi.Adrv9001.GainTables/public/ORxGainTable_*.csv linux-path/firmware/ORxGainTable.csv
 * Run dos2unix on the copied firmware CSV files: `dos2unix linux-path/firmware/RxGainTable_GainCompensated.csv linux-path/firmware/RxGainTable.csv linux-path/firmware/TxAttenTable.csv linux-path/firmware/ORxGainTable.csv`

4. Compile the Code for ARM and ARM64
 * cd linux-path
 * cross_cc_arm (shell alias that sets up ARM cross-compilation. If unavailable, use `export ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf-`)
 * make zynq_xcomm_adv7511_defconfig && make -j$(nproc)
 * make mrproper
 * cross_cc_arm64 (shell alias that sets up ARM64 cross-compilation. If unavailable, use `export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-`)
 * make adi_zynqmp_defconfig && make -j$(nproc)

## Error handling

* For the steps under 1., 2. and 3. if some files do not exist, it means it's a process failure. Ask the user for next steps and detail what you've done so far.
  You **MUST** not assume that a new file is needed or was renamed. Always ask for guidance in this case.
* For step 4, things you **MUST** check:
  1. Identify if the error is coming from an API file. Those live under:
    * linux-path/drivers/iio/adc/navassa/devices/adrv9001;
    * linux-path/drivers/iio/adc/navassa/common;
    * linux-path/drivers/iio/adc/navassa/third_party.
  2. If the error IS in an API file:
    * Since local fixes were already re-applied in step 2, this is a new issue not seen before.
      Read the API code and understand how similar issues were fixed before.
      One pattern to grep is "ifdef __KERNEL__".
  3. If the error is NOT in an API file:
    * The main driver needs to adapt to the breaking change! Identify what changed and adapt the code. You
      **MUST** be sure about what you're doing. Don't assume anything! If unsure, ask the user.
  4. You **MUST** treat warnings as errors!
* If you need to abort at any point, do **NOT** rollback any changes. Leave the tree as-is and save the progress log
  as described in the [Output](#output) section before stopping.

## Commit the changes

After making sure everything builds, **without warnings**, read the prompt git-commit.md and follow it to commit the changes!
Look for it in the following paths (first match wins):
 * `.pi/agent/prompts/git-commit.md` (pi, project-level)
 * `~/.pi/agent/prompts/git-commit.md` (pi, user-level)
 * `.claude/commands/git-commit.md` (Claude Code, project-level)
 * `~/.claude/commands/git-commit.md` (Claude Code, user-level)

If not found in any of the above paths, ask the user for guidance.
When following git-commit.md, make sure to include the API version and firmware version as part of the context you provide to the prompt.

### Commit ordering

The changes **MUST** be split into separate, logical commits in the following order:

1. **API update** — Only the API files copied from the SDK (everything under `drivers/iio/adc/navassa/`
   that came from step 1), **including** permanent kernel patches and squashed commits (see below).
   Mention squashed commits in the commit message.
2. **Firmware update** — Only the firmware files copied in step 3 (`firmware/`).
3. **Fix API compile-time errors/warnings** — **New** fixes applied to API files to make them build
   in-kernel (e.g., `#ifdef __KERNEL__` guards, `static` annotations) that are not already covered by
   permanent kernel patches or squashed commits. Split into logical commits as appropriate.
4. **Adapt the driver to the new API** — Changes to the main driver files (`adrv9002.c`,
   `adrv9002_debugfs.c`, etc.) to adapt to breaking API changes.

### Squashed commits

**IMPORTANT** - If, while dealing with [Error Handling](#error-handling), you got issues already fixed by previous commits, you **MUST** make that information part of
the API update commit message. Append the following section to the commit message body:

```
Changes that are yet not in the upstream API and were squashed in the update:
commit <12-char-hash> ("<original commit subject>")
```

List every such commit on its own line.

## Output

Save a progress log to linux-path/adrv9002-sdk-update.log. You **MUST** not skip this step in case you need to abort the process!
The log must include:
 * SDK version and path used
 * API and firmware versions (as read from CHANGELOG.md and firmware filename)
 * Last API update commit hash used as baseline
 * Local fixes re-applied from step 2 (list of commit hashes and subjects, both recent and previously squashed)
 * Commands that failed (with their error output)
 * Changes made (files copied, Makefile edits, compile fixes)
 * Current status (completed, aborted at step X, etc.)

## Usage

1. Update navassa SDK to the version 0.29.5
2. Update adrv9002 BU API (no version given, discovers latest SDK from ~/work)

