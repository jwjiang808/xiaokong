# 小控

后端 FastAPI + deepagents，前端 Flet，两者只通过 HTTP 通信。

## 目录

```text
xiaokong/
├── backend/
│   ├── config.py     # 从 .env 读配置
│   ├── agent.py      # create_deep_agent(...)
│   ├── history.py    # SQLite 会话、运行和步骤持久化
│   ├── workspace.py  # 本地工作区 + 执行后端
│   ├── shell.py      # Windows 容错解码的 shell
│   ├── tools/        # 智能体工具（publish_project）
│   ├── mcp.py        # MCP 接口占位
│   ├── audio.py      # 豆包 TTS / 流式 ASR 入口
│   ├── asr_doubao.py # 豆包 sauc 流式识别协议
│   └── main.py       # FastAPI 接口
├── frontend/
│   ├── api.py        # 调后端接口
│   ├── conversation.py # 用户消息、思考/工具步骤、回答分区
│   ├── speech.py     # 边生成边朗读
│   ├── robot.py      # 机器人小控
│   └── main.py       # Flet 界面
├── common/
│   └── logging_setup.py # Loguru 统一日志
├── main.py           # 前端入口
├── .env.example
├── run.ps1
└── build.ps1
```

## 运行

```powershell
cd E:\PythonProjects\xiaokong
.\run.ps1
```

会启动两个进程：

- 后端：`python -m backend.main` → `http://127.0.0.1:8000`
- 前端：`flet run main.py`

也可以分别启动：

```powershell
.\.venv\Scripts\python.exe -m backend.main
.\.venv\Scripts\flet.exe run main.py
```

## 配置

复制 `.env.example` 为 `.env`，填写模型地址和 Key。配置只从 `.env` 读取。

前端后端地址：`XIAOKONG_BACKEND_URL`（默认 `http://127.0.0.1:8000`）。

## 智能体工作区

默认目录：`%USERPROFILE%\Documents\小控工作区`，可用
`XIAOKONG_WORKSPACE` 修改。首次启动自动创建：

```text
小控工作区/
├── AGENTS.md   # 记忆，模型会自动读写
├── work/       # 开发中的代码
├── output/     # 验证通过后发布的代码
└── skills/     # 模型自己创建的技能（SKILL.md）
```

后端用 `LocalShellBackend(root_dir=工作区, virtual_mode=True)`：

- 文件工具被限制在工作区内
- 提供 `execute`，可以运行 Python / shell
- 模型验证代码后调用 `publish_project`，把 `work/<项目>` 复制到 `output/<项目>`
- 记忆通过 `memory=["/AGENTS.md"]` 注入
- Skills 通过 `skills=["/skills/"]` 加载

MCP 只保留接口：`backend/mcp.py` 的 `load_mcp_tools()` 目前返回空列表。

> 注意：`execute` 在本机运行，不是容器隔离。它会继承最小的系统环境变量
> （PATH、TEMP 等），不会继承 API Key。

## 执行历史数据库

使用 Python 内置 SQLite，单文件、无服务、无需额外安装，适合 PyInstaller 打包。
默认数据库：

```text
%USERPROFILE%\Documents\小控工作区\xiaokong.db
```

可用 `XIAOKONG_DB_PATH` 修改。常见数据库工具（DB Browser for SQLite、
DBeaver、DataGrip）可以直接打开：

- `readable_runs`：一轮对话的输入、最终回答、状态和时间。
- `readable_steps`：每个思考/工具步骤一行，包含完整输入与输出。
- `readable_messages`：按步骤保存的中间回复文本。
- `steps`：原始事件流水，用于最细粒度追踪。
- `step_records`：供 `readable_steps` 使用的整理后步骤数据。

数据库保存完整内容；前端只显示折叠后的截断预览，避免超长内容难以阅读。

前端标题栏的历史按钮会展开左侧会话栏。每轮对话归属一个会话，可以新建会话，
也可以点击历史记录恢复之前的用户消息、执行步骤和回答。

## 图片与 PPT

