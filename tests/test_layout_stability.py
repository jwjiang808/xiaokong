from __future__ import annotations

import asyncio

import pytest

from xiaokong.ui.robot import TechRobotDoll

LAYOUT_FIELDS = (
    "width",
    "height",
    "spacing",
    "padding",
    "margin",
    "expand",
    "left",
    "top",
    "right",
    "bottom",
    "border_radius",
)


def walk(control, seen=None):
    if control is None:
        return
    if seen is None:
        seen = set()
    if id(control) in seen:
        return
    seen.add(id(control))
    yield control
    for attr in ("content", "controls"):
        child = getattr(control, attr, None)
        if isinstance(child, (list, tuple)):
            for item in child:
                yield from walk(item, seen)
        elif child is not None:
            yield from walk(child, seen)


def snapshot(root) -> dict[int, tuple]:
    result = {}
    for control in walk(root):
        values = []
        for field in LAYOUT_FIELDS:
            try:
                values.append(repr(getattr(control, field, None)))
            except Exception:  # pragma: no cover - defensive
                values.append("<error>")
        result[id(control)] = (type(control).__name__, tuple(values))
    return result


async def _run_scene(scene: str) -> None:
    robot = TechRobotDoll()
    task = asyncio.create_task(robot._animate())
    if scene == "idle":
        before = snapshot(robot.panel)
        await asyncio.sleep(1.6)
    else:
        robot.set_speaking(True)
        await asyncio.sleep(0.2)
        before = snapshot(robot.panel)
        for level in (0.1, 0.9, 0.3, 1.0, 0.0, 0.7):
            robot.set_mouth_level(level)
            await asyncio.sleep(0.3)

    after = snapshot(robot.panel)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert before.keys() == after.keys()
    changed = [key for key in before if before[key][1] != after[key][1]]
    assert not changed, f"{len(changed)} controls changed layout in {scene}"


@pytest.mark.parametrize("scene", ["idle", "speaking"])
async def test_robot_never_moves_the_layout(scene: str) -> None:
    await _run_scene(scene)
