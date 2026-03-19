# 特定领域专家能力的形成：作为 Externalized Policy Update 的知识沉淀

## 核心命题

如果 BFRL 的目标是不改基座模型权重而持续提升 agent 在特定领域中的表现，那么“知识沉淀”就不能被理解成普通的知识库建设，而必须被理解成：

> 把 rollout 中产生的可复用策略变化，外部化到 `memory/daily-notes/`、`memory/doc/`、`memory/sop/` 以及相关检索/评估工件中，使同一个基模在后续任务中真的变得更会做。

这意味着，判断知识沉淀是否成功的标准不是“文档更全了”，而是：

- 相同或相近任务上，后续 rollout 的 outcome 是否提升
- 同一基模在不改权重的前提下，是否更稳定地作出更好的决策
- 新经验是否被编译进了后续 rollout 会实际读取和使用的 context

在这个意义上，BFRL 中的“知识沉淀”本质上是 **externalized policy update**，而不是普通意义上的资料积累。

## 为什么普通的“领域知识库”视角不够

把特定领域知识沉淀理解成“多写文档”“补充领域知识”“建立更大的知识库”，会自然滑回 harness 的工程视角。那样做当然有价值，但它回答的主要是：

- agent 是否更容易理解当前系统
- 人类是否更容易追踪 agent 的行为
- 团队是否更容易协作和交接

这些是重要的，但它们还没有直接触及 BFRL 最核心的问题：

> 这些 artifact 的变化，是否真正承担了传统 RL 中一部分原本由 `weight update` 承担的 `policy improvement`？

所以在 BFRL 里，文档不是为了“说明系统”，而是为了“改变系统下一次如何行动”。

如果一条所谓的“知识”无法在未来 rollout 中稳定改变 agent 的行为，那么它更像资料，而不是有效的策略沉淀。

## 目标函数：优化的不是文档完备度，而是 Effective Policy

在特定领域里，真正被优化的对象不是模型权重，而是 agent 下一次 rollout 实际读到并使用的 **effective policy**。

可以把它粗略写成：

`effective policy = base model + runtime context assembly + retrieved artifacts + tool affordances + outcome harness`

其中可被 BFRL 持续更新的，主要不是 `base model`，而是其余几项，尤其是：

- 读取什么历史经验
- 忽略什么历史经验
- 什么时候调用什么工具
- 遵循什么 SOP
- 在什么条件下升级给人
- 如何理解 success / quality / cost / risk / escalation

因此，特定领域知识沉淀的目标函数应当改写为：

> 在固定或近似固定的基座模型下，通过更新外部 artifacts，使某个 task distribution 上的期望 outcome 持续改善。

## 什么样的内容才值得沉淀

不是所有领域信息都应该进入 BFRL 的 memory hierarchy。真正值得沉淀的是 **policy-bearing knowledge**，也就是那些能改变未来决策和行动的内容。

这类内容通常包括：

- 决策边界：什么情况下应走 A，什么情况下必须走 B
- 升级边界：什么情况下不能继续 autonomous rollout，必须交给人
- 检索线索：遇到什么信号时，应该优先读取哪类历史经验
- 失败模式：什么表象容易误导 agent，什么根因最常见
- 工具使用偏好：什么顺序、什么组合、什么停止条件更可靠
- 成本/风险权衡：什么情况下应优先保守、什么情况下应优先速度
- 已验证流程：在明确起始条件下可直接执行的 procedure

相反，下面这些内容虽然可能有帮助，但不天然构成有效沉淀：

- 纯背景知识，除非它能稳定改变决策
- 只服务于某个一次性 case 的偶然细节
- 不会被后续检索或引用的长篇记录
- 不能转化为未来 context 选择的“知道了”

一句话说，BFRL 关心的不是“知道得更多”，而是“下次做得更对”。

## 分层外部 memory，不只是存储，而是策略载体

在 BFRL 里，真正的运行时内存仍然是当前 rollout 的 `context window`。`memory/` 下的 artifacts 是外部 memory tiers，它们通过检索、换入和写回参与 policy update。

| 层次 | 主要内容 | 在 BFRL 里的角色 |
| --- | --- | --- |
| `memory/logs/` | 原始轨迹、完整执行记录 | durable backing store / source of truth |
| `memory/daily-notes/` | 压缩后的单次或近邻经验 | episodic policy delta buffer |
| `memory/doc/` | 跨 task 稳定共享的抽象、约束、失败模式 | shared semantic policy cache |
| `memory/sop/` | 被验证过的可执行流程 | compiled policy / executable runbook |

这里有两个容易混淆的点需要明确：

第一，`memory/doc/` 不只是项目说明文档，而是 expert-level context 的承载层。

第二，`memory/sop/` 不是“比 doc 更细的另一层文档”，而是从稳定经验中编译出来的可执行策略表示。

所以，`notes -> doc -> sop` 不是普通的信息归档链，而是：

> 从局部经验，到稳定抽象，再到可执行策略的逐层编译。