- 聊天输入框支持 `png/jpg/jpeg/webp/bmp` 图片，前端会把长边压到 1600 像素后作为视觉输入传给模型。
- 文档不再由前端转成文字；小控收到本地文件路径后，用 `execute` 中的 PowerShell/Python 自行读取。
- 可以点击文件夹按钮指定一个资料目录，小控会按需列出和读取其中文件。
- 当前 `deepseek-v4.1-flash` 已实测支持图片理解。
- 工作区已安装 `skills/ppt-master/`（PPT Master 6.7.3，MIT），可直接说“用小控把这份资料做成 PPT”。
- PPT Master 使用独立 `.venv`，不要把它和 PyMuPDF 一起打进分发包，除非已经核对 AGPL 许可要求。

对话区按照事件顺序显示“思考/工具折叠组 → 中间回复 → 下一组思考 → 最终回答”。
最终回答前会显示分隔线和本轮总耗时。

语音只走豆包：

界面使用一个“语音交互”开关，同时控制语音自动发送和回复朗读，默认关闭。

| 变量 | 默认值 |
|---|---|
| `XIAOKONG_DOUBAO_API_KEY` | 必填 |
| `XIAOKONG_DOUBAO_TTS_RESOURCE_ID` | `seed-tts-2.0` |
| `XIAOKONG_DOUBAO_TTS_VOICE` | `zh_female_vv_uranus_bigtts` |
| `XIAOKONG_DOUBAO_ASR_RESOURCE_ID` | `volc.seedasr.sauc.duration` |
| `XIAOKONG_DOUBAO_ASR_MODEL` | `bigmodel` |

**绝对不能提交 Git：**

| 文件 | 原因 |
|---|---|
| `.env`（`.env.example` 除外） | API Key、模型地址 |
| `.venv/` | 本机虚拟环境 |
| `.flet/` | Flet 运行时缓存 |
| `build/`、`dist/`、`*.spec` | 构建产物 |
| `.idea/`、`.vscode/`、`*.log` | 本地设置与日志 |

以上都已写进 `.gitignore`。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/conversations` | 最近的会话列表 |
| GET | `/conversations/{id}` | 恢复一个会话的消息和步骤 |
| POST | `/chat` | SSE 结构化事件：思考、工具步骤、文本增量、完成或错误 |
| POST | `/tts` | `{"text": "..."}` → MP3；默认不启用朗读 |
| POST | `/asr` | 上传 WAV → 豆包流式 ASR（sauc）→ `{"text": "..."}` |

调试：

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}]}'
```

## 加功能

- 自定义工具：写一个 LangChain tool，加进 `backend/agent.py` 的 `TOOLS`。
- 子智能体：写一个 `SubAgent` 字典，加进 `SUBAGENTS`。
- 新接口：在 `backend/main.py` 加一个路由，前端在 `frontend/api.py` 调它。

## 打包

```powershell
.\build.ps1
```

输出：

```text
dist\小控.exe                     # 前端
dist\server\xiaokong-server.exe   # 后端
```

打包后把 `.env` 放到 `dist\server\.env`（后端读取模型/语音配置）。
前端默认连 `http://127.0.0.1:8000`，可用环境变量
`XIAOKONG_BACKEND_URL` 改成别的地址。

> 注意：`dist\server\.env` 里是真实密钥，分发时不要把它一起发出去。

## 换机器与工作区

EXE 只包含程序代码，不包含 `小控工作区`、SQLite 历史或 `.env`。
首次启动后端时会自动创建：

```text
%USERPROFILE%\Documents\小控工作区\
├── AGENTS.md
├── xiaokong.db
├── work/
├── output/
└── skills/
```

模型和豆包语音仍需要在新机器的 `dist\server\.env` 中配置。

PPT Master 可以复制：

```text
skills\ppt-master\
```

不要复制其中的 `.venv`，该目录与本机环境绑定。技能目录内的 `python` 是
离线便携运行时，需要一起复制。复制完成后双击：

```text
skills\ppt-master\一键安装.cmd
```

脚本直接使用技能目录内的 Python 和依赖完成导入测试与完整性检查，不联网，
不需要系统 Python 或管理员权限。
DeepAgents 会自动扫描 `skills/` 下所有带 `SKILL.md` 的目录，不需要逐个注册。
