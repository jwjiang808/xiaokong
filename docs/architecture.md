# 架构说明

## 分层

```text
┌──────────────────────────────────────────────┐
│ ui/                                          │
│  app.py      AssistantApp：状态 / 事件 / 布局 │
│  messages.py 聊天气泡                          │
│  robot.py    机器人小控                        │
└───────────────┬──────────────────────────────┘
                │ AgentEvent (TextDelta / AgentDone / ToolCall …)
┌───────────────▼──────────────────────────────┐
│ agent/                                        │
│  base.py    Agent / AgentContext / Attachment │
│  chat.py    ChatAgent（默认）                  │
│  deep.py    DeepAgentAdapter（deepagents）     │
│  registry.py 按 agent_kind 创建                │
│  tools.py   工具注册表（预留）                  │
└───────────────┬──────────────────────────────┘
                │
┌───────────────▼──────────────────────────────┐
│ services/   llm.py / asr.py / asr_stream.py / tts.py │
└──────────────────────────────────────────────┘

speech/   切句 → 合成队列 → 播放 → 音量包络 → 字幕进度
storage.py / config.py  本地状态
```

依赖方向：`ui → agent → services`，`ui → speech`。`services` 不知道 UI，
`agent` 不知道 Flet，`ui` 不直接调用任何 HTTP 接口。

## Agent 契约

```python
@dataclass
class AgentContext:
    system_prompt: str
    history: list[dict[str, str]]      # 不含 system / 当前问题
    attachments: list[Attachment]      # 课件文本

class Agent(ABC):
    def stream(self, ctx, user_text) -> AsyncIterator[AgentEvent]: ...
    async def close(self) -> None: ...
```

UI 只处理事件：

| 事件 | UI 行为 |
|---|---|
| `TextDelta` | 追加到消息、字幕，并推入语音流水线 |
| `AgentDone` | 用最终文本替换累积内容 |
| `ToolCall` / `ToolResult` | 预留，当前 UI 忽略 |

这样以后把 `ChatAgent` 换成工具调用型智能体，UI 不需要改。

## deepagents 适配（0.7.28）

`DeepAgentAdapter` 读取 `deepagents.create_deep_agent` 的返回图：

```python
graph = create_deep_agent(
    model=ChatOpenAI(model=..., base_url=..., api_key=...),
    tools=self._tools or None,
    system_prompt=system_prompt,
    subagents=self._subagents or None,
    name="xiaokong",
)

async for chunk, metadata in graph.astream(
    {"messages": messages}, stream_mode="messages"
):
    ...
```

deepagents 自带的 `ls / read_file / write_file / glob / grep / execute / task`
工具默认可用；`register_tool()` 和 `register_subagent()` 是课程场景的扩展点。

### 为什么默认仍是 chat

deepagents 会引入规划、文件系统、子智能体等能力，行为和延迟都与直接对话不同。
因此 `agent_kind` 默认 `"chat"`，需要时改成 `"deep"` 即可切换，两者输出同样的
`AgentEvent` 流，UI 与语音链路无需改动。

## 语音链路

```text
LLM 文本流 ──▶ SentenceSplitter（按句切分、去 Markdown/代码）
           ──▶ SpeechPipeline（合成当前句 + 预合成下一句）
           ──▶ ClipPlayer（bytes 播放、音量包络、播放位置）
           ──▶ Robot（口型/手势）+ 字幕（高亮已读、渐隐、滚动）
```

`ClipPlayer` 必须把音频 **bytes** 交给 `flet_audio`：临时文件路径不会触发
`on_loaded`，表现为完全没有声音。

## 测试

`tests/` 覆盖：切句、朗读流水线、字幕规则、口型映射、布局稳定、动作平滑、
ASR 接线、配置迁移、提示词升级、Agent 注册与消息构造。
