from __future__ import annotations

import asyncio
import contextlib
import math
import time
from typing import Final

import flet as ft

_PANEL_BG: Final = ["#07131F", "#0B2234", "#102F43"]
_METAL: Final = ["#E7F4FF", "#9CC7DF", "#355B75"]
_METAL_DARK: Final = ["#5C8298", "#1B3A50", "#091B29"]
_CYAN: Final = "#42E8E0"
_BLUE: Final = "#45A9FF"

STAGE_WIDTH: Final = 260
STAGE_HEIGHT: Final = 405

# Mouth opening range expressed as a vertical scale of the mouth control.
MOUTH_CLOSED: Final = 0.10
MOUTH_OPEN: Final = 1.05

# The voice bars animate with a paint transform instead of a size change so the
# surrounding layout never reflows (a reflow is what made the panel "shake").
BAR_HEIGHT: Final = 22
BAR_ROW_HEIGHT: Final = 38

# The spoken text is drawn as a few bands that fade from bright (just spoken)
# back to dim (spoken a while ago).
READ_FADE_BANDS: Final = 7
READ_DIM: Final = "#2C4757"
READ_BRIGHT: Final = "#F2FEFF"
READ_CURSOR: Final = "▍"
# Once the reply has been spoken the whole caption settles on one soft colour
# instead of keeping a bright tail.
READ_SETTLED: Final = "#8FB2C0"
# Viewport for the caption: about three lines. The caption scrolls inside it,
# so nothing is ever cut off and the whole answer can be reviewed.
READ_BOX_HEIGHT: Final = 48

# Arm rotation is measured around the shoulder. Because the left arm sits on
# the left of the body, a POSITIVE angle swings it outward while a NEGATIVE
# angle swings it inward; the right arm is mirrored. These poses are therefore
# (left_angle, right_angle) pairs that open outward.
_REST_ARMS: Final = (-0.10, 0.10)
_GESTURES: Final = (
    (0.14, -0.14),   # gentle open
    (0.36, -0.15),   # left hand leads
    (0.16, -0.34),   # right hand leads
    (0.26, -0.24),   # both, medium
    (0.44, -0.26),   # left raised high
    (0.22, -0.42),   # right raised high
    (0.12, -0.12),   # settle
)


def _glow(color: str, blur: int = 18, opacity: float = 0.34) -> ft.BoxShadow:
    return ft.BoxShadow(
        blur_radius=blur,
        color=ft.Colors.with_opacity(opacity, color),
        offset=ft.Offset(0, 0),
    )


