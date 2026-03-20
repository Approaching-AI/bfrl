# Daily Notes -> Doc -> SOP 方法论复核

## 目的

本文复核当前 `agents/` 中三段 Agent 设计是否符合 `bfrl` 的核心方法论，并给出一个更稳的 `daily-notes -> doc -> sop` 整理方案。

这里关注的不是“代码能不能跑”，而是：

- 这套拆分是否真的服务于 externalized policy update
- 它是否和 `memory/doc/` 中已经建立的理论一致
- 如果后续要继续扩展，最应该先改哪一层

## 先给结论

当前三段职责划分本身是合理的，但**把它们立即固化成三个持续接力的正式 Agent**，在方法论上有些偏早。

更准确的判断是：

1. `note relation -> doc maintenance -> sop promotion` 作为**三段职责边界**是对的。
2. 它们是否必须是**三个独立运行时 Agent**，当前还不是最关键的问题。
3. 当前系统更大的缺口不是“Agent 还不够多”，而是：
   - `daily note` 还缺少足够稳定的 policy-delta 表达
   - work order 的基本单元过于 `note-centric`
   - `memory/doc/` 还没有显式区分理论层、系统层、expert 层、交付层
   - 只有正向提升链路，还没有反熵 / 降级 / 漂移治理链路
   - retrieval / context assembly 还没有进入正式维护闭环

一句话压缩：

> 三段职责合理，三 Agent 运行时拆分暂时可用，但不应被误认为方法论终点。

## 为什么说当前三段职责是合理的

### 1. 它基本对齐了 `memory` 的三层压缩方向

当前设计把链路压成：

- Agent 1：判断经验该往哪里走
- Agent 2：把跨 task 的稳定知识写进 `memory/doc/`
- Agent 3：把稳定程序性知识编译进 `memory/sop/`

这和 `project-overview.md`、`domain-bfrl.md`、`domain-expert-formation.md` 中的总判断是一致的：

- `daily-notes` 是 episodic memory
- `doc` 是 expert context
- `sop` 是 compiled policy

所以，**作为“压缩职责”拆分，它是正交且清楚的。**

### 2. 它避免了新增长期知识层

当前设计坚持：

- 长期知识只留在 `memory/daily-notes/`、`memory/doc/`、`memory/sop/`
- `runtime/state/`、`runtime/work-orders/`、`runtime/reports/` 只是运行时协调工件

这点很重要，因为一旦在三层之间再长出一个长期 `derived/summary/intermediate` 层，系统就会从“policy compilation”滑回“自动摘要系统”。

### 3. 它把 SOP 明确成 executable policy

现在的设计没有把 SOP 当成“更详细的 doc”，而是明确要求：

- 触发条件
- 前置条件
- 步骤
- 检查点
- 异常分支

这和 `domain-expert-formation.md` 中“doc 压的是 expert context，SOP 压的是 executable policy”是对齐的。

## 当前设计真正的问题不在“三段职责”，而在“四个缺口”

## 缺口 1：工作单粒度过于 `note-centric`

当前 `Note Relation Agent` 的接口设计几乎把“一条 note 对应一份 work order”当成默认单位。

这在工程上有两个优点：

- 幂等简单
- 出错恢复边界清楚

但在方法论上也有一个明显代价：

- 真正值得进入 `doc` 或 `sop` 的知识，通常不是“某一篇 note 本身”，而是**多个 note 之间形成的经验簇**

也就是说：

- `note` 适合作为 ingest 和 ledger 的单位
- 但不一定适合作为 consolidation 的最终单位

如果长期坚持 per-note downstream work order，系统会倾向于：

- 频繁小修文档
- 难以看出跨 note 的重复结构
- 更容易过早 promotion
- 更难显式表达“这个 patch 其实由一个经验簇共同支撑”

所以更好的做法是：

- `per-note state` 继续保留，用于发现新 note、记录 hash、保障幂等
- 但 downstream work order 应逐步改成**per-cluster** 或 **per-affected-artifact patch set**

换句话说：

> note 是 ingestion 单元，不应被默认等同于 consolidation 单元。

## 缺口 2：当前链路只有“正向提升”，没有“反熵治理”

`memory/doc/` 核心方法论已经反复强调：

- 经验不仅会上升，也会失效
- SOP 会被新 case 打破
- doc 会漂移
- 旧知识应被降级、修订、合并或废弃

但现在正式 `/agents` 设计里，治理能力还停留在“以后再加 Audit / Demotion Agent”。

这作为第一阶段实现边界是可以接受的，但如果从方法论上看，必须明确：

> 没有治理闭环的 promotion system，不是完整的 BFRL memory system。

因此，后续正式设计里至少应把下面这条线提升成并列的一条 lane：

