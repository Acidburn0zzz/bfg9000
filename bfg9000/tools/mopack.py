import json

from . import tool
from .common import SimpleCommand
from .. import shell
from ..path import Path, Root
from ..safe_str import safe_format


@tool('mopack')
class Mopack(SimpleCommand):
    package_dir = Path('mopack')

    def __init__(self, env):
        super().__init__(env, name='mopack', env_var='MOPACK',
                         default='mopack')

    def _dir_arg(self, directory):
        return ['--directory', directory] if directory else []

    def _call_resolve(self, cmd, config, *, directory=None,
                      toolchain=None):
        result = cmd + ['resolve']
        result.append(config)
        result.extend(self._dir_arg(directory))

        for k, v in self.env.install_dirs.items():
            if v is not None and v.root == Root.absolute:
                result.append(safe_format('-P{}={}', k.name, v))

        if toolchain:
            result.append('-Bbfg9000:toolchain=' + toolchain)
        return result

    def _call_usage(self, cmd, name, *, directory=None):
        return cmd + ['usage', '--json', name] + self._dir_arg(directory)

    def _call_deploy(self, cmd, *, directory=None):
        return cmd + ['deploy'] + self._dir_arg(directory)

    def _call_clean(self, cmd, *, directory=None):
        return cmd + ['clean'] + self._dir_arg(directory)

    def _call(self, cmd, subcmd, *args, **kwargs):
        return getattr(self, '_call_' + subcmd)(cmd, *args, **kwargs)

    def run(self, subcmd, *args, **kwargs):
        result = super().run(subcmd, *args, **kwargs)
        if subcmd == 'usage':
            return json.loads(result.strip())
        return result


def try_usage(env, name):
    try:
        return env.tool('mopack').run(
            'usage', name, directory=env.builddir
        )
    except (OSError, shell.CalledProcessError):
        return {'type': 'system'}