def _mix_color(low: str, high: str, amount: float) -> str:
    """Blend two #RRGGBB colors; used for the caption fade bands."""
    amount = max(0.0, min(1.0, amount))
    start = tuple(int(low[index : index + 2], 16) for index in (1, 3, 5))
    end = tuple(int(high[index : index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(
        f"{round(a + (b - a) * amount):02X}"
        for a, b in zip(start, end, strict=True)
    )


class TechRobotDoll:
    """A lightweight, GPU-free robot mascot animated by Flet controls."""

    def __init__(self, scale: float = 1.26) -> None:
        self._speaking = False
        self._task: asyncio.Task[None] | None = None
        # 0.0 closed .. 1.0 fully open, driven by the real audio envelope.
        self._mouth_level: float | None = None
        # Short-lived reaction pulse fired when the robot starts speaking.
        self._burst = 0.0
        # Smoothed loudness: `_pulse` for the level meter / core, `_motion` for
        # limb and head movement so the body never buzzes with the raw audio.
        self._pulse = 0.0
        self._motion = 0.0
        # Arm gesture state: eases between poses while the robot is talking.
        self._gesture_value: tuple[float, float] = _REST_ARMS
        self._gesture_from: tuple[float, float] = _REST_ARMS
        self._gesture_to: tuple[float, float] = _REST_ARMS
        self._gesture_index = len(_GESTURES) - 1
        self._gesture_start = 0.0
        self._gesture_move = 0.55
        self._gesture_hold = 1.5
        self._gesture_deadline = 0.0
        self._scale = max(0.5, float(scale))

        self.status_dot = ft.Container(
            width=8,
            height=8,
            border_radius=4,
            bgcolor="#5BE7C4",
            shadow=[_glow("#5BE7C4", 10, 0.55)],
        )
        self.status_text = ft.Text(
            "待机中",
            size=11,
            color="#B8D7E8",
            weight=ft.FontWeight.W_600,
        )

        self.eye_left, self.eye_left_core = self._build_eye()
        self.eye_right, self.eye_right_core = self._build_eye()
        self.mouth, self.mouth_glow = self._build_mouth()

        self.face_panel = ft.Container(
            width=104,
            height=62,
            border_radius=27,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            gradient=ft.LinearGradient(
                colors=["#03111D", "#0A2438"],
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
            ),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, _CYAN)),
            shadow=[_glow("#0B87A5", 14, 0.20)],
            content=ft.Stack(
                controls=[
                    ft.Row(
                        controls=[
                            self.eye_left,
                            ft.Container(expand=True),
                            self.eye_right,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        left=23,
                        right=23,
                        bottom=1,
                        height=16,
                        alignment=ft.Alignment.CENTER,
                        content=self.mouth,
                    ),
                ],
                width=76,
                height=42,
            ),
        )

        self.head = ft.Container(
            width=146,
            height=112,
            border_radius=43,
            padding=ft.Padding.only(left=13, right=13, top=24, bottom=12),
            gradient=ft.LinearGradient(
                colors=_METAL,
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                rotation=0.25,
            ),
            border=ft.Border.all(2, "#F4FBFF"),
            shadow=[
                _glow("#46D7FF", 24, 0.29),
                ft.BoxShadow(
                    blur_radius=18,
                    color=ft.Colors.with_opacity(0.34, ft.Colors.BLACK),
                    offset=ft.Offset(0, 10),
                ),
            ],
            content=ft.Column(
                controls=[
                    self.face_panel,
                    ft.Container(
                        width=38,
                        height=4,
                        border_radius=2,
                        bgcolor=ft.Colors.with_opacity(0.48, "#456477"),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
        )

        self.ear_left = self._build_ear()
        self.ear_right = self._build_ear()

        self.antenna_orb = ft.Container(
            width=16,
            height=16,
            border_radius=8,
            gradient=ft.RadialGradient(
                colors=["#FFFFFF", _CYAN, "#138E9B"],
                stops=[0, 0.34, 1],
            ),
            shadow=[_glow(_CYAN, 20, 0.72)],
            scale=ft.Scale(1),
        )
        self.antenna = ft.Container(
            width=58,
            height=58,
            content=ft.Column(
                controls=[
                    self.antenna_orb,
                    ft.Container(
                        width=5,
                        height=23,
                        border_radius=3,
                        gradient=ft.LinearGradient(
                            colors=["#DDF9FF", "#3C819B"],
                            begin=ft.Alignment.TOP_CENTER,
                            end=ft.Alignment.BOTTOM_CENTER,
                        ),
                    ),
                    ft.Container(
                        width=21,
                        height=6,
                        border_radius=3,
                        bgcolor="#5A8294",
                    ),
                ],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        self.chest_core = ft.Container(
            width=32,
            height=32,
            border_radius=16,
            gradient=ft.RadialGradient(
                colors=["#F2FFFF", _CYAN, "#0D6B84"],
                stops=[0, 0.25, 1],
            ),
            border=ft.Border.all(2, ft.Colors.with_opacity(0.72, "#D6FFFF")),
            shadow=[_glow(_CYAN, 18, 0.58)],
            scale=ft.Scale(1),
        )
        self.body_screen = ft.Container(
            width=70,
            height=62,
            border_radius=21,
            gradient=ft.LinearGradient(
                colors=["#06131E", "#0D2C42"],
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
            ),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.32, _BLUE)),
            alignment=ft.Alignment.CENTER,
            content=ft.Stack(
                controls=[
                    ft.Container(
                        width=46,
                        height=46,
                        border_radius=23,
                        border=ft.Border.all(
                            2,
                            ft.Colors.with_opacity(0.28, _CYAN),
                        ),
                    ),
                    self.chest_core,
                ],
                alignment=ft.Alignment.CENTER,
            ),
        )
        self.body = ft.Container(
            width=118,
            height=150,
            border_radius=42,
            padding=ft.Padding.only(left=18, right=18, top=22, bottom=18),
            gradient=ft.LinearGradient(
                colors=["#F2FAFF", "#A4C8DB", "#44657A"],
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                rotation=0.18,
            ),
            border=ft.Border.all(2, "#F4FCFF"),
            shadow=[
                _glow(_BLUE, 22, 0.22),
                ft.BoxShadow(
                    blur_radius=20,
                    color=ft.Colors.with_opacity(0.40, ft.Colors.BLACK),
                    offset=ft.Offset(0, 12),
                ),
            ],
            content=ft.Column(
                controls=[
                    self.body_screen,
                    ft.Container(
                        width=54,
                        height=7,
                        border_radius=4,
                        bgcolor=ft.Colors.with_opacity(0.30, "#29485B"),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
        )

        # Hands live inside the arm control so they swing with the shoulder
        # instead of floating next to the head.
        self.left_arm = self._build_arm(-1)
        self.right_arm = self._build_arm(1)

        self.pulse_bars = [
            ft.Container(
                width=4,
                height=BAR_HEIGHT,
                border_radius=3,
                bgcolor=ft.Colors.with_opacity(
                    0.75,
                    _CYAN if index % 2 == 0 else _BLUE,
                ),
                scale=ft.Scale(
                    scale_y=0.4,
                    alignment=ft.Alignment.BOTTOM_CENTER,
                ),
            )
            for index in range(7)
        ]
        self.pulse_row = ft.Row(
            controls=self.pulse_bars,
            spacing=5,
            height=BAR_ROW_HEIGHT,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        # "Streaming read-aloud" panel. Everything here is updated with paint
        # only properties (color / shadow / scale) so the layout never moves.
        # Live subtitles: the reply streams in here and the part already spoken
        # is highlighted, karaoke style, in step with the audio.
        self._read_text = ""
        self._read_spoken = 0
        self._read_cursor_on = True
        self._read_pinned = -1
        self._read_rendered: tuple = ("", -1, None, None)
        self.read_text = ft.Text(
            spans=[ft.TextSpan("", style=ft.TextStyle(color=READ_SETTLED))],
            size=11,
        )
        # A real scroll view: while speaking it follows the newest line, and
        # once the reply is done the mouse wheel can scroll back through it.
        self.read_text_box = ft.Column(
            controls=[self.read_text],
            spacing=0,
            height=READ_BOX_HEIGHT,
            scroll=ft.ScrollMode.AUTO,
            # Scrolling is driven explicitly (see _animate) so the view can be
            # pinned to the newest line while speaking and then left alone for
            # the reader to scroll back through.
            auto_scroll=False,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )
        self.voice_dot = ft.Container(
            width=6,
            height=6,
            border_radius=3,
            bgcolor="#72E8C6",
            shadow=[_glow("#72E8C6", 8, 0.55)],
        )
        self.voice_status = ft.Text(
            "就绪",
            size=9,
            weight=ft.FontWeight.BOLD,
            color="#72E8C6",
        )
        self.voice_status_box = ft.Container(
            width=44,
            alignment=ft.Alignment.CENTER_RIGHT,
            content=self.voice_status,
        )
        self.level_fill = ft.Container(
            height=3,
            border_radius=2,
            gradient=ft.LinearGradient(
                colors=[_CYAN, _BLUE],
                begin=ft.Alignment.CENTER_LEFT,
                end=ft.Alignment.CENTER_RIGHT,
            ),
            shadow=[_glow(_CYAN, 8, 0.5)],
            scale=ft.Scale(
                scale_x=0.04,
                alignment=ft.Alignment.CENTER_LEFT,
            ),
        )
        self.level_track = ft.Container(
            height=3,
            border_radius=2,
            bgcolor=ft.Colors.with_opacity(0.14, _CYAN),
            content=self.level_fill,
        )
        self.voice_box = ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=9),
            border_radius=16,
            bgcolor=ft.Colors.with_opacity(0.16, "#06101A"),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.18, _CYAN),
            ),
            content=ft.Column(
                controls=[
                    self.read_text_box,
                    ft.Row(
                        controls=[
                            self.pulse_row,
                            ft.Container(expand=True),
                            self.voice_dot,
                            ft.Container(width=5),
                            self.voice_status_box,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.level_track,
                ],
                spacing=6,
            ),
        )

        robot_stack = ft.Stack(
            width=STAGE_WIDTH,
            height=STAGE_HEIGHT,
            # A Flutter Stack clips by default, which cut the left arm off as
            # soon as it swung past the stage edge. Let the limbs paint past
            # the stage box; the panel is wider than the stage anyway.
            clip_behavior=ft.ClipBehavior.NONE,
            controls=[
                ft.Container(
                    width=210,
                    height=48,
                    border_radius=100,
                    left=25,
                    top=340,
                    gradient=ft.RadialGradient(
                        colors=[
                            ft.Colors.with_opacity(0.36, _CYAN),
                            ft.Colors.with_opacity(0.0, _CYAN),
                        ],
                    ),
                ),
                # Shoulders sit at the head/body joint (head ends at y=166), not
                # on the head, and the arms hang alongside the torso.
                ft.Container(left=22, top=170, content=self.left_arm),
                ft.Container(right=22, top=170, content=self.right_arm),
                ft.Container(left=71, top=170, content=self.body),
                ft.Container(left=57, top=54, content=self.head),
                ft.Container(left=101, top=2, content=self.antenna),
                ft.Container(left=31, top=72, content=self.ear_left),
                ft.Container(right=31, top=72, content=self.ear_right),
            ],
        )

        # Reserve room for the scaled stage so the surrounding layout keeps a
        # stable size; the scale itself is a paint transform.
        self.stage = ft.Container(
            width=STAGE_WIDTH * self._scale,
            height=STAGE_HEIGHT * self._scale,
            alignment=ft.Alignment.CENTER,
            content=ft.Container(
                width=STAGE_WIDTH,
                height=STAGE_HEIGHT,
                scale=ft.Scale(self._scale),
                content=robot_stack,
            ),
        )

        self.panel = ft.Container(
            width=400,
            # Keep the enlarged robot inside the panel on very narrow windows so
            # it cannot spill over the chat column.
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            gradient=ft.LinearGradient(
                colors=_PANEL_BG,
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
            ),
            border=ft.Border.only(left=ft.BorderSide(1, "#193D51")),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(
                                width=34,
                                height=34,
                                border_radius=12,
                                gradient=ft.LinearGradient(
                                    colors=["#1AB9D1", "#1766A5"],
                                    begin=ft.Alignment.TOP_LEFT,
                                    end=ft.Alignment.BOTTOM_RIGHT,
                                ),
                                shadow=[_glow(_BLUE, 14, 0.38)],
                                alignment=ft.Alignment.CENTER,
                                content=ft.Icon(
                                    ft.Icons.SMART_TOY_ROUNDED,
                                    size=19,
                                    color=ft.Colors.WHITE,
                                ),
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        "小控",
                                        size=16,
                                        color="#E8F8FF",
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Row(
                                        controls=[
                                            self.status_dot,
                                            self.status_text,
                                        ],
                                        spacing=6,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                ],
                                spacing=1,
                                tight=True,
                            ),
                            ft.Container(expand=True),
                            ft.Container(
                                width=30,
                                height=22,
                                border_radius=8,
                                bgcolor=ft.Colors.with_opacity(0.10, _CYAN),
                                border=ft.Border.all(
                                    1,
                                    ft.Colors.with_opacity(0.24, _CYAN),
                                ),
                                alignment=ft.Alignment.CENTER,
                                content=ft.Text(
                                    "AI",
                                    size=10,
                                    color="#87EDEE",
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        expand=True,
                        alignment=ft.Alignment.CENTER,
                        content=self.stage,
                    ),
                    self.voice_box,
                ],
                spacing=8,
            ),
        )

    def _build_eye(self) -> tuple[ft.Container, ft.Container]:
        core = ft.Container(
            width=10,
            height=10,
            border_radius=5,
            gradient=ft.RadialGradient(
                colors=["#FFFFFF", _CYAN, "#1183A3"],
                stops=[0, 0.36, 1],
            ),
            shadow=[_glow(_CYAN, 12, 0.72)],
        )
        eye = ft.Container(
            width=24,
            height=24,
            border_radius=12,
            bgcolor="#061723",
            border=ft.Border.all(2, "#3D7187"),
            alignment=ft.Alignment.CENTER,
            scale=ft.Scale(1),
            content=core,
        )
        return eye, core

    def _build_mouth(self) -> tuple[ft.Container, ft.Container]:
        glow = ft.Container(
            width=62,
            height=22,
            border_radius=11,
            bgcolor=ft.Colors.with_opacity(0.30, _CYAN),
            shadow=[_glow(_CYAN, 18, 0.58)],
            opacity=0.18,
        )
        mouth = ft.Container(
            width=54,
            height=21,
            border_radius=ft.BorderRadius.only(
                top_left=4,
                top_right=4,
                bottom_left=12,
                bottom_right=12,
            ),
            gradient=ft.LinearGradient(
                colors=["#02070C", "#071D2A"],
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
            ),
            border=ft.Border.all(2, ft.Colors.with_opacity(0.65, _CYAN)),
            shadow=[_glow(_CYAN, 12, 0.44)],
            scale=ft.Scale(scale_y=0.12),
            alignment=ft.Alignment.CENTER,
        )
        return mouth, glow

    def _build_ear(self) -> ft.Container:
        return ft.Container(
            width=20,
            height=42,
            border_radius=10,
            gradient=ft.LinearGradient(
                colors=_METAL_DARK,
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
            ),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.26, _CYAN)),
            shadow=[_glow(_BLUE, 10, 0.22)],
        )

    def _build_arm(self, direction: int) -> ft.Container:
        limb = ft.Container(
            width=34,
            height=100,
            border_radius=20,
            gradient=ft.LinearGradient(
                colors=_METAL_DARK,
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                rotation=0.20,
            ),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.30, "#BFEFFF")),
            shadow=[
                _glow(_BLUE, 12, 0.16),
                ft.BoxShadow(
                    blur_radius=11,
                    color=ft.Colors.with_opacity(0.28, ft.Colors.BLACK),
                    offset=ft.Offset(0, 7),
                ),
            ],
        )
        # The hand is part of the arm so rotating the shoulder rotates the hand.
        return ft.Container(
            width=46,
            height=138,
            rotate=ft.Rotate(
                angle=0.10 * direction,
                alignment=ft.Alignment.TOP_CENTER,
            ),
            content=ft.Column(
                controls=[limb, self._build_hand()],
                spacing=-5,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _build_hand(self) -> ft.Container:
        return ft.Container(
            width=30,
            height=30,
            border_radius=15,
            gradient=ft.RadialGradient(
                colors=["#EAF8FF", "#7199AE", "#29485A"],
                stops=[0, 0.56, 1],
            ),
            border=ft.Border.all(1, "#DDF8FF"),
            shadow=[_glow(_BLUE, 10, 0.20)],
        )

    @property
    def speaking(self) -> bool:
        return self._speaking

    def set_mouth_level(self, level: float | None) -> None:
        """Feed the current audio loudness (0.0-1.0) that drives the mouth.

        ``None`` switches the mouth back to a built-in idle speaking motion,
        which is also the fallback when no audio envelope is available.
        """
        if level is None:
            self._mouth_level = None
            return
        self._mouth_level = max(0.0, min(1.0, float(level)))

    def clear_mouth_level(self) -> None:
        self._mouth_level = None

    def set_read_text(self, text: str) -> None:
        """Feed the speakable reply text that streams into the caption box."""
        self._read_text = text or ""

    def set_read_spoken(self, count: int) -> None:
        """How many characters of ``set_read_text`` have been voiced already."""
        self._read_spoken = max(0, int(count))

    def _render_read_text(self) -> None:
        """Live-caption render.

        Only the part already voiced is shown, so the text appears in step with
        the voice like a real conversation. While speaking, the newest
        characters are bright with a glow and the older ones fade backwards
        behind a caret. Once the reply finishes, the whole caption settles on a
        single soft colour instead of keeping a bright tail.
        """
        text = self._read_text
        spoken = min(len(text), self._read_spoken)

        spans: list[ft.TextSpan] = []
        # The whole spoken text stays in the control: the box scrolls instead
        # of trimming it, so nothing is hidden.
        window = text[:spoken]

        if window and not self._speaking:
            # Finished: one uniform, softer colour for the whole message.
            spans.append(
                ft.TextSpan(
                    window,
                    style=ft.TextStyle(color=READ_SETTLED),
                )
            )
        elif window:
            bands = min(READ_FADE_BANDS, len(window))
            for index in range(bands):
                begin = index * len(window) // bands
                end = (index + 1) * len(window) // bands
                piece = window[begin:end]
                if not piece:
                    continue
                # 1.0 = the freshest characters.
                freshness = (index + 1) / bands
                style = ft.TextStyle(
                    color=_mix_color(READ_DIM, READ_BRIGHT, freshness),
                )
                if freshness > 0.82:
                    style.weight = ft.FontWeight.BOLD
                    style.shadow = ft.BoxShadow(
                        blur_radius=9,
                        color=ft.Colors.with_opacity(0.65, _CYAN),
                    )
                spans.append(ft.TextSpan(piece, style=style))

        # The caret marks the speaking point, so it goes away once settled.
        if self._speaking and self._read_cursor_on:
            spans.append(
                ft.TextSpan(
                    READ_CURSOR,
                    style=ft.TextStyle(
                        color=_CYAN,
                        weight=ft.FontWeight.BOLD,
                        shadow=ft.BoxShadow(
                            blur_radius=12,
                            color=ft.Colors.with_opacity(0.9, _CYAN),
                        ),
                    ),
                )
            )
        self.read_text.spans = spans or [
            ft.TextSpan("", style=ft.TextStyle(color=READ_SETTLED))
        ]

    def set_speaking(self, speaking: bool) -> None:
        if self._speaking == speaking:
            return
        self._speaking = speaking
        if speaking:
            self._burst = 1.0
            self.status_text.value = "正在说话"
            self.status_text.color = "#A9F6EE"
            self.status_dot.bgcolor = _CYAN
            self.status_dot.shadow = [_glow(_CYAN, 12, 0.72)]
            self.voice_status.value = "回应中"
            self.voice_status.color = "#A9F6EE"
            self.voice_dot.bgcolor = _CYAN
            self.voice_dot.shadow = [_glow(_CYAN, 12, 0.85)]
        else:
            self._mouth_level = None
            self.status_text.value = "待机中"
            self.status_text.color = "#B8D7E8"
            self.status_dot.bgcolor = "#5BE7C4"
            self.status_dot.shadow = [_glow("#5BE7C4", 10, 0.55)]
            self.voice_status.value = "就绪"
            self.voice_status.color = "#72E8C6"
            self.voice_dot.bgcolor = "#72E8C6"
            self.voice_dot.shadow = [_glow("#72E8C6", 8, 0.55)]

        for control in (
            self.status_text,
            self.status_dot,
            self.voice_status,
            self.voice_dot,
        ):
            try:
                control.update()
            except RuntimeError:
                pass

    def start(self, page: ft.Page) -> None:
        if self._task is None:
            self._task = page.run_task(self._animate)

    def _advance_gesture(self, now: float) -> tuple[float, float]:
        """Ease the arms between poses so gestures read as deliberate motion."""
        if now >= self._gesture_deadline:
            self._gesture_from = self._gesture_value
            self._gesture_index = (self._gesture_index + 1) % len(_GESTURES)
            self._gesture_to = _GESTURES[self._gesture_index]
            self._gesture_start = now
            # Slow, smooth moves with a clear pause in between: fewer gestures
            # that each read as deliberate, instead of constant motion.
            self._gesture_move = 0.55
            self._gesture_hold = 0.9 if self._gesture_hold > 1.2 else 1.5
            self._gesture_deadline = now + self._gesture_move + self._gesture_hold

        span = max(1e-6, self._gesture_move)
        progress = min(1.0, max(0.0, (now - self._gesture_start) / span))
        eased = 0.5 - 0.5 * math.cos(math.pi * progress)
        self._gesture_value = (
            self._gesture_from[0]
            + (self._gesture_to[0] - self._gesture_from[0]) * eased,
            self._gesture_from[1]
            + (self._gesture_to[1] - self._gesture_from[1]) * eased,
        )
        return self._gesture_value

    async def _animate(self) -> None:
        started = time.monotonic()
        previous = started

        while True:
            now = time.monotonic()
            t = now - started
            dt = min(0.2, max(0.0, now - previous))
            previous = now

            # Reactions fade out, which gives a small "wake up" gesture whenever
            # the assistant starts speaking.
            self._burst = max(0.0, self._burst - dt * 1.7)

            if self._speaking:
                raw_level = self._mouth_level
                if raw_level is None:
                    # No audio envelope: fall back to a slow synthetic
                    # open/close that stays clearly visible.
                    raw_level = 0.5 + 0.5 * math.sin(t * 5.5)
                level = max(0.0, min(1.0, raw_level))
            else:
                level = 0.0

            # The mouth follows the raw level so it looks like real speech, but
            # the body must NOT: multiplying an arm angle by a per-frame loudness
            # value makes the limbs buzz like boiling water. Both smoothed values
            # below are only ever used for body motion and the level meter.
            self._pulse += (level - self._pulse) * min(1.0, dt * 9.0)
            self._motion += (level - self._motion) * min(1.0, dt * 2.2)

            if self._speaking:
                energy = min(
                    1.0,
                    0.45 + 0.40 * self._motion + 0.30 * self._burst,
                )

                mouth_scale = MOUTH_CLOSED + level * (MOUTH_OPEN - MOUTH_CLOSED)
                # Slow, gentle nod. No high-frequency terms: they read as jitter.
                head_angle = (
                    0.026 * math.sin(t * 1.9)
                    + 0.030 * energy * math.sin(t * 3.1)
                )
                head_offset_y = (
                    -0.014 * energy
                    + 0.010 * math.sin(t * 2.4)
                )
                head_offset_x = 0.009 * math.sin(t * 1.1)
                # Hands ease between outward poses; the smoothed energy only
                # changes how wide the gesture is, over about half a second.
                gesture_left, gesture_right = self._advance_gesture(t)
                amplitude = 0.75 + 0.28 * energy
                left_angle = gesture_left * amplitude
                right_angle = gesture_right * amplitude
                body_offset_y = -0.004 + 0.009 * math.sin(t * 2.4)
                body_angle = 0.009 * math.sin(t * 1.3)
                core_scale = 0.96 + 0.24 * self._pulse + 0.04 * math.sin(t * 4.0)
                antenna_scale = 0.93 + 0.16 * self._pulse + 0.04 * math.sin(t * 3.4)
                bar_scale = 0.55 + 0.95 * self._pulse
                self.mouth_glow.opacity = 0.18 + 0.72 * level
            else:
                breath = 0.5 + 0.5 * math.sin(t * 1.35)
                sway = math.sin(t * 0.55)
                mouth_scale = MOUTH_CLOSED + breath * 0.035
                head_angle = (
                    0.020 * math.sin(t * 0.85)
                    + 0.010 * math.sin(t * 0.31)
                )
                head_offset_y = -0.004 + 0.008 * math.sin(t * 1.35)
                head_offset_x = 0.022 * math.sin(t * 0.42)
                # Ease back to the resting pose after talking stops.
                decay = min(1.0, dt * 3.2)
                self._gesture_value = (
                    self._gesture_value[0]
                    + (_REST_ARMS[0] - self._gesture_value[0]) * decay,
                    self._gesture_value[1]
                    + (_REST_ARMS[1] - self._gesture_value[1]) * decay,
                )
                self._gesture_deadline = 0.0
                left_angle = self._gesture_value[0] + 0.026 * math.sin(t * 1.10)
                right_angle = (
                    self._gesture_value[1] - 0.028 * math.sin(t * 1.10 + 0.9)
                )
                body_offset_y = 0.007 * math.sin(t * 1.35)
                body_angle = 0.010 * sway
                core_scale = 0.95 + breath * 0.09
                antenna_scale = 0.90 + breath * 0.14
                bar_scale = 0.30 + breath * 0.16
                self.mouth_glow.opacity = 0.10 + breath * 0.08

            blink = 1.0
            # Blink roughly every four seconds; a faster interval reads as a
            # flicker rather than a natural blink.
            cycle = t % 4.2
            if cycle > 3.92:
                blink = max(0.10, abs(cycle - 4.06) / 0.14)

            self.mouth.scale = ft.Scale(scale_y=mouth_scale)
            self.head.rotate = ft.Rotate(
                angle=head_angle,
                alignment=ft.Alignment.CENTER,
            )
            self.head.offset = ft.Offset(head_offset_x, head_offset_y)
            self.body.offset = ft.Offset(0, body_offset_y)
            self.body.rotate = ft.Rotate(
                angle=body_angle,
                alignment=ft.Alignment.TOP_CENTER,
            )
            self.left_arm.rotate = ft.Rotate(
                angle=left_angle,
                alignment=ft.Alignment.TOP_CENTER,
            )
            self.right_arm.rotate = ft.Rotate(
                angle=right_angle,
                alignment=ft.Alignment.TOP_CENTER,
            )
            self.eye_left.scale = ft.Scale(scale_y=blink)
            self.eye_right.scale = ft.Scale(scale_y=blink)
            self.chest_core.scale = ft.Scale(scale=core_scale)
            self.antenna_orb.scale = ft.Scale(scale=antenna_scale)

            # Bars use a transform, never a size change, so the layout is fixed.
            for index, bar in enumerate(self.pulse_bars):
                wave = 0.55 + 0.45 * abs(math.sin(t * 4.6 + index * 0.9))
                bar.scale = ft.Scale(
                    scale_y=max(0.12, min(1.7, bar_scale * wave * 1.35)),
                    alignment=ft.Alignment.BOTTOM_CENTER,
                )

            # "流式朗读回复文字" panel: brightness, glow and the energy bar all
            # ride the same smoothed loudness, so the display matches the voice.
            level_now = self._pulse
            # Re-render only when the text, the reading position, or the caret
            # blink state changes.
            # Only the speaking caret blinks, so the caption stops re-rendering
            # once the reply is finished (which lets the reader scroll freely).
            cursor_on = int(t * 2.4) % 2 == 0 if self._speaking else None
            render_key = (
                self._read_text,
                self._read_spoken,
                cursor_on,
                self._speaking,
            )
            if render_key != self._read_rendered:
                self._read_rendered = render_key
                self._read_cursor_on = bool(cursor_on)
                self._render_read_text()
                # Pin the viewport to the newest line whenever more text has
                # been revealed. scroll_to() requires auto_scroll to be off.
                if self._read_spoken > self._read_pinned:
                    self._read_pinned = self._read_spoken
                    with contextlib.suppress(Exception):
                        await self.read_text_box.scroll_to(offset=-1)
            self.level_fill.scale = ft.Scale(
                scale_x=0.04 + 0.96 * level_now,
                alignment=ft.Alignment.CENTER_LEFT,
            )
            self.level_fill.shadow = [
                _glow(_CYAN, 6 + int(14 * level_now), 0.25 + 0.6 * level_now)
            ]
            self.voice_box.border = ft.Border.all(
                1,
                ft.Colors.with_opacity(0.16 + 0.64 * level_now, _CYAN),
            )

            # Guard the refresh: if the panel is temporarily detached (hidden
            # then removed, or not yet mounted) Flet raises instead of
            # returning None, and an unhandled raise here would silently kill
            # the whole animation task forever.
            try:
                self.panel.update()
            except RuntimeError:
                pass
            await asyncio.sleep(0.04)
