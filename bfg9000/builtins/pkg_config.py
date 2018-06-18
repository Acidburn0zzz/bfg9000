import warnings
from collections import Counter, defaultdict
from itertools import chain
from six import iteritems, itervalues, string_types

from . import builtin
from .. import path
from .file_types import generated_file
from .install import can_install
from ..build_inputs import build_input
from ..file_types import *
from ..iterutils import flatten, iterate, uniques, isiterable, recursive_walk
from ..objutils import objectify
from ..safe_str import literal, shell_literal
from ..shell import posix as pshell
from ..shell.syntax import Syntax, Writer
from ..tools.pkg_config import PkgConfigPackage
from ..versioning import simplify_specifiers, Specifier, SpecifierSet

build_input('pkg_config')(lambda build_inputs, env: [])


class Requirement(object):
    def __init__(self, name, version=None):
        self.name = name
        self.version = objectify(version or '', SpecifierSet)

    def __and__(self, rhs):
        result = Requirement(self.name, self.version)
        result &= rhs
        return result

    def __iand__(self, rhs):
        if self.name != rhs.name:
            raise ValueError('requirement names do not match')
        self.version = self.version & rhs.version
        return self

    def __eq__(self, rhs):
        return (type(self) == type(rhs) and self.name == rhs.name and
                self.version == rhs.version)

    def split(self, single=False):
        specs = simplify_specifiers(self.version)
        if len(specs) == 0:
            return [SimpleRequirement(self.name)]
        if single and len(specs) > 1:
            raise ValueError(
                ("multiple specifiers ({}) used in pkg-config requirement " +
                 "for '{}'").format(self.version, self.name)
            )
        return [SimpleRequirement(self.name, i) for i in specs]

    def __hash__(self):
        return hash((self.name, self.version))

    def __repr__(self):
        return '<Requirement({!r})>'.format(self._string())

    def _string(self):  # pragma: no cover
        return self.name + str(self.version)


class SimpleRequirement(object):
    def __init__(self, name, version=None):
        self.name = name
        self.version = (None if version is None else
                        objectify(version, Specifier))

    def __eq__(self, rhs):
        return (type(self) == type(rhs) and self.name == rhs.name and
                self.version == rhs.version)

    def _safe_str(self):
        if not self.version:
            return shell_literal(self.name)
        op = self.version.operator
        if op == '==':
            op = '='
        return shell_literal('{name} {op} {version}'.format(
            name=self.name, op=op, version=self.version.version
        ))

    def __hash__(self):
        return hash((self.name, self.version))

    def __repr__(self):
        return '<SimpleRequirement({!r})>'.format(self._string())

    def _string(self):  # pragma: no cover
        return self.name + str(self.version)


class RequirementSet(object):
    def __init__(self, iterable=None):
        self._reqs = {}
        if iterable:
            for i in iterable:
                self.add(i)

    def add(self, item):
        if item.name not in self._reqs:
            self._reqs[item.name] = item
        else:
            self._reqs[item.name] &= item

    def remove(self, name):
        del self._reqs[name]

    def update(self, other):
        for i in other:
            self.add(i)

    def merge_from(self, other):
        items = list(other)
        for i in items:
            if i.name in self._reqs:
                self._reqs[i.name] &= i
                other.remove(i.name)

    def split(self, single=False):
        return sorted(flatten(i.split(single) for i in self),
                      key=lambda x: x.name)

    def __iter__(self):
        return itervalues(self._reqs)

    def __repr__(self):
        return '<RequirementSet({!r})>'.format(
            [i._string() for i in iter(self)]
        )


