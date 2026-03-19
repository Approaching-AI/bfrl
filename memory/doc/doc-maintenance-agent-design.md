# Doc Maintenance Agent 详细设计

## 定位

`Doc Maintenance Agent` 是正向链路中的第二个职责单元。

它的任务不是判断关系，也不是提炼 SOP，而是把已经完成 relation assignment 的经验，稳定地写入真实的 `memory/doc/`。

一句话说：

> Agent1 负责判断“该改什么”，Agent2 负责把这些变化正确地落进 doc。

## 当前范围

当前设计只覆盖**单一领域 + 正向链路**。

这意味着：

- 只处理同一领域下的 doc 维护
- 只做新增、合并、修订、创建
- 不做全库审查
- 不做 doc 的系统性降级治理

## 非目标

这个 Agent 当前不负责：

- 自己重新做 note 关系判断
- 自己决定 SOP 是否应该降级
- 做全量 doc 重建
- 做跨领域路由

它是一个 **doc writer / doc updater** Agent，而不是 triage Agent，也不是 governance Agent。

## 核心职责

### 1. 消费 Agent1 的 work-order JSON

它以 `Note Relation Agent` 的结构化输出为主输入，而不是重新从零理解所有 notes。

### 2. 更新已有 doc

当 work-order 指向现有 doc 时，它应对目标文档做最小 patch。

### 3. 创建新 doc

当 work-order 给出 `create-new-doc` 且理由充分时，它应在 `memory/doc/` 下新建专题文档。

### 4. 维护 doc 索引

当 doc 新建或 scope 发生明显变化时，它应同步更新 `memory/doc/INDEX.md`。

### 5. 把程序性知识线索保留下来

它不负责写 SOP，但应把在 doc 更新过程中确认下来的程序性知识线索继续保留给 `SOP Promotion Agent`。

## 输入

### 1. Agent1 的 `work-order.json`

这是主输入。至少要包含：

- note id
- note hash
- relations
- affected docs
- credit assignment
- SOP candidate 信号

### 2. 支撑更新的 notes

它需要读取 work-order 中引用的相关 notes，而不是全量 daily notes。

### 3. 当前 doc 本体

如果目标是更新已有 doc，它需要读取文档当前版本。

### 4. doc 索引

当前建议优先读取：

- `memory/doc/INDEX.md`

用于知道：

- 已有哪些 doc
- 各 doc 的 title / scope / task family
- 当前主题是否已有合适落点

如果索引暂时不存在，第一版允许回退到目录扫描，并在本次成功写入 doc 后首次创建 `memory/doc/INDEX.md`。

### 5. 必要时读取相关 doc

如果某个专题 doc 与另一个世界观 doc 明显相关，它可以只读取必要片段，避免 scope 误判。

## 输出

这个 Agent 的输出应分成两层。

### 1. 长期知识输出

真正写回 `memory/doc/` 的内容：

- 更新后的已有 doc
- 新创建的 doc
- 更新后的 `memory/doc/INDEX.md`

### 2. 运行时输出

用于后续链路接力的 machine-readable JSON：

- `result.json`
- 必要时的 markdown report

## 文档更新原则

### 1. 最小 patch

默认不重写整篇 doc，而是：

- 新增必要结论
- 合并重复结论
- 修订被新 note 改写的结论
- 保留尚未解决的分歧

### 2. 直接证据优先

doc 中的新增或修订内容应优先直接指向 notes，而不是只引用另一个 doc。

换句话说：

- `doc` 可以互相链接导航
- 但关键结论最好仍能追到原始 notes

### 3. scope 不漂移

更新某篇 doc 时，不应让它逐渐变成“什么都装一点”的大杂烩。

如果新经验已经明显超出该 doc 的既有 scope，应优先考虑 `create-new-doc`。

### 4. 不把 doc 写成流水账

doc 是 expert context，不是 session dump。

所以它应该压缩经验，而不是按时间顺序重复记录事件过程。

## 什么时候更新已有 doc

以下情况优先 `update-existing-doc`：

- 新经验明显属于某篇 doc 已定义的 scope
- 只是补充、修订或细化已有结论
- 强行新建 doc 会造成主题碎片化

## 什么时候创建新 doc

以下情况允许 `create-new-doc`：

- 新经验已经形成稳定专题
- 现有 doc 都没有合适落点
- 把它硬塞进现有 doc 会造成 scope 混乱
- 预计该主题后续还会继续出现

## doc 的最低结构要求

当前不要求所有 doc 完全同构，但建议至少具备以下最小要素：

### 1. 标题

说明这篇 doc 在讲什么。

### 2. Scope

说明这篇 doc 负责什么，不负责什么。

### 3. 核心内容区

根据文档类型可以是：

- 当前判断
- 决策边界
- 常见失败模式
- 未解决问题
- 阶段性结论

### 4. Source notes

