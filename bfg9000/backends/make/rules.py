import os
from cStringIO import StringIO
from itertools import chain

from .syntax import *
from ... import path
from ... import safe_str
from ... import shell
from ... import iterutils
from ...builtins import find

Path = path.Path

var = MakeVariable
def qvar(name):
    return MakeVariable(name, quoted=True)

_rule_handlers = {}
def rule_handler(rule_name):
    def decorator(fn):
        _rule_handlers[rule_name] = fn
        return fn
    return decorator

def write(env, build_inputs):
    buildfile = Makefile()
    buildfile.variable(path_vars[path.Root.srcdir], env.srcdir)
    for i in path.InstallRoot:
        buildfile.variable(path_vars[i], env.install_dirs[i])

    all_rule(build_inputs.get_default_targets(), buildfile)
    install_rule(build_inputs.install_targets, buildfile, env)
    test_rule(build_inputs.tests, buildfile)
    for e in build_inputs.edges:
        _rule_handlers[type(e).__name__](e, build_inputs, buildfile, env)
    directory_rule(buildfile)
    regenerate_rule(build_inputs.find_dirs, buildfile, env)

    with open(os.path.join(env.builddir, 'Makefile'), 'w') as out:
        buildfile.write(out)

def cmd_var(compiler, buildfile):
    name = compiler.command_var.upper()
    return buildfile.variable(name, compiler.command_name, exist_ok=True)

def flags_vars(name, value, buildfile):
    name = name.upper()
    global_flags = buildfile.variable('GLOBAL_' + name, value, exist_ok=True)
    flags = buildfile.variable(name, global_flags, target=True, exist_ok=True)
    return global_flags, flags

def all_rule(default_targets, buildfile):
    buildfile.rule(
        target='all',
        deps=default_targets,
        phony=True
    )

# TODO: Write a better `install` program to simplify this
def install_rule(install_targets, buildfile, env):
    if not install_targets:
        return

    def install_cmd(kind):
        install = buildfile.variable('INSTALL', 'install', exist_ok=True)
        if kind == 'program':
            return buildfile.variable('INSTALL_PROGRAM', install, exist_ok=True)
        else:
            return buildfile.variable('INSTALL_DATA', [install, '-m', '644'],
                                      exist_ok=True)

    def install_line(file):
        src = file.path
        dst = path.install_path(file.path, file.install_root)
        return [install_cmd(file.install_kind), '-D', src, dst]

    def mkdir_line(dir):
        src = dir.path
        dst = path.install_path(dir.path.parent(), dir.install_root)
        return 'mkdir -p ' + dst + ' && cp -r ' + src + '/* ' + dst

    post_install = filter(None, (getattr(i, 'post_install', None)
                                 for i in install_targets.files))

    recipe = ([install_line(i) for i in install_targets.files] +
              [mkdir_line(i) for i in install_targets.directories] +
              post_install)
    buildfile.rule(
        target='install',
        deps='all',
        recipe=recipe,
        phony=True
    )

def test_rule(tests, buildfile):
    if not tests:
        return

    deps = []
    if tests.targets:
        buildfile.rule(
            target='tests',
            deps=tests.targets,
            phony=True
        )
        deps.append('tests')
    deps.extend(tests.extra_deps)

    def build_commands(tests, collapse=False):
        cmd, deps = [], []
        def command(test, args=None):
            env = [safe_str.jbos(k, '=', v) for k, v in test.env.iteritems()]
            subcmd = env + [test.target] + test.options + (args or [])
            if collapse:
                out = MakeWriter(StringIO())
                out.write_shell(subcmd)
                s = out.stream.getvalue()
                if len(subcmd) > 1:
                    s = shell.quote(s)
                return safe_str.escaped_str(s)
            return subcmd

        for i in tests:
            if type(i).__name__ == 'TestDriver':
                args, moredeps = build_commands(i.tests, True)
                if i.target.creator:
                    deps.append(i.target)
                deps.extend(moredeps)
                cmd.append(command(i, args))
            else:
                cmd.append(command(i))
        return cmd, deps

    recipe, moredeps = build_commands(tests.tests)
    buildfile.rule(
        target='test',
        deps=deps + moredeps,
        recipe=recipe,
        phony=True
    )

dir_sentinel = '.dir'
def directory_rule(buildfile):
    pattern = Pattern(os.path.join('%', dir_sentinel))
    out = qvar('@')
    buildfile.rule(
        target=pattern,
        recipe=[
            # XXX: `mkdir -p` isn't safe (or valid!) on all platforms.
            ['@mkdir', '-p', MakeFunc('patsubst', pattern, Pattern('%'), out)],
            ['@touch', out]
        ]
    )

