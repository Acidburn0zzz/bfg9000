import os
from . import *

from bfg9000 import shell

is_mingw = (env.host_platform.family == 'windows' and
            env.builder('c++').flavor == 'cc')
is_msvc = env.builder('c++').flavor == 'msvc'
pkg_config_cmd = os.getenv('PKG_CONFIG', 'pkg-config')


def pkg_config(args, path='pkgconfig'):
    env = os.environ.copy()
    env['PKG_CONFIG_PATH'] = os.path.abspath(path)
    return shell.execute([pkg_config_cmd] + args, stdout=shell.Mode.pipe,
                         env=env).rstrip()


def readPcFile(filename, field):
    with open(filename) as f:
        for line in f:
            if line.startswith(field + ':'):
                return line[len(field) + 1:].strip()
    raise ValueError('unable to find {!r} field'.format(field))


@skip_if_backend('msbuild')
@skip_if(is_mingw, 'no libogg on mingw (yet)')
class TestPkgConfig(IntegrationTest):
    def __init__(self, *args, **kwargs):
        super().__init__(os.path.join(examples_dir, '12_pkg_config'),
                         configure=False, install=True, *args, **kwargs)

    def test_configure_default(self):
        self.configure()
        self.assertExists(os.path.join('pkgconfig', 'hello.pc'))

        if env.host_platform.genus == 'linux':
            self.assertEqual(pkg_config(['hello', '--print-requires']), '')
            self.assertEqual(pkg_config(['hello', '--print-requires-private']),
                             'ogg')
        self.assertEqual(pkg_config(['hello', '--libs-only-l']), '-lhello')
        self.assertEqual(pkg_config(['hello', '--libs-only-l', '--static']),
                         '-lhello -logg')

        self.assertEqual(pkg_config(['hello', '--libs-only-other']), '')

    # Dual-use libraries collide on MSVC.
    @skip_if(is_msvc, hide=True)
    def test_configure_dual(self):
        self.configure(extra_args=['--enable-shared', '--enable-static'])

        hello = os.path.join('pkgconfig', 'hello.pc')
        self.assertExists(hello)
        self.assertEqual(readPcFile(hello, 'Libs'), "-L'${libdir}' -lhello")

        if env.host_platform.genus == 'linux':
            self.assertEqual(pkg_config(['hello', '--print-requires']), '')
            self.assertEqual(pkg_config(['hello', '--print-requires-private']),
                             'ogg')
        self.assertEqual(pkg_config(['hello', '--libs-only-l']), '-lhello')
        self.assertEqual(pkg_config(['hello', '--libs-only-l', '--static']),
                         '-lhello -linner -logg')

        self.assertEqual(pkg_config(['hello', '--libs-only-other']), '')

    def test_configure_static(self):
        self.configure(extra_args=['--disable-shared', '--enable-static'])
        self.assertExists(os.path.join('pkgconfig', 'hello.pc'))

        if env.host_platform.genus == 'linux':
            self.assertEqual(pkg_config(['hello', '--print-requires']), '')
            self.assertEqual(pkg_config(['hello', '--print-requires-private']),
                             'ogg')
        self.assertEqual(pkg_config(['hello', '--libs-only-l']), '-lhello')
        self.assertEqual(pkg_config(['hello', '--libs-only-l', '--static']),
                         '-lhello -linner -logg')

        self.assertEqual(pkg_config(['hello', '--libs-only-other']), '')

    def test_configure_using_system_pkg(self):
        self.configure(env={'PKG_CONFIG': 'nonexist'})
        self.assertExists(os.path.join('pkgconfig', 'hello.pc'))

        self.assertEqual(pkg_config(['hello', '--print-requires']), '')
        self.assertEqual(pkg_config(['hello', '--print-requires-private']), '')
        self.assertEqual(pkg_config(['hello', '--libs-only-l']), '-lhello')
        self.assertEqual(pkg_config(['hello', '--libs-only-l', '--static']),
                         '-lhello -logg')

        self.assertEqual(pkg_config(['hello', '--libs-only-other']), '')

    def test_install(self):
        self.configure()
        self.build('install')

        extra = []
        if env.target_platform.has_import_library:
            extra = [os.path.join(self.libdir, import_library('hello').path)]

        self.assertDirectory(self.installdir, [
            os.path.join(self.includedir, 'hello.hpp'),
            os.path.join(self.libdir, shared_library('hello').path),
            os.path.join(self.libdir, shared_library('inner').path),
            os.path.join(self.libdir, 'pkgconfig', 'hello.pc'),
        ] + extra)

        self.configure(srcdir='pkg_config_use', installdir=None, env={
            'PKG_CONFIG_PATH': os.path.join(self.libdir, 'pkgconfig')
        })
        self.build()

        env_vars = None
        if env.target_platform.family == 'windows':
            env_vars = {'PATH': (os.path.abspath(self.libdir) +
                                 os.pathsep + os.environ['PATH'])}
        self.assertOutput([executable('program')], 'hello, library!\n',
                          env=env_vars)


