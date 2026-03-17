# bfrl — Backward Free Reinforcement Learning

## 核心思想

Backward Free RL 是一种新的强化学习范式：**不调整模型权重**，通过 context engineering 的手段实现 RL 的效果。

"Backward Free" 意味着不需要反向传播（backpropagation），不需要梯度更新，不需要训练基础设施。强化学习的信号通过上下文的构造和管理来传递，而非通过权重更新。

## 使命

把 RL 的成本降低几个数量级，让模型就算在非常偏僻的场景（niche domains、低资源环境）也能有比较好的效果。

传统 RL（如 RLHF、PPO、GRPO 等）需要大量 GPU 资源做训练，门槛很高。bfrl 的目标是让任何人都能用 RL 的方式提升模型表现，而不需要训练基础设施。

## 项目定位

- 开源项目
- 包含代码实现，不包含论文
- 面向社区，降低 RL 的使用门槛