每条非平凡结论都应能追溯到支持它的 notes。

### 5. Related docs / SOPs

必要时给出相关文档和相关 SOP 的导航。

## `memory/doc/INDEX.md` 的职责

为了让 Agent 不依赖目录盲扫，建议把 `memory/doc/INDEX.md` 作为 doc registry。

它至少应记录：

- doc 标题
- 文件路径
- scope
- 主题或 task family
- 当前状态（active / draft / archived）

`Doc Maintenance Agent` 在以下场景必须更新索引：

- 新建 doc
- doc scope 发生实质变化
- doc 被归档或重命名

## 核心工作流程

### Phase 1: Load Work Order

1. 读取 `work-order.json`
2. 校验 note hash 和 note id
3. 判断目标动作是 `update-existing-doc` 还是 `create-new-doc`

### Phase 2: Build Evidence Set

1. 读取 work-order 指向的 notes
2. 读取目标 doc 或候选 doc
3. 必要时读取 `memory/doc/INDEX.md`
4. 只补充最少量相关 doc 片段

### Phase 3: Decide Target Doc Shape

如果是已有 doc：

- 判断是新增、修订还是合并

如果是新 doc：

- 确定 title
- 确定路径
- 确定 scope
- 确定初始结构

### Phase 4: Apply Patch

对目标 doc 做最小变更：

- 保留已有稳定结论
- 合并重复信息
- 加入新的证据支持
- 显式修订被改写的结论

### Phase 5: Update Doc Index

如有新 doc 或 scope 变化，更新 `memory/doc/INDEX.md`。

### Phase 6: Emit Result JSON

输出 machine-readable 结果，供后续链路使用。

## `result.json` 建议结构

```json
{
  "result_id": "20260319-130015-doc-update-2026-03-19-01",
  "source_work_order_id": "20260319-120008-2026-03-19-01",
  "created_at": "2026-03-19T13:00:15+08:00",
  "note_id": "2026-03-19-01",
  "doc_actions": [
    {
      "action": "updated",
      "doc_path": "memory/doc/daily-doc-sop-system-design.md",
      "reason": "补充单一领域边界与新建 doc 能力边界"
    }
  ],
  "new_doc_paths": [],
  "index_updated": true,
  "sop_signals": [],
  "status": "ready_for_sop_agent"
}
```

### 这份 JSON 的作用

- 让 `SOP Promotion Agent` 知道哪些 doc 已经被刷新
- 让系统知道这份 work-order 是否已经被 doc 链路消费
- 给未来治理 Agent 留下可追踪的变更记录

## 新建 doc 的命名原则

第一版应尽量保守，避免把命名自由度交给模型随意发挥。

建议至少满足：

- 文件名能表达主题
- 尽量使用稳定 slug
- 与已有 doc 不冲突
- 不把日期写进专题 doc 文件名，除非它本身就是阶段性纪要

也就是说：

- 专题 doc 用“主题命名”
- 阶段性 doc 才用“时间范围命名”

## 与 Agent1 的接口要求

如果 Agent1 要让 Agent2 真正好用，它给出的 work-order 至少需要清楚回答：

- 更新哪篇 doc，还是新建 doc
- 这条经验为什么应落到该 doc
- 支撑这次更新的 notes 是哪些
- 是否存在需要留意的旧结论

## 与 Agent3 的接口要求

Agent2 不负责写 SOP，但它更新 doc 时可能会发现某些程序性知识已经更清晰了。

因此它给 Agent3 的结果至少应包含：

- 本次更新后哪些 doc 更接近 SOP 候选
- 哪些步骤、触发条件、成功标记已经在 doc 中清晰出现
- 是否已有现成 SOP 需要更新而不是新建

## 失败模式

### 1. 过度创建 doc

稍有新意就新建 doc，最后导致 `memory/doc/` 碎片化。

### 2. 过度合并 doc

把不同主题硬塞进一篇 doc，最终 scope 漂移。

### 3. 证据链断裂

结论看起来合理，但追不到 notes。

### 4. 用旧 doc 包装新结论

表面上只是在“更新 doc”，实际已经引入了与原 scope 不兼容的新主题。

## 为什么它单独存在

因为“关系判断正确”与“文档写得稳定”是两种不同能力。

如果把这两件事揉在一起，最容易出现的问题是：

- Agent1 一边判断一边改写，失去最小变更边界
- 为了图省事直接重写整篇 doc
- create / update 的决策变得不透明

把 Agent2 单独定义出来，本质上是在给 `memory/doc/` 加一个稳定写入口。

## 一个压缩结论

`Doc Maintenance Agent` 的职责可以压成一句话：

> 消费 Agent1 的关系工作单，把稳定经验以最小 patch 的方式写入正确的 doc，并维护 doc 索引。

它是正式系统里负责“让 expert context 真正落盘”的那个 Agent。