@skip_if_backend('msbuild')
@skip_if(is_mingw, 'no libogg on mingw (yet)')
class TestPkgConfigAuto(IntegrationTest):
    def __init__(self, *args, **kwargs):
        super().__init__('pkg_config_auto', configure=False, install=True,
                         *args, **kwargs)

    def test_configure_default(self):
        self.configure()
        self.assertExists(os.path.join('pkgconfig', 'hello.pc'))

        self.assertEqual(pkg_config(['hello', '--libs-only-l']), '-lhello')
        self.assertEqual(pkg_config(['hello', '--libs-only-l', '--static']),
                         '-lhello -logg')

        self.assertEqual(pkg_config(['hello', '--libs-only-other']), '')

    # Dual-use libraries collide on MSVC.
    @skip_if(is_msvc, hide=True)
    def test_configure_dual(self):
        self.configure(extra_args=['--enable-shared', '--enable-static'])

        hello = os.path.join('pkgconfig', 'hello.pc')
        self.assertExists(hello)
        self.assertEqual(readPcFile(hello, 'Libs'), "-L'${libdir}' -lhello")

        self.assertEqual(pkg_config(['hello', '--libs-only-l']), '-lhello')
        self.assertEqual(pkg_config(['hello', '--libs-only-l', '--static']),
                         '-lhello -linner -logg')

        self.assertEqual(pkg_config(['hello', '--libs-only-other']), '')

    def test_configure_static(self):
        self.configure(extra_args=['--disable-shared', '--enable-static'])
        self.assertExists(os.path.join('pkgconfig', 'hello.pc'))

        self.assertEqual(pkg_config(['hello', '--libs-only-l']), '-lhello')
        self.assertEqual(pkg_config(['hello', '--libs-only-l', '--static']),
                         '-lhello -linner -logg')

        self.assertEqual(pkg_config(['hello', '--libs-only-other']), '')

    def test_install(self):
        pjoin = os.path.join
        self.configure()
        self.build('install')

        extra = []
        if env.target_platform.has_import_library:
            extra.append(pjoin(self.libdir, import_library('hello').path))

        if env.target_platform.has_versioned_library:
            extra.extend([
                pjoin(self.libdir, shared_library('hello', '1.2.3').path),
                pjoin(self.libdir, shared_library('hello', '1').path),
                pjoin(self.libdir, shared_library('inner', '1.2.3').path),
                pjoin(self.libdir, shared_library('inner', '1').path),
            ])
        else:
            extra.append(pjoin(self.libdir, shared_library('inner').path))

        self.assertDirectory(self.installdir, [
            pjoin(self.includedir, 'hello.hpp'),
            pjoin(self.libdir, shared_library('hello').path),
            pjoin(self.libdir, 'pkgconfig', 'hello.pc'),
        ] + extra)

        self.configure(srcdir='pkg_config_use', installdir=None, env={
            'PKG_CONFIG_PATH': pjoin(self.libdir, 'pkgconfig')
        })
        self.build()

        env_vars = None
        if env.target_platform.family == 'windows':
            env_vars = {'PATH': (os.path.abspath(self.libdir) +
                                 os.pathsep + os.environ['PATH'])}
        self.assertOutput([executable('program')], 'hello, library!\n',
                          env=env_vars)
