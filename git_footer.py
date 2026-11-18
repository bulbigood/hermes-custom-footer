"""Optional command for preserving the previous Git footer."""

import os
import subprocess
from pathlib import Path


def detached_label(oid, env):
    label = f'(detached) {oid[:8]}'
    try:
        result = subprocess.run(
            ['git', 'for-each-ref', '--sort=refname',
             '--format=%(objectname)%09%(symref)%09%(refname:lstrip=2)', 'refs/remotes/'],
            env=env, capture_output=True, text=True, errors='replace', timeout=0.5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return label
    if result.returncode:
        return label
    branches = []
    for line in result.stdout.split('\n'):
        fields = line.split('\t', 2)
        if len(fields) == 3 and fields[0] == oid and not fields[1]:
            branches.append(fields[2])
    if branches:
        preferred = next((name for name in branches if name.startswith('origin/')), branches[0])
        label += f' — {preferred}'
        if len(branches) > 1:
            label += f' ({len(branches) - 1} more)'
    return label


def main():
    safe = lambda value: value.replace('\n', r'\n').replace('\r', r'\r').replace('`', r'\x60')
    lines = [safe(str(Path.cwd()))]
    env = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C'}
    try:
        result = subprocess.run(
            ['git', '-c', 'core.fsmonitor=false', 'status', '--porcelain=v2', '--branch'],
            env=env,
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
            oid = None
            for line in result.stdout.split('\n'):
                if line.startswith('# branch.head '):
                    branch = line.removeprefix('# branch.head ')
                elif line.startswith('# branch.oid '):
                    oid = line.removeprefix('# branch.oid ')
                elif line.startswith('# branch.ab '):
                    ahead = int(line.split()[2])
                elif line.startswith(('1 ', '2 ', 'u ', '? ', '! ')):
                    dirty = True
            detached = branch == '(detached)'
            if detached and oid and oid != '(initial)':
                branch = detached_label(oid, env)
            lines.append(f'Branch: {safe(branch)}')
            status = []
            if dirty:
                status.append('Worktree: dirty')
            if not detached:
                if ahead is None:
                    status.append('Pushed: unknown (no upstream)')
                elif ahead:
                    status.append(f'Pushed: no ({ahead} commits)')
            if status:
                lines.append(' | '.join(status))
    print('```text', *lines, '```', sep='\n')


if __name__ == '__main__':
    main()
