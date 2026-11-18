"""Optional command for preserving the previous Git footer."""

import os
import subprocess
from pathlib import Path


def main():
    cwd = Path.cwd()
    try:
        result = subprocess.run(
            ['git', '-c', 'core.fsmonitor=false', 'status', '--porcelain=v2', '--branch'],
            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C'},
            capture_output=True, text=True, errors='replace', timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        status = 'git status unavailable'
    else:
        if result.returncode:
            status = 'no git' if 'not a git repository' in result.stderr else 'git status unavailable'
        else:
            branch, changes, pushed = 'unknown', 'clean', 'unknown (no upstream)'
            for line in result.stdout.splitlines():
                if line.startswith('# branch.head '):
                    branch = line.removeprefix('# branch.head ')
                elif line.startswith('# branch.ab '):
                    ahead = int(line.split()[2])
                    pushed = f'no ({ahead} commits)' if ahead else 'yes'
                elif line.startswith(('1 ', '2 ', 'u ', '? ', '! ')):
                    changes = 'dirty'
            status = f'Branch: {branch} | Worktree: {changes} | Pushed: {pushed}'
    safe = lambda value: value.replace('\n', r'\n').replace('\r', r'\r').replace('`', r'\x60')
    print(f'```text\n{safe(status)}\n{safe(str(cwd))}\n```')


if __name__ == '__main__':
    main()
