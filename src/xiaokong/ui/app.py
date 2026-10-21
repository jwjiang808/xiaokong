"""小控 desktop application: page wiring, chat, voice and settings."""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
import time
from pathlib import Path

import flet as ft
import flet_audio_recorder as far
import httpx
from markitdown import MarkItDown

from ..agent import (
    AgentContext,
    AgentDone,
    Attachment,
    TextDelta,
    create_agent,
)
from ..config import AppSettings, get_settings_path, load_settings, save_settings
from ..services import (
    ApiError,
    DoubaoStreamingASR,
    DoubaoStreamingError,
    synthesize_speech,
    transcribe_audio,
)
from ..speech.pipeline import SpeechPipeline
from ..speech.player import ClipPlayer
from ..speech.text import clean_for_speech
from ..storage import Conversation, ConversationStore
from .messages import build_message, safe_update
from .robot import TechRobotDoll

APP_TITLE = "小控-你的专用课程助手"
SUPPORTED_DOCUMENT_EXTENSIONS = ["docx", "pptx", "xlsx", "xls", "pdf", "txt"]
MAX_DOCUMENT_CHARS = 60_000


class AssistantApp:
    """Owns all UI state for one Flet page."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page

        self.settings = load_settings()
        self.store = ConversationStore()
        conversations = self.store.all()
        self.current_conversation = (
            conversations[0] if conversations else self.store.create()
        )
        self.messages: list[dict[str, str]] = [
            {"role": "system", "content": self.settings.system_prompt},
            *self.current_conversation.messages,
        ]

        self.busy = False
        self.recording = False
        self.recording_path: Path | None = None
        self.streaming_session: DoubaoStreamingASR | None = None

        self.speech_session = 0
        self.speech_pipeline: SpeechPipeline | None = None

        self.sidebar_collapsed = False
        self.robot_visible = True
        self.chat_collapsed = True  # voice-only mode is the default
        self.attached_document_name: str | None = None
        self.attached_document_text: str | None = None

        self.document_converter = MarkItDown(enable_plugins=False)
        self.robot = TechRobotDoll()
        self.player = ClipPlayer(page, self.robot)
        self.agent = create_agent(self.settings.agent_kind, self.settings)

        self._configure_page()
        self._build_widgets()
        self._wire_events()

    # ------------------------------------------------------------------
    # page / widget construction
    # ------------------------------------------------------------------
    def _configure_page(self) -> None:
        page = self.page
        page.title = APP_TITLE
        page.theme_mode = ft.ThemeMode.LIGHT
        page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.TEAL,
            font_family="Microsoft YaHei UI",
        )
        page.bgcolor = "#F4F7F9"
        page.padding = 0
        page.window.width = 1200
        page.window.height = 760
        page.window.min_width = 980
        page.window.min_height = 760

    def _build_widgets(self) -> None:
        self.chat_list = ft.ListView(
            expand=True,
            spacing=16,
            padding=ft.Padding.symmetric(horizontal=20, vertical=18),
            auto_scroll=True,
        )
        self.status_text = ft.Text("", size=12, color="#52616B")
        self.progress = ft.ProgressRing(
            width=16,
            height=16,
            stroke_width=2,
            visible=False,
        )
        self.recorder = far.AudioRecorder(
            configuration=far.AudioRecorderConfiguration(
                encoder=far.AudioEncoder.WAV,
            ),
        )
        self.page.services.append(self.recorder)

        self.input_field = ft.TextField(
            hint_text="输入问题",
            hint_style=ft.TextStyle(color="#7B8794"),
            text_style=ft.TextStyle(color="#111827", size=15),
            multiline=True,
            min_lines=1,
            max_lines=5,
            filled=True,
            fill_color="#FFFFFF",
            border={
                ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                    border_radius=12,
                    side=ft.BorderSide(1, "#C9D4DF"),
                ),
                ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                    border_radius=12,
                    side=ft.BorderSide(2, "#0F9E91"),
                ),
            },
            expand=True,
            shift_enter=True,
            disabled=False,
        )
        self.send_button = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            tooltip="发送",
            icon_color=ft.Colors.WHITE,
            bgcolor="#0F9E91",
        )
        self.mic_button = ft.IconButton(
            icon=ft.Icons.MIC_ROUNDED,
            tooltip="开始录音",
            icon_color="#B42318",
            bgcolor="#FFE8E6",
        )
        self.file_button = ft.IconButton(
            icon=ft.Icons.ATTACH_FILE_ROUNDED,
            tooltip="上传文件",
            icon_color="#0F766E",
            bgcolor="#E6F7F4",
        )

        self.attachment_name_text = ft.Text(
            "",
            size=13,
            weight=ft.FontWeight.BOLD,
            color="#134E4A",
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )
        self.attachment_info_text = ft.Text("", size=11, color="#64748B")
        self.attachment_bar = ft.Container(
            visible=False,
            bgcolor="#ECFDF5",
            border=ft.Border.all(1, "#A7F3D0"),
            border_radius=9,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.DESCRIPTION_ROUNDED,
                        size=19,
                        color="#0F766E",
                    ),
                    ft.Column(
                        controls=[
                            self.attachment_name_text,
                            self.attachment_info_text,
                        ],
                        spacing=1,
                        expand=True,
                        tight=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        tooltip="移除文件",
                        icon_size=18,
                        on_click=lambda _e: self.clear_attachment(),
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        self.auto_send_switch = ft.Switch(
            label="语音自动发送",
            value=self.settings.auto_send_voice,
        )
        self.auto_speak_switch = ft.Switch(
            label="朗读回复",
            value=self.settings.auto_speak_replies,
        )

        self.history_list = ft.Column(
            controls=[],
            spacing=4,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        self.sidebar_box = ft.Container(
            width=270,
            bgcolor="#FFFFFF",
            border=ft.Border.only(right=ft.BorderSide(1, "#DCE4EA")),
            padding=ft.Padding.symmetric(horizontal=10, vertical=12),
        )

    def _wire_events(self) -> None:
        self.send_button.on_click = self.send_click
        self.file_button.on_click = self.pick_document
        self.input_field.on_submit = self.input_submit
        self.mic_button.on_click = self.toggle_recording

    # ------------------------------------------------------------------
    # status / conversation state
    # ------------------------------------------------------------------
    def set_status(self, text: str, *, is_error: bool = False) -> None:
        self.status_text.value = text
        self.status_text.color = (
            ft.Colors.ERROR if is_error else ft.Colors.ON_SURFACE_VARIANT
        )
        self.page.update()

    def set_busy(self, value: bool) -> None:
        self.busy = value
        self.progress.visible = value
        self.send_button.disabled = value
        self.mic_button.disabled = value
        self.file_button.disabled = value
        self.input_field.disabled = value
        self.page.update()

    @staticmethod
    def conversation_title(text: str) -> str:
        title = " ".join(text.strip().split())
        return title[:22] + ("…" if len(title) > 22 else "")

    def persist_current_conversation(self) -> None:
        self.store.update(
            self.current_conversation.id,
            title=self.current_conversation.title,
            messages=self.messages[1:],
        )

    def add_message(self, role: str, text: str) -> None:
        self.messages.append({"role": role, "content": text})
        row, _markdown = build_message(role, text)
        self.chat_list.controls.append(row)
        if role == "user" and self.current_conversation.title == "新对话":
            updated = self.store.update(
                self.current_conversation.id,
                title=self.conversation_title(text),
            )
            if updated is not None:
                self.current_conversation = updated
        else:
            self.persist_current_conversation()
        self.render_sidebar()
        self.page.update()

    # ------------------------------------------------------------------
    # sidebar / conversations
    # ------------------------------------------------------------------
    def render_sidebar(self) -> None:
        box = self.sidebar_box
        box.width = 62 if self.sidebar_collapsed else 270
        if self.sidebar_collapsed:
            box.padding = ft.Padding.symmetric(horizontal=7, vertical=12)
            box.content = ft.Column(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.ADD_COMMENT_ROUNDED,
                        tooltip="新对话",
                        on_click=self.new_conversation,
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
            return

        box.padding = ft.Padding.symmetric(horizontal=10, vertical=12)
        self.history_list.controls = []
        for conversation in self.store.all():
            selected = conversation.id == self.current_conversation.id
            self.history_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                                size=18,
                                color="#0F766E" if selected else "#64748B",
                            ),
                            ft.Text(
                                conversation.title,
                                size=14,
                                color="#0F172A" if selected else "#475569",
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,
                            ),
                        ],
                        spacing=9,
                    ),
                    bgcolor="#DDF7F3" if selected else None,
                    border_radius=9,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=10),
                    on_click=lambda _e, item=conversation: self.load_conversation(item),
                )
            )

        box.content = ft.Column(
            controls=[
                ft.Button(
                    "新对话",
                    icon=ft.Icons.ADD_COMMENT_ROUNDED,
                    width=225,
                    style=ft.ButtonStyle(
                        bgcolor="#0F9E91",
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=9),
                    ),
                    on_click=self.new_conversation,
                ),
                ft.Divider(height=16),
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.HISTORY_ROUNDED,
                            size=17,
                            color="#64748B",
                        ),
                        ft.Text(
                            "历史对话",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color="#64748B",
                        ),
                    ],
                    spacing=7,
                ),
                ft.Container(content=self.history_list, expand=True),
            ],
            expand=True,
            spacing=6,
        )

    def load_conversation(self, conversation: Conversation) -> None:
        if self.busy or conversation.id == self.current_conversation.id:
            return
        self.clear_attachment()
        self.current_conversation = conversation
        self.messages = [
            {"role": "system", "content": self.settings.system_prompt},
            *conversation.messages,
        ]
        self.chat_list.controls.clear()
        for message in conversation.messages:
            row, _markdown = build_message(
                message["role"],
                message["content"],
            )
            self.chat_list.controls.append(row)
        self.render_sidebar()
        self.page.update()

    def new_conversation(self, _e: ft.Event[ft.Control] | None = None) -> None:
        if self.busy:
            return
        self.clear_attachment()
        self.current_conversation = self.store.create()
        self.messages = [{"role": "system", "content": self.settings.system_prompt}]
        self.chat_list.controls.clear()
        self.input_field.value = ""
        self.render_sidebar()
        self.page.update()

    def toggle_sidebar(self, _e: ft.Event[ft.IconButton]) -> None:
        self.sidebar_collapsed = not self.sidebar_collapsed
        self.render_sidebar()
        self.page.update()

    def toggle_robot(self, _e: ft.Event[ft.IconButton]) -> None:
        self.robot_visible = not self.robot_visible
        self.robot.panel.visible = self.robot_visible
        self.page.update()

    def toggle_chat(self, _e: ft.Event[ft.IconButton] | None = None) -> None:
        self.chat_collapsed = not self.chat_collapsed
        if self.chat_collapsed:
            self.robot_visible = True
            self.robot.panel.visible = True
        self.render_layout()

    # ------------------------------------------------------------------
    # speech
    # ------------------------------------------------------------------
    async def cancel_speech(self) -> None:
        self.speech_session += 1
        pipeline = self.speech_pipeline
        self.speech_pipeline = None
        if pipeline is not None:
            pipeline.cancel()
        await self.player.stop()
        self.robot.set_speaking(False)
        self.robot.clear_mouth_level()

    async def _play_sentence(self, audio: bytes, pipeline_ref: dict) -> None:
        """Play one sentence and report how far the voice has got."""
        active = pipeline_ref.get("pipeline")

        def on_progress(ratio: float) -> None:
            if active is None or not active.spoken:
                return
            done = sum(len(item) for item in active.spoken[:-1])
            current = active.spoken[-1]
            self.robot.set_read_spoken(done + round(len(current) * ratio))

        await self.player.play(audio, wait=True, on_progress=on_progress)
        if active is not None and active.spoken:
            self.robot.set_read_spoken(
                sum(len(item) for item in active.spoken)
            )

    # ------------------------------------------------------------------
    # documents
    # ------------------------------------------------------------------
    def clear_attachment(self) -> None:
        self.attached_document_name = None
        self.attached_document_text = None
        self.attachment_name_text.value = ""
        self.attachment_info_text.value = ""
        self.attachment_bar.visible = False
        safe_update(self.attachment_bar)

    async def pick_document(self, _e: ft.Event[ft.IconButton]) -> None:
        if self.busy:
            return
        files = await ft.FilePicker().pick_files(
            allow_multiple=False,
            with_data=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=SUPPORTED_DOCUMENT_EXTENSIONS,
        )
        if not files:
            return

        selected = files[0]
        suffix = Path(selected.name).suffix.lower().lstrip(".")
        if suffix not in SUPPORTED_DOCUMENT_EXTENSIONS:
            self.set_status("暂不支持这种文件格式。", is_error=True)
            return

        temp_path: Path | None = None
        source_path = Path(selected.path) if selected.path else None
        if source_path is None or not source_path.exists():
            if not selected.bytes:
                self.set_status("无法读取所选文件。", is_error=True)
                return
            temp_path = Path(tempfile.gettempdir()) / (
                f"xiaokong_upload_{int(time.time() * 1000)}.{suffix}"
            )
            await asyncio.to_thread(temp_path.write_bytes, selected.bytes)
            source_path = temp_path

        self.set_busy(True)
        self.set_status("正在解析文件...")
        try:
            result = await asyncio.to_thread(
                self.document_converter.convert_local,
                source_path,
            )
            text = (
                getattr(result, "markdown", None)
                or getattr(result, "text_content", "")
                or ""
            ).strip()
            if not text:
                raise ValueError("没有从文件中提取到文本。")

            truncated = len(text) > MAX_DOCUMENT_CHARS
            if truncated:
                text = text[:MAX_DOCUMENT_CHARS]

            self.attached_document_name = selected.name
            self.attached_document_text = text
            self.attachment_name_text.value = selected.name
            self.attachment_info_text.value = (
                f"已提取 {len(text):,} 字符"
                + ("，超出部分已截断" if truncated else "")
            )
            self.attachment_bar.visible = True
            self.attachment_bar.update()
            self.set_status("文件解析完成，可以开始提问。")
        except Exception as exc:  # noqa: BLE001 - surface any parser failure
            self.set_status(f"文件解析失败：{exc}", is_error=True)
        finally:
            if temp_path is not None:
                with contextlib.suppress(OSError):
                    temp_path.unlink(missing_ok=True)
            self.set_busy(False)

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------
    async def send_text(self, text: str, *, speak: bool | None = None) -> None:
        text = text.strip()
        if not text or self.busy:
            return

        await self.cancel_speech()
        self.add_message("user", text)
        self.input_field.value = ""
        self.set_busy(True)
        self.set_status("正在生成回复...")

        should_speak = (
            bool(self.auto_speak_switch.value) if speak is None else speak
        )
        session_id = self.speech_session
        read_text = ""
        self.robot.set_read_text("")
        self.robot.set_read_spoken(0)

        pipeline: SpeechPipeline | None = None
        pipeline_ref: dict = {}
        if should_speak:
            session_id = self.speech_session + 1
            self.speech_session = session_id

            def handle_speech_finished() -> None:
                if session_id == self.speech_session:
                    self.robot.set_speaking(False)
                    self.robot.clear_mouth_level()
                    self.robot.set_read_spoken(len(read_text))
                    self.set_status("就绪")

            pipeline = SpeechPipeline(
                synthesize=lambda chunk: synthesize_speech(self.settings, chunk),
                play_clip=lambda audio: self._play_sentence(audio, pipeline_ref),
                on_start=lambda: self.set_status("正在回应..."),
                on_error=lambda message: self.set_status(
                    f"语音失败：{message}",
                    is_error=True,
                ),
                on_finish=handle_speech_finished,
            )
            pipeline_ref["pipeline"] = pipeline
            self.speech_pipeline = pipeline
            pipeline.start()

        try:
            assistant_row, assistant_markdown = build_message("assistant", "")
            self.chat_list.controls.append(assistant_row)
            self.messages.append({"role": "assistant", "content": ""})
            self.page.update()

            reply_parts: list[str] = []
            try:
                attachments = []
                if self.attached_document_text and self.attached_document_name:
                    attachments.append(
                        Attachment(
                            name=self.attached_document_name,
                            text=self.attached_document_text,
                        )
                    )
                context = AgentContext(
                    system_prompt=self.settings.system_prompt,
                    history=list(self.messages[1:-2]),
                    attachments=attachments,
                )
                async for event in self.agent.stream(context, text):
                    if isinstance(event, TextDelta):
                        reply_parts.append(event.text)
                        assistant_markdown.value = "".join(reply_parts)
                        safe_update(assistant_markdown)
                        read_text = clean_for_speech("".join(reply_parts))
                        self.robot.set_read_text(read_text)
                        if pipeline is None:
                            self.robot.set_read_spoken(len(read_text))
                        else:
                            pipeline.push(event.text)
                    elif isinstance(event, AgentDone):
                        # Final trimmed text wins over accumulated deltas.
                        if event.text:
                            reply_parts = [event.text]
            except Exception as exc:  # noqa: BLE001 - show provider errors
                self.set_status(str(exc), is_error=True)
                self.messages.pop()
                self.persist_current_conversation()
                if not reply_parts:
                    assistant_markdown.value = "生成失败"
                    safe_update(assistant_markdown)
                return

            reply = "".join(reply_parts).strip()
            if not reply:
                self.messages.pop()
                assistant_markdown.value = "生成失败"
                safe_update(assistant_markdown)
                self.set_status("问答接口返回了空内容。", is_error=True)
                return

            self.messages[-1]["content"] = reply
            self.persist_current_conversation()
            self.render_sidebar()
        finally:
            if pipeline is not None and session_id == self.speech_session:
                pipeline.close()
            self.set_busy(False)

    async def send_click(self, _e: ft.Event[ft.IconButton]) -> None:
        await self.send_text(self.input_field.value)

    async def input_submit(self, _e: ft.Event[ft.TextField]) -> None:
        await self.send_text(self.input_field.value)

    # ------------------------------------------------------------------
    # recording / ASR
    # ------------------------------------------------------------------
    async def update_streaming_text(self, text: str) -> None:
        self.input_field.value = text
        self.set_status("正在识别语音...")
        self.page.update()

    def handle_stream_chunk(self, event: far.AudioRecorderStreamEvent) -> None:
        if self.streaming_session is not None:
            asyncio.create_task(self.streaming_session.send_audio(event.chunk))

    async def toggle_recording(self, _e: ft.Event[ft.IconButton]) -> None:
        if self.busy:
            return

        if not self.recording:
            await self._start_recording()
            return

        await self._stop_recording()

    async def _start_recording(self) -> None:
        try:
            if not await self.recorder.has_permission():
                self.set_status("没有麦克风权限。", is_error=True)
                return

            use_streaming_asr = (
                self.settings.asr_provider == "doubao"
                and "sauc." in self.settings.doubao_asr_resource_id
            )
            if use_streaming_asr:
                self.streaming_session = DoubaoStreamingASR(
                    api_key=self.settings.doubao_api_key,
                    resource_id=self.settings.doubao_asr_resource_id,
                    on_partial=self.update_streaming_text,
                )
                await self.streaming_session.start()
                self.recorder.on_stream = self.handle_stream_chunk
                # The client only takes the streaming path when it can see the
                # handler; invoke_method does not flush pending properties.
                self.recorder.update()
                started = await self.recorder.start_recording(
                    configuration=far.AudioRecorderConfiguration(
                        encoder=far.AudioEncoder.PCM16BITS,
                        sample_rate=16000,
                        channels=1,
                    ),
                )
                if not started:
                    raise RuntimeError("录音器没有进入流式模式。")
                self.input_field.value = ""
            else:
                self.recorder.on_stream = None
                self.recorder.update()
                self.recording_path = Path(tempfile.gettempdir()) / (
                    f"xiaokong_{int(time.time() * 1000)}.wav"
                )
                started = await self.recorder.start_recording(
                    output_path=str(self.recording_path),
                    configuration=far.AudioRecorderConfiguration(
                        encoder=far.AudioEncoder.WAV,
                        sample_rate=16000,
                        channels=1,
                    ),
                )
                if not started:
                    raise RuntimeError("无法开始录音。")

            self.recording = True
            self.mic_button.icon = ft.Icons.STOP_CIRCLE_ROUNDED
            self.mic_button.tooltip = "停止录音"
            self.set_status("正在录音，点击停止后自动识别...")
        except Exception as exc:  # noqa: BLE001 - surface recorder errors
            if self.streaming_session is not None:
                await self.streaming_session.cancel()
                self.streaming_session = None
            self.set_status(f"无法开始录音：{exc}", is_error=True)

    async def _stop_recording(self) -> None:
        self.recording = False
        self.mic_button.disabled = True
        try:
            output_path = await self.recorder.stop_recording()
            self.mic_button.icon = ft.Icons.MIC_ROUNDED
            self.mic_button.tooltip = "开始录音"
            self.page.update()

            transcribed = ""
            if self.streaming_session is not None:
                self.set_busy(True)
                self.set_status("正在完成语音识别...")
                try:
                    transcribed = await self.streaming_session.finish()
                except DoubaoStreamingError as exc:
                    self.set_status(str(exc), is_error=True)
                    return
                finally:
                    await self.streaming_session.cancel()
                    self.streaming_session = None
                    self.recorder.on_stream = None
                    self.set_busy(False)
            else:
                if output_path:
                    self.recording_path = Path(output_path)
                if not self.recording_path or not self.recording_path.exists():
                    self.set_status("没有生成录音文件。", is_error=True)
                    return

                self.set_busy(True)
                self.set_status("正在识别语音...")
                try:
                    transcribed = await transcribe_audio(
                        self.settings,
                        self.recording_path,
                    )
                except (ApiError, httpx.HTTPError) as exc:
                    self.set_status(str(exc), is_error=True)
                    return
                finally:
                    self.set_busy(False)

            self.input_field.value = transcribed
            self.page.update()
            if self.auto_send_switch.value:
                await self.send_text(transcribed)
            else:
                self.set_status("识别完成，请确认后发送。")
        except Exception as exc:  # noqa: BLE001 - surface recorder errors
            self.set_status(f"录音失败：{exc}", is_error=True)
        finally:
            self.mic_button.disabled = False
            self.page.update()

    # ------------------------------------------------------------------
    # settings dialog
    # ------------------------------------------------------------------
    def settings_fields(self) -> dict[str, ft.Control]:
        settings = self.settings
        return {
            "llm_base_url": ft.TextField(
                label="LLM API Base URL",
                value=settings.llm_base_url,
                hint_text="https://opencode.ai/zen/go/v1",
            ),
            "llm_api_key": ft.TextField(
                label="LLM API Key",
                value="",
                hint_text=(
                    "已内置，可不填" if settings.llm_api_key else "请输入 API Key"
                ),
                password=True,
                can_reveal_password=False,
            ),
            "chat_model": ft.TextField(
                label="对话模型",
                value=settings.chat_model,
            ),
            "asr_provider": ft.Dropdown(
                label="ASR 接口类型",
                value=settings.asr_provider,
                options=[
                    ft.dropdown.Option("doubao", "豆包语音"),
                    ft.dropdown.Option("openai", "OpenAI 兼容"),
                    ft.dropdown.Option("tts_ai", "TTS.ai /v1/stt/"),
                ],
            ),
            "asr_base_url": ft.TextField(
                label="ASR API Base URL",
                value=settings.asr_base_url,
                hint_text="https://api.groq.com/openai/v1",
            ),
            "asr_api_key": ft.TextField(
                label="ASR API Key",
                value="",
                hint_text=(
                    "已内置，可不填" if settings.asr_api_key else "请输入 API Key"
                ),
                password=True,
                can_reveal_password=False,
            ),
            "asr_model": ft.TextField(
                label="ASR 模型",
                value=settings.asr_model,
            ),
            "tts_provider": ft.Dropdown(
                label="TTS 接口类型",
                value=settings.tts_provider,
                options=[
                    ft.dropdown.Option("doubao", "豆包语音"),
                    ft.dropdown.Option("tts_ai", "TTS.ai /v1/tts/"),
                    ft.dropdown.Option("openai", "OpenAI 兼容"),
                ],
            ),
            "tts_base_url": ft.TextField(
                label="TTS API Base URL",
                value=settings.tts_base_url,
                hint_text="https://api.tts.ai",
            ),
            "tts_api_key": ft.TextField(
                label="TTS API Key（TTS.ai 可留空）",
                value="",
                hint_text="已内置，可不填" if settings.tts_api_key else "需要时填写",
                password=True,
                can_reveal_password=False,
            ),
            "tts_model": ft.TextField(label="TTS 模型", value=settings.tts_model),
            "tts_voice": ft.TextField(label="TTS 音色", value=settings.tts_voice),
            "doubao_api_key": ft.TextField(
                label="豆包语音 API Key",
                value="",
                hint_text=(
                    "已内置，可不填"
                    if settings.doubao_api_key
                    else "请输入 API Key"
                ),
                password=True,
                can_reveal_password=False,
            ),
            "doubao_tts_resource_id": ft.TextField(
                label="豆包 TTS Resource ID",
                value=settings.doubao_tts_resource_id,
            ),
            "doubao_tts_voice": ft.TextField(
                label="豆包 TTS 音色",
                value=settings.doubao_tts_voice,
            ),
            "doubao_asr_resource_id": ft.TextField(
                label="豆包 ASR Resource ID",
                value=settings.doubao_asr_resource_id,
            ),
            "doubao_asr_model": ft.TextField(
                label="豆包 ASR 模型",
                value=settings.doubao_asr_model,
            ),
            "system_prompt": ft.TextField(
                label="系统提示词",
                value=settings.system_prompt,
                multiline=True,
                min_lines=3,
                max_lines=7,
            ),
        }

    def open_settings(self, _e: ft.Event[ft.IconButton] | None = None) -> None:
        fields = self.settings_fields()

        def save(_e: ft.Event[ft.Button]) -> None:
            current = self.settings
            self.settings = AppSettings(
                llm_base_url=fields["llm_base_url"].value or "",
                llm_api_key=(
                    (fields["llm_api_key"].value or "").strip()
                    or current.llm_api_key
                ),
                chat_model=fields["chat_model"].value or "",
                asr_provider=fields["asr_provider"].value or "doubao",
                asr_base_url=fields["asr_base_url"].value or "",
                asr_api_key=(
                    (fields["asr_api_key"].value or "").strip()
                    or current.asr_api_key
                ),
                asr_model=fields["asr_model"].value or "",
                tts_provider=fields["tts_provider"].value or "doubao",
                tts_base_url=fields["tts_base_url"].value or "",
                tts_api_key=(
                    (fields["tts_api_key"].value or "").strip()
                    or current.tts_api_key
                ),
                tts_model=fields["tts_model"].value or "",
                tts_voice=fields["tts_voice"].value or "",
                doubao_api_key=(
                    (fields["doubao_api_key"].value or "").strip()
                    or current.doubao_api_key
                ),
                doubao_tts_resource_id=(
                    fields["doubao_tts_resource_id"].value or ""
                ),
                doubao_tts_voice=fields["doubao_tts_voice"].value or "",
                doubao_asr_resource_id=(
                    fields["doubao_asr_resource_id"].value or ""
                ),
                doubao_asr_model=fields["doubao_asr_model"].value or "",
                system_prompt=fields["system_prompt"].value or "",
                auto_send_voice=bool(self.auto_send_switch.value),
                auto_speak_replies=bool(self.auto_speak_switch.value),
                agent_kind=current.agent_kind,
            )
            save_settings(self.settings)
            self.agent = create_agent(self.settings.agent_kind, self.settings)
            self.messages[0] = {
                "role": "system",
                "content": self.settings.system_prompt,
            }
            self.page.pop_dialog()
            self.set_status(f"设置已保存：{get_settings_path()}")

        section_title = lambda text: ft.Text(  # noqa: E731
            text,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.PRIMARY,
        )
        controls = [
            section_title("大模型（OpenAI 兼容）"),
            fields["llm_base_url"],
            fields["llm_api_key"],
            fields["chat_model"],
            ft.Divider(),
            section_title("豆包语音（ASR + TTS）"),
            fields["doubao_api_key"],
            fields["doubao_tts_resource_id"],
            fields["doubao_tts_voice"],
            fields["doubao_asr_resource_id"],
            fields["doubao_asr_model"],
            ft.Divider(),
            section_title("语音识别（ASR）"),
            fields["asr_provider"],
            fields["asr_base_url"],
            fields["asr_api_key"],
            fields["asr_model"],
            ft.Divider(),
            section_title("语音合成（TTS）"),
            fields["tts_provider"],
            fields["tts_base_url"],
            fields["tts_api_key"],
            fields["tts_model"],
            fields["tts_voice"],
            ft.Divider(),
            section_title("对话"),
            fields["system_prompt"],
            ft.Divider(),
            section_title("配置来源"),
            ft.Text(
                "项目根目录存在 .env 时，其中的配置优先于这里保存的值。"
                "变量模板见 .env.example。",
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ]

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("接口设置"),
            content=ft.Container(
                width=620,
                content=ft.Column(
                    controls=controls,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=12,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _e: self.page.pop_dialog()),
                ft.Button("保存", icon=ft.Icons.SAVE_ROUNDED, on_click=save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------
    def _build_appbar(self) -> ft.AppBar:
        self.sidebar_toggle_button = ft.IconButton(
            icon=ft.Icons.MENU_ROUNDED,
            tooltip="显示或收起侧边栏",
            icon_color="#52616B",
            on_click=self.toggle_sidebar,
        )
        self.chat_toggle_button = ft.IconButton(
            icon=ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
            tooltip="折叠文字对话，只保留语音",
            icon_color="#52616B",
            on_click=self.toggle_chat,
        )
        return ft.AppBar(
            leading=self.sidebar_toggle_button,
            title=ft.Text(
                APP_TITLE,
                weight=ft.FontWeight.BOLD,
                color="#102A43",
                size=20,
            ),
            center_title=False,
            bgcolor="#FFFFFF",
            color="#102A43",
            elevation=0,
            actions=[
                ft.IconButton(
                    icon=ft.Icons.SMART_TOY_ROUNDED,
                    tooltip="显示或隐藏机器人",
                    icon_color="#0B7F89",
                    on_click=self.toggle_robot,
                ),
                self.chat_toggle_button,
                ft.IconButton(
                    icon=ft.Icons.SETTINGS_ROUNDED,
                    tooltip="接口设置",
                    icon_color="#52616B",
                    on_click=self.open_settings,
                ),
            ],
        )

    def _build_composer(self) -> ft.Container:
        self.composer = ft.Container(
            padding=ft.Padding.symmetric(horizontal=18, vertical=12),
            bgcolor="#FFFFFF",
            border=ft.Border.only(top=ft.BorderSide(1, "#DCE4EA")),
            shadow=ft.BoxShadow(
                blur_radius=14,
                color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
                offset=ft.Offset(0, -2),
            ),
            content=ft.Column(
                controls=[
                    self.attachment_bar,
                    ft.Row(
                        controls=[
                            self.file_button,
                            self.mic_button,
                            self.input_field,
                            self.send_button,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            self.auto_send_switch,
                            self.auto_speak_switch,
                            ft.Container(expand=True),
                            self.progress,
                            self.status_text,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=16,
                    ),
                ],
                spacing=10,
                tight=True,
            ),
        )
        return self.composer

    def render_layout(self) -> None:
        """Swap between the full chat layout and the voice-only layout."""
        self.page.controls.clear()
        if self.chat_collapsed:
            self.robot.panel.width = None
            self.robot.panel.expand = True
            self.page.controls.append(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[self.robot.panel],
                            expand=True,
                            spacing=0,
                            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                        ),
                        self.composer,
                    ],
                    expand=True,
                    spacing=0,
                )
            )
        else:
            self.robot.panel.width = 400
            self.robot.panel.expand = None
            self.page.controls.append(
                ft.Row(
                    controls=[
                        self.sidebar_box,
                        ft.Column(
                            controls=[self.chat_list, self.composer],
                            expand=True,
                            spacing=0,
                        ),
                        self.robot.panel,
                    ],
                    expand=True,
                    spacing=0,
                )
            )

        self.sidebar_toggle_button.visible = not self.chat_collapsed
        self.chat_toggle_button.icon = (
            ft.Icons.CHAT_BUBBLE_ROUNDED
            if self.chat_collapsed
            else ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED
        )
        self.chat_toggle_button.tooltip = (
            "展开文字对话"
            if self.chat_collapsed
            else "折叠文字对话，只保留语音"
        )
        self.page.update()

    # ------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------
    def run(self) -> None:
        self.page.appbar = self._build_appbar()
        self._build_composer()

        for saved_message in self.current_conversation.messages:
            row, _markdown = build_message(
                saved_message["role"],
                saved_message["content"],
            )
            self.chat_list.controls.append(row)
        self.render_sidebar()
        self.render_layout()
        self.robot.start(self.page)

        if not self.settings.llm_api_key:
            self.set_status("请点击右上角设置接口。", is_error=True)
            self.open_settings()


def main(page: ft.Page) -> None:
    AssistantApp(page).run()


def run() -> None:
    ft.run(main)
