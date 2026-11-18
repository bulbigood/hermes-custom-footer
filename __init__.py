"""Append stdout from an operator-configured local command to final replies."""

import logging
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

from agent.runtime_cwd import resolve_agent_cwd, scope_terminal_cwd, scoped_session_cwd
from tools.approval import get_current_session_key
from tools.terminal_scope import terminal_env
from tools.terminal_tool import get_session_cwd

_LOG = logging.getLogger(__name__)
_MAX_OUTPUT = 16 * 1024


def _run(command, cwd, platform, timeout):
    # No inherited gateway secrets or assistant text.
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'CUSTOM_FOOTER_PLATFORM': platform}
    with subprocess.Popen(
        command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
    ) as process:
        deadline = time.monotonic() + timeout
        output = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise TimeoutError
                    chunk = os.read(process.stdout.fileno(), min(4096, _MAX_OUTPUT + 1 - len(output)))
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > _MAX_OUTPUT:
                        raise ValueError('stdout limit exceeded')
            if process.wait(timeout=max(0, deadline - time.monotonic())) != 0:
                _LOG.warning('custom-footer: command exited unsuccessfully')
                return ''
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raise
        return output.decode('utf-8').strip('\r\n')


def register(ctx):
    def append_footer(response_text: str, platform: str = '', session_id: str = '', **_kwargs) -> str | None:
        if not response_text.strip():
            return None
        command = ctx.get_config('command')
        if command is None:
            return None
        platforms = ctx.get_config('platforms')
        timeout = ctx.get_config('timeout_seconds', 1.0)
        if (
            not isinstance(command, list) or not command
            or not all(isinstance(arg, str) and '\x00' not in arg for arg in command)
            or not Path(command[0]).is_absolute()
            or (platforms is not None and (not isinstance(platforms, list)
                or not all(isinstance(item, str) and item for item in platforms)))
            or type(timeout) not in (int, float) or not 0 < timeout <= 5
        ):
            _LOG.warning('custom-footer: invalid plugin settings')
            return None
        if platforms is not None and platform not in platforms:
            return None
        if (terminal_env('TERMINAL_ENV', '').strip() or 'local') != 'local':
            return None
        try:
            # Use the terminal's routing key, not the transcript ID, when both exist.
            key = get_current_session_key(default='') or session_id
            recorded = get_session_cwd(key) if key else None
            declared = recorded or scoped_session_cwd() or scope_terminal_cwd()
            cwd = Path(declared).expanduser().absolute() if declared else resolve_agent_cwd()
            footer = _run(command, cwd, platform, timeout)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            _LOG.warning('custom-footer: command skipped (%s)', type(exc).__name__)
            return None
        answer = response_text.rstrip()
        if not footer.strip() or answer == footer.rstrip() or answer.endswith('\n\n' + footer.rstrip()):
            return None
        return f'{answer}\n\n{footer}'

    ctx.register_hook('transform_llm_output', append_footer)
