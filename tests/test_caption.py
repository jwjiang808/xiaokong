from __future__ import annotations

import flet as ft

from xiaokong.ui.robot import READ_CURSOR, READ_SETTLED, TechRobotDoll


def visible(robot: TechRobotDoll) -> str:
    parts = [span.text for span in robot.read_text.spans]
    if parts and parts[-1] == READ_CURSOR:
        parts = parts[:-1]
    return "".join(parts)


def bands(robot: TechRobotDoll) -> list[str]:
    return [
        span.style.color
        for span in robot.read_text.spans
        if span.text and span.text != READ_CURSOR
    ]


def luminance(color: str) -> int:
    return int(color[1:3], 16) + int(color[3:5], 16) + int(color[5:7], 16)


def test_unspoken_text_is_never_rendered() -> None:
    robot = TechRobotDoll()
    text = "人工智能是让机器模拟人类智能行为的技术，能学习推理和决策。"
    robot.set_read_text(text)
    robot.set_read_spoken(0)
    robot._render_read_text()
    assert visible(robot) == ""

    robot.set_read_spoken(10)
    robot._render_read_text()
    assert visible(robot) == text[:10]


def test_spoken_text_fades_towards_the_tip() -> None:
    robot = TechRobotDoll()
    robot.set_speaking(True)
    robot.set_read_text("人工智能是让机器模拟人类智能行为的技术。")
    robot.set_read_spoken(14)
    robot._render_read_text()

    values = [luminance(color) for color in bands(robot)]
    assert len(values) >= 3
    assert values == sorted(values)
    assert values[-1] > values[0] + 100
    assert robot.read_text.spans[-1].text == READ_CURSOR


def test_settled_caption_is_uniform_and_has_no_caret() -> None:
    robot = TechRobotDoll()
    robot.set_read_text("课程助手要讲清楚概念，也要给出例子。")
    robot.set_read_spoken(20)
    robot._render_read_text()

    colors = set(bands(robot))
    assert colors == {READ_SETTLED}
    assert robot.read_text.spans[-1].text != READ_CURSOR


def test_long_multiline_answer_is_kept_and_scrollable() -> None:
    robot = TechRobotDoll()
    text = "\n".join(f"第{i}点：这是多行回答的测试内容。" for i in range(12))
    robot.set_read_text(text)
    robot.set_read_spoken(len(text))
    robot._render_read_text()

    assert visible(robot) == text
    assert visible(robot).count("\n") == 11
    assert robot.read_text_box.scroll == ft.ScrollMode.AUTO
    assert robot.read_text.max_lines is None
    assert robot.read_text_box.auto_scroll is False
