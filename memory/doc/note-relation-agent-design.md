# Note Relation Agent 详细设计

## 定位

`Note Relation Agent` 是 `daily-notes -> doc -> sop` 正向链路中的第一个职责单元。

它的任务不是写 doc，也不是写 SOP，而是先回答一个更基础的问题：

> 新来的 daily note 与已有经验体系是什么关系，它应该推动哪些知识工件发生变化？

如果这个问题判断错了，后面的 `doc` 维护和 `sop` 提升都会变成低质量压缩。

## 当前范围

当前设计只覆盖**单一领域**。

这意味着：

- 当前仓库里的 notes / doc / SOP 默认都属于同一个领域上下文
- Agent 不需要先判断“这条 note 属于哪个领域”
- Agent 只需要在该领域内部做 task family、经验簇、文档影响面的判断

多领域路由、跨领域共享、跨领域冲突处理，全部留到后续设计。

## 非目标

这个 Agent 当前不负责：

- 直接写入 `memory/doc/`
- 直接写入 `memory/sop/`
- 做全库审查
- 对已有 SOP 做降级治理
- 解决多领域路由

它是一个 **triage + relation assignment** Agent，而不是维护 Agent。

## 核心职责

### 1. 发现新 note

识别哪些 daily notes 还没有进入正向链路。

### 2. 建立 note 关系

判断新 note 与历史 notes 的关系，例如：

- `continuation`
- `support`
- `conflict`
- `supersede`
- `replay-candidate`

### 3. 识别受影响的知识工件

判断这条新 note 影响哪些：

- 世界观 / 方法类 doc
- 专题 expert doc
- 阶段性 doc
- SOP 候选主题

### 4. 做第一次 context credit assignment

把新经验先分流到以下几类出口：

- 仅保留在 note
- 提交给 doc 维护
- 提交给 SOP 提升候选
- 标记为需要未来治理关注

## 输入

在当前阶段，这个 Agent 的最小输入应包括：

### 1. 新增 daily notes

这是本次处理的主输入。

### 2. 运行时状态

只需要支持正向链路所需的最小状态，例如：

- 哪些 notes 已经被 read
- 哪些 notes 已经被 triage
- 上一次处理到哪里
- 某条 note 当前对应的内容 hash 是什么
- 某条 note 是否已经产出 work order

这些状态属于运行时 bookkeeping，不属于新的知识层。

### 3. 邻近历史 notes

不是全量历史，而是与新 note 最可能相关的 note 子集：

- 时间上相邻
- task family 相近
- 被同一批 doc 引用过
- 共享相似失败模式或决策点

### 4. 当前 doc / SOP 轮廓

它不需要通读全部 doc / SOP，但至少要知道：

- 当前有哪些 doc
- 各 doc 的 scope 是什么
- 当前有哪些 SOP
- 哪些 SOP 已经覆盖了哪些程序性知识

当前建议优先从索引中读取这类轮廓信息：

- `memory/doc/INDEX.md`
- `memory/sop/INDEX.md`

如果索引暂时不存在，再回退到目录扫描。

## 输出

这个 Agent 的输出不应是新的长期知识文档，而应是**给后续 Agent 的工作单**。

逻辑上至少要包含下面几类结果：

### 1. note 关系判定

对每条新 note，给出它与哪些历史 notes 相关，以及关系类型是什么。

### 2. 受影响 doc 列表

指出哪些 doc 需要被更新，以及为什么需要更新。

### 3. SOP 候选信号

指出这条新 note 是否包含程序性知识，并且是否已经具备被提升为 SOP 候选的迹象。

### 4. 延后处理信号

当它发现冲突、覆盖、失效迹象，但当前阶段并不处理降级时，应把这些问题明确标记出来，交给未来的治理 Agent。

## 落盘格式：关系判断必须输出 JSON

关系判断不应只停留在 markdown 报告里，而应落成结构化 JSON，作为后续 Agent 的直接输入。

推荐同时落两类文件：

### 1. `runtime-state.json`

保存 Agent 的处理状态和 note 状态机。

### 2. `work-order/*.json`

保存某次 triage 的关系判断结果和后续动作建议。

markdown 报告可以保留，但它只是给人看；真正的 machine-readable 接口应该是 JSON。

当前第一版建议采用**一条 note 对应一份 work-order JSON**。

这样有三个好处：

- 幂等最简单
- 重试边界最清楚
- 后续 Agent 的接力最稳定

## 已读 notes 的设计

这个 Agent 必须显式处理“哪些 notes 已经读过”，否则会出现两类问题：

- 重复读取同一批 note，造成无谓成本
- note 被补充或修订后，系统却误以为已经处理过

