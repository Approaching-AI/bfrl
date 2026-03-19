# Daily Notes -> Doc Demo

这个目录实现了两个轮询 Agent：

- `daily-notes-to-doc`
  - 从 `daily-notes` 增量构建派生文档
  - 维护 `processed_notes` / `last_processed_note`
- `doc-audit`
  - 检查派生文档是否过时、缺引用、结构不合法、或与 source state 不一致

它有两套运行方式：

- 确定性本地 demo
  - [daily_notes_doc_agents.py](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/daily_notes_doc_agents.py)
- 真实 Codex demo
  - 通过 [automation_codex_demo.py](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/automation_codex_demo.py) 统一调度
  - 底层 session runner 是 [codex_session_demo.py](/C:/Users/oql/OneDrive/Study/bfrl/demo/codex_demo/codex_session_demo.py)

## 目录

- [configs](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/configs)
  - 确定性本地 demo 配置
- [runner-configs](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/runner-configs)
  - 真实 Codex 轮询配置
- [runner-tasks](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/runner-tasks)
  - 真实 Codex 任务模板
- [system-prompts](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/system-prompts)
  - 两个 Agent 的 system prompt
- [fixtures/workspace](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/fixtures/workspace)
  - 演示用工作区
- [jobs](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/jobs)
  - 确定性本地 demo 的 state/report
- [runner-jobs](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/runner-jobs)
  - 真实 Codex 轮询的 inbox/archive/logs/notes/state

## 派生文档结构

目标目录：

- [daily-note-derived](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/fixtures/workspace/memory/doc/daily-note-derived)

核心文件：

- [README.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/fixtures/workspace/memory/doc/daily-note-derived/README.md)
- [current-state.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/fixtures/workspace/memory/doc/daily-note-derived/current-state.md)
- [decisions.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/fixtures/workspace/memory/doc/daily-note-derived/decisions.md)
- [open-questions.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/fixtures/workspace/memory/doc/daily-note-derived/open-questions.md)
- [source-map.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/fixtures/workspace/memory/doc/daily-note-derived/source-map.md)

关键约束：

- 每条非平凡结论都需要 `Source notes:`
- 引用必须能定位到 `../../daily-notes/<note-id>.md`
- `source-map.md` 必须是一条 note 一行、排序稳定、无重复

## 真实 Codex 运行

真实 runner 配置：

- [daily-notes-to-doc.json](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/runner-configs/daily-notes-to-doc.json)
- [doc-audit.json](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/runner-configs/doc-audit.json)

真实任务模板：

- [daily-notes-to-doc-task.json](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/runner-tasks/daily-notes-to-doc-task.json)
- [doc-audit-task.json](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/runner-tasks/doc-audit-task.json)

system prompt：

- [daily-notes-to-doc-system.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/system-prompts/daily-notes-to-doc-system.md)
- [doc-audit-system.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/system-prompts/doc-audit-system.md)

列出这组 runner 配置：

```powershell
python demo\automation_poller\automation_codex_demo.py list --config-dir demo\automation_poller\daily_notes_doc\runner-configs
```

跑 source agent：

```powershell
python demo\automation_poller\automation_codex_demo.py run --config demo\automation_poller\daily_notes_doc\runner-configs\daily-notes-to-doc.json
```

跑 audit agent：

```powershell
python demo\automation_poller\automation_codex_demo.py run --config demo\automation_poller\daily_notes_doc\runner-configs\doc-audit.json
```

统一跑两个 Agent：

```powershell
python demo\automation_poller\automation_codex_demo.py watch-all --config-dir demo\automation_poller\daily_notes_doc\runner-configs --once --max-runs 2
```

## 结果查看

正式 demo 的派生文档：

- [daily-note-derived](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/fixtures/workspace/memory/doc/daily-note-derived)

正式 source 状态和报告：

- [runtime-state.json](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/jobs/daily-notes-to-doc/state/runtime-state.json)
- [reports](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/jobs/daily-notes-to-doc/reports)

正式 audit 状态和报告：

- [runtime-state.json](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/jobs/doc-audit/state/runtime-state.json)
- [reports](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/jobs/doc-audit/reports)

真实 runner 的调度日志：

- [daily-notes-to-doc-real](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/runner-jobs/daily-notes-to-doc-real)
- [doc-audit-real](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/runner-jobs/doc-audit-real)

## 确定性本地验证

如果你要跑最早那套本地规则化验证：

```powershell
python demo\automation_poller\daily_notes_doc\daily_notes_doc_agents.py validate
```

这条命令会在：

- [daily_notes_doc/_scratch](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/_scratch)

下面完成闭环验证，但它不是“真实 Codex 执行”。

## 真实验证结论

这套真实架构已经验证过：

- 真实 Codex 会写派生 docs、state、report
- `daily-notes-to-doc` 重跑后会 `skipped`
- `doc-audit` 会写 `pass/fail` 报告
- 统一 `watch-all` 可以顺序跑通两个 Agent
- 在 [real-agent-validation](/C:/Users/oql/OneDrive/Study/bfrl/demo/codex_demo/_scratch/real-agent-validation) 里已经做过真实 `fail -> refresh -> pass` 闭环验证
