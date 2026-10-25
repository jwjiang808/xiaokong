"""小控前端：Flet 界面，只通过 HTTP 调后端。"""

from __future__ import annotations

import asyncio
import base64
import io
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import flet as ft
import flet_audio_recorder as far
from loguru import logger
from PIL import Image, ImageOps

from common.logging_setup import setup_logging
from frontend import api
from frontend.conversation import AssistantTurn, build_user_message
from frontend.robot import TechRobotDoll
from frontend.speech import SpeechQueue, clean

setup_logging()

APP_TITLE = "小控"
IMAGE_TYPES = {"png", "jpg", "jpeg", "webp", "bmp"}
MAX_IMAGE_EDGE = 1600


def image_data_url(path: Path) -> str:
    """压缩图片并转换成模型可接收的 data URL。"""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
        image = image.convert("RGBA" if has_alpha else "RGB")
        image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        if has_alpha:
            image.save(buffer, format="PNG", optimize=True)
            mime = "image/png"
        else:
            image.save(buffer, format="JPEG", quality=86, optimize=True)
            mime = "image/jpeg"
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def duration_between(start: str | None, finish: str | None) -> float | None:
    if not start or not finish:
        return None
    try:
        return max(
            0.0,
            (datetime.fromisoformat(finish) - datetime.fromisoformat(start)).total_seconds(),
        )
    except ValueError:
        return None