## 还缺的一层：检索策略与 Outcome Harness 也是可更新对象

如果只把更新对象理解成 `daily-notes/doc/sop`，仍然不够完整。

这里也需要补一个术语边界：`Harness Engineering` 是最近才被明确命名并迅速传播的新提法；而本文使用的 `Outcome Harness`，不是外部已经固定下来的标准术语，而是沿着这条思路继续细分出来的项目内概念。

它专指 harness 中负责“从环境读取最终状态，并把它转成可用于后续学习和决策的 outcome signal”的那一部分。

因为一次 rollout 的失败，可能并不是因为“缺知识”，而可能是：

- 正确的知识没有被检索进来
- 被错误的历史经验干扰了
- 本次 working set 组织方式有问题
- outcome harness 奖励了错误的东西

因此，在更准确的框架里，可被 BFRL 更新的对象至少有五类：

1. `memory/daily-notes/`
2. `memory/doc/`
3. `memory/sop/`
4. retrieval / context assembly policy
5. outcome harness / reward interpretation policy

这五类共同构成 agent 的外部化 policy substrate。

## 三个闭环，而不是一个闭环

如果只看到 `rollout -> notes -> next rollout`，还是太粗了。要让特定领域能力真的形成出来，至少要有三个互相咬合的闭环。

### 1. Rollout Loop

负责和环境交互：

1. 取一个 task
2. 组装本次 working set
3. agent 调用工具执行
4. 环境返回 outcome
5. 生成本次 rollout 的原始轨迹和初步结论

### 2. Consolidation Loop

负责把 rollout 结果变成稳定记忆：

1. 从 logs 中提取 policy delta
2. 判断哪些经验只是局部的，哪些具有跨 task 意义
3. 合并重复结论
4. 升级、降级或废弃已有 artifact
5. 必要时修订 retrieval policy 或 outcome harness

这一步不是附属工作，而是整个系统的反熵机制。

### 3. Retrieval Loop

负责把已沉淀的 artifact 重新激活为下一次 rollout 的 working set：

1. 根据 task family 和当前信号检索相关 artifacts
2. 决定读哪些 doc、哪些 SOP、哪些近邻 notes
3. 避免把无关、过时或冲突内容一起塞进 context
4. 让本次 rollout 实际受益于历史更新

如果缺少第三个闭环，那么知识沉淀就只是“写进了磁盘”，还没有真正完成学习。

## Context Credit Assignment：BFRL 里最核心的分配问题

传统 RL 难在 reward 来了之后该更新哪些权重。

BFRL 的对应难点不是 weight credit assignment，而是：

> 一次 rollout 的 outcome 到底应该改写哪一层外部策略载体？

这是特定领域知识沉淀最关键的判断点。一个更准确的分配表如下：

| 去向 | 适用情形 | 含义 |
| --- | --- | --- |
| `memory/daily-notes/` | 经验局部、尚未验证可迁移性 | 记录 episodic policy delta |
| `memory/doc/` | 结论跨 task 反复成立 | 提升为 expert invariant / heuristic |
| `memory/sop/` | 已形成稳定步骤且边界清楚 | 编译为 executable policy |
| retrieval policy | 失败主因是正确知识未被读入或上下文组装不当 | 更新 working set 构造方式 |
| outcome harness | 失败暴露的是 reward 定义或评估机制错位 | 修订 success / risk / cost 的解释 |
| 降级 / 废弃 | 旧规则被新 case 反复打破 | 从 SOP 降回 doc，或从 doc 降回 notes，或直接标废 |

注意最后一行非常重要。一个只会上升、不会降级和废弃的 memory system，一定会熵增失控。

## Rollout Note 的正确职责：记录 Policy Delta，而不只是工作纪要

如果 daily note 只是“做了什么、结果如何”的工作纪要，它当然有记录价值，但还不够成为 BFRL 的经验载体。

在特定领域里，一次 rollout 的 note 更合理的最小结构应围绕 `policy delta` 展开，至少包含：

- `task family`：这次任务属于哪一类
- `loaded context`：本次实际读了哪些 notes/doc/SOP
- `key decision points`：哪些判断点真正决定了 outcome
- `outcome card`：`success / quality / cost / risk / escalation`
- `useful signals`：哪些上下文或环境信号是有效的
- `misleading signals`：哪些信息让 agent 走偏了
- `policy delta candidate`：这次应新增、修订或删除什么策略
- `proposed destination`：这条变化应进入 note、doc、SOP、retrieval 还是 harness
- `invalidated artifacts`：哪些旧结论被这次 rollout 否定了
- `replay priority`：这次 case 是否值得重放

这样设计的重点不是格式美观，而是让后续 consolidation task 可以明确地从 note 中抽取“应该更新什么”。

## Consolidation 不是整理文档，而是 Policy Compilation

很多系统做到写 notes 就停了，但 BFRL 的关键恰恰在 notes 之后。

Consolidation task 的职责不是“帮忙整理一下文档”，而是：