所以它不能只记录“处理到哪个 note id”，还必须记录**读到的是哪个版本**。

### 为什么只记 note id 不够

因为 daily note 虽然默认 append-only，但允许追加更正说明。这样会出现：

- note id 没变
- 文件内容变了
- 旧的 relation 判断已经不一定成立

因此状态里至少要同时记录：

- note id
- 内容摘要或 hash
- 上次读取时间
- 上次完成 triage 的版本

## note 状态机

当前建议把每条 note 的运行时状态拆成下面几步：

- `discovered`
- `read`
- `triaged`
- `work_order_emitted`
- `forwarded`
- `deferred`

它们的含义分别是：

### `discovered`

系统发现了这条 note，但还没真正读取内容。

### `read`

系统已经读取了该版本的内容，并记录了 hash / read timestamp。

### `triaged`

系统已经完成关系判断和影响面判断。

### `work_order_emitted`

系统已经把判断结果落成 JSON 工作单。

### `forwarded`

工作单已经被后续 doc / SOP 维护链路接收。

### `deferred`

当前不进入正向链路，而是延后交给未来治理 Agent。

这套状态机的关键不是形式，而是要支持：

- 幂等重跑
- 出错恢复
- 内容变更后重读

## `runtime-state.json` 建议结构

当前阶段建议至少包含下面字段：

```json
{
  "run_count": 3,
  "last_run_started_at": "2026-03-19T12:00:00+08:00",
  "last_run_finished_at": "2026-03-19T12:00:08+08:00",
  "last_status": "updated",
  "last_note_discovered": "2026-03-19-01",
  "last_work_order_path": "jobs/note-relation/work-orders/20260319-120008-2026-03-19-01.json",
  "notes": {
    "2026-03-19-01": {
      "path": "memory/daily-notes/2026-03-19-01.md",
      "content_hash": "sha256:...",
      "status": "work_order_emitted",
      "first_seen_at": "2026-03-19T12:00:01+08:00",
      "last_read_at": "2026-03-19T12:00:02+08:00",
      "last_triaged_at": "2026-03-19T12:00:06+08:00",
      "last_work_order_id": "20260319-120008-2026-03-19-01",
      "needs_reread": false
    }
  }
}
```

### 最关键的不是字段多少，而是三件事

- 能知道某条 note 是否已经读过
- 能知道读的是不是当前版本
- 能知道是否已经为它发出工作单

## `work-order.json` 建议结构

每次 triage 至少输出一份 machine-readable JSON。

建议结构如下：

```json
{
  "work_order_id": "20260319-120008-2026-03-19-01",
  "created_at": "2026-03-19T12:00:08+08:00",
  "note_id": "2026-03-19-01",
  "note_path": "memory/daily-notes/2026-03-19-01.md",
  "note_hash": "sha256:...",
  "task_family": "daily-notes-to-doc-system-design",
  "relations": [
    {
      "target_note_id": "2026-03-17-01",
      "relation_type": "support",
      "reason": "复现了 notes->doc->sop 的正向提升主线"
    }
  ],
  "affected_docs": [
    {
      "action": "update-existing-doc",
      "doc_path": "memory/doc/daily-doc-sop-system-design.md",
      "reason": "补充单一领域边界与新建 doc 能力边界"
    }
  ],
  "sop_candidates": [],
  "credit_assignment": {
    "primary_destination": "doc-update",
    "secondary_destinations": [],
    "future_governance": []
  },
  "status": "ready_for_doc_agent"
}
```

### 这份 JSON 的作用

- 给 `Doc Maintenance Agent` 明确输入
- 给 `SOP Promotion Agent` 明确候选线索
- 给未来治理 Agent 保留冲突和失效信号

## reread 规则

为了处理“哪篇 notes 已经读过”这个问题，建议使用下面的 reread 规则：

### 1. 新 note

如果 note id 不在状态里，直接进入 `discovered -> read`。

### 2. 已读但未 triage 完成

如果已有状态但未到 `triaged`，重跑时应继续处理，不应跳过。

### 3. 已 triage 但内容 hash 变化

即使 note id 相同，也必须重新读取并重新生成 work order。

### 4. 已 triage 且 hash 未变

可以跳过全文重读，只读取必要状态信息。

这套规则决定了 Agent1 能不能真正做到可靠增量。

## 这个 Agent 的知识保存到哪里

这个问题必须拆开看，因为“Agent 知识”其实有三种完全不同的东西。

### 1. 领域知识

如果 `Note Relation Agent` 识别出的是**领域内稳定知识**，那它不应该保存在 Agent 私有位置，而应该仍然回到正式三层里：

