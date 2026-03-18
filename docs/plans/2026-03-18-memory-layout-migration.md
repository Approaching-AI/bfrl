# Memory Layout Migration Implementation Plan

> **For agentic workers:** Implement this plan with disciplined step tracking. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把记忆相关工件统一迁移到 `memory/` 下，并同步修正仓库导航与项目文档引用。

**Architecture:** 先建立新的 `memory/` 目录骨架，再执行受控迁移，最后统一修正文档导航与路径引用。迁移只改变组织方式，不改变理论内容与工件职责。

**Tech Stack:** Markdown, PowerShell, git

---

### Task 1: Create Memory Skeleton

**Files:**
- Create: `memory/logs/.gitkeep`
- Create: `memory/daily-notes/.gitkeep`
- Create: `memory/doc/.gitkeep`
- Create: `memory/sop/.gitkeep`
- Create: `memory/handoff/.gitkeep`

- [ ] **Step 1: Create the target directory tree**

Run: `New-Item -ItemType Directory -Force memory/logs,memory/daily-notes,memory/doc,memory/sop,memory/handoff`
Expected: all directories exist

- [ ] **Step 2: Add placeholder files for empty directories**

Create `.gitkeep` files where needed so the structure remains visible in git.

- [ ] **Step 3: Verify target tree exists**

Run: `Get-ChildItem -Recurse memory`
Expected: the five subdirectories are present

### Task 2: Migrate Existing Content

**Files:**
- Move: `daily-notes/*` -> `memory/daily-notes/`
- Move: `doc/*` except `doc/sop/*` -> `memory/doc/`
- Move: `doc/sop/*` -> `memory/sop/`
- Move: `handoff/*` -> `memory/handoff/`

- [ ] **Step 1: Move note files**

Preserve current on-disk state, including untracked files.

- [ ] **Step 2: Move doc files and directories**

Keep the theoretical document subtree intact under `memory/doc/`.

- [ ] **Step 3: Move SOP content**

Ensure `sop` becomes a sibling of `doc`, not a child.

- [ ] **Step 4: Move handoff content**

Retain placeholders if the directory is otherwise empty.

- [ ] **Step 5: Verify old top-level content is cleared**

Run: `Get-ChildItem daily-notes,doc,handoff`
Expected: either absent or intentionally retained only if needed for cleanup

### Task 3: Update Stable Entry Documents

**Files:**
- Modify: `AGENT.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update memory hierarchy wording in `AGENT.md`**

Replace old paths with `memory/...` and make `memory/` the canonical external memory root.

- [ ] **Step 2: Update project structure in `CLAUDE.md`**

Point overview and structure bullets at `memory/`.

- [ ] **Step 3: Re-read both files**

Run: `Get-Content -Raw AGENT.md` and `Get-Content -Raw CLAUDE.md`
Expected: no stale root-level path references remain

### Task 4: Update Project Document References

**Files:**
- Modify: `memory/daily-notes/2026-03-17-01.md`
- Modify: `memory/doc/project-overview.md`
- Modify: `memory/doc/domain-bfrl.md`
- Modify: `memory/doc/bfrl-theoretical-increment-over-harness/bfrl-theoretical-increment-over-harness.md`

- [ ] **Step 1: Update structure descriptions**

Change directory descriptions from root-level locations to `memory/...`.

- [ ] **Step 2: Update explicit path references**

Fix links and inline path examples so they point at the new layout.

- [ ] **Step 3: Leave generated build artifacts alone unless needed**

Prefer correcting source Markdown over chasing every generated `.tex` fragment.

### Task 5: Verify Migration

**Files:**
- Check: repository tree and changed Markdown files

- [ ] **Step 1: Run path verification search**

Run a recursive search for stale references such as `daily-notes/`, `doc/sop/`, and `handoff/`.

- [ ] **Step 2: Inspect git status**

Run: `git status --short`
Expected: moved files and updated docs are visible without destructive reversions

- [ ] **Step 3: Summarize residual issues**

If generated artifacts or historical references intentionally remain, note them explicitly.