- `promotion lane`：note -> doc -> sop
- `governance lane`：audit -> merge / revise / demote / retire

不一定要立刻再造四五个 Agent，但方法论上必须承认它是主系统的一部分，而不是可有可无的边角。

## 缺口 3：`memory/doc/` 的角色还不够显式

当前 `memory/doc/` 里混合了几类完全不同的文档：

- 项目世界观 / 理论增量
- 系统设计 / runtime 架构
- 领域方法文档
- `daily-doc-sop` 这一套实现设计
- 未来还可能出现 task family expert doc
- 未来还可能出现阶段性总结或交付型 doc

这种混放在早期可以接受，但一旦 `Doc Maintenance Agent` 真开始长期自动维护，问题就会出现：

- 它到底应该默认维护哪一类 doc
- 哪些 doc 是 canonical expert context
- 哪些 doc 只是方法说明或阶段交付，不该被新 note 自动 patch

如果这个边界不先立起来，Agent 2 很容易出现两种偏差：

- 过度保守：只敢改少数现有文档，导致 expert context 长不出来
- 过度积极：把任何新经验都写进世界观文档或设计文档，导致 scope 漂移

所以 `memory/doc/` 最好尽早显式区分下面几层。

建议目录角色：

- `memory/doc/theory/`
  - 项目世界观、理论增量、BFRL 基本解释
- `memory/doc/system/`
  - agent runtime、orchestrator、runner contract、memory 维护机制
- `memory/doc/expert/`
  - 某个 task family / recurring issue 的 canonical expert context
- `memory/doc/reports/`
  - 阶段性总结、对外材料、受众定向文档

这样一来，自动维护的默认目标就会更清楚：

- `note -> doc` 主要写入 `expert/`
- `theory/` 和 `system/` 只有在方法论真的被改变时才更新
- `reports/` 不应默认成为自动 consolidation 的主落点

## 缺口 4：上游 `daily note` 还没有真正变成 policy-delta 载体

当前方法论文档已经说得很清楚：

- daily note 不应只是工作纪要
- 它应至少能让后续 agent 看出 task family、outcome、关键判断点、信号、delta candidate、目标层级

但从现有 daily notes 看，记录仍然主要是：

- 本次做了什么
- 修了哪些实现问题
- 得出了哪些总体结论

这类笔记对人和项目都很有用，但对 `Note Relation Agent` 来说，推理负担仍然偏重。

因此，在继续强化三 Agent 之前，更值得先补的是：

- 一个**轻量但稳定的 daily note schema**

不需要把 note 压成僵硬 JSON，但建议至少长期保留这些 section：

- `Task family`
- `Outcome card`
- `Key decisions`
- `Useful signals`
- `Misleading signals`
- `Policy delta candidate`
- `Proposed destination`
- `Invalidated artifacts`

只要这些 section 稳定存在，Agent 1 的 relation assignment 才会从“强推理”慢慢变成“弱推理 + 强证据”。

## 更稳的设计：保留三段职责，但调整成“两层闭环 + 一条治理线”

## 第一层：Consolidation Loop

这一层负责把 rollout 经验变成可复用策略。

内部仍然保留三段职责，但不必执着于三份长期独立运行时：

1. `relation / triage`
   - 识别 experience cluster
   - 判断受影响 artifact
2. `expert doc maintenance`
   - 维护 canonical expert docs
3. `sop compilation`
   - 把稳定程序性知识编译成 SOP

这三段可以是：

- 三个独立 Agent
- 一个 Agent 的三个 phase
- 或者一个主 Agent + 两个按需唤醒的子 phase

方法论上最重要的是**边界清楚**，不是**进程数固定为三**。

这里还有一个具体边界值得补清楚：

- `Note Relation Agent` 适合输出 procedural hints
- `Doc Maintenance Agent` 才适合第一次正式判断“是否形成 SOP promotion signal”
- `SOP Promotion Agent` 再负责最终编译与写入

否则 Agent1 太容易因为过早 promotion framing，而压缩掉后续 Agent 还需要重新判断的信息。

## 第二层：Retrieval Loop

这是当前正式系统还没有进入主链路、但从 BFRL 角度不能一直缺位的一层。

要明确：

- 不是“写进 doc / SOP”就等于学习完成了
- 只有后续 rollout 真正把它们读进 working set，policy update 才算发生

因此，后续应把 retrieval policy 也视为正式维护对象，例如：

- 当前 task family 优先读哪些 expert docs
- 优先读最近失败样本还是最近成功样本
- 什么时候触发某个 SOP
- 哪些 note 只适合 replay，不适合常驻上下文

这层不一定要立刻变成独立 Agent，但应进入正式文档设计，而不是永远停留在“以后再说”。

