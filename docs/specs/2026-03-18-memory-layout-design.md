# Memory Layout Design

## Goal

把当前分散在仓库根目录的 `daily-notes/`、`doc/`、`doc/sop/`、`handoff/` 统一纳入一个清晰的外部记忆总目录，避免项目文档与学习工件继续混杂。

## Decision

采用单一总目录 `memory/`，结构如下：

- `memory/logs/`
- `memory/daily-notes/`
- `memory/doc/`
- `memory/sop/`
- `memory/handoff/`

## Rationale

### 1. 对齐 BFRL 的 memory hierarchy

这次调整直接把 `log -> daily-notes -> doc -> sop` 变成显式目录结构，而不是分散约定。

### 2. 降低根目录噪声

根目录保留项目入口与方法论文档；任务经验、知识沉淀与交接材料进入统一 memory 空间。

### 3. 让后续流程设计更自然

后续设计 log 到 SOP 的压缩流程时，不再需要跨多个顶层目录来描述同一套系统。

## Scope

本次只做结构迁移与文档修正，不扩展实现任何新的自动化流程。

包括：

- 新建 `memory/` 及其子目录
- 迁移现有内容到新位置
- 更新 `AGENT.md`
- 更新 `CLAUDE.md`
- 更新项目文档中的路径引用

不包括：

- 设计 note 格式
- 设计 doc/sop 蒸馏规则细节
- 实现日志采集或自动压缩脚本

## Migration Rules

### Path mapping

- `daily-notes/` -> `memory/daily-notes/`
- `doc/` 中非 `sop/` 内容 -> `memory/doc/`
- `doc/sop/` -> `memory/sop/`
- `handoff/` -> `memory/handoff/`
- 新增 `memory/logs/`

### Documentation rules

- 所有稳定导航文档改用新路径
- `AGENT.md` 明确把 `memory/` 视为外部记忆总目录
- `CLAUDE.md` 把项目结构说明改成新布局

## Risks

- 现有工作区包含未跟踪文件与路径漂移，迁移时必须保留现状而不是回退到 git 记录
- 理论文档目录内存在生成产物，路径更新时应优先保证主 `.md` 文本正确

## Success Criteria

- 仓库根目录不再直接承载 `daily-notes/`、`doc/`、`handoff/`
- `memory/` 目录结构完整
- `AGENT.md` 与 `CLAUDE.md` 的导航路径一致
- 项目主文档中不再继续使用旧路径描述当前结构
