# SOP Promotion Agent 详细设计

## 定位

`SOP Promotion Agent` 是正向链路中的第三个职责单元。

它的任务不是判断 note 关系，也不是维护 general doc，而是把已经足够稳定的程序性知识编译成 `memory/sop/` 下的领域执行步骤。

一句话说：

> Agent1 决定哪些经验值得继续推进，Agent2 让这些经验进入 doc，Agent3 决定哪些 doc 中的程序性知识已经可以编译成 SOP。

## 当前范围

当前设计只覆盖**单一领域 + 正向提升**。

这意味着：

- 只负责 `doc -> sop`
- 只负责创建或更新 SOP
- 不负责 SOP 审查
- 不负责 SOP 降级
- 不负责跨领域 SOP 组织

## 非目标

这个 Agent 当前不负责：

- 自己重新做 note relation assignment
- 全库审计现有 SOP
- 把 SOP 降级回 doc
- 定义未来治理 Agent 的编排

它是一个 **promotion / compilation** Agent，而不是 governance Agent。

## 核心职责

### 1. 读取 SOP 候选信号

这些信号可能来自：

- Agent2 的 `result.json`
- 必要时回溯 Agent1 work-order 中保留下来的程序性知识线索，作为证据链补充，而不是作为最终裁决

### 2. 判断是否满足 SOP 条件

不是所有程序性知识都能进 SOP。它必须判断：

- 是否足够稳定
- 是否足够具体
- 是否已经具备触发条件、步骤和成功标记

### 3. 创建或更新 SOP

一旦条件满足，就把程序性知识编译为 `memory/sop/` 下的 runbook。

### 4. 维护 SOP 索引

新建或实质更新 SOP 时，应同步维护 `memory/sop/INDEX.md`。

## 输入

### 1. 上游候选信号

至少包括：

- doc maintenance result 中的 `sop_signals`
- 必要时可回读上游 work-order 中的 `procedural_hints`

### 2. 支撑这些候选的 doc

SOP 不是从原始 note 直接跳出来的，它通常建立在已经稳定化的 doc 上。

### 3. 必要的原始 notes

当需要核实程序性知识是否真的被多个 case 支持时，可以回读关键 notes。

### 4. 当前 SOP 索引

当前建议优先读取：

- `memory/sop/INDEX.md`

用于知道：

- 已有哪些 SOP
- 各 SOP 的 scope 是什么
- 该更新已有 SOP 还是创建新 SOP

如果索引暂时不存在，第一版允许回退到目录扫描，并在本次成功写入 SOP 后首次创建 `memory/sop/INDEX.md`。

## 输出

### 1. 长期知识输出

真正写回 `memory/sop/` 的内容：

- 新建的 SOP
- 更新后的 SOP
- 更新后的 `memory/sop/INDEX.md`

### 2. 运行时输出

供链路继续接力的 machine-readable JSON：

- `promotion-result.json`

## 什么样的内容才能进入 SOP

以下条件应尽量同时满足：

### 1. 面向具体领域动作

它不是抽象原则，而是实际可执行的任务步骤。

### 2. 触发条件清楚

系统知道什么时候该调用这个 SOP。

### 3. 结束条件清楚

系统知道什么时候算完成，或者至少知道什么是成功标记。

### 4. 步骤已经稳定

它不是一次性路径，而是被多个 note / case 反复支持过。

### 5. 对后续 Agent 有直接执行价值

写成 SOP 后，后续 Agent 能明显减少试错。

## 什么样的内容不应该进入 SOP

- 只是背景解释
- 只是某次 case 的偶然路径
- 步骤边界仍然模糊
- 结论频繁被新 case 打破

这些内容应该继续留在 `memory/doc/`。

## SOP 的最低结构要求

参考 `sinopec/docs/sop/`，当前建议每个 SOP 至少具备：

### 1. 触发条件

什么时候应该调用这个 SOP。

### 2. 前置条件

执行前默认已经满足的环境条件。

### 3. 执行步骤

按顺序给出主流程。

### 4. 检查点 / 成功标记

如何判断当前步骤是否成功，如何判断 SOP 是否完成。

### 5. 常见异常分支

如果执行时遇到常见故障，应转到哪里，或者怎样处理。

### 6. 关联文档

必要时给出相关 doc 和相关 SOP。

### 7. Source notes / source docs

SOP 不是凭空发明出来的，应能追溯到支撑它的 doc 和 notes。

## 创建新 SOP 还是更新已有 SOP