class App:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.robot = TechRobotDoll()
        self.conversation_id = uuid.uuid4().hex
        self.messages: list[dict[str, object]] = []
        self.read_text = ""
        self.busy = False
        self.recording = False
        self.recording_path: Path | None = None
        self.speech: SpeechQueue | None = None
        self.chat_collapsed = True
        self.attachment_name: str | None = None
        self.attachment_path: str | None = None
        self.attachment_kind: str | None = None
        self.attachment_image_url: str | None = None

        self._build()
        self._layout()
        self.robot.start(page)
        page.run_task(self.refresh_history)

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
        self.history_list = ft.ListView(
            expand=True,
            spacing=4,
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        )
        self.history_panel = ft.Container(
            width=224,
            bgcolor="#FFFFFF",
            border=ft.Border.only(right=ft.BorderSide(1, "#E2E8F0")),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                "历史记录",
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color="#334155",
                            ),
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.Icons.ADD_COMMENT_ROUNDED,
                                tooltip="新建会话",
                                icon_size=18,
                                on_click=self.new_conversation,
                            ),
                        ],
                        spacing=4,
                    ),
                    ft.Divider(height=1, color="#E2E8F0"),
                    self.history_list,
                ],
                spacing=4,
                expand=True,
            ),
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
            tooltip="选择本地文件",
            icon_color="#0F766E",
            bgcolor="#E6F7F4",
            on_click=self.pick_file,
        )
        self.folder_button = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN_ROUNDED,
            tooltip="选择资料目录",
            icon_color="#0F766E",
            bgcolor="#E6F7F4",
            on_click=self.pick_directory,
        )
        self.status = ft.Text("就绪", size=12, color="#52616B")
        self.progress = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)
        self.voice_mode = ft.Switch(
            label="语音交互",
            value=False,
            on_change=self.toggle_voice_mode,
        )
        self.attachment_label = ft.Text("", size=12, color="#0F766E", expand=True)
        self.attachment_icon = ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, size=16)
        self.attachment_preview = ft.Image(
            src="",
            width=72,
            height=52,
            fit=ft.BoxFit.COVER,
            border_radius=6,
            visible=False,
        )
        self.attachment_clear = ft.IconButton(
            icon=ft.Icons.CLOSE_ROUNDED,
            tooltip="移除附件",
            icon_size=16,
            on_click=self.clear_attachment,
        )

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
                            self.attachment_preview,
                            self.attachment_icon,
                            self.attachment_label,
                            self.attachment_clear,
                        ],
                        spacing=6,
                        visible=False,
                    ),
                    ft.Row(
                        controls=[
                            self.file_button,
                            self.folder_button,
                            self.mic_button,
                            self.input,
                            self.send_button,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            self.voice_mode,
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
            self.robot.panel.width = 360
            self.robot.panel.expand = None
            self.page.controls.append(
                ft.Row(
                    [
                        self.history_panel,
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
                    icon=ft.Icons.HISTORY_ROUNDED,
                    tooltip="打开历史记录",
                    on_click=self.show_history,
                ),
                ft.IconButton(
                    icon=(
                        ft.Icons.CHAT_BUBBLE_ROUNDED
                        if self.chat_collapsed
                        else ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED
                    ),
                    tooltip="展开/收起文字对话和历史",
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

    def show_history(self, _e) -> None:
        if self.chat_collapsed:
            self.chat_collapsed = False
            self._layout()
        self.page.run_task(self.refresh_history)

    async def refresh_history(self) -> None:
        try:
            items = await api.list_conversations()
        except Exception as exc:
            logger.warning("history list failed: {}", exc)
            self.history_list.controls = [
                ft.Text(
                    "无法读取历史记录",
                    size=12,
                    color="#B42318",
                    text_align=ft.TextAlign.CENTER,
                )
            ]
            self.page.update()
            return

        self.history_list.controls.clear()
        if not items:
            self.history_list.controls.append(
                ft.Text(
                    "暂无历史记录",
                    size=12,
                    color="#94A3B8",
                    text_align=ft.TextAlign.CENTER,
                )
            )
        for item in items:
            conversation_id = str(item["id"])
            selected = conversation_id == self.conversation_id
            updated = str(item.get("updated_at") or "").replace("T", " ")
            updated = updated[5:16] if len(updated) >= 16 else updated
            tile = ft.ListTile(
                title=ft.Text(
                    str(item.get("title") or "未命名会话"),
                    size=12,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    color="#1E293B",
                ),
                subtitle=ft.Text(
                    f"{item.get('run_count', 0)} 次 · {updated}",
                    size=10,
                    color="#94A3B8",
                ),
                selected=selected,
                selected_tile_color="#E6F7F4",
                dense=True,
                content_padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                on_click=lambda _, cid=conversation_id: self.page.run_task(
                    self.open_conversation, cid
                ),
            )
            self.history_list.controls.append(
                ft.Container(
                    content=tile,
                    bgcolor="#E6F7F4" if selected else None,
                    border_radius=8,
                )
            )
        self.page.update()

    async def new_conversation(self, _e=None) -> None:
        if self.busy:
            return
        if self.speech:
            self.speech.cancel()
            self.speech = None
        self.conversation_id = uuid.uuid4().hex
        self.messages.clear()
        self.chat.controls.clear()
        self.input.value = ""
        self.read_text = ""
        self.robot.set_read_text("")
        self.robot.set_read_spoken(0)
        self.clear_attachment()
        self.set_status("新会话")
        await self.refresh_history()

    def _history_turn(self, run: dict[str, Any]) -> AssistantTurn:
        turn = AssistantTurn()
        blocks = run.get("blocks")
        if blocks is None:
            blocks = [{"type": "step", **step} for step in run.get("steps", [])]
        has_text = False
        for block in blocks:
            if block.get("type") == "text":
                text = str(block.get("content") or "")
                turn.add_event(
                    {
                        "type": "text",
                        "text": text,
                        "step": block.get("step") or uuid.uuid4().hex,
                    }
                )
                if text:
                    has_text = True
                continue
            kind = str(block.get("kind") or "tool")
            step_id = str(block.get("step_id") or uuid.uuid4().hex)
            base = {
                "id": step_id,
                "type": "step" if kind == "thinking" else "tool",
                "kind": kind,
                "title": block.get("title") or ("思考" if kind == "thinking" else "工具"),
                "detail": block.get("detail") or "",
            }
            turn.add_event(
                {
                    "status": "running",
                    "content": block.get("input_content") or "",
                    **base,
                }
            )
            status = block.get("status")
            if status in {"done", "error"}:
                turn.add_event(
                    {
                        "status": status,
                        "summary": "失败" if status == "error" else "完成",
                        "content": block.get("output_content") or "",
                        **base,
                    }
                )
        if not has_text and run.get("assistant_content"):
            turn.add_event(
                {"type": "text", "text": str(run["assistant_content"])}
            )
        elif run.get("error"):
            turn.fail(str(run["error"]))
        turn.finish(duration_between(run.get("started_at"), run.get("finished_at")))
        return turn

    async def open_conversation(self, conversation_id: str) -> None:
        if self.busy:
            return
        try:
            conversation = await api.get_conversation(conversation_id)
        except Exception as exc:
            logger.exception("history open failed")
            self.set_status(f"历史会话读取失败：{exc}")
            return

        self.conversation_id = conversation_id
        self.messages.clear()
        self.chat.controls.clear()
        last_answer = ""
        for run in conversation.get("runs", []):
            self.chat.controls.append(
                build_user_message(str(run.get("user_content") or ""))
            )
            turn = self._history_turn(run)
            self.chat.controls.append(turn.row)
            self.messages.append(
                {
                    "role": "user",
                    "content": run.get("user_input") or run.get("user_content") or "",
                }
            )
            answer = str(run.get("assistant_content") or "")
            self.messages.append({"role": "assistant", "content": answer})
            if answer:
                last_answer = answer

        self.read_text = clean(last_answer)
        self.robot.set_read_text(self.read_text)
        self.robot.set_read_spoken(len(self.read_text))
        self.set_status("已打开历史会话")
        await self.refresh_history()

    def toggle_voice_mode(self, _e) -> None:
        if not self.voice_mode.value and self.speech:
            self.speech.cancel()
            self.speech = None
            self.robot.set_speaking(False)
            self.set_status("语音交互已关闭")

    def set_status(self, text: str) -> None:
        self.status.value = text
        self.page.update()

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.progress.visible = busy
        self.send_button.disabled = busy
        self.mic_button.disabled = busy
        self.file_button.disabled = busy
        self.folder_button.disabled = busy
        self.page.update()

    # ------------------------------------------------------------------
    async def send(self, _e=None) -> None:
        text = self.input.value.strip()
        image_url = self.attachment_image_url
        if self.busy:
            return
        if not text and not image_url and not self.attachment_path:
            return
        if not text:
            text = "请分析这张图片。" if image_url else "请分析这份资料。"

        attachment_label = None
        content: str | list[dict[str, object]] = text
        if image_url:
            content = [
                {
                    "type": "text",
                    "text": f"图片文件：{self.attachment_name}\n问题：{text}",
                },
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
            attachment_label = f"图片 · {self.attachment_name}"
        elif self.attachment_path:
            kind = "目录" if self.attachment_kind == "directory" else "文件"
            content = (
                f"【用户提供的本地{kind}】\n"
                f"路径：{self.attachment_path}\n"
                f"这是用户明确选择的路径。请使用 execute 的 PowerShell/Python "
                f"在该路径读取资料，不要要求用户复制或粘贴内容。内置 read_file "
                f"只用于工作区虚拟路径。\n\n问题：{text}"
            )
            attachment_label = f"{kind} · {self.attachment_path}"

        self.messages.append({"role": "user", "content": content})
        row = build_user_message(text, image_url, attachment_label)
        self.chat.controls.append(row)
        if image_url:
            self.clear_attachment()
        self.input.value = ""
        self.set_busy(True)
        self.set_status("正在回复...")
        logger.info("send: {}", text[:60])

        turn = AssistantTurn()
        self.chat.controls.append(turn.row)
        self.page.update()

        if self.speech:
            self.speech.cancel()
            self.speech = None
        self.read_text = ""
        self.robot.set_read_text("")
        self.robot.set_read_spoken(0)
        if self.voice_mode.value:
            self.speech = SpeechQueue(self.page, self.robot, self.speech_finished)

        started_at = time.monotonic()
        try:
            async for event in api.chat(
                self.messages,
                self.conversation_id,
                text,
            ):
                turn.add_event(event)
                if event.get("type") == "text":
                    readable = clean(turn.latest_text)
                    self.read_text = readable
                    self.robot.set_read_text(readable)
                    if self.speech:
                        self.speech.push(str(event.get("text") or ""))
                    else:
                        self.robot.set_read_spoken(len(readable))
                self.page.update()
        except Exception as exc:
            logger.exception("chat failed")
            turn.fail(str(exc))
            self.set_status(f"请求失败：{exc}")
            return
        finally:
            turn.finish(time.monotonic() - started_at)
            if self.speech:
                self.speech.close()
            self.set_busy(False)
            await self.refresh_history()

        reply = turn.answer_text.strip()
        self.messages.append({"role": "assistant", "content": reply})
        if not self.voice_mode.value:
            self.set_status("就绪")

    def speech_finished(self, speech: SpeechQueue) -> None:
        if self.speech is not speech:
            return
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
            if self.voice_mode.value:
                await self.send()
        except Exception as exc:
            logger.exception("asr failed")
            self.set_status(f"识别失败：{exc}")
        finally:
            self.set_busy(False)

    def _set_attachment(
        self,
        name: str,
        path: str | None,
        kind: str,
        image_url: str | None = None,
    ) -> None:
        self.attachment_name = name
        self.attachment_path = path
        self.attachment_kind = kind
        self.attachment_image_url = image_url
        if image_url:
            self.attachment_label.value = f"图片 · {name}"
        else:
            label = "目录" if kind == "directory" else "文件"
            self.attachment_label.value = f"{label} · {path}"
        self.attachment_icon.visible = not bool(image_url)
        self.attachment_preview.src = image_url or ""
        self.attachment_preview.visible = bool(image_url)
        self.attachment_row.visible = True
        self.page.update()

    async def pick_file(self, _e) -> None:
        files = await ft.FilePicker().pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.ANY,
        )
        if not files or not files[0].path:
            return
        path = Path(files[0].path).resolve()
        if not path.is_file():
            self.set_status("无法读取文件")
            return
        suffix = path.suffix.lower().lstrip(".")
        if suffix in IMAGE_TYPES:
            self.set_status("正在处理图片...")
            try:
                image_url = await asyncio.to_thread(image_data_url, path)
            except Exception as exc:
                logger.exception("image load failed")
                self.set_status(f"图片读取失败：{exc}")
                return
            self._set_attachment(path.name, None, "image", image_url)
            self.set_status("图片已加入当前消息")
            return
        self._set_attachment(path.name, str(path), "file")
        self.set_status("文件路径已加入，智能体将自行读取")

    async def pick_directory(self, _e) -> None:
        selected = await ft.FilePicker().get_directory_path(
            dialog_title="选择智能体可读取的资料目录"
        )
        if not selected:
            return
        path = Path(selected).resolve()
        if not path.is_dir():
            self.set_status("无法读取目录")
            return
        self._set_attachment(path.name or str(path), str(path), "directory")
        self.set_status("目录已加入，智能体将自行浏览")

    def clear_attachment(self, _e=None) -> None:
        self.attachment_name = None
        self.attachment_path = None
        self.attachment_kind = None
        self.attachment_image_url = None
        self.attachment_label.value = ""
        self.attachment_icon.visible = True
        self.attachment_preview.src = ""
        self.attachment_preview.visible = False
        self.attachment_row.visible = False
        self.page.update()


def main(page: ft.Page) -> None:
    App(page)


def run() -> None:
    ft.run(main)
