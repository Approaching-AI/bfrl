# bfrl — Backward Free Reinforcement Learning

不调整权重，通过 context engineering 实现 RL 效果。使命：把 RL 成本降低几个数量级，让模型在任何场景都能有好的表现。

详见 `doc/project-overview.md`。

## 项目结构

- `daily-notes/` — 每日工作记录，按 `YYYY-MM-DD.md` 命名
- `doc/` — 项目文档快照
- `doc/sop/` — 标准操作流程
- `handoff/` — session 间的任务交接文件
- `meta-agent/` — agent 工作方法论（git submodule）

## Meta Agent Guidelines

Read and follow the guidelines in `meta-agent/CLAUDE.md`. Detailed methodology is in `meta-agent/doc/methodology.md`.

Periodically (e.g., daily or weekly) check if meta-agent has updates:
```bash
git submodule update --remote meta-agent
```
If there are changes, commit the update.
