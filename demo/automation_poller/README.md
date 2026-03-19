# Automation Poller Demo

这个目录演示“按配置轮询执行 Codex 任务”。

它本身不关心任务内容，只关心三件事：

1. 从配置文件读取轮询周期和 runner 参数
2. 按周期生成任务实例
3. 为每个 automation 维护独立的 `inbox / archive / logs / notes / state`

## 目录

- [automation_codex_demo.py](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/automation_codex_demo.py)
- [configs](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/configs)
- [tasks](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/tasks)
- [jobs](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/jobs)
- [daily_notes_doc](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc)

底层 session runner 由 [codex_session_demo.py](/C:/Users/oql/OneDrive/Study/bfrl/demo/codex_demo/codex_session_demo.py) 提供。

## 配置模型

每个 automation 配置至少包含：

- `name`
- `poll_interval_seconds`
- `task_file`
- `runner`

`runner` 里可以指定：

- `mode`
- `session_style`
- `model`
- `max_turns`
- `shell`
- `usage_view`
- `codex_prompt_mode`
- `background`
- `reasoning_effort`

## 命令

列出一组配置目录里的 automation：

```powershell
python demo\automation_poller\automation_codex_demo.py list
```

如果要列出别的配置目录：

```powershell
python demo\automation_poller\automation_codex_demo.py list --config-dir demo\automation_poller\daily_notes_doc\runner-configs
```

跑单个配置文件：

```powershell
python demo\automation_poller\automation_codex_demo.py run --config demo\automation_poller\configs\hello-codex.json
```

轮询单个配置文件：

```powershell
python demo\automation_poller\automation_codex_demo.py watch --config demo\automation_poller\configs\hello-codex.json --once --max-runs 1
```

轮询一整个配置目录：

```powershell
python demo\automation_poller\automation_codex_demo.py watch-all --config-dir demo\automation_poller\configs --once --max-runs 2
```

参数语义：

- `--config`
  - 指向单个配置文件
  - 只用于 `run` 和 `watch`
- `--config-dir`
  - 指向一个配置目录
  - 只用于 `list` 和 `watch-all`

## 产物位置

每个 automation 都会有自己的 job 目录：

- `jobs/<name>/inbox`
- `jobs/<name>/archive`
- `jobs/<name>/logs`
- `jobs/<name>/notes`
- `jobs/<name>/state/runtime-state.json`

## Daily Notes -> Doc 示例

轮询框架上的双 Agent 示例在：

- [daily_notes_doc/README.md](/C:/Users/oql/OneDrive/Study/bfrl/demo/automation_poller/daily_notes_doc/README.md)

统一运行：

```powershell
python demo\automation_poller\automation_codex_demo.py watch-all --config-dir demo\automation_poller\daily_notes_doc\runner-configs --once --max-runs 2
```
