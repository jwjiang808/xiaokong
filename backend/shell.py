"""Windows 下容错解码的 shell 后端。

deepagents 的 LocalShellBackend 用 text=True 按 GBK 解码；Python 脚本输出
UTF-8 时会直接抛 UnicodeDecodeError。这里先按 UTF-8、再按 GBK 解码。
"""

from __future__ import annotations

import subprocess
import sys

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse


def decode_output(raw: bytes) -> str:
    if not raw:
        return ""
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class WorkspaceShellBackend(LocalShellBackend):
    """执行命令并把输出稳定解码成文本。"""

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        if not command or not isinstance(command, str):
            return ExecuteResponse(
                output="Error: Command must be a non-empty string.",
                exit_code=1,
                truncated=False,
            )

        effective_timeout = (
            timeout if timeout is not None else self._default_timeout
        )
        if effective_timeout <= 0:
            raise ValueError(f"timeout must be positive, got {effective_timeout}")

        try:
            result = subprocess.run(
                command,
                check=False,
                shell=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=False,
                timeout=effective_timeout,
                env=self._env,
                cwd=str(self.cwd),
                start_new_session=(sys.platform != "win32"),
            )
            stdout = decode_output(result.stdout)
            stderr = decode_output(result.stderr)

            parts: list[str] = []
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.extend(
                    f"[stderr] {line}" for line in stderr.strip().splitlines()
                )
            output = "\n".join(parts) if parts else "<no output>"

            truncated = False
            if len(output) > self._max_output_bytes:
                output = (
                    output[: self._max_output_bytes]
                    + f"\n\n... Output truncated at {self._max_output_bytes} bytes."
                )
                truncated = True
            if result.returncode != 0:
                output = f"{output.rstrip()}\n\nExit code: {result.returncode}"

            return ExecuteResponse(
                output=output,
                exit_code=result.returncode,
                truncated=truncated,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"Error: Command timed out after {effective_timeout} seconds.",
                exit_code=124,
                truncated=False,
            )
        except Exception as exc:
            return ExecuteResponse(
                output=f"Error executing command ({type(exc).__name__}): {exc}",
                exit_code=1,
                truncated=False,
            )
