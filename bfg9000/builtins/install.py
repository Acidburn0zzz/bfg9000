import warnings

from . import builtin
from .. import path
from .. import shell
from ..backends.make import writer as make
from ..backends.ninja import writer as ninja
from ..build_inputs import build_input
from ..file_types import Directory, File, file_install_path, installify
from ..iterutils import flatten, iterate, iterate_each, map_iterable, unlistify


@build_input('install')
class InstallOutputs:
    def __init__(self, build_inputs, env):
        self.explicit = []
        self.implicit = []

    def add(self, item):
        if item not in self.explicit:
            self.explicit.append(item)

        for i in item.all:
            self._add_implicit(i)

    def _add_implicit(self, item):
        if not isinstance(item, File):
            raise TypeError('expected a file or directory')
        if item.path.root not in (path.Root.srcdir, path.Root.builddir):
            raise ValueError('external files are not installable')

        if item not in self.implicit:
            self.implicit.append(item)

        for i in item.install_deps:
            self._add_implicit(i)

    def __bool__(self):
        return bool(self.implicit)

    def __iter__(self):
        return iter(self.implicit)


def can_install(env):
    return all(i is not None for i in env.install_dirs.values())


@builtin.function()
def install(context, *args):
    if len(args) == 0:
        return

    can_inst = can_install(context.env)
    if not can_inst:
        warnings.warn('unset installation directories; installation of this ' +
                      'build disabled')

    context['default'](*args)
    for i in iterate_each(args):
        context.build['install'].add(i)

    return unlistify(tuple(
        map_iterable(lambda x: installify(x, context.env), i) for i in args
    ))


def _doppel_cmd(env, buildfile):
    doppel = env.tool('doppel')

    def wrapper(kind):
        cmd = buildfile.cmd_var(doppel)
        basename = cmd.name

        if kind != 'program':
            kind = 'data'
            cmd = [cmd] + doppel.data_args
        if basename.isupper():
            kind = kind.upper()

        name = '{name}_{kind}'.format(name=basename, kind=kind)
        cmd = buildfile.variable(name, cmd, buildfile.Section.command, True)
        return lambda *args, **kwargs: doppel(*args, cmd=cmd, **kwargs)
    return wrapper


def _install_files(install_outputs, buildfile, env):
    doppel = _doppel_cmd(env, buildfile)

    def install_line(output):
        cmd = doppel(output.install_kind)
        if isinstance(output, Directory):
            if output.files is not None:
                src = [i.path.relpath(output.path) for i in output.files]
                dst = file_install_path(output)
                return cmd('into', src, dst, directory=output.path)

            warnings.warn(
                ('installed directory {!r} has no matching files; did you ' +
                 'forget to set `include`?').format(output.path)
            )

        src = output.path
        dst = file_install_path(output)
        return cmd('onto', src, dst)

    return ([install_line(i) for i in install_outputs] +
            [i.post_install for i in install_outputs if i.post_install])


def _install_mopack(env):
    if env.mopack:
        return [env.tool('mopack')('deploy', directory=path.Path('.'))]
    return []


def _uninstall_files(install_outputs, env):
    def uninstall_line(output):
        if isinstance(output, Directory):
            dst = file_install_path(output)
            return [dst.append(i.path.relpath(output.path)) for i in
                    iterate(output.files)]
        return [file_install_path(output)]

    if install_outputs:
        rm = env.tool('rm')
        return [rm(flatten(uninstall_line(i) for i in install_outputs))]
    return []


@make.post_rule
def make_install_rule(build_inputs, buildfile, env):
    if not can_install(env):
        return

    install_outputs = build_inputs['install']
    install_files = _install_files(install_outputs, buildfile, env)
    uninstall_files = _uninstall_files(install_outputs, env)

    if install_files or uninstall_files:
        for i in path.InstallRoot:
            buildfile.variable(make.path_vars[i], env.install_dirs[i],
                               make.Section.path)
        if path.DestDir.destdir in make.path_vars:
            buildfile.variable(make.path_vars[path.DestDir.destdir],
                               env.variables.get('DESTDIR', ''),
                               make.Section.path)

    install_commands = install_files + _install_mopack(env)

    if install_commands:
        buildfile.rule(
            target='install',
            deps='all',
            recipe=install_commands,
            phony=True
        )
    if uninstall_files:
        buildfile.rule(
            target='uninstall',
            recipe=uninstall_files,
            phony=True
        )


@ninja.post_rule
def ninja_install_rule(build_inputs, buildfile, env):
    if not can_install(env):
        return

    install_outputs = build_inputs['install']
    install_files = _install_files(install_outputs, buildfile, env)
    uninstall_files = _uninstall_files(install_outputs, env)

    if install_files or uninstall_files:
        for i in path.InstallRoot:
            buildfile.variable(ninja.path_vars[i], env.install_dirs[i],
                               ninja.Section.path)
        if path.DestDir.destdir in ninja.path_vars:
            buildfile.variable(ninja.path_vars[path.DestDir.destdir],
                               env.variables.get('DESTDIR', ''),
                               ninja.Section.path)

    install_commands = install_files + _install_mopack(env)

    if install_commands:
        ninja.command_build(
            buildfile, env,
            output='install',
            inputs=['all'],
            command=shell.join_lines(install_commands),
            phony=True
        )
    if uninstall_files:
        ninja.command_build(
            buildfile, env,
            output='uninstall',
            command=shell.join_lines(uninstall_files),
            phony=True
        )
