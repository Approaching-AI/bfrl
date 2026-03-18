# AGENT.md

本文件是这个工作区的稳定入口，不是百科全书。

目标不是把所有规则都塞进这里，而是让 agent 先建立正确心智模型，再去读取最相关的局部文档。若本文件开始变长、变散、变旧，应把细节下沉到 `memory/doc/`、`memory/daily-notes/`、`memory/sop/`，这里只保留稳定原则与导航。

## 1. 项目使命

`bfrl` 的核心命题是：**不更新模型权重，也能通过 context engineering、tool use、memory、outcome feedback 与文档压缩，形成类似 RL 的持续改进。**

请把它理解为：

- Harness Engineering 负责让 agent 可靠工作。
- BFRL 负责把这种可靠工作重新解释为一种学习过程。
- 这个仓库的长期目标，不只是“把任务做完”，而是“让下一次更会做”。

一句话版本：

> Harness 是工程外壳，BFRL 是学习论解释。

## 2. 最高层心智模型

### 2.1 Context 是运行时策略空间

- 真正的运行时工作内存是当前 `context window`。
- prompt 只是其中一部分；工具调用、读到的文件、历史记录、验证结果也都在塑造策略。
- 因此优化对象不是“写一个更大的 prompt”，而是“让当前任务读到最小、最准、最有用的上下文组合”。

### 2.2 外部工件就是可更新的策略载体

请把 `memory/` 视为仓库中的统一外部记忆根目录，并把其中工件视为分层外部记忆，而不是普通文档：

- `memory/logs/`：durable backing store
- `memory/daily-notes/`：compressed episodic memory，最接近 experience buffer
- `memory/doc/`：shared semantic cache / expert context
- `memory/sop/`：compiled policy / executable runbook
- `memory/handoff/`：session continuity artifact

真正发生“策略更新”的地方，通常不是 base model，而是这些工件。

### 2.3 系统只依赖一种原语

> `task rollout -> outcome -> consolidation -> next rollout`

业务任务、知识整理、SOP 蒸馏、框架修复、反熵维护，本质上都是 task。

## 3. 你在这个仓库里的角色

- 人负责方向、价值判断、边界条件和高风险决策。
- Agent 负责执行、验证、记录、压缩、回写。
- 当任务失败时，优先怀疑 harness、context、检索、工具、评测或工件组织有缺口，而不是笼统地“再试一次”。

工作重点是：

- 验证并设计整个项目的价值实现，需要完成代码任务。
- 设计更可读、更可验证的环境
- 让知识进入仓库而不是停留在聊天里
- 让经验从单次任务沉淀为可复用策略

## 4. 默认工作循环

每次进入任务时，默认按这个顺序思考：

1. 明确本次 task 的目标、终止条件与风险边界。
2. 读取最小必要上下文：
   - 先读本文件
   - 再读 `CLAUDE.md`
   - 再读与当前任务最相关的 `memory/doc/`、`memory/daily-notes/`、`memory/sop/`、`memory/handoff/`
3. 小步推进，只做一个清晰子问题，避免假装“一次做完整个项目”。
4. 用工具探索、执行、验证，不依赖纯口头自评。
5. 结束时必须回写学习：
   - task-specific 经验写入 `memory/daily-notes/`
   - cross-task 稳定知识写入 `memory/doc/`
   - 多次验证的稳定流程写入 `memory/sop/`
6. 离开时保持 clean state：别人或下一次 agent 应能从当前状态继续，而不先清理烂摊子。

## 5. Outcome First

本仓库优先采用 outcome-based reward，而不是额外堆 verifier。

默认顺序：

1. 先找环境本身能给出的 outcome signal。
2. 其次使用测试、脚本、结构检查、静态检查、benchmark。
3. 模型打分或人工主观判断只作为补充，不应成为唯一依据。

要点：

- 不要把“模型说自己完成了”当成成功。
- 重点看环境最终状态，而不只是对话过程。
- 如果 outcome 不清楚，先补 outcome harness，再继续自动化。

## 6. 学习沉淀与信用分配

一次 rollout 结束后，必须问自己：

> 这次经验应该改写哪一层 context？

默认只有五种去向：

1. 写入 `memory/daily-notes/`
   - 经验局部、一次性、尚未验证复用性
2. 更新 `memory/doc/`
   - 经验跨 task 重复出现
   - 不依赖某个具体输入
   - 能改变后续任务判断
3. 提炼 `memory/sop/`
   - 已形成稳定步骤
   - 起始条件和结束条件清楚
   - 经多个 case 验证有效
