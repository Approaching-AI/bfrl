# Daily Notes -> Doc -> SOP 系统设计

## 定位

本文定义 `bfrl` 中正式的 `daily-notes -> doc -> sop` 维护系统，用于替代 demo 阶段的派生层实验设计。

目标不是再增加一层新的 memory 架构，而是在**不改变 `memory/daily-notes/`、`memory/doc/`、`memory/sop/` 三层分工**的前提下，让 Agent 能持续完成：

- 从 daily notes 中识别可复用经验
- 将跨 task 的稳定经验直接维护到 `memory/doc/`
- 将已稳定、可执行、面向具体领域的流程维护到 `memory/sop/`
- 为后续审查和降级治理保留清晰边界

这套系统的设计前提来自：

- `AGENT.md` 对 memory hierarchy 的定义
- `meta-agent/doc/methodology.md` 对 daily notes / doc / SOP 的基本分工
- `sinopec` 项目中已经跑出来的现实形态：daily notes 是细粒度过程记录，doc 是面向主题和受众的认知快照，SOP 是面向某一领域任务的具体执行步骤

## 当前实现范围

当前先实现**正向提升链路**：

- `daily-notes -> doc`
- `doc -> sop`

也就是说，先把“如何从新经验里提炼出稳定知识，并进一步提炼成领域执行步骤”这条链路做扎实。

当前还增加一个明确边界：

- **只设计单一领域内的正向链路**

也就是说，当前默认 `memory/daily-notes/`、`memory/doc/`、`memory/sop/` 都服务于同一个领域上下文。如何在多个领域之间做路由、隔离、共享与冲突处理，是后续再解决的问题，不属于这第一阶段设计。

以下内容暂时不纳入当前实现范围：

- 面向全库的持续审查
- 已有 doc / SOP 的系统性降级
- 冲突知识的长期治理
- 额外的审计或治理 Agent 编排
- 多领域之间的组织与切换

这些工作后续可以交给新的 Agent 处理，但该 Agent 是否单独存在、是否拆成多个 Agent、如何调度，目前都可以待定。

## 约束

### 1. 不新增知识层

正式系统不能在 `daily-notes`、`doc`、`sop` 之间再插入一个长期存在的 `derived` / `summary` / `intermediate` 层。

可以存在的只有两类东西：

- **知识工件**：`memory/daily-notes/`、`memory/doc/`、`memory/sop/`
- **运行时状态**：轮询状态、processed note ledger、refresh time、审计报告等

运行时状态只服务自动化，不承担知识沉淀职责。

### 2. SOP 必须是领域执行步骤

`memory/sop/` 中的内容不是“更详细的 doc”，而是某个领域中可执行的 runbook。

参考 `sinopec/docs/sop/` 可以看出，成熟 SOP 至少具备：

- 触发条件 / 起始条件
- 结束条件或成功标记
- 明确步骤顺序
- 常见错误与分支处理
- 与其他 SOP 的依赖关系

因此，`doc -> sop` 的提升不是“再总结一下”，而是“把稳定知识编译成领域动作序列”。

### 3. 索引文件仍然属于原层级

为了让 Agent 能知道当前有哪些 doc / SOP，以及它们各自的 scope，允许在原有层级中维护索引文件，例如：

- `memory/doc/INDEX.md`
- `memory/sop/INDEX.md`

这不构成新的知识层，因为索引仍然分别属于 `doc` 和 `sop` 自身，只是帮助 Agent 检索和导航。

## 为什么 demo 不能直接变成正式系统

demo 中的 `daily-note-derived/` 证明了三件事：

- 新 note 的增量处理是可做的
- 幂等处理和 source-map 审计是可做的
- `source agent + audit agent` 的轮询闭环是可做的

但它不适合作为正式架构，原因是：

1. 它把 `doc` 误收敛成了单一派生目录，而真实项目里的 doc 是多份、面向不同主题和受众的快照集合。
2. 它弱化了 `note <-> note`、`note <-> doc`、`doc <-> sop` 的多对多关系。
3. 它还没有把 SOP 作为“领域执行策略”纳入系统主循环。

正式系统要保留 demo 的自动化优点，但写回到真实 `memory/doc/` 和 `memory/sop/`。

还需要明确一点：

- **基础 runner 具备创建文件能力**
- **但当前 demo 实现仍然只会维护固定 doc 集合，不能按主题自动新建真实 doc**

所以“允许创建新 doc”是正式系统要补上的能力，不是当前 demo 已经具备的能力。

## 核心对象

### 1. Daily Note

`daily note` 是一次 rollout 或一次 session 的 episodic memory。它不是普通工作纪要，而是 policy delta 的候选载体。

正式系统要求 note 至少能让后续 Agent 读出下面信息：

- 当前任务属于什么 task family
- 本次实际 outcome 是什么
- 哪些判断点影响了 outcome
- 本次依赖了哪些已有 context
- 这次新增了什么经验
- 这次推翻了什么旧经验
- 这条经验更可能沉到 note、doc 还是 SOP

这些信息不要求被压成僵硬表格，但需要通过稳定 section 或稳定表达方式可被后续 Agent 识别。