class PkgConfigInfo(object):
    directory = path.Path('pkgconfig')

    class _simple_property(object):
        def __init__(self, fn):
            self.fn = fn

        def __get__(self, obj, objtype=None):
            if obj is None:
                return self
            return getattr(obj, '_' + self.fn.__name__)

        def __set__(self, obj, value):
            setattr(obj, '_' + self.fn.__name__, self.fn(obj, value))

    def __init__(self, builtins, name=None, desc_name=None, desc=None,
                 url=None, version=None, requires=None, requires_private=None,
                 conflicts=None, includes=None, libs=None, libs_private=None,
                 options=None, link_options=None, link_options_private=None,
                 lang='c', auto_fill=True):
        self._builtins = builtins
        self.auto_fill = auto_fill

        self.name = name
        self.desc_name = desc_name
        self.desc = desc
        self.url = url
        self.version = version
        self.lang = lang

        self.requires = requires
        self.requires_private = requires_private
        self.conflicts = conflicts

        self.includes = includes
        self.libs = libs
        self.libs_private = libs_private
        self.options = pshell.listify(options)
        self.link_options = pshell.listify(link_options)
        self.link_options_private = pshell.listify(link_options_private)

    @property
    def output(self):
        return PkgConfigPcFile(self.directory.append(self.name + '.pc'))

    @_simple_property
    def includes(self, value):
        return uniques(self._builtins['header_directory'](i)
                       for i in iterate(value)) if value is not None else None

    @_simple_property
    def libs(self, value):
        return (uniques(self._library(i) for i in iterate(value))
                if value is not None else None)

    @_simple_property
    def libs_private(self, value):
        return (uniques(self._library(i) for i in iterate(value))
                if value is not None else None)

    @_simple_property
    def requires(self, value):
        return (self._filter_packages(iterate(value))
                if value is not None else None)

    @_simple_property
    def requires_private(self, value):
        return (self._filter_packages(iterate(value))
                if value is not None else None)

    @_simple_property
    def conflicts(self, value):
        return (self._filter_packages(iterate(value))[0]
                if value is not None else None)

    def _library(self, lib):
        if isinstance(lib, DualUseLibrary):
            return lib
        return self._builtins['library'](lib)

    def _write_variable(self, out, name, value):
        out.write(name, Syntax.variable)
        out.write_literal('=')
        out.write(value, Syntax.variable)
        out.write_literal('\n')

    def _write_field(self, out, name, value, syntax=Syntax.variable, **kwargs):
        if value:
            out.write(name, Syntax.variable)
            out.write_literal(': ')
            out.write_each(iterate(value), syntax, **kwargs)
            out.write_literal('\n')

    def write(self, out, env):
        def pkg_installify(f):
            return installify(f, destdir=False, absolute_ok=True)

        data = self._process_inputs()
        out = Writer(out)

        pkg = CommonPackage(
            None, None, syntax='cc', raw_static=False,
            includes=[pkg_installify(i) for i in data['includes']],
            libs=[pkg_installify(i.all[0]) for i in data['libs']],
            **data['extra_fields']
        )
        pkg_private = CommonPackage(
            None, None, syntax='cc', raw_static=False,
            libs=[pkg_installify(i.all[0]) for i in data['libs_private']],
            **data['extra_fields_private']
        )

        builder = env.builder(self.lang)
        cflags = pkg.compile_options(builder.compiler, None)

        linker = builder.linker('executable')
        ldflags = pkg.link_options(linker, None) + pkg.link_libs(linker, None)
        ldflags_private = (pkg_private.link_options(linker, None) +
                           pkg_private.link_libs(linker, None))

        for i in path.InstallRoot:
            if i != path.InstallRoot.bindir:
                self._write_variable(out, i.name, env.install_dirs[i])

        out.write_literal('\n')

        self._write_field(out, 'Name', data['desc_name'])
        self._write_field(out, 'Description', data['desc'])
        self._write_field(out, 'URL', data['url'])
        self._write_field(out, 'Version', data['version'])
        self._write_field(out, 'Requires', data['requires'], Syntax.shell,
                          delim=literal(', '))
        self._write_field(out, 'Requires.private', data['requires_private'],
                          Syntax.shell, delim=literal(', '))
        self._write_field(out, 'Conflicts', data['conflicts'],
                          Syntax.shell, delim=literal(', '))
        self._write_field(out, 'Cflags', cflags + data['cflags'], Syntax.shell)
        self._write_field(out, 'Libs', ldflags + data['ldflags'], Syntax.shell)
        self._write_field(out, 'Libs.private', ldflags_private +
                          data['ldflags_private'], Syntax.shell)

    def _process_inputs(self):
        result = {
            'name': self.name,
            'desc_name': self.desc_name or self.name,
            'url': self.url,
            'version': self.version,
        }
        result['desc'] = self.desc or '{} library'.format(result['desc_name'])

        includes = self.includes or []
        libs = self.libs or []
        libs_private = self.libs_private or []
        requires, extra = self.requires or [RequirementSet(), []]
        requires_private, extra_private = (self.requires_private or
                                           [RequirementSet(), []])
        conflicts = self.conflicts or RequirementSet()

        fwd_ldflags = flatten(
            i.forward_opts['options'] if hasattr(i, 'forward_opts') else []
            for i in chain(libs, libs_private)
        )

        # Add all the (unique) dependent libs to libs_private, unless they're
        # already in libs.
        fwd = chain.from_iterable(
            i.forward_opts['libs'] if hasattr(i, 'forward_opts') else []
            for i in chain(libs, libs_private)
        )
        libs_private = uniques(chain(
            (i for i in fwd if i not in libs), libs_private
        ))

        # Get the package dependencies for all the libs (public and private)
        # that were passed in.
        auto_requires, auto_extra = self._filter_packages(chain.from_iterable(
            recursive_walk(i, 'package_deps', 'install_deps')
            for i in chain(libs, libs_private)
        ))

        requires_private.update(auto_requires)
        requires.merge_from(requires_private)

        result['requires'] = requires.split(single=True)
        result['requires_private'] = requires_private.split(single=True)
        result['conflicts'] = conflicts.split()

        result['includes'] = includes
        result['libs'] = libs
        result['libs_private'] = libs_private
        result['extra_fields'] = {}
        result['extra_fields_private'] = {}

        self._process_packages(result, extra)
        self._process_packages(result, chain(extra_private, auto_extra),
                               private=True)

        result['cflags'] = self.options
        result['ldflags'] = self.link_options
        result['ldflags_private'] = fwd_ldflags + self.link_options_private

        return result

    @staticmethod
    def _process_packages(result, pkgs, private=False):
        # Add the options from each of the system packages (.includes, .libs,
        # and occasionally .lib_dirs).
        def key(x):
            return x + '_private' if private else x

        extra = result[key('extra_fields')]
        for i in pkgs:
            for k, v in iteritems(i.all_options):
                if k == 'includes':
                    if not private:
                        result[k].extend(v)
                if k == 'libs':
                    result[key(k)].extend(v)
                elif k == 'pthread':
                    extra[k] = v or extra.get(k, False)
                elif isiterable(v):
                    if k not in v:
                        extra[k] = []
                    extra[k].extend(v)
                else:
                    warnings.warn('unhandled package option {!r}'.format(k))

    @staticmethod
    def _filter_packages(packages):
        pkg_config = RequirementSet()
        system = []
        for i in packages:
            if isinstance(i, string_types):
                pkg_config.add(Requirement(i))
            elif isinstance(i, (tuple, list)):
                pkg_config.add(Requirement(*i))
            elif isinstance(i, PkgConfigPackage):
                pkg_config.add(Requirement(i.name, i.specifier))
            elif isinstance(i, CommonPackage):
                system.append(i)
            else:
                raise TypeError('unsupported package type: {}'.format(type(i)))
        return pkg_config, uniques(system)


