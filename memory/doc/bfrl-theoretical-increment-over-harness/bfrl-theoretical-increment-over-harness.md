# BFRL 相比 Harness Engineering 的理论增量

## 摘要

这里先补一个术语背景，避免误解：

> `Harness Engineering` 本身就是 AI agent 领域里一个非常新的提法。当前可见的直接命名源头，是 OpenAI 于 2026 年 2 月 11 日发布的《Harness engineering: leveraging Codex in an agent-first world》；几天后，Thoughtworks 于 2026 年 2 月 17 日跟进讨论，并明确把它称为一个“only 2 weeks old”的新词。

因此，本文所说的 Harness Engineering，不是一个已经稳定几十年的既有学派名词，而是最近才被快速显化、正在被行业吸收和解释的一组 agent engineering 实践的名字。

Harness Engineering 已经展示出一条非常清晰的工程路线：当模型足够强时，决定 agent 上限的关键因素不再只是模型参数本身，而是环境、上下文、约束、验证、记忆与反馈回路的设计。它首先回答的是一个工程问题：**怎样让 agent 在真实世界里稳定、可控、可维护地工作。**

BFRL（Backward Free Reinforcement Learning） 继承这一点，但它试图继续回答另一个更上位的问题：**如果 agent 的行为主要由 context、memory、tool use 和环境反馈来塑造，那么这些东西能否承担传统 RL 中一部分原本由 weight update 承担的职责？**

因此，BFRL 不是 Harness Engineering 的对立面，也不只是它的同义改写。更准确地说：

> Harness Engineering 是 BFRL 的工程外壳，BFRL 是 Harness Engineering 的学习论解释。

如果 Harness 更像“让 agent 可靠工作的控制系统”，那么 BFRL 更像“把这个控制系统解释为一种无反向传播的学习系统”。

如果借用更标准的 RL 语言来描述，那么 BFRL 的一个关键特点是：它把 `policy update` 的对象从基座模型的权重，转移到了 `memory/daily-notes / memory/doc / memory/sop` 这类外部策略载体上；而完成这一更新的，也不是离线训练管线，而是 agent 自身。

## 一个简表

| 维度 | Harness Engineering | BFRL 的理论增量 |
| --- | --- | --- |
| 问题定义 | 如何让 agent 稳定完成任务 | 如何把任务执行过程本身变成学习过程 |
| 主要对象 | 环境、工具、约束、文档、评测、反馈回路 | context 作为策略空间，logs/notes/doc/SOP 构成分层外部 memory 与 compiled policy 链 |
| 改进机制 | agent 出错后补脚手架、补规则、补验证 | rollout 产生 outcome，outcome 沉淀为 notes，再反馈到后续 context |
| 对记忆的理解 | 跨 session 连续性的工程需要 | 不只是 experience buffer，而是 backing store → working set → semantic cache → compiled policy 的层级系统 |
| 对文档的理解 | system of record，提升 agent legibility | expert context 的压缩层，是学习后形成的稳定策略表示 |
| 任务边界 | 当前公开实践以 coding / product delivery 为主 | task 主要来源于我们自己的 AIMA，可先从领域问题出发（如 openclaw），再扩展到更 general 的全部领域 |
| 理论姿态 | 工程范式 | 学习框架 |

## 从“工程脚手架”到“策略载体”

Harness Engineering 的核心是为 agent 设计一个足够可靠的工作环境。这个环境通常包括：

- 可读的仓库结构和 system of record
- 明确的工具与权限边界
- 架构约束与机械化检查
- 进度文件、功能清单、初始化脚本等跨 session 工件
- 评测、监控、回归测试与清理机制

这套东西首先解决的是**可靠性问题**。它让 agent 不至于在长周期任务中迷失、漂移、污染环境，或者错误地宣告任务完成。

BFRL 的第一层理论增量，是把这些东西从“辅助 agent 的脚手架”重新解释为“塑造策略的载体”。

换句话说，在 BFRL 里：

- context 不只是提示词，而是运行时的策略工作区
- `memory/logs/` 不只是归档，而是存在磁盘中随时可能调用的数据
- `memory/daily-notes/` 不只是日志，而是经验缓存
- `memory/doc/` 不只是文档，而是跨 task 的稳定知识表示
- `memory/sop/` 不只是流程，而是被验证过的可复用策略

