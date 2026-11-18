"""Optional command for preserving the previous Git footer."""

import os
import subprocess
from pathlib import Path


def main():
    safe = lambda value: value.replace('\n', r'\n').replace('\r', r'\r').replace('`', r'\x60')
    lines = [safe(str(Path.cwd()))]
    try:
        result = subprocess.run(
            ['git', '-c', 'core.fsmonitor=false', 'status', '--porcelain=v2', '--branch'],
            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C'},
            capture_output=True, text=True, errors='replace', timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        lines.append('git status unavailable')
    else:
        if result.returncode:
            if 'not a git repository' not in result.stderr:
                lines.append('git status unavailable')
        else:
            branch, dirty, ahead = 'unknown', False, None
            for line in result.stdout.splitlines():
                if line.startswith('# branch.head '):
                    branch = line.removeprefix('# branch.head ')
                elif line.startswith('# branch.ab '):
                    ahead = int(line.split()[2])
                elif line.startswith(('1 ', '2 ', 'u ', '? ', '! ')):
                    dirty = True
            lines.append(f'Branch: {safe(branch)}')
            status = []
            if dirty:
                status.append('Worktree: dirty')
            if ahead is None:
                status.append('Pushed: unknown (no upstream)')
            elif ahead:
                status.append(f'Pushed: no ({ahead} commits)')
            if status:
                lines.append(' | '.join(status))
    print('```text', *lines, '```', sep='\n')


if __name__ == '__main__':
    main()
