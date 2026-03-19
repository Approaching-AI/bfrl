# Demo

当前 `demo/` 下有两块：

- [codex_demo](/C:/Users/oql/OneDrive/Study/bfrl/demo/codex_demo)
  - 单次 Codex session demo
  - 关注一条任务如何进入 session、如何调用工具、如何写日志
- [automation_poller](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller)
  - 轮询调度 demo
  - 关注如何按配置周期性生成任务、运行任务、维护每个 job 的状态

## 目录

- [codex_session_demo.py](/C:/Users/oql/OneDrive/Study/bfrl/demo/codex_demo/codex_session_demo.py)
- [automation_codex_demo.py](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/automation_codex_demo.py)
- [automation_poller/README.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/README.md)
- [daily_notes_doc/README.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/README.md)

## 单次 Session Demo

跑一个单任务 session：

```powershell
python demo\codex_demo\codex_session_demo.py run --task demo\codex_demo\inbox\sample-task.json
```

跑 command-proxy 风格：

```powershell
python demo\codex_demo\codex_session_demo.py --session-style command-proxy run --task demo\codex_demo\inbox\sample-task.json
```

如果要走真实 Codex：

```powershell
python demo\codex_demo\codex_session_demo.py --mode codex --model gpt-5.4 run --task demo\codex_demo\inbox\sample-task.json
```

## 轮询 Demo

列出轮询配置：

```powershell
python demo\automation_poller\automation_codex_demo.py list
```

跑单个轮询配置：

```powershell
python demo\automation_poller\automation_codex_demo.py run --config demo\automation_poller\configs\hello-codex.json
```

跑全部启用配置：

```powershell
python demo\automation_poller\automation_codex_demo.py watch-all --once --max-runs 2
```

## 真实双 Agent Demo

`daily-notes -> doc` 和 `doc-audit` 的真实 Codex 轮询 demo 在：

- [daily_notes_doc](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc)

统一运行命令：

```powershell
python demo\automation_poller\automation_codex_demo.py watch-all --config-dir demo\automation_poller\daily_notes_doc\runner-configs --once --max-runs 2
```

更完整的说明看：

- [daily_notes_doc/README.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/README.md)