这一步非常关键。它意味着 agent 的改进不一定要发生在权重空间，也可以发生在上下文空间和环境空间。

更精确地说，真正的运行时内存是 `context window`；`memory/logs / memory/daily-notes / memory/doc / memory/sop` 是被检索、换入并写回 `context` 的外部记忆层。其中 `memory/sop` 又比普通存储层更进一步，它已经是从经验层级里编译出来的可执行策略，而不只是“另一层文档”。

## 把 context 明确提升为“可编程策略空间”

Harness Engineering 当然已经在实践上依赖 context engineering，但它通常把 context 看作提高 agent 表现的关键工程手段之一。

BFRL 更进一步，明确提出：

> context 不是权重更新的补充物，而是一个高维、动态、可编程的策略空间。

这与传统 prompt 的区别在于：

- context 不是一次性输入，而是 agent 在 task 执行中不断塑造的动态序列
- tool use 会把 context 的有效带宽放大，因而 context 的“表达能力”远高于表面 token 数
- context 中承载的不只是任务信息，也包括历史经验、失败模式、局部规范、领域术语、操作步骤和验证结果

在这个视角下，Harness 中常见的环境搭建、信息组织、任务拆解、验证回路，都可以被视为对策略空间的显式设计。

## Notes as Experience Buffer

这是 BFRL 相比 Harness 最有辨识度的理论推进之一。

在 Harness Engineering 里，progress file、feature list、git log、文档更新等工件的主要作用，是帮助后续 agent 更快进入状态，减少跨 context window 的信息丢失。

在 BFRL 里，这些工件被统一解释为经验缓存系统，尤其是 `notes`：

- 一次 task rollout 的执行过程会产生 outcome
- outcome 与过程中暴露出的策略问题一起被总结进 notes
- 后续 rollout 按需读取 notes
- agent 在不更新权重的情况下，通过读取经验来调整行为

这实际上把传统 RL 中的 `experience replay buffer` 映射到了 agent 的工作流里。

它的意义在于：**策略变化真实发生了，但变化发生在可读写的 context 层，而不是不可见的参数层。**

如果沿用 RL 术语，那么这里可以把 BFRL 理解为一种 `externalized policy update`。传统 RL 主要通过梯度步骤、价值回传或其他参数更新，去改变 policy / value function 所依附的模型权重；而在 BFRL 里，被更新的对象不是 foundation model 的参数，而是 `memory/daily-notes / memory/doc / memory/sop` 这些外部工件。换句话说，BFRL 改写的不是 base model，而是 agent 下次 rollout 会读取到的 `effective policy`。

更进一步，这个更新过程本身也是 agent 完成的。如果借用 `actor-learner` 的说法，那么 rollout agent 负责与环境交互、产出 trajectory 和 outcome；而承担知识沉淀的 maintenance agent，则借鉴 Harness 中的反熵机制，通过轮询、整理、压缩、校验和蒸馏，把 `memory/daily-notes/` 逐步提升为 `memory/doc/` 和 `memory/sop/`。因此，BFRL 的学习回路不是传统的 `rollout → reward → weight update`，而更接近 `rollout → agentic consolidation → updated notes/doc/SOP → next rollout`。

## 从 logs 到 notes 到 doc 再到 SOP：经验压缩、分层记忆与策略编译

Harness Engineering 一般会把文档和规则视为提升 agent legibility 的关键基础设施。这一点非常重要，但它默认文档主要是工程资产。

BFRL 的理论增量在于，它把这些资产放进了一个同时具有“分层存储”和“策略编译”特征的系统里。这个类比在方向上确实很像操作系统里的磁盘、内存、缓存，但还需要一个关键修正：真正的运行时内存不是 `memory/daily-notes/` 或 `memory/doc/`，而是 agent 当前的 `context window`；`memory/logs / memory/daily-notes / memory/doc / memory/sop` 是被检索、换入 `context` 的外部 memory tiers。

- `memory/logs/` 是 durable backing store，也更接近 append-only task log。它保存一次 rollout 的完整原始轨迹，是 source of truth，容量最高，但直接进入运行时工作集的优先级最低。
- `memory/daily-notes/` 是 compressed episodic memory。它从 `memory/logs/` 中提取出近因经验，供后续相邻 rollout 快速复用。
- `memory/doc/` 是 shared semantic cache / expert cache。它沉淀多个 task 共享的 expert-level context，是面向某类具体问题的 read-optimized 热知识层。
- `memory/sop/` 是 executable runbook。它由稳定知识进一步编译而成，已经不是单纯的 cache，而是可直接驱动行为的 control artifact。