@builtin.function('builtins', 'build_inputs', 'env')
def pkg_config(builtins, build, env, name=None, **kwargs):
    if can_install(env):
        build['pkg_config'].append(PkgConfigInfo(builtins, name, **kwargs))


@builtin.post('builtins', 'build_inputs', 'env')
def finalize_pkg_config(builtins, build, env):
    install = build['install']
    defaults = {
        'name': build['project'].name,
        'version': build['project'].version or '0.0',
        'includes': [i for i in install
                     if isinstance(i, (HeaderFile, HeaderDirectory))],
        # Get all the explicitly-installed libraries, fetching the
        # DualUseLibrary (i.e. the `parent`) if applicable.
        'libs': uniques(getattr(i, 'parent', i) for i in install.explicit
                        if isinstance(i, Library)),
    }

    for info in build['pkg_config']:
        if not info.auto_fill:
            continue
        for key, value in iteritems(defaults):
            if getattr(info, key) is None:
                setattr(info, key, value)

    # Make sure we don't have any duplicate pkg-config packages.
    dupes = Counter(i.name for i in build['pkg_config'])
    for name, count in iteritems(dupes):
        if count > 1:
            raise ValueError("duplicate pkg-config package '{}'".format(name))

    for info in build['pkg_config']:
        with generated_file(build, env, info.output) as out:
            info.write(out, env)
            builtins['install'](info.output)