4. 修订检索/组装策略
   - 问题不是“不会做”，而是“没把对的 context 读进来”
5. 修订 outcome harness
   - 问题不是执行差，而是成功标准定义错了

升降级规则：

- `memory/daily-notes -> memory/doc`：同类结论多次出现，且具有跨任务价值
- `memory/doc -> memory/sop`：已验证为稳定、可执行、可复用流程
- `memory/sop -> memory/doc` 或 `memory/daily-notes`：新 case 持续打破原流程，说明它尚未稳定

## 7. 文档原则

### 7.1 仓库是 system of record

对 agent 来说，**看不到的知识等于不存在**。

因此：

- 重要判断不要只留在聊天、脑海或临时口头约定里
- 尽量把知识编码进仓库中的版本化工件
- 文档应能被后续 agent 检索、引用、修订

### 7.2 渐进式暴露优于巨型手册

- `AGENT.md` 应保持简短、稳定、像目录
- 细节下沉到 `memory/doc/`
- 经验先进入 `memory/daily-notes/`
- 流程成熟后再进入 `memory/sop/`

如果一个规则变成“大段背景 + 多个例外 + 难验证”，优先拆出去，不要继续堆在本文件里。

### 7.3 反熵是核心工作，不是边角料

随着 agent 反复工作，仓库会自然熵增。清理、压缩、去重、修补陈旧文档，本身就是高价值 task。

默认倾向：

- 连续小步清理，避免技术债集中爆炸
- 把“人的品味”尽量变成显式、可检查、可复用的仓库规则
- 发现旧文档与真实行为不符时，优先修文档或修系统，不要让漂移继续存在

## 8. 当前仓库的导航

进入具体任务时，优先按下面路径找信息：

- `CLAUDE.md`
  - 项目身份、目录约定、与 `meta-agent` 的关系
- `memory/doc/project-overview.md`
  - BFRL 的总纲与任务边界
- `memory/doc/bfrl-theoretical-increment-over-harness/bfrl-theoretical-increment-over-harness.md`
  - BFRL 相对 Harness Engineering 的理论增量
- `memory/doc/domain-bfrl.md`
  - 特定领域 BFRL、outcome harness、context credit assignment
- `memory/daily-notes/`
  - 单次 rollout 的近因经验
- `memory/sop/`
  - 已验证的稳定流程；目前仍应谨慎增长
- `memory/handoff/`
  - session 间交接
- `meta-agent/`
  - 若 submodule 已初始化，把它视为次级方法论文档；若未初始化，不要假设其中内容存在

## 9. 具体工作偏好

默认采用以下偏好，除非当前任务明确要求别的做法：

- 先窄后广：先解决一个具体任务分布，再谈 generality
- 先 outcome 再流程：没有 outcome，就没有可靠学习
- 先可验证再可叙述：用事实、测试、状态变化说话
- 先小而稳的入口，再多层细节
- 先让 agent 可读，再追求“人看着优雅”
- 优先选择稳定、可检查、可组合的结构
- 遇到重复失败时，优先补 memory / retrieval / SOP，而不是重复 ad-hoc prompting

## 10. 什么时候该停下来问人

出现以下情况时，应优先升级而不是自作主张：

- 任务成功标准本身不明确
- 自动操作可能带来不可逆损失
- 不同目标之间存在价值冲突
- 需要决定是否把经验上升为制度性规则
- 发现仓库现有文档彼此冲突且无法从环境中裁决

## 11. 对未来 AGENT.md 的维护要求

维护本文件时，请守住三条：

1. 只保留稳定原则、导航与工作循环。
2. 不把它写成覆盖一切的大手册。
3. 一旦细节开始增多，就把细节迁移到更合适的文档层。

## 12. 思想来源

本文件综合自以下来源：

- 本仓库的 `CLAUDE.md`
- 本仓库的 `memory/doc/project-overview.md`
- 本仓库的 `memory/doc/bfrl-theoretical-increment-over-harness/bfrl-theoretical-increment-over-harness.md`
- 本仓库的 `memory/doc/domain-bfrl.md`
- OpenAI, *Harness engineering: leveraging Codex in an agent-first world*
- Anthropic, *Effective harnesses for long-running agents*
- Anthropic, *Demystifying evals for AI agents*
- Anthropic, *Effective context engineering for AI agents*

如果未来这些上游思想发生变化，优先更新底层文档，再回到这里做最小必要修订。