### 2. Doc

`doc` 是 expert context 的主题快照，不是“所有 notes 的总摘要”。

一个 note 可能影响多篇 doc，例如：

- 世界观与方法类 doc
- 某一 task family 的专题 doc
- 某个阶段性总结 doc
- 面向特定受众的交付型 doc

这在 `sinopec` 中已经出现了现实例子：同一批日常工作记录最终支撑了阶段纪要、内部性能分析、客户版报告和可行性研究等不同文档。

因此正式系统要把 `doc` 视为**按主题维护的快照集合**。

### 3. SOP

`sop` 是从 doc 和 notes 中编译出的领域执行流程。

一条知识进入 SOP 的前提不是“重要”，而是：

- 它已经形成了稳定步骤
- 它的起止边界清楚
- 它能直接指导领域操作
- 它已经过多次 note 或多个 case 的支持

换句话说，SOP 是 compiled policy，不是 expanded summary。

## 关系模型

### 1. Note 与 Note 的关系

正式系统必须显式处理五种 note 关系：

- `continuation`：同一任务链的延续
- `support`：支持既有结论
- `conflict`：与既有结论冲突
- `supersede`：新经验覆盖旧经验
- `replay-candidate`：值得后续重放的关键样本

这里最重要的不是“把图存在哪”，而是让后续 Agent 能判断一篇新 note 和哪些旧 note 构成同一经验簇。

### 2. Note 与 Doc 的关系

`note -> doc` 不是一对一，而是多对多。

- 一条 note 可以给多篇 doc 供证
- 一篇 doc 的一条结论也可能来自多条 note 的共同支持
- 一条新 note 还可能推翻 doc 中的旧结论

因此 doc 更新的单位不是“整篇重写”，而是“对受影响结论做最小修订”。

### 3. Doc 与 SOP 的关系

`doc -> sop` 是编译关系，`sop -> doc` 是降级关系。

- 当某条 doc 中的程序性知识变得稳定、可执行、边界清晰时，提升为 SOP
- 当某个 SOP 被新 case 持续打破时，降级回 doc，重新作为启发式或领域知识维护
- doc 与 SOP 也是多对多关系：一条 doc 中的结论可能被编译到多个 SOP 中，而一个 SOP 也可能依赖多篇 doc 的知识支持

## 三段职责与 Agent 边界

轮询器本身只负责调度，不算知识 Agent。

当前文档先定义三段职责边界，用于实现正向链路：

1. note 关系识别
2. doc 维护
3. SOP 提升

它们可以先由一个 Agent 串行完成，也可以后续再拆成多个独立 Agent。这里定义的是**职责边界**，不是必须立即落成“三个独立运行时进程”。

### Agent 1: Note Relation Agent

详细设计见：`memory/doc/daily-doc-sop/note-relation-agent-design.md`

#### 职责

负责读取新增 daily notes，识别其与历史 notes / docs / SOP 的关系，并产出“本次应该改哪些知识工件”的工作判断。

#### 它要解决的问题

- 识别哪些是新的 notes
- 这篇新 note 属于哪个 task family
- 它与哪些旧 notes 是延续、支持、冲突或覆盖关系
- 它应该影响哪些 doc
- 它是否足以触发 SOP 候选
- 它是否暴露了需要后续治理的失效信号

#### 设计方式

它不直接大量改写文档，而是做 **relation-first triage**：

0. 维护每条 note 的状态
1. 读取新 note
2. 检索时间上相邻、主题上相近、被同一 doc 引用过的历史 notes
3. 检索可能受影响的 doc 与 SOP
4. 做一次 context credit assignment
5. 产出本次变更的目标集合：
   - 保持在 note
   - 更新哪些 doc
   - 提交给 SOP 候选
   - 标记哪些旧结论可能失效

它的核心价值是减少后续 Agent 的盲改和全量扫描成本。

### Agent 2: Doc Maintenance Agent

详细设计见：`memory/doc/daily-doc-sop/doc-maintenance-agent-design.md`

#### 职责

负责把 Agent 1 识别出的稳定经验真正写入 `memory/doc/` 中的真实文档，而不是写入一个新的中间目录。

#### 它要解决的问题

- 哪篇 doc 应该吸收这次经验
- 这次是新增结论、合并结论、修订结论，还是标记冲突
- 一条结论的支持 notes 是哪些
- 某篇 doc 是否已经因为新 notes 出现明显过时

#### 设计方式

它按“受影响 doc 集合”工作，而不是按“所有 doc 全量重建”工作：

1. 读取 Agent 1 给出的受影响 doc 列表
2. 读取对应 doc 的当前内容
3. 读取支撑本次更新所需的旧 notes、新 notes、相关专题 doc
4. 做最小 patch：
   - 合并重复经验
   - 保留尚未解决的分歧
   - 对被推翻的结论显式修订
   - 补充 source notes
5. 维护 doc 内部的稳定结构，例如：
   - 当前判断
   - 决策边界
   - 常见失败模式
   - 未解决问题
   - Source notes

它的目标不是把 doc 写成流水账，而是维护 expert-level context。