- 局部、一次性的，继续留在 `memory/daily-notes/`
- 跨 task 稳定的，交给 `memory/doc/`
- 已程序化、可执行的，交给 `memory/sop/`

也就是说，这个 Agent 不应该拥有自己的长期知识库。

### 2. 运行时状态

如果保存的是“这个 Agent 处理到哪里了”，那应该进入运行时状态，而不是进入 `memory/`：

- 哪些 note 已 read
- 哪些 note 已 triage
- 哪些 note 已产出 work order
- 哪些 note 已被后续链路接收
- 哪些 note 暂时延后到未来治理

这些信息应存在 automation job 的 `state` 中，例如 `runtime-state.json` 一类文件。

### 3. 工作单和解释性产物

如果保存的是“这次 relation 判定的结果”，它也不应直接变成新的知识层，而应作为后续 Agent 的输入工单存在于运行时目录中，例如：

- `work-orders/`
- `reports/`
- `logs/`

这种产物的作用是接力，不是沉淀知识本体。

## 结论：不要给它再造一个 memory 层

所以，`Note Relation Agent` 的知识保存原则应该是：

- **领域知识**：只进 `daily-notes / doc / sop`
- **处理状态**：进 job state
- **分流结果**：进 work order / report

绝不能因为它要做关系判断，就额外长出一个长期存在的 `relation-memory/` 或 `triage-doc/` 目录。

## 单一领域下的判断单元

由于当前只做单一领域，`Note Relation Agent` 的主要判断单元不是“领域”，而是下面三层：

### 1. Task Family

例如同一个领域下的几类 recurring task。

这是最小的经验聚类入口。

### 2. Experience Cluster

若干条围绕同一问题、同一策略边界或同一失败模式的 notes，会形成一个经验簇。

这个经验簇不需要单独落成新架构，但 Agent 必须在工作时能识别它。

### 3. Affected Artifact Set

也就是这次经验簇会推动哪些现有知识工件发生变化。

## 核心工作流程

### Phase 1: New Note Discovery

1. 读取运行时状态
2. 找出未 triage 的新 notes
3. 按时间顺序进入处理队列

### Phase 2: Local Context Assembly

对每条新 note，组装一个最小 working set：

- 当前 note
- 时间上相邻的 notes
- 同类 task family 的代表性旧 notes
- 直接相关的 doc
- 可能相关的 SOP 标题或摘要

目标不是“读得越多越好”，而是读到足够做关系判断的最小上下文。

### Phase 3: Relation Assignment

判断这条新 note 与哪些旧 notes 存在以下关系：

- 是同一条任务链的续写
- 复现了旧结论
- 给旧结论补了新边界
- 与旧结论冲突
- 明显覆盖了旧结论

这一阶段输出的是“关系判断”，不是“最终知识写法”。

### Phase 4: Artifact Impact Detection

在关系判断之后，确定它对知识工件的影响：

- 是否应该更新某篇世界观/方法 doc
- 是否应该更新某篇专题 doc
- 是否应该影响某篇阶段性 doc
- 是否出现了 SOP 候选

### Phase 5: Credit Assignment

将经验分流到四类出口：

- `note-only`
- `doc-update`
- `sop-candidate`
- `future-governance`

这里的关键不是分类名字，而是让后续 Agent 接手时有明确边界。

### Phase 6: Emit Work Order

把结果写成后续 Agent 可消费的工作单，并更新运行时状态。

## 判断规则

### 1. 什么情况下只留在 note

- 经验局部且一次性
- 还看不出跨 task 价值
- 只是在补充事实，没有改变后续判断

### 2. 什么情况下推给 doc

- 经验已经影响后续决策
- 同类结论在多个 note 中重复出现
- 它不是特定 case 才成立的偶然细节

### 3. 什么情况下推给 SOP 候选

- 经验已经表现为稳定步骤
- 它面向具体领域动作
- 已经可以写出触发条件、步骤和成功标记

### 4. 什么情况下只标记为 future-governance

- 发现旧 doc 可能过时，但当前证据还不够
- 发现某个 SOP 可能被打破，但当前阶段不做降级
- 发现知识冲突，但还不能在当前链路里裁决

## 与 Agent 2 的接口

`Doc Maintenance Agent` 真正需要的不是“所有原始 notes”，而是一个被缩小后的变更范围。因此 `Note Relation Agent` 交给 Agent 2 的重点应该是：

- 哪些 doc 需要更新
- 每篇 doc 的更新原因
- 支撑这次更新的 notes 集合
- 哪些旧结论需要特别留意是否被修订

这会决定 Agent 2 是做“最小 patch”，还是被迫重扫大量文档。