这个链条意味着，BFRL 不只是“留下痕迹”，而是在定义一种从局部经验到通用策略的压缩、提升与编译过程。

更进一步，BFRL 还提出：

> `memory/logs → memory/daily-notes → memory/doc → memory/sop` 的压缩+整理过程本身也是 task。

这个压缩+整理过程也是需要通过 Agent 来处理，是 BFRL 整个系统的“反熵增”机制（根据 Harness 的理论，只使用 Agent 进行操作会不可避免的导致熵增）。这一步是整个 BFRL 最重要与核心的部分，是最终整个系统的能否自举的关键。

这使系统获得了一个很强的统一性：

- 业务任务是 task
- 知识整理是 task
- SOP 蒸馏是 task
- 框架自我优化也是 task

整个系统只需要一种原语：`task rollout + notes 记录`。

这里唯一需要避免的误解，是把 `memory/sop/` 视为又一层“存储”。更准确地说，`memory/sop/` 是这条 memory hierarchy 的编译目标：它类似把稳定知识 lowering 成可执行 procedure，而不是再上一层 cache。

这是 Harness Engineering 目前公开论述里还没有明确完成的抽象统一。

## 从“长任务连续性”到“持续学习连续性”

Harness Engineering 的长处，在于它非常关注跨 session 的连续工作能力。Anthropic 的 long-running harness 文章里，initializer agent、progress file、feature list、`init.sh` 和 clean state 都是为了解决这个问题。

但这些设计主要回答的是：

- 下一次 agent 怎么快速接上
- 如何避免中途烂尾
- 如何防止错误状态在环境中扩散

BFRL 在这之上再推进一步，试图回答：

- 下一次 agent 不只是“接上”，能不能“更会做”
- 经验沉淀之后，系统是否真的发生了策略改进
- 这种改进能否在不改权重的前提下累积

因此，BFRL 关注的不只是工作连续性，而是**学习连续性**。

## Task 来源多元，不以单一应用或单一领域为边界

当前公开的 Harness Engineering 例子大多从 coding agent、仓库维护、软件交付和相关评测出发。虽然 Anthropic 已经明确指出这些方法未来有机会推广到科研、金融建模等领域，但它的现有叙事重心仍然是“如何把软件工程这条链路 harness 住”。

BFRL 的 task 定义更宽。它不应该被理解为“来自单一 app backlog 的 feature task”，而应该被理解为**任何可以产生 outcome 并被经验化的任务单元**。task 的来源可以很多，包括但不限于：

- 来自用户或业务侧的外部任务，如目前 AIMA 提供的任务。
- 来自领域环境的事件、异常和待处理问题
- 来自评测套件、回归测试和 benchmark 的验证任务
- 来自知识压缩过程本身的整理任务
- 来自系统维护的反熵任务，例如文档修复、SOP 更新、失效规则清理
- 来自更大任务分解后生成的子任务
- 来自 agent 自主发现的薄弱点和补全任务

也因此，BFRL 的路线天然具有一种“从专门领域走向通用领域”的扩展性：

1. 最开始，系统往往只处理某个领域中特定而高价值的问题。
2. 在这个领域内，rollout、notes、doc、SOP 逐渐形成稳定的 expert context。
3. 当相邻任务和相邻子领域不断纳入时，expert context 开始跨 task 复用。
4. 当多个领域都出现类似的压缩结构时，系统才逐步向更 general 的全部领域扩展。

换句话说，BFRL 不是先假设一个“通用 agent”，再去零散适配各领域；它更像是先在具体领域里积累可迁移经验，再通过 context 层的压缩和抽象，逐步走向 generality。

这使 BFRL 的 generality 不是预设出来的，而是从 task 分布中涌现出来的。

## 把 outcome-based reward 明确纳入框架中心

Harness Engineering 一定会使用反馈，但它并不天然把反馈组织成 RL 语言中的 reward 结构。

BFRL 明确选择了 `outcome-based reward`，并强调尽量不依赖额外 verifier 模型。这个取向有两个理论后果：

第一，它把学习信号尽量绑定到任务自身的最终结果，而不是额外再建一层昂贵的监督基础设施。