## 第三条线：Governance Lane

这是 promotion lane 的反向平衡器。

建议后续至少覆盖四类治理动作：

1. `unabsorbed note audit`
   - 检查哪些 note 长期没有影响任何 doc
2. `doc drift audit`
   - 检查哪些 doc 结论已被新 note 冲击
3. `sop breakage audit`
   - 检查哪些 SOP 被多个新 case 反复打破
4. `demotion / merge / retire`
   - 把不稳定 SOP 降回 doc
   - 合并重复 doc
   - 归档过时文档

## 建议的组织方式

如果只从 `daily-notes -> doc -> sop` 的整理效率看，我建议采用下面的组织方式。

## 1. Daily Notes：保持自然语言，但增加稳定骨架

目标：

- 继续让 note 适合人写
- 同时让 Agent 能更可靠地读出 policy delta

建议最小结构：

```md
# <session title>

- operator: <name>
- task family: <slug>
- outcome: success | partial | fail

## Context Loaded

## Key Decisions

## Useful Signals

## Misleading Signals

## Policy Delta Candidate

## Proposed Destination

## Invalidated Artifacts

## Next Replay / Next Step
```

这里最重要的不是格式统一，而是让后续 consolidation 能稳定找到：

- 这次经验属于哪一类任务
- 它改变了什么
- 它应该落到哪层

## 2. Doc：明确只有 `expert/` 是自动 consolidation 的默认主战场

建议把 `memory/doc/` 拆成角色明确的子目录后，再让 Agent 2 真正自动长期维护。

推荐职责：

- `theory/`
  - 项目总体理论，不作为高频自动 patch 目标
- `system/`
  - 运行时架构、agent 方法，不作为高频自动 patch 目标
- `expert/`
  - 自动 consolidation 的默认目标目录
- `reports/`
  - 人类或阶段性交付导向文档，不作为默认自动 patch 目标

同时建议强化 `memory/doc/INDEX.md`，至少记录：

- path
- doc type
- scope
- maintenance mode
- current status
- source note families

## 3. SOP：按 task family / workflow 组织，而不是按“更详细说明”组织

`memory/sop/` 建议天然按 task family 或 workflow 切分。

每个 SOP 除当前已有的：

- trigger
- preconditions
- steps
- checkpoints
- exceptions

还建议加两个字段：

- `stability evidence`
  - 由哪些 notes / docs 支撑
- `demotion trigger`
  - 什么现象出现时应怀疑它已经不稳

这样 SOP 就不是只会上升、不知道何时该降级的单向制品。

## 4. Work Order：从“每 note 一单”升级为“每 note 入账 + 每经验簇/工件一单”

推荐的中间态做法不是推翻当前 runtime，而是把它升级成双层输出：

### 第一层：per-note ledger

继续保存：

- note id
- hash
- read status
- triaged status

这层主要是幂等与恢复。

### 第二层：per-cluster / per-artifact patch order

真正交给 Agent 2 / Agent 3 的应逐步变成：

- 本轮识别出的 experience cluster
- cluster 涉及哪些 notes
- 它共同支撑哪个 expert doc patch
- 它是否共同满足 SOP promotion 前提

这样可以同时保留工程稳定性和方法论正确性。

## 推荐的阶段化落地顺序

## Phase 1

保留当前三 Agent runtime，不急着推翻。

但先完成三件事：

1. 统一 daily note 轻量 schema
2. 给 `memory/doc/` 明确角色分层
3. 在方法论文档里把“promotion lane 不是完整系统”写清楚

## Phase 2

升级 `Note Relation Agent`：

- 继续做 per-note ingest
- 但开始输出 cluster-aware 的 downstream patch order

## Phase 3

引入治理 lane：

- 先从 audit 开始
- 再增加 demotion / merge / retire

## Phase 4

把 retrieval / context assembly 正式纳入维护范围。

也就是承认下面这些对象同样属于可更新 policy substrate：

- retrieval policy
- working-set assembly policy
- outcome harness interpretation

## 一个最终判断

如果只问“当前三个 Agent 合不合理”，我的答案是：

- **合理，但应被理解为三段压缩职责，而不是已经定型的最终系统形态。**

如果再进一步问“有没有更好的 `daily-notes -> doc -> sop` 整理方式”，我的答案是：

- **有。最值得改的不是再细拆 Agent，而是把系统从 per-note promotion chain 升级为 cluster-aware consolidation loop，并尽快补上 doc taxonomy、daily note schema、governance lane 和 retrieval loop。**

一句话版结论：

> 保留三段职责，弱化对“三个独立 Agent”这件事的执念；把真正的设计重心前移到 note schema、experience cluster、expert doc registry、SOP 证据边界，以及后续治理闭环。
