import os.path
import re

from .utils import library_macro
from ..file_types import *
from ..iterutils import iterate, listify, uniques
from ..path import Root
from ..platforms import platform_name


class CcCompiler(object):
    def __init__(self, env, lang, name, command, cflags):
        self.platform = env.platform
        self.lang = lang

        self.rule_name = self.command_var = name
        self.command = command

        self.global_args = cflags

    @property
    def flavor(self):
        return 'cc'

    @property
    def deps_flavor(self):
        return 'gcc'

    def __call__(self, cmd, input, output, deps=None, args=None):
        result = [cmd]
        result.extend(iterate(args))
        result.extend(['-c', input])
        if deps:
            result.extend(['-MMD', '-MF', deps])
        result.extend(['-o', output])
        return result

    def output_file(self, name):
        return ObjectFile(name + '.o', Root.builddir, self.lang)

    def include_dir(self, directory):
        if directory.system:
            return ['-isystem' + directory.path]
        else:
            return ['-I' + directory.path]

    def link_args(self, name, mode):
        if mode == 'executable':
            return []
        elif mode in ['shared_library', 'static_library']:
            args = ['-fPIC']
            if self.platform.has_import_library:
                args.append('-D' + library_macro(name, mode))
            return args
        else:
            raise ValueError("unknown mode '{}'".format(mode))


class CcLinker(object):
    def __init__(self, env, mode, lang, name, command, ldflags, ldlibs):
        self.env = env
        self.mode = mode
        self.lang = lang

        self.rule_name = 'link_' + name
        self.command_var = name
        self.command = command
        self.link_var = 'ld'

        self.global_args = ldflags
        self.global_libs = ldlibs

        # Create a regular expression to extract the library name for linking
        # with -l. TODO: Support .lib as an extension on Windows/Cygwin?
        exts = [r'\.a']
        if not self.platform.has_import_library:
            exts.append(re.escape(self.platform.shared_library_ext))
        self._lib_re = re.compile('lib(.*)(?:' + '|'.join(exts) + ')$')

    @property
    def platform(self):
        return self.env.platform

    @property
    def flavor(self):
        return 'cc'

    def __call__(self, cmd, input, output, libs=None, args=None):
        result = [cmd]
        result.extend(iterate(args))
        result.extend(iterate(input))
        result.extend(iterate(libs))
        result.extend(['-o', output])
        return result

    @property
    def post_install(self):
        if self.platform.has_rpath:
            return self.env.tool('patchelf')
        return None

    @property
    def auto_link(self):
        return False

    def output_file(self, name):
        if self.mode == 'executable':
            return Executable(
                name + self.platform.executable_ext, Root.builddir, self.lang
            )
        elif self.mode == 'shared_library':
            head, tail = os.path.split(name)

            def lib(prefix='lib'):
                return os.path.join(
                    head, prefix + tail + self.platform.shared_library_ext
                )

            if self.platform.has_import_library:
                dllprefix = 'cyg' if self.platform.name == 'cygwin' else 'lib'
                return DllLibrary(lib(dllprefix), lib() + '.a', Root.builddir,
                                  self.lang)
            else:
                return SharedLibrary(lib(), Root.builddir, self.lang)
        else:
            raise ValueError("unknown mode '{}'".format(self.mode))

    @property
    def mode_args(self):
        return ['-shared', '-fPIC'] if self.mode == 'shared_library' else []

    def lib_dirs(self, libraries, target):
        def get_dir(lib):
            return lib.path.parent() if isinstance(lib, Library) else lib

        libraries = listify(libraries)
        dirs = uniques(get_dir(i) for i in iterate(libraries)
                       if not isinstance(i, StaticLibrary))
        result = ['-L' + i for i in dirs]

        if self.platform.has_rpath:
            start = target.path.parent()
            paths = uniques(i.path.parent().relpath(start) for i in libraries
                            if isinstance(i, SharedLibrary))
            if paths:
                base = '$ORIGIN'
                result.append('-Wl,-rpath={}'.format( ':'.join(
                    base if i == '.' else os.path.join(base, i) for i in paths
                ) ))

        return result

    def link_lib(self, library):
        if isinstance(library, WholeArchive):
            if platform_name() == 'darwin':
                return ['-Wl,-force_load', library.link.path]
            return ['-Wl,--whole-archive', library.link.path,
                    '-Wl,--no-whole-archive']
        elif isinstance(library, StaticLibrary):
            return [library.link.path]

        # If we're here, we have a SharedLibrary.
        lib_name = library.link.path.basename()
        m = self._lib_re.match(lib_name)
        if not m:
            raise ValueError("'{}' is not a valid library".format(lib_name))
        return ['-l' + m.group(1)]

    def import_lib(self, library):
        if self.platform.has_import_library and self.mode == 'shared_library':
            return ['-Wl,--out-implib=' + library.import_lib.path]
        return []