"""Chat message rendering helpers."""

from __future__ import annotations

import flet as ft


def safe_update(*controls: ft.Control) -> None:
    """Update controls that may not be mounted.

    In voice-only mode the chat list is not part of the page, so calling
    ``update()`` on a message control would raise. The change is still kept in
    the control tree, so it appears as soon as the chat is expanded again.
    """
    for control in controls:
        try:
            control.update()
        except RuntimeError:
            pass


def build_message(role: str, text: str) -> tuple[ft.Control, ft.Markdown]:
    """Build one chat row and return it together with its Markdown body."""
    is_user = role == "user"
    text_color = "#102A43" if is_user else "#17212B"
    avatar = ft.Container(
        content=ft.Icon(
            ft.Icons.PERSON_ROUNDED if is_user else ft.Icons.SET_MEAL_ROUNDED,
            size=20,
            color=ft.Colors.WHITE,
        ),
        width=38,
        height=38,
        border_radius=19,
        gradient=ft.LinearGradient(
            colors=["#3B82F6", "#1D4ED8"] if is_user else ["#14B8A6", "#0F766E"],
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
        ),
        shadow=ft.BoxShadow(
            blur_radius=8,
            color=ft.Colors.with_opacity(0.18, ft.Colors.BLACK),
            offset=ft.Offset(0, 2),
        ),
        alignment=ft.Alignment.CENTER,
    )
    markdown_style = ft.MarkdownStyleSheet(
        p_text_style=ft.TextStyle(color=text_color, size=15, height=1.45),
        a_text_style=ft.TextStyle(
            color="#0B63CE",
            size=15,
            weight=ft.FontWeight.BOLD,
        ),
        code_text_style=ft.TextStyle(
            color="#9B1C31",
            bgcolor="#F1F3F5",
            size=14,
        ),
        h1_text_style=ft.TextStyle(
            color=text_color,
            size=24,
            weight=ft.FontWeight.BOLD,
        ),
        h2_text_style=ft.TextStyle(
            color=text_color,
            size=21,
            weight=ft.FontWeight.BOLD,
        ),
        h3_text_style=ft.TextStyle(
            color=text_color,
            size=18,
            weight=ft.FontWeight.BOLD,
        ),
        strong_text_style=ft.TextStyle(
            color=text_color,
            weight=ft.FontWeight.BOLD,
        ),
        em_text_style=ft.TextStyle(color=text_color, italic=True),
        list_bullet_text_style=ft.TextStyle(color=text_color),
    )
    markdown = ft.Markdown(
        text,
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        auto_follow_links=True,
        md_style_sheet=markdown_style,
    )
    bubble = ft.Container(
        content=markdown,
        bgcolor="#E8F2FF" if is_user else "#FFFFFF",
        border=ft.Border.all(1, "#B8D4FF" if is_user else "#D9E2EA"),
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        width=560,
        shadow=ft.BoxShadow(
            blur_radius=10,
            color=ft.Colors.with_opacity(0.07, ft.Colors.BLACK),
            offset=ft.Offset(0, 2),
        ),
    )

    controls = [bubble, avatar] if is_user else [avatar, bubble]
    return (
        ft.Row(
            controls=controls,
            alignment=(
                ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
            ),
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=10,
        ),
        markdown,
    )
