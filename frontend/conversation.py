"""Chat transcript controls for user messages and agent activity."""

from __future__ import annotations

from typing import Any

import flet as ft

STEP_ICONS = {
    "thinking": ft.Icons.PSYCHOLOGY_ROUNDED,
    "skill": ft.Icons.EXTENSION_ROUNDED,
    "read": ft.Icons.DESCRIPTION_ROUNDED,
    "write": ft.Icons.EDIT_NOTE_ROUNDED,
    "search": ft.Icons.SEARCH_ROUNDED,
    "shell": ft.Icons.TERMINAL_ROUNDED,
    "task": ft.Icons.ACCOUNT_TREE_ROUNDED,
    "publish": ft.Icons.PUBLISH_ROUNDED,
    "tool": ft.Icons.TUNE_ROUNDED,
}


def _avatar(role: str) -> ft.Container:
    is_user = role == "user"
    return ft.Container(
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


def build_user_message(
    text: str,
    image_url: str | None = None,
    attachment_label: str | None = None,
) -> ft.Row:
    controls: list[ft.Control] = []
    if image_url:
        controls.append(
            ft.Image(
                src=image_url,
                width=420,
                height=240,
                fit=ft.BoxFit.CONTAIN,
                border_radius=8,
            )
        )
    if attachment_label:
        controls.append(
            ft.Row(
                controls=[
                    ft.Icon(ft.Icons.ATTACH_FILE_ROUNDED, size=15, color="#0F766E"),
                    ft.Text(
                        attachment_label,
                        size=12,
                        color="#0F766E",
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=5,
                tight=True,
            )
        )
    controls.append(
        ft.Markdown(
            text,
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        )
    )
    bubble = ft.Container(
        content=ft.Column(controls, spacing=8, tight=True),
        bgcolor="#E8F2FF",
        border=ft.Border.all(1, "#B8D4FF"),
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        width=560,
    )
    return ft.Row(
        controls=[bubble, _avatar("user")],
        alignment=ft.MainAxisAlignment.END,
        vertical_alignment=ft.CrossAxisAlignment.START,
        spacing=10,
    )


class StepRow:
    def __init__(self, event: dict[str, Any]) -> None:
        self.kind = str(event.get("kind") or "tool")
        self.title = ft.Text(
            str(event.get("title") or "执行中"),
            size=13,
            weight=ft.FontWeight.W_500,
            color="#263238",
        )
        self.detail = ft.Text(
            str(event.get("detail") or ""),
            size=11,
            color="#64748B",
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.icon = ft.Icon(
            STEP_ICONS.get(self.kind, STEP_ICONS["tool"]),
            size=16,
            color="#0F766E",
        )
        self.progress = ft.ProgressRing(
            width=13,
            height=13,
            stroke_width=1.8,
            color="#0F766E",
        )
        self.result_icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE_ROUNDED,
            size=16,
            color="#0F9E91",
            visible=False,
        )
        self.detail_text = ft.Text(
            "",
            size=11,
            color="#334155",
            selectable=True,
            font_family="Consolas",
        )
        self.detail_box = ft.Container(
            content=self.detail_text,
            bgcolor="#F1F5F9",
            border_radius=6,
            padding=8,
            visible=False,
        )
        self.control = ft.ExpansionTile(
            title=ft.Row(
                [
                    self.title,
                    ft.Container(expand=True),
                    self.progress,
                    self.result_icon,
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            subtitle=self.detail,
            controls=[self.detail_box],
            leading=self.icon,
            controls_padding=ft.Padding.only(left=8, right=8, bottom=6),
            tile_padding=ft.Padding.symmetric(horizontal=2, vertical=0),
            dense=True,
            maintain_state=True,
            expanded=False,
            show_trailing_icon=True,
        )
        self._append_content(event)

    def _append_content(self, event: dict[str, Any]) -> None:
        content = str(event.get("content") or "").strip()
        if not content:
            return
        combined = (
            f"{self.detail_text.value}\n\n{content}"
            if self.detail_text.value
            else content
        )
        if len(combined) > 1200:
            combined = (
                combined[:1200]
                + "\n\n… 界面预览已截断；完整过程请查看 SQLite。"
            )
        self.detail_text.value = combined
        self.detail_box.visible = True

    def update(self, event: dict[str, Any]) -> None:
        if title := event.get("title"):
            self.title.value = str(title)
        if detail := event.get("detail"):
            self.detail.value = str(detail)
        if summary := event.get("summary"):
            self.detail.value = str(summary)
        self._append_content(event)
        status = event.get("status")
        if status == "running":
            self.progress.visible = True
            self.result_icon.visible = False
            return
        self.progress.visible = False
        self.result_icon.visible = True
        if status == "error":
            self.result_icon.name = ft.Icons.ERROR_ROUNDED
            self.result_icon.color = "#DC2626"
            self.title.color = "#B42318"
        else:
            self.result_icon.name = ft.Icons.CHECK_CIRCLE_ROUNDED
            self.result_icon.color = "#0F9E91"
            self.title.color = "#263238"
            if self.kind == "thinking":
                self.title.value = "思考完成"


class MessageBlock:
    def __init__(self) -> None:
        self.text = ""
        self.label = ft.Text(
            "中间回复",
            size=10,
            color="#64748B",
            visible=False,
        )
        self.markdown = ft.Markdown(
            "",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        )
        self.control = ft.Container(
            content=ft.Column([self.label, self.markdown], spacing=4, tight=True),
            bgcolor="#F8FAFC",
            border=ft.Border.all(1, "#E2E8F0"),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        )

    def append(self, text: str) -> None:
        self.text += text
        self.markdown.value = self.text

    def mark_intermediate(self) -> None:
        self.label.visible = True
        self.control.bgcolor = "#F8FAFC"
        self.control.border = ft.Border.all(1, "#E2E8F0")
        self.control.border_radius = 8
        self.control.padding = ft.Padding.symmetric(horizontal=12, vertical=8)

    def mark_final(self) -> None:
        self.label.visible = False
        self.control.bgcolor = None
        self.control.border = None
        self.control.border_radius = 0
        self.control.padding = ft.Padding.only(top=2)


class ThinkingGroup:
    def __init__(self) -> None:
        self.steps: dict[str, StepRow] = {}
        self.step_controls = ft.Column(spacing=7, tight=True)
        self.spinner = ft.ProgressRing(
            width=13,
            height=13,
            stroke_width=1.8,
            color="#0F766E",
        )
        self.check = ft.Icon(
            ft.Icons.CHECK_CIRCLE_ROUNDED,
            size=15,
            color="#0F9E91",
            visible=False,
        )
        self.title = ft.Text(
            "正在思考...",
            size=12,
            color="#475569",
            weight=ft.FontWeight.W_500,
        )
        self.subtitle = ft.Text("", size=10, color="#94A3B8")
        self.tile = ft.ExpansionTile(
            title=ft.Row([self.spinner, self.check, self.title], spacing=7),
            subtitle=self.subtitle,
            controls=[self.step_controls],
            controls_padding=ft.Padding.only(left=8, right=8, bottom=6),
            tile_padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            dense=True,
            maintain_state=True,
            expanded=True,
            show_trailing_icon=True,
        )
        self.control = ft.Container(
            content=self.tile,
            bgcolor="#F8FAFC",
            border=ft.Border.all(1, "#E2E8F0"),
            border_radius=9,
            padding=ft.Padding.symmetric(horizontal=2, vertical=1),
        )

    def add(self, event: dict[str, Any]) -> None:
        step_id = str(event.get("id") or "")
        if not step_id:
            return
        step = self.steps.get(step_id)
        if step is None:
            step = StepRow(event)
            self.steps[step_id] = step
            self.step_controls.controls.append(step.control)
        else:
            step.update(event)
        self.subtitle.value = f"{len(self.steps)} 个步骤"

    def close(self) -> None:
        self.spinner.visible = False
        self.check.visible = True
        self.title.value = "思考过程"
        self.subtitle.value = f"已完成 {len(self.steps)} 个步骤"
        self.tile.expanded = False

    def fail(self, error: str) -> None:
        self.add(
            {
                "id": "error",
                "type": "tool",
                "kind": "tool",
                "title": "执行失败",
                "detail": error,
                "status": "error",
            }
        )
        self.spinner.visible = False
        self.check.name = ft.Icons.ERROR_ROUNDED
        self.check.color = "#DC2626"
        self.check.visible = True
        self.title.value = "执行失败"
        self.title.color = "#B42318"


class AssistantTurn:
    """Alternating thinking groups and intermediate/final messages."""

    def __init__(self) -> None:
        self.text_blocks: dict[str, MessageBlock] = {}
        self.last_text_key: str | None = None
        self.current_group: ThinkingGroup | None = None
        self.finished = False
        self.failed = False
        self.timeline = ft.Column(spacing=10, tight=True)
        self.content = ft.Column(
            [self.timeline],
            spacing=0,
            tight=True,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.row = ft.Row(
            controls=[_avatar("assistant"), self.content],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=10,
        )
        self.answer_text = ""
        self.latest_text = ""

    def _group(self) -> ThinkingGroup:
        if self.current_group is None:
            self.current_group = ThinkingGroup()
            self.timeline.controls.append(self.current_group.control)
        return self.current_group

    def add_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type in {"step", "tool"}:
            self._group().add(event)
            return

        if event_type != "text":
            return
        text = str(event.get("text") or "")
        if not text:
            return
        key = str(event.get("step") or "text")
        block = self.text_blocks.get(key)
        if block is None:
            if self.current_group is not None:
                self.current_group.close()
                self.current_group = None
            block = MessageBlock()
            self.text_blocks[key] = block
            self.timeline.controls.append(block.control)
        block.append(text)
        self.latest_text = block.text
        self.last_text_key = key

    def finish(self, elapsed_seconds: float | None = None) -> None:
        if self.finished:
            return
        self.finished = True
        if self.current_group is not None:
            self.current_group.close()
            self.current_group = None

        final_block = None
        if self.last_text_key:
            candidate = self.text_blocks.get(self.last_text_key)
            if candidate is not None and self.timeline.controls:
                if self.timeline.controls[-1] is candidate.control:
                    final_block = candidate

        for block in self.text_blocks.values():
            if block is final_block:
                block.mark_final()
            else:
                block.mark_intermediate()

        if final_block is None:
            self.answer_text = ""
            return

        self.answer_text = final_block.text
        duration = (
            f"{elapsed_seconds:.1f} 秒"
            if elapsed_seconds is not None
            else ""
        )
        divider = ft.Row(
            [
                ft.Divider(expand=True, height=1, color="#CBD5E1"),
                ft.Text(duration, size=11, color="#94A3B8"),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        index = next(
            (
                i
                for i, control in enumerate(self.timeline.controls)
                if control is final_block.control
            ),
            len(self.timeline.controls),
        )
        self.timeline.controls.insert(index, divider)

    def fail(self, error: str) -> None:
        self.failed = True
        self._group().fail(error)
        self.current_group = None
