# bfrl — Backward Free Reinforcement Learning

不调整权重，通过 context engineering 实现 RL 效果。使命：把 RL 成本降低几个数量级，让模型在任何场景都能有好的表现。

先读 `AGENT.md`，再按需进入 `memory/` 中的相关工件。

详见 `memory/doc/project-overview.md`。

## 项目结构

- `memory/` — 统一外部记忆根目录
- `memory/logs/` — 原始轨迹与 rollout backing store
- `memory/daily-notes/` — 每日工作记录，按 `YYYY-MM-DD-<index>.md` 命名
- `memory/doc/` — 项目文档快照
- `memory/sop/` — 标准操作流程
- `memory/handoff/` — session 间的任务交接文件
- `agents/` — `auto-meta-agent` agent runtime（git submodule，挂载路径保持为 `agents/`）
- `meta-agent/` — agent 工作方法论（git submodule）

## Meta Agent Guidelines

Read and follow the guidelines in `meta-agent/AGENTS.md`. Detailed methodology is in `meta-agent/doc/methodology.md`.

Periodically (e.g., daily or weekly) check if meta-agent has updates:
```bash
git submodule update --remote meta-agent
```
If there are changes, commit the update.
