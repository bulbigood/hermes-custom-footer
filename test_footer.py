import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import __init__ as plugin
from agent.runtime_cwd import set_session_cwd, reset_session_cwd

class FooterTest(unittest.TestCase):
    class Context:
        def __init__(self, **settings):
            self.settings = settings

        def get_config(self, key, default=None):
            return self.settings.get(key, default)

        def register_hook(self, name, callback):
            self.name, self.callback = name, callback

    def hook(self, code=None, *args, **settings):
        if code is not None:
            settings['command'] = [sys.executable, '-c', code, *args]
        ctx = self.Context(**settings)
        plugin.register(ctx)
        self.assertEqual(ctx.name, 'transform_llm_output')
        return ctx.callback

    def test_command_uses_session_cwd_and_literal_args(self):
        callback = self.hook(
            'import os,sys; print(os.getcwd()); print(sys.argv[1]); '
            'print(os.environ["CUSTOM_FOOTER_PLATFORM"]); print(repr(sys.stdin.read()))',
            'space; $(literal)',
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp).resolve()
            tok = set_session_cwd(str(p))
            try:
                answer = callback(response_text='Answer', platform='telegram')
                self.assertEqual(answer, f"Answer\n\n{p}\nspace; $(literal)\ntelegram\n''")
                self.assertIsNone(callback(response_text=answer, platform='telegram'))
            finally:
                reset_session_cwd(tok)

    def test_platform_filter_and_blank_answer(self):
        callback = self.hook('print("footer")', platforms=['telegram'])
        self.assertIsNone(callback(response_text='Answer', platform='cli'))
        self.assertIsNone(callback(response_text=' ', platform='telegram'))
        self.assertEqual(callback(response_text='Answer', platform='telegram'), 'Answer\n\nfooter')

    def test_bundled_git_command_formats_git_and_non_git_directories(self):
        script = str(Path(__file__).with_name('git_footer.py').resolve())
        callback = self.hook(command=[sys.executable, script], timeout_seconds=2)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve()
            token = set_session_cwd(str(path))
            try:
                self.assertEqual(callback(response_text='Answer'), f'Answer\n\n```text\n{path}\n```')
                subprocess.run(['/usr/bin/git', 'init', '-q', '-b', 'main', str(path)], check=True)
                (path / 'untracked').touch()
                self.assertEqual(callback(response_text='Answer'),
                                 f'Answer\n\n```text\n{path}\nBranch: main\nWorktree: dirty | Pushed: unknown (no upstream)\n```')
            finally:
                reset_session_cwd(token)

    def test_git_footer_shows_only_dirty_or_unpushed_status(self):
        script = str(Path(__file__).with_name('git_footer.py').resolve())
        callback = self.hook(command=[sys.executable, script], timeout_seconds=2)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve()

            def git(*args):
                subprocess.run(['/usr/bin/git', '-c', 'user.name=Footer Test', '-c',
                                'user.email=footer@example.invalid', '-c', 'commit.gpgsign=false',
                                '-c', 'core.hooksPath=/dev/null', *args], cwd=path, check=True)

            git('init', '-q', '-b', 'main')
            git('commit', '-q', '--allow-empty', '-m', 'Initial')
            git('branch', 'upstream')
            git('branch', '-q', '--set-upstream-to=upstream')
            token = set_session_cwd(str(path))
            try:
                prefix = f'Answer\n\n```text\n{path}\nBranch: main\n'
                self.assertEqual(callback(response_text='Answer'), prefix + '```')
                (path / 'untracked').touch()
                self.assertEqual(callback(response_text='Answer'), prefix + 'Worktree: dirty\n```')
                git('commit', '-q', '--allow-empty', '-m', 'Local change')
                self.assertEqual(callback(response_text='Answer'),
                                 prefix + 'Worktree: dirty | Pushed: no (1 commits)\n```')
                (path / 'untracked').unlink()
                self.assertEqual(callback(response_text='Answer'), prefix + 'Pushed: no (1 commits)\n```')
            finally:
                reset_session_cwd(token)

    def test_missing_or_failed_command_leaves_answer_unchanged(self):
        for callback in (self.hook(), self.hook('pass'), self.hook('print("oops"); raise SystemExit(2)'),
                         self.hook('import time; time.sleep(10)', timeout_seconds=0.05),
                         self.hook('print("x" * 100000)'), self.hook(command='echo unsafe')):
            with self.subTest(callback=callback):
                self.assertIsNone(callback(response_text='Answer', platform='telegram'))

if __name__ == '__main__':
    unittest.main()