### 1. 更新已有 SOP

以下情况优先更新：

- 候选内容明显属于某个现有 SOP 的 scope
- 只是新增检查点、异常分支或前置条件
- 只是让已有步骤更清楚

### 2. 创建新 SOP

以下情况允许新建：

- 程序性知识已经形成独立流程
- 现有 SOP 都没有合适落点
- 强行塞进已有 SOP 会导致 scope 失真

## `memory/sop/INDEX.md` 的职责

为了避免 SOP 重复创建，建议把 `memory/sop/INDEX.md` 作为 SOP registry。

它至少应记录：

- SOP 标题
- 文件路径
- 触发场景 / scope
- 依赖的 doc 或相关 SOP
- 当前状态

`SOP Promotion Agent` 在以下场景必须更新索引：

- 新建 SOP
- SOP scope 发生实质变化
- SOP 被重命名或归档

## 核心工作流程

### Phase 1: Load Candidate

1. 读取上游 JSON 输入
2. 判断候选是否进入本轮 promotion
3. 验证候选引用的 doc / notes 是否可读

### Phase 2: Build Evidence Set

1. 读取相关 doc
2. 读取必要的原始 notes
3. 读取当前 `memory/sop/INDEX.md`
4. 必要时读取候选范围内的现有 SOP

### Phase 3: Promotion Decision

做三选一判断：

- `create-new-sop`
- `update-existing-sop`
- `retain-in-doc`

当前阶段不做 `demote-sop`。

### Phase 4: Compile SOP

如果进入前两种分支，就把程序性知识编译为 SOP 结构：

- 触发条件
- 前置条件
- 主步骤
- 检查点
- 异常分支
- 相关文档
- Source notes / docs

### Phase 5: Update SOP Index

如果有新建或重要更新，就更新 `memory/sop/INDEX.md`。

### Phase 6: Emit Promotion Result JSON

把 promotion 结果写成 machine-readable JSON，供系统追踪。

## `promotion-result.json` 建议结构

```json
{
  "promotion_result_id": "20260319-140022-sop-promotion-2026-03-19-01",
  "created_at": "2026-03-19T14:00:22+08:00",
  "source_ids": [
    "20260319-120008-2026-03-19-01",
    "20260319-130015-doc-update-2026-03-19-01"
  ],
  "decision": "retain-in-doc",
  "reason": "程序性知识已出现，但触发条件和结束条件仍不够稳定",
  "sop_actions": [],
  "index_updated": false,
  "status": "completed"
}
```

### 当 decision 是 `create-new-sop` 或 `update-existing-sop`

`sop_actions` 中至少要包含：

- action
- sop_path
- reason

## `retain-in-doc` 也是合法输出

这一点很重要。

`SOP Promotion Agent` 不应该因为自己存在，就强行把所有程序性知识升格为 SOP。

如果当前证据还不够，它完全可以输出：

- `retain-in-doc`

这不是失败，而是正常结果。

## 与 Agent2 的接口要求

Agent2 给 Agent3 的输入至少需要清楚回答：

- 哪些 doc 已被刷新
- 哪些片段已经表现出稳定步骤
- 哪些候选仍然不足以 promotion
- 是否应该更新已有 SOP 而不是创建新 SOP

## 失败模式

### 1. 过早 promotion

程序性知识还不稳定，就被写成 SOP。

### 2. SOP 过于抽象

看起来像“原则总结”，不是 runbook。

### 3. SOP scope 混乱

多个不同流程被混进一个 SOP，导致触发边界不清。

### 4. 忽略前置条件

步骤本身看起来对，但执行时其实依赖一堆没写明的环境条件。

### 5. 重复创建 SOP

已有 SOP 已经能承载，但系统又新建了一个相似文件。

## 为什么它单独存在

因为“写 doc”和“编译 SOP”是两种完全不同的压缩。

- doc 压缩的是 expert context
- SOP 压缩的是 executable policy

如果把两者混在一个 Agent 里，很容易出现：

- doc 被写成步骤列表
- SOP 被写成概念说明
- promotion 边界失真

所以 Agent3 的存在，是为了给 `memory/sop/` 单独保留一个“只面向执行步骤”的写入口。

## 一个压缩结论

`SOP Promotion Agent` 的职责可以压成一句话：

> 读取上游候选和已稳定化的 doc，把真正成熟的程序性知识编译成领域 SOP，并维护 SOP 索引。

它负责的不是“再总结一遍”，而是把知识变成可以执行的 runbook。
