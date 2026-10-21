# 小控 - 你的专用课程助手

一个面向课程学习的 Windows 桌面语音助手：读课件、答问题、边生成边朗读，
并带一个会做手势的机器人「小控」。

## 功能

- OpenAI 兼容大模型（默认 OpenCodeGo），流式输出
- 豆包 / OpenAI 兼容 / TTS.ai 的 ASR 与 TTS
- 课件解析：PPTX / DOCX / XLSX / XLS / PDF / TXT（MarkItDown）
- **边生成边朗读**：按句子流水线合成，下一句在当前句播放时预合成
- **实时字幕**：只显示已说出的内容，已读部分渐隐，说完统一成柔和色；可滚轮回看
- 机器人小控：口型跟随真实音频音量，手臂做缓动手势
- 两种界面：默认「只保留语音」，一键展开完整对话 + 历史记录
- 本地历史对话与配置；旧版本数据自动迁移

## 目录结构

```text
xiaokong/
├── main.py                 # Flet 入口（薄壳）
├── pyproject.toml
├── requirements.txt
├── run.ps1 / build.ps1
├── src/xiaokong/
│   ├── config.py           # 配置、默认提示词、数据目录迁移
│   ├── embedded_secrets.py # 内置密钥（可用环境/设置覆盖）
│   ├── storage.py          # 会话持久化
│   ├── agent/              # 智能体层（只在这里调用模型）
│   │   ├── base.py         # Agent / AgentContext / Tool 契约
│   │   ├── events.py       # TextDelta / ToolCall / AgentDone
│   │   ├── chat.py         # 默认 ChatAgent（直接流式对话）
│   │   ├── deep.py         # deepagents 0.7.x 适配器（预留/可选）
│   │   ├── registry.py     # 按 agent_kind 创建智能体
│   │   └── tools.py        # 工具注册表骨架
│   ├── services/           # 上游 API 客户端
│   │   ├── llm.py          # 流式 chat/completions
│   │   ├── asr.py          # 批量语音识别
│   │   ├── asr_stream.py   # 豆包流式语音识别
│   │   ├── tts.py          # 豆包 / TTS.ai / OpenAI 兼容语音合成
│   │   └── common.py       # URL、鉴权、错误提取
│   ├── speech/             # 语音流水线
│   │   ├── text.py         # 切句 + Markdown 清洗
│   │   ├── pipeline.py     # 句子队列与预合成
│   │   ├── player.py       # 播放 + 口型 + 字幕进度
│   │   └── analysis.py     # 音量包络、播放位置跟随
│   └── ui/
│       ├── app.py          # AssistantApp：页面、对话、录音、设置
│       ├── messages.py     # 消息气泡渲染
│       └── robot.py        # 机器人小控
├── tests/
└── docs/architecture.md
```

## 快速开始

```powershell
cd E:\PythonProjects\xiaokong
.\run.ps1
```

或手动：

```powershell
uv venv .venv --python 3.13
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.\.venv\Scripts\flet.exe run main.py
```

## 配置

设置保存在 `%APPDATA%\小控\settings.json`，历史对话保存在
`%APPDATA%\小控\conversations.json`。旧版 `问答助手` / `FletVoiceQA`
目录会自动迁移。

默认系统提示词把助手设定为专业课程助手（见 `config.DEFAULT_SYSTEM_PROMPT`），
可在「接口设置 → 对话 → 系统提示词」修改。

## 环境配置（.env）

模型地址、Key 等部署配置现在支持项目根目录的 `.env`。

优先级从高到低：

1. **真实环境变量 / `.env`**
2. `%APPDATA%\小控\settings.json`（界面里保存的值）
3. `src/xiaokong/embedded_secrets.py`（本地内置密钥）
4. 代码默认值

文件：

| 文件 | 用途 | 是否提交 |
|---|---|---|
| `.env.example` | 变量模板，无密钥 | ✅ 可以提交 |
| `.env` | 本机实际配置，含密钥 | ❌ **绝不提交** |
| `src/xiaokong/embedded_secrets.example.py` | 内置密钥模板 | ✅ 可以提交 |
| `src/xiaokong/embedded_secrets.py` | 真实内置密钥 | ❌ **绝不提交** |

生成或刷新 `.env`（从界面设置导出，不打印密钥）：

```powershell
.\.venv\Scripts\python.exe scripts\export_env.py
```

也可以用 `XIAOKONG_ENV_FILE` 指定任意路径的 env 文件。
打包后把 `.env` 放在 `小控.exe` 同目录也会被读取。

常用变量：

```dotenv
XIAOKONG_LLM_BASE_URL=https://opencode.ai/zen/go/v1
XIAOKONG_LLM_API_KEY=...
XIAOKONG_CHAT_MODEL=deepseek-v4.1-flash
XIAOKONG_AGENT_KIND=chat
```

也兼容 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` 这类通用变量。

### 绝不能提交 Git 的文件

| 路径 | 原因 |
|---|---|
| `.env`、`.env.*`（`.env.example` 除外） | API Key、模型地址等本机配置 |
| `src/xiaokong/embedded_secrets.py` | 真实内置密钥 |
| `%APPDATA%\小控\settings.json` / `conversations.json` | 不在仓库内，但同样含密钥与聊天记录 |
| `.venv/` | 本机虚拟环境 |
| `.flet/` | Flet 运行时缓存 |
| `build/`、`dist/`、`*.spec` | 构建产物（EXE 不要进 Git） |
| `*.log`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/` | 临时文件 |

以上（除 `%APPDATA%` 外）都已经写进 `.gitignore`。

## 智能体层（deepagents）

模型调用全部收敛在 `agent/`：

```text
UI ──AgentEvent──▶ Agent ──▶ services.llm / deepagents
```

- `agent_kind = "chat"`：默认，直接流式调用 OpenAI 兼容接口。
- `agent_kind = "deep"`：启用 `deepagents==0.7.28` 适配器（需要安装并配置
  `langchain-openai`，已列入依赖）。

切换方式（在 `%APPDATA%\小控\settings.json` 中）：

```json
{ "agent_kind": "deep" }
```

后续加工具/子智能体的入口：

```python
from xiaokong.agent import create_agent
from xiaokong.agent.deep import DeepAgentAdapter

agent = create_agent("deep", settings)
assert isinstance(agent, DeepAgentAdapter)
agent.register_tool(my_tool)          # LangChain BaseTool
agent.register_subagent({             # deepagents SubAgent
    "name": "courseware-analyst",
    "description": "分析课件结构与重点",
    "system_prompt": "你是课件分析专家……",
})
```

详见 [docs/architecture.md](docs/architecture.md)。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 打包

```powershell
.\build.ps1
```

输出：`dist\小控.exe`。
