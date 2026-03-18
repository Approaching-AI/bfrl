# bfrl — Backward Free Reinforcement Learning

## 核心思想

Backward Free RL 是一种新的强化学习范式：**不调整模型权重**，通过 context engineering 的手段实现 RL 的效果。

"Backward Free" 意味着不需要反向传播（backpropagation），不需要梯度更新，不需要训练基础设施。强化学习的信号通过上下文的构造和管理来传递，而非通过权重更新。

## 使命

把 RL 的成本降低几个数量级，让模型就算在非常偏僻的场景（niche domains、低资源环境）也能有比较好的效果。

传统 RL（如 RLHF、PPO、GRPO 等）需要大量 GPU 资源做训练，门槛很高。bfrl 通过 context engineering 替代 weight update，预计能将 RL 成本降低 2-3 个数量级。不需要 GPU 集群、不需要训练流水线，只需要 inference API 调用——让任何人都能用 RL 的方式提升模型表现。

## 设计基础

两个关键观察支撑了 bfrl 的可行性：

1. **Context 的影响力在增长。** 现代 agent 的 context window 越来越长，context 对 agent 行为的影响越来越大。更长的 context 意味着更多的"参数"可以在不改权重的情况下调控 agent 的输出——这就是 context engineering 能替代 weight update 的物理基础。

2. **Context 是动态的，设计空间很大。** Agent 在运行过程中会通过 tool use 来决定后续的 context 内容（搜索、读取文件、调用 API 等）。这意味着 context 不是静态的 prompt，而是一个由 agent 自身行为塑造的动态序列。Tool 系统本身足够复杂，提供了充分的表达能力来实现复杂的策略优化逻辑。

一个具体的直觉：以目前主流的 ~200k context window 为例，其中 10k token 如果是纯自然语言，表达能力有限。但如果这 10k token 包含 tool calls（搜索、读文件、执行代码等），它实际触及的信息空间远超 10k 文本本身——tool use 将 context 的有效带宽放大了很多倍。

这两点合在一起意味着：context = 一个高维、动态、可编程的策略空间。传统 RL 通过梯度更新在权重空间里搜索好的策略；bfrl 通过 context engineering 在上下文空间里做同样的事，但不需要反向传播。

## Reward 设计

采用 **outcome-based reward**：直接看任务最终结果，不引入额外的 verifier 模型。

理由：
- Verifier 本身是额外成本，与降低 RL 成本的使命矛盾
- 在偏僻场景（niche domains）下，好的 verifier 可能根本不存在
- Outcome 是最自然、最低成本的 reward 信号，来自任务本身

## 核心机制：Notes as Experience Buffer

每次 rollout（不论成功还是失败）都总结记录 notes，内容包括做了什么、结果如何、哪里出了问题。这些 notes 持久化存储，后续 rollout 的 agent 按需读取，历史经验就通过 context 传递给了新的 session。

与传统 RL 的对应关系：

| 传统 RL | bfrl |
|---------|------|
| Rollout | Agent 执行一次任务 |
| Reward signal | Outcome（任务结果） |
| Experience replay buffer | 积累的 notes |
| Policy update (gradient) | Agent 读取 notes 后在 context 中调整行为 |

权重没变，但策略变了。

这个设计与 meta-agent 方法论天然契合：`memory/daily-notes/` 的积累机制就是 experience buffer 的实现。

## RL 粒度：Task vs Expert

- **Task** 是 rollout 的基本单位，每个 task 有自己的 context（具体的输入、步骤、outcome）。
- **Expert** 是多个 task 经验的并集——多个 task context 之间有大量重合，expert context 就是这些重合点的提炼。

Task-level 经验自然积累，跨 task 共享的知识沉淀为 expert-level context。框架围绕 task-level 设计，expert 是涌现的结果。

### 信息沉淀路径

这与 meta-agent 方法论的层次天然对应：

| 层次 | RL 含义 | 信息粒度 |
|------|---------|----------|
| `memory/daily-notes/` | Task-level 经验 | 单次 rollout 的细节 |
| `memory/doc/` | Expert-level 知识 | 多次 task 的并集，去掉 task-specific 细节 |
| `memory/sop/` | 被验证的可复用策略 | 从 `memory/doc/` 中进一步结晶的操作流程 |

从 notes → doc → SOP 的过程就是从 task context 到 expert context 的逐步压缩。

### 压缩过程本身也是 task

Notes → doc → SOP 的信息压缩由 agent 执行，而非人工。关键洞察：这个压缩任务本身也是一个 task，同样适用 bfrl 的 rollout + notes 机制来学习优化。

这意味着整个系统只有一种原语：**task rollout + notes 记录**。不管是：
- 业务任务（完成具体工作）
- 知识压缩（notes → doc → SOP）
- 框架自身优化（学习如何更好地压缩、更好地利用 notes）

全走同一条路径。系统的复杂度被压到最低。

## Context 与基模亲和性

设计目标是基模无关（至少在同一能力水平的模型间无关），自然语言本身适合这个目标。

但存在一个已知特性：当 notes 全由同一个模型生成时，会产生对该模型的亲和性——每个模型的输出有隐含的分布特征（用词、句式、推理组织方式），模型指纹技术已证实这些特征真实存在。同模型读自己生成的 notes 会更"顺"，跨模型时利用效率可能打折扣。

应对策略：
- **默认单模型运行**，接受亲和性作为已知特性，不增加额外复杂度
- **混合生成作为可选特性**：用不同模型参与 rollout，让 notes 分布更中性，增强基模无关性
- 不采用结构化降维的方式（如强制 key-value、表格），因为这会限制表达空间，有些知识就是需要自然语言描述

## 项目定位

- 开源项目
- 包含代码实现，不包含论文
- 面向社区，降低 RL 的使用门槛