- 从多个 rollout 中识别重复出现的 decision boundary
- 提炼跨 task 共享的 heuristic 和 invariants
- 发现某个 failure mode 已足够高频，应进入 doc
- 发现某条流程已足够稳定，应编译成 SOP
- 发现现有 SOP 被越来越多例外击穿，应降级
- 修正 retrieval 线索，让后续 rollout 更容易读到正确经验
- 修正 harness，让系统奖励真正重要的结果

如果要更严谨一点，可以把 `memory/logs -> memory/daily-notes -> memory/doc -> memory/sop` 理解成一个持续进行的 policy compilation pipeline。

## Retrieval 不只是“查资料”，而是组装 Working Set

知识沉淀真正生效的时刻，不是在写回磁盘时，而是在后续 rollout 中被重新换入 `context window` 时。

因此，retrieval 的问题不应表述成“怎么把文档搜出来”，而应表述成：

> 当前 task 的 working set 应该由哪些 artifact 组成，才能最大化 outcome？

一个较合理的 working set 结构通常包括：

1. 运行时基础约束
2. 当前 task 的局部输入和目标
3. 当前领域最相关的 doc 切片
4. 触发条件匹配的 SOP
5. 若干近邻成功/失败 notes
6. 必要的升级边界和风险提示

优化重点不是把历史都塞进去，而是让有限 context 中的每一块内容都有明确的行为价值。

## 特定领域专家能力是如何涌现出来的

在这个框架下，“expert” 不是系统预装进去的，也不是单独训练出来的一个模块，而是多次 task 的共享结构在 memory hierarchy 中不断压缩后的结果。

这个涌现过程大致是：

1. 零散 task rollout 产生局部经验
2. 局部经验以 notes 形式保留下来
3. 重复出现的决策结构被提炼成 doc
4. 稳定且边界明确的策略被编译成 SOP
5. 后续 rollout 通过 retrieval 重新激活这些 artifact
6. 相同基模在相似 task 上表现改善
7. “expert-level context” 因而逐渐形成

所以，特定领域专家能力的形成，不是“收集更多知识点”，而是：

> 把反复证明有效的策略变化，逐步从 episodic memory 提升为 stable expert context，再编译为 executable policy。

## 如何判断沉淀是否真的发生了

因为 BFRL 的目标不是 legibility，而是 policy improvement，所以验证方法也必须相应改变。

至少要问下面几个问题：

- 在相同基模下，仅更新 artifacts 而不更新权重，后续 outcome 是否提升
- 新增 doc / SOP 之后，相关 task family 的 success rate 是否更高
- escalation rate 是否下降，或至少变得更准确
- cost 是否下降，risk 是否更可控
- 对历史失败样本重放时，系统是否更容易规避同类错误
- 去掉某条新 artifact 后，表现是否明显回退

最后一条尤其重要。它相当于做 artifact ablation，用来判断某次“知识沉淀”究竟是不是有效 policy update。

## 常见误区

### 误区 1：把沉淀做成领域百科

这会提升可读性，但不一定提升 outcome。

### 误区 2：只积累，不反熵

没有降级、合并、废弃机制，memory 迟早会被过时和冲突内容污染。

### 误区 3：把所有 note 强行结构化

过度结构化会压扁表达空间，让很多真正有价值的边界条件和启发难以保存。

### 误区 4：把 SOP 当成普通文档

SOP 的本质是 compiled policy，而不是更长、更详细的说明书。

### 误区 5：把知识沉淀和知识利用割裂开

写回没有检索闭环，就没有真正学习。

## 一个更细的实施框架

如果现在要围绕某个特定领域实现这套机制，一个更准确的落地顺序应当是：

1. 选定一个窄 task family，而不是一个大领域
2. 定义 outcome harness，明确 success / quality / cost / risk / escalation
3. 设计 rollout note schema，让每次任务都能显式产出 policy delta candidate
4. 建立 consolidation task，把 notes 提升、合并、降级、废弃
5. 建立 retrieval policy，让 doc / SOP / notes 能重新进入 working set
6. 用 replay 和 ablation 检验 artifact update 是否真的改善行为
7. 只有在这个闭环稳定后，才逐步扩到相邻 task family

这个顺序的重点在于：先让“学习闭环”成立，再让“知识体量”增长。

## 一个压缩结论

特定领域里的知识沉淀，如果放在 BFRL 框架中，最准确的理解不是：

> 让 agent 记住更多领域知识。

而是：

> 让 agent 把 rollout 中产生的可复用策略变化，持续编译进外部 memory 与 retrieval/harness 工件，使相同基模在后续相似任务中表现持续改进。

因此，特定领域 BFRL 的核心不是知识库，而是：

> **domain expert formation through externalized policy update**

这才是“notes / doc / SOP”在 BFRL 里的真正含义。

## 相关文档

- `memory/doc/project-overview.md`
- `memory/doc/domain-bfrl.md`
- `memory/doc/bfrl-theoretical-increment-over-harness/bfrl-theoretical-increment-over-harness.md`