def regenerate_rule(find_dirs, buildfile, env):
    bfgpath = Path('build.bfg', path.Root.srcdir)
    extra_deps = []

    if find_dirs:
        find.write_depfile(os.path.join(env.builddir, find.depfile_name),
                           'Makefile', find_dirs, makeify=True)
        buildfile.include(find.depfile_name)

    buildfile.rule(
        target=Path('Makefile'),
        deps=[bfgpath] + extra_deps,
        recipe=[[env.bfgpath, '--regenerate', '.']]
    )

@rule_handler('Compile')
def emit_object_file(rule, build_inputs, buildfile, env):
    compiler = rule.builder
    recipename = MakeVariable('RULE_{}'.format(compiler.name.upper()))
    global_cflags, cflags = flags_vars(
        compiler.command_var + 'FLAGS',
        compiler.global_args +
          build_inputs.global_options.get(rule.file.lang, []),
        buildfile
    )

    path = rule.target.path
    target_dir = path.parent()

    variables = {}
    cflags_value = []

    if rule.in_shared_library:
        cflags_value.extend(compiler.library_args)
    cflags_value.extend(chain.from_iterable(
        compiler.include_dir(i) for i in rule.include
    ))
    cflags_value.extend(rule.options)
    if cflags_value:
        variables[cflags] = [global_cflags] + cflags_value

    if not buildfile.has_variable(recipename):
        command_kwargs = {}
        recipe_extra = []
        if compiler.deps_flavor == 'gcc':
            command_kwargs['deps'] = deps = qvar('@') + '.d'
            recipe_extra = ['@' + env.depfixer + ' < ' + deps + ' >> ' + deps]
        elif compiler.deps_flavor == 'msvc':
            command_kwargs['deps'] = True

        buildfile.define(recipename, [
            compiler.command(
                cmd=cmd_var(compiler, buildfile), input=qvar('<'),
                output=qvar('@'), args=cflags, **command_kwargs
            ),
        ] + recipe_extra)

    buildfile.rule(
        target=path,
        deps=[rule.file] + rule.extra_deps,
        order_only=[target_dir.append(dir_sentinel)] if target_dir else None,
        recipe=recipename,
        variables=variables
    )
    buildfile.include(path.addext('.d'), optional=True)

@rule_handler('Link')
def emit_link(rule, build_inputs, buildfile, env):
    linker = rule.builder
    recipename = MakeVariable('RULE_{}'.format(linker.name.upper()))
    global_ldflags, ldflags = flags_vars(
        linker.link_var + 'FLAGS',
        linker.global_args + build_inputs.global_link_options,
        buildfile
    )

    variables = {}
    command_kwargs = {}
    ldflags_value = list(linker.mode_args)

    # Get the path for the DLL if this is a Windows build.
    path = iterutils.first(rule.target).path

    if linker.mode != 'static_library':
        ldflags_value.extend(rule.options)
        ldflags_value.extend(linker.lib_dirs(rule.libs))
        ldflags_value.extend(linker.rpath(rule.libs, path.parent()))
        ldflags_value.extend(linker.import_lib(rule.target))

        global_ldlibs, ldlibs = flags_vars(
            linker.link_var + 'LIBS', linker.global_libs, buildfile
        )
        command_kwargs['libs'] = ldlibs
        if rule.libs:
            libs = sum((linker.link_lib(i) for i in rule.libs), [])
            variables[ldlibs] = [global_ldlibs] + libs

    if ldflags_value:
        variables[ldflags] = [global_ldflags] + ldflags_value

    if not buildfile.has_variable(recipename):
        buildfile.define(recipename, [
            linker.command(
                cmd=cmd_var(linker, buildfile), input=var('1'), output=var('2'),
                args=ldflags, **command_kwargs
            )
        ])

    recipe = MakeCall(recipename, rule.files, path)
    if iterutils.isiterable(rule.target):
        target = path.addext('.stamp')
        buildfile.rule(target=rule.target, deps=[target])
        recipe = [recipe, ['@touch', var('@')]]
    else:
        target = path

    dirs = iterutils.uniques(
        i.path.parent() for i in iterutils.iterate(rule.target)
    )
    lib_deps = [i for i in rule.libs if i.creator]
    buildfile.rule(
        target=target,
        deps=rule.files + lib_deps + rule.extra_deps,
        order_only=[i.append(dir_sentinel) for i in dirs if i],
        recipe=recipe,
        variables=variables
    )

@rule_handler('Alias')
def emit_alias(rule, build_inputs, buildfile, env):
    buildfile.rule(
        target=rule.target,
        deps=rule.extra_deps,
        phony=True
    )

@rule_handler('Command')
def emit_command(rule, build_inputs, buildfile, env):
    buildfile.rule(
        target=rule.target,
        deps=rule.extra_deps,
        recipe=rule.cmds,
        phony=True
    )