第二，它让 BFRL 更适合那些 verifier 稀缺、标注成本高、但 outcome 可以从环境中读出的场景。

当然，这里也留下了一个开放问题：在 autonomous 模式下，task 从哪来、outcome signal 从哪来、rollout loop 怎么稳定运行。这些问题目前在 BFRL 里仍然是待完成项，但正因为这些问题被清晰提出，BFRL 才更像一个正在成形的学习框架，而不是若干工程技巧的集合。

## 将“expert”视为多 task context 的涌现结果

Harness Engineering 往往会讨论让 agent 更懂当前系统，但它不一定需要引入“expert”这一层抽象。

BFRL 明确提出：

- task 是 rollout 的基本单位
- expert 不是预置的角色，而是多个 task context 之间重合部分的沉淀结果

这有一个很重要的理论含义：系统不需要一开始就拥有完备的领域专家模块。它可以先完成大量 task，然后在经验压缩的过程中，让 expert-level context 自然涌现。

这让 BFRL 对“如何从任务执行走向领域能力”给出了更清晰的解释路径。

## 基模无关与模型亲和性被显式纳入讨论

Harness Engineering 的很多实践默认可以跨模型迁移，但较少显式讨论“不同模型读取同一批历史工件时，利用效率是否一致”。

BFRL 把这个问题摆到了台面上：

- 理想目标是基模无关
- 现实中，同一模型生成并读取自己的 notes 往往更顺手
- 因此存在模型亲和性问题
- 混合生成和自然语言表达方式会影响后续迁移效果

这使 BFRL 在理论上更早面对“跨模型经验可迁移性”这个问题。

## BFRL 不是替代 Harness，而是试图把 Harness 纳入统一理论

这里需要非常明确：BFRL 的理论增量，并不意味着 Harness Engineering 不重要，恰恰相反。

如果没有 Harness 提供的这些东西：

- 稳定环境
- 可读写工具链
- 可检查的约束
- 清晰的工件边界
- 评测与验证回路
- 反熵与垃圾回收机制

那么 BFRL 很难在真实系统中跑出稳定的 autonomous loop。

所以更准确的关系不是“BFRL 取代 Harness”，而是：

- Harness 负责让系统可靠地运行
- BFRL 负责解释系统如何在运行中持续学习

前者解决“能不能稳定做”，后者解决“做过之后有没有变得更会做”。

## 一个更正式的结论

如果把当前公开的 Harness Engineering 视为 agent 时代的工程控制论，那么 BFRL 的理论增量可以概括为以下四点：

1. 它把 harness 从工程脚手架提升为策略载体。
2. 它把跨 session 记忆提升为 experience buffer。
3. 它把文档、知识与 SOP 放进一个明确的分层外部 memory 与 compiled policy 体系里。
4. 它把 task 执行、知识整理、流程蒸馏与系统自我优化统一到同一种学习原语之下。

更具体地说，BFRL 试图把传统 RL 里由 `weight update` 承担的那部分 `policy improvement`，改写为由 agent 执行的 `artifact update`：更新 `memory/daily-notes / memory/doc / memory/sop`，再通过下一次 rollout 把这些更新重新体现为行为变化。

在这个意义上，BFRL 相比 Harness 的真正新增，不是“多了一些 context engineering 技巧”，而是提出了一个更强的命题：

> 在足够强的 agent 系统里，context、memory、tool use、环境反馈与工件压缩，可以组成一种无需反向传播的持续学习机制。

如果这个命题成立，那么 Harness Engineering 就不只是 agent 的外部支架，而会成为一种可被系统化、可被迁移、可被累积优化的学习基础设施。

## 参考资料

- OpenAI, *Harness engineering: leveraging Codex in an agent-first world*  
  https://openai.com/index/harness-engineering/
- Anthropic, *Effective harnesses for long-running agents*  
  https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Anthropic, *Demystifying evals for AI agents*  
  https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Anthropic, *Building agents with the Claude Agent SDK*  
  https://claude.com/blog/building-agents-with-the-claude-agent-sdk
- Martin Fowler / Birgitta Böckeler, *Harness Engineering*  
  https://martinfowler.com/articles/exploring-gen-ai/harness-engineering.html
- 本项目：`memory/doc/project-overview.md`
- 本项目：`memory/daily-notes/2026-03-17-01.md`