### Agent 3: SOP Promotion Agent

详细设计见：`memory/doc/daily-doc-sop/sop-promotion-agent-design.md`

#### 职责

负责将已经稳定的程序性知识从 `memory/doc/` 提升到 `memory/sop/`。

#### 它要解决的问题

- 哪些知识已经具备 SOP 条件
- 应该形成哪一类领域执行步骤
- 一个 SOP 的触发条件、结束条件和步骤该如何表达

#### 设计方式

它不是“再写一份总结”，而是面向领域动作设计 runbook：

1. 读取某个专题 doc 及其关联 notes
2. 判断其中哪些部分是稳定的程序性知识
3. 将其编译成 SOP 结构：
   - 触发条件
   - 前置条件
   - 步骤
   - 检查点 / 成功标记
   - 异常分支
   - 下一步或关联 SOP
4. 将输出直接写入 `memory/sop/`

这个 Agent 的设计应直接参考 `sinopec/docs/sop/` 的风格，而不是参考派生摘要文档。

### 未来扩展：Audit / Demotion Agent

后续应增加一个新的 Agent，专门处理审查、漂移发现和降级治理，但它不属于当前第一阶段的实现范围。

这个未来 Agent 至少可能负责：

- 检查新 note 是否没有被任何 doc 吸收
- 检查 doc 中是否存在被新 note 推翻但未修订的结论
- 检查某个 SOP 是否已经被多个新 case 打破
- 判断某个 SOP 是否需要降级回 doc
- 判断某些 doc 是否长期过时、冲突或重复

但这个 Agent 是否单独存在、是否再拆成多个治理 Agent、是否与主链路同步运行，当前都可以待定。

## 当前正向链路的顺序

一次新的 note 到来后，推荐的顺序是：

1. `Note Relation Agent`
   - 判断关系
   - 识别受影响 doc / SOP
2. `Doc Maintenance Agent`
   - 更新真实 doc
   - 写入或修订证据链
3. `SOP Promotion Agent`
   - 将稳定程序性知识提升为 SOP

这比“一个 agent 全包”更稳定，因为三者优化目标不同：

- Agent 1 追求正确分配
- Agent 2 追求知识压缩
- Agent 3 追求流程可执行性

如果在实现阶段发现拆成三个 Agent 成本太高，也可以先让一个 Agent 依次执行这三段职责，只要输出边界保持一致即可。

## 正式系统中 doc 的组织原则

参考 `sinopec`，正式系统中的 `memory/doc/` 应允许至少三类真实文档共存：

### 1. 世界观 / 方法类 doc

例如：

- 项目总纲
- 理论增量说明
- domain BFRL 方法

这些 doc 回答“这个项目怎么看世界、怎么定义问题”。

### 2. 专题 expert doc

围绕某个 task family 或某个 recurring issue 形成的稳定专题文档。

这些 doc 回答“某一类问题当前最稳定的理解是什么”。

### 3. 阶段性或受众定向 doc

例如阶段纪要、内部总结、交付型说明文档。

这些 doc 仍然属于 `doc`，但它们的 scope 更明确，通常引用一段时间范围内的 notes 和专题 doc。

因此，正式系统不应假设“daily notes 最终只能压成一套固定文件”，而应支持一批 notes 直接扇出到多份 doc。

## SOP 的正式标准

一条知识只有满足以下条件，才应进入 `memory/sop/`：

1. 面向具体领域任务，而不是抽象原则
2. 含有清晰触发条件
3. 含有可执行步骤
4. 含有结束条件或成功标记
5. 已被多个 note / case 支持
6. 对后续 Agent 真的能直接减少试错成本

不满足这些条件的内容，应继续留在 `memory/doc/` 中作为领域知识、失败模式或启发式。

## 未来审查与降级原则

下面这些原则是未来 Audit / Demotion Agent 应重点处理的内容，不属于当前第一阶段主链路的硬实现范围：

- 新 note 是否没有被任何 doc 吸收
- 某篇 doc 是否长期没有被新 note 更新却已经明显过时
- doc 中是否存在被新 note 推翻但未修订的结论
- 某个 SOP 是否已经被多个新 case 打破
- `doc` 和 `sop` 的边界是否混乱，导致 SOP 退化为说明书

这里的审计不是只查格式，而是查知识漂移与策略失效。

## 一个压缩结论

`daily-notes -> doc -> sop` 的正式系统，不是“自动摘要系统”，而是一个面向 externalized policy update 的三 Agent 维护系统：

- `Note Relation Agent` 负责关系判定与信用分配
- `Doc Maintenance Agent` 负责 expert context 的直接维护
- `SOP Promotion Agent` 负责把稳定领域知识编译成执行流程

而审查、漂移发现、降级治理属于后续单独增加的 Agent 范围，当前可以先不把这部分架构写死。

其中最关键的原则只有两个：

1. 不在 `daily-notes`、`doc`、`sop` 之间增加新的长期知识层
2. 把 SOP 明确定义为某个领域中的具体执行步骤，而不是“更详细的总结”

这才符合 `bfrl` 的世界观，也与 `sinopec` 中已经长出来的真实组织方式一致。
