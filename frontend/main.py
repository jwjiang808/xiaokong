"""小控前端：Flet 界面，只通过 HTTP 调后端。"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path

import flet as ft
import flet_audio_recorder as far
from markitdown import MarkItDown

from . import api
from .robot import TechRobotDoll
from .speech import SpeechQueue, clean

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("xiaokong.ui")

APP_TITLE = "小控-你的专用课程助手"
FILE_TYPES = ["docx", "pptx", "xlsx", "xls", "pdf", "txt"]


def build_message(role: str, text: str) -> tuple[ft.Row, ft.Markdown]:
    is_user = role == "user"
    markdown = ft.Markdown(
        text,
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
    )
    bubble = ft.Container(
        content=markdown,
        bgcolor="#E8F2FF" if is_user else "#FFFFFF",
        border=ft.Border.all(1, "#B8D4FF" if is_user else "#D9E2EA"),
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        width=560,
    )
    avatar = ft.Container(
        content=ft.Icon(
            ft.Icons.PERSON_ROUNDED if is_user else ft.Icons.SET_MEAL_ROUNDED,
            size=20,
            color=ft.Colors.WHITE,
        ),
        width=38,
        height=38,
        border_radius=19,
        bgcolor="#3B82F6" if is_user else "#0F9E91",
        alignment=ft.Alignment.CENTER,
    )
    row = ft.Row(
        controls=[bubble, avatar] if is_user else [avatar, bubble],
        alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.START,
        spacing=10,
    )
    return row, markdown


class App:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.robot = TechRobotDoll()
        self.messages: list[dict[str, str]] = []
        self.read_text = ""
        self.busy = False
        self.recording = False
        self.recording_path: Path | None = None
        self.speech: SpeechQueue | None = None
        self.chat_collapsed = True
        self.attachment_name: str | None = None
        self.attachment_text: str | None = None
        self.converter = MarkItDown(enable_plugins=False)

        self._build()
        self._layout()
        self.robot.start(page)

    # ------------------------------------------------------------------
    def _build(self) -> None:
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

        self.chat = ft.ListView(
            expand=True,
            spacing=16,
            padding=ft.Padding.symmetric(horizontal=20, vertical=18),
            auto_scroll=True,
        )
        self.input = ft.TextField(
            hint_text="输入问题",
            multiline=True,
            min_lines=1,
            max_lines=5,
            filled=True,
            fill_color="#FFFFFF",
            border=ft.OutlineInputBorder(border_radius=12),
            expand=True,
            shift_enter=True,
        )
        self.input.on_submit = self.send
        self.send_button = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            tooltip="发送",
            icon_color=ft.Colors.WHITE,
            bgcolor="#0F9E91",
            on_click=self.send,
        )
        self.mic_button = ft.IconButton(
            icon=ft.Icons.MIC_ROUNDED,
            tooltip="按住说话",
            icon_color="#B42318",
            bgcolor="#FFE8E6",
            on_click=self.toggle_record,
        )
        self.file_button = ft.IconButton(
            icon=ft.Icons.ATTACH_FILE_ROUNDED,
            tooltip="上传课件",
            icon_color="#0F766E",
            bgcolor="#E6F7F4",
            on_click=self.pick_file,
        )
        self.status = ft.Text("就绪", size=12, color="#52616B")
        self.progress = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)
        self.auto_send = ft.Switch(label="语音自动发送", value=True)
        self.auto_speak = ft.Switch(label="朗读回复", value=True)
        self.attachment_label = ft.Text("", size=12, color="#0F766E", expand=True)

        self.recorder = far.AudioRecorder(
            configuration=far.AudioRecorderConfiguration(
                encoder=far.AudioEncoder.WAV,
            ),
        )
        page.services.append(self.recorder)

        self.composer = ft.Container(
            padding=ft.Padding.symmetric(horizontal=18, vertical=12),
            bgcolor="#FFFFFF",
            border=ft.Border.only(top=ft.BorderSide(1, "#DCE4EA")),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, size=16),
                            self.attachment_label,
                        ],
                        spacing=6,
                        visible=False,
                    ),
                    ft.Row(
                        controls=[
                            self.file_button,
                            self.mic_button,
                            self.input,
                            self.send_button,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            self.auto_send,
                            self.auto_speak,
                            ft.Container(expand=True),
                            self.progress,
                            self.status,
                        ],
                        spacing=16,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
        )
        self.attachment_row = self.composer.content.controls[0]

    def _layout(self) -> None:
        self.page.controls.clear()
        if self.chat_collapsed:
            self.robot.panel.width = None
            self.robot.panel.expand = True
            self.page.controls.append(
                ft.Column(
                    [
                        ft.Row(
                            [self.robot.panel],
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
                    [
                        ft.Column([self.chat, self.composer], expand=True, spacing=0),
                        self.robot.panel,
                    ],
                    expand=True,
                    spacing=0,
                )
            )
        self.page.appbar = ft.AppBar(
            title=ft.Text(APP_TITLE, size=20, weight=ft.FontWeight.BOLD),
            bgcolor="#FFFFFF",
            actions=[
                ft.IconButton(
                    icon=ft.Icons.SMART_TOY_ROUNDED,
                    tooltip="显示/隐藏机器人",
                    on_click=self.toggle_robot,
                ),
                ft.IconButton(
                    icon=(
                        ft.Icons.CHAT_BUBBLE_ROUNDED
                        if self.chat_collapsed
                        else ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED
                    ),
                    tooltip="展开/收起文字对话",
                    on_click=self.toggle_chat,
                ),
            ],
        )
        self.page.update()

    def toggle_robot(self, _e) -> None:
        self.robot.panel.visible = not self.robot.panel.visible
        self.page.update()

    def toggle_chat(self, _e) -> None:
        self.chat_collapsed = not self.chat_collapsed
        self._layout()

    def set_status(self, text: str) -> None:
        self.status.value = text
        self.page.update()

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.progress.visible = busy
        self.send_button.disabled = busy
        self.mic_button.disabled = busy
        self.file_button.disabled = busy
        self.page.update()

    # ------------------------------------------------------------------
    async def send(self, _e=None) -> None:
        text = self.input.value.strip()
        if not text or self.busy:
            return

        content = text
        if self.attachment_text:
            content = (
                f"【课件《{self.attachment_name}》内容】\n"
                f"{self.attachment_text}\n\n问题：{text}"
            )
        self.messages.append({"role": "user", "content": content})
        row, _ = build_message("user", text)
        self.chat.controls.append(row)
        self.input.value = ""
        self.set_busy(True)
        self.set_status("正在回复...")
        log.info("send: %s", text[:60])

        reply_row, reply_markdown = build_message("assistant", "")
        self.chat.controls.append(reply_row)
        self.page.update()

        if self.speech:
            self.speech.cancel()
            self.speech = None
        self.read_text = ""
        self.robot.set_read_text("")
        self.robot.set_read_spoken(0)
        if self.auto_speak.value:
            self.speech = SpeechQueue(self.page, self.robot, self.speech_finished)

        parts: list[str] = []
        try:
            async for delta in api.chat(self.messages):
                parts.append(delta)
                reply_markdown.value = "".join(parts)
                self.page.update()
                readable = clean("".join(parts))
                self.read_text = readable
                self.robot.set_read_text(readable)
                if self.speech:
                    self.speech.push(delta)
                else:
                    self.robot.set_read_spoken(len(readable))
        except Exception as exc:
            log.exception("chat failed")
            self.set_status(f"请求失败：{exc}")
            return
        finally:
            if self.speech:
                self.speech.close()
            self.set_busy(False)

        reply = "".join(parts).strip()
        self.messages.append({"role": "assistant", "content": reply})
        if not self.auto_speak.value:
            self.set_status("就绪")

    def speech_finished(self) -> None:
        self.speech = None
        self.robot.set_speaking(False)
        self.robot.set_read_spoken(len(self.read_text))
        self.set_status("就绪")

    # ------------------------------------------------------------------
    async def toggle_record(self, _e) -> None:
        if self.busy:
            return
        if not self.recording:
            if not await self.recorder.has_permission():
                self.set_status("没有麦克风权限")
                return
            self.recording_path = Path(tempfile.gettempdir()) / (
                f"xiaokong_{int(time.time() * 1000)}.wav"
            )
            await self.recorder.start_recording(
                output_path=str(self.recording_path),
                configuration=far.AudioRecorderConfiguration(
                    encoder=far.AudioEncoder.WAV,
                    sample_rate=16000,
                    channels=1,
                ),
            )
            self.recording = True
            self.mic_button.icon = ft.Icons.STOP_CIRCLE_ROUNDED
            self.set_status("正在录音，再点一次结束")
            return

        self.recording = False
        self.mic_button.icon = ft.Icons.MIC_ROUNDED
        await self.recorder.stop_recording()
        if not self.recording_path or not self.recording_path.exists():
            self.set_status("没有录音文件")
            return
        self.set_busy(True)
        self.set_status("正在识别...")
        try:
            text = await api.asr(
                self.recording_path.read_bytes(),
                self.recording_path.name,
            )
            self.input.value = text
            self.set_status("识别完成")
            if self.auto_send.value:
                await self.send()
        except Exception as exc:
            log.exception("asr failed")
            self.set_status(f"识别失败：{exc}")
        finally:
            self.set_busy(False)

    async def pick_file(self, _e) -> None:
        files = await ft.FilePicker().pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=FILE_TYPES,
        )
        if not files:
            return
        selected = files[0]
        path = Path(selected.path) if selected.path else None
        if not path or not path.exists():
            self.set_status("无法读取文件")
            return
        self.set_status("正在解析课件...")
        try:
            result = await asyncio.to_thread(self.converter.convert_local, path)
            text = (getattr(result, "markdown", "") or "").strip()
            self.attachment_name = selected.name
            self.attachment_text = text
            self.attachment_label.value = f"{selected.name}（{len(text):,} 字）"
            self.attachment_row.visible = True
            self.set_status("课件已加载")
        except Exception as exc:
            self.set_status(f"解析失败：{exc}")
        finally:
            self.page.update()


def main(page: ft.Page) -> None:
    App(page)


def run() -> None:
    ft.run(main)
