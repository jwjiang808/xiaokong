from __future__ import annotations

import asyncio

from xiaokong.ui.robot import TechRobotDoll

FRAME = 0.04
MAX_CURVATURE = 0.060
MAX_MEAN_CURVATURE = 0.030


async def test_arms_do_not_buzz_with_noisy_audio() -> None:
    robot = TechRobotDoll()
    task = asyncio.create_task(robot._animate())
    robot.set_speaking(True)

    angles: list[float] = []
    toggle = 0.0
    for _ in range(90):
        toggle = 1.0 - toggle
        robot.set_mouth_level(toggle)
        await asyncio.sleep(FRAME)
        angles.append(robot.left_arm.rotate.angle)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    curvatures = [
        abs(angles[i + 1] - 2 * angles[i] + angles[i - 1])
        for i in range(1, len(angles) - 1)
    ]
    assert max(curvatures) < MAX_CURVATURE
    assert sum(curvatures) / len(curvatures) < MAX_MEAN_CURVATURE
    assert max(angles) - min(angles) > 0.10