这里还隐含一个关键能力：

- `update-existing-doc`
- `create-new-doc`

也就是说，`Note Relation Agent` 不仅要指出“改哪篇 doc”，还要能在没有合适目标文档时发出“应新建 doc”的信号。

## 与 Agent 3 的接口

`SOP Promotion Agent` 需要的不是通用总结，而是程序性知识线索。因此 `Note Relation Agent` 给 Agent 3 的重点应该是：

- 哪些 note / doc 片段已经体现稳定步骤
- 这些步骤针对的具体领域任务是什么
- 触发条件和成功标记是否已经初步可见
- 当前是否只是候选，还是已经接近可编译状态

## 新建 doc 的判定

当前设计里，如果出现下面情况，`Note Relation Agent` 应允许发出 `create-new-doc`：

- 新经验明显形成了一个独立专题，但现有 `memory/doc/` 中没有合适承载文档
- 把它硬塞进现有 doc 会导致 scope 混乱
- 这个主题预期会持续出现，而不是一次性记录

相反，下面情况不应该新建 doc：

- 只是补充某篇现有 doc 的一个小边界
- 只是单次 case 的局部结论
- 主题还没稳定到值得拥有独立 doc

所以“是否新建 doc”本身也是 relation assignment 的一部分。

## 当前系统能不能做到新建 doc

要分成“基础设施”和“现有实现”两层说。

### 1. 基础设施层面

可以。

当前 Codex runner 本身具备创建和编辑文件的能力，只要 task 允许写入目标路径，Agent 就可以新建 markdown 文档。

### 2. 当前 demo 实现层面

还不行。

目前仓库里的 `daily-notes-to-doc` demo 仍然是**固定目标文件集**：

- 目标目录被固定为 `memory/doc/daily-note-derived/`
- 目标文件被固定为 `README.md`、`current-state.md`、`decisions.md`、`open-questions.md`、`source-map.md`
- task prompt 也要求只维护这些文件

所以现在这套 demo 能做的是“刷新既定 doc 集合”，不能做“按主题自动新建真实 doc”。

## 如果要支持新建 doc，需要补什么

至少需要补三件事：

### 1. `create-new-doc` 工作单能力

`Note Relation Agent` 的输出里必须能显式区分：

- 更新已有 doc
- 新建 doc

### 2. doc 命名与落点规则

系统必须知道新 doc 应该如何命名、放在哪、scope 怎么写清楚。

否则 Agent 会开始随意命名和随意散落。

### 3. doc registry 或 doc index

新 doc 一旦创建，后续 Agent 需要知道它已经存在，否则同一主题会被重复创建。

这个 registry 更适合放在 `memory/doc/` 的索引文档里，而不是另造一层 metadata 系统。

## 失败模式

这个 Agent 最容易出现的错误有四类：

### 1. 过度提升

把一次性的 note 误送进 doc 或 SOP 候选。

### 2. 漏掉关系

没有看出新 note 与旧经验的连接，导致重复知识无法合并。

### 3. 错误影响面

把该更新专题 doc 的经验误送到世界观 doc，或者反过来。

### 4. 隐性冲突被忽略

新 note 实际上已经推翻旧结论，但 Agent 没有把它标记出来，后续知识会继续漂移。

## 运行时状态建议

当前阶段最小化即可，不需要复杂系统。逻辑上至少要有：

- `discovered`
- `read`
- `triaged`
- `work_order_emitted`
- `forwarded`
- `deferred`

这些状态用于保障正向链路幂等和接力，不承担知识本体功能。

如果只保留 `triaged / forwarded` 而没有 `read`，系统将无法准确回答“哪些 notes 已经读过但尚未完成分流”。

## 为什么它是第一个 Agent

因为当前系统真正要解决的不是“如何总结”，而是“该总结什么、总结到哪里”。

只要这个问题没有先被处理，后面的 doc 维护和 SOP 提升都会退化成：

- 全量扫描
- 大段重写
- 边界混乱
- 错误升格

所以 `Note Relation Agent` 本质上是整个正向链路的入口控制器。

## 一个压缩结论

在当前单一领域版本中，`Note Relation Agent` 的职责可以概括成一句话：

> 读取新 notes，识别它们与历史经验的关系，并把经验正确地分流到 `note`、`doc` 和 `sop` 的后续处理入口。

它不直接生产最终知识，但它决定最终知识会不会被写到正确的位置上。

再补一句更落地的话：

> 这个 Agent 不应该保存自己的长期知识；它只保存运行时状态和分流工作单，而真正的知识仍然只应该沉到 `daily-notes`、`doc` 和 `sop` 中。
