# 小控 - 你的专用课程助手

后端 FastAPI + deepagents，前端 Flet，两者只通过 HTTP 通信。

## 目录

```text
xiaokong/
├── backend/
│   ├── config.py     # 从 .env 读配置
│   ├── agent.py      # create_deep_agent(...)
│   ├── audio.py      # TTS / ASR
│   └── main.py       # FastAPI 接口
├── frontend/
│   ├── api.py        # 调后端接口
│   ├── speech.py     # 边生成边朗读
│   ├── robot.py      # 机器人小控
│   └── main.py       # Flet 界面
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
| POST | `/chat` | SSE 流式回复，`data: {"text": "..."}` |
| POST | `/tts` | `{"text": "..."}` → MP3 |
| POST | `/asr` | multipart 文件 → `{"text": "..."}` |

调试：

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}]}'
```

## 加功能

- 课程工具：写一个 LangChain tool，加进 `backend/agent.py` 的 `TOOLS`。
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
