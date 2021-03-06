from unittest import mock

from .common import BuiltinTest

from bfg9000.builtins import default, install  # noqa
from bfg9000.file_types import Executable, Phony
from bfg9000.path import Path, Root, InstallRoot


class TestInstall(BuiltinTest):
    def test_install_none(self):
        self.assertEqual(self.context['install'](), None)
        self.assertEqual(self.build['install'].explicit, [])
        self.assertEqual(self.build['install'].implicit, [])

    def test_install_single(self):
        exe = Executable(Path('exe', Root.srcdir), None)
        installed = Executable(Path('exe', InstallRoot.bindir), None)
        self.assertEqual(self.context['install'](exe), installed)
        self.assertEqual(self.build['install'].explicit, [exe])
        self.assertEqual(self.build['install'].implicit, [exe])

    def test_install_multiple(self):
        exe1 = Executable(Path('exe1', Root.srcdir), None)
        exe2 = Executable(Path('exe2', Root.srcdir), None)
        installed1 = Executable(Path('exe1', InstallRoot.bindir), None)
        installed2 = Executable(Path('exe2', InstallRoot.bindir), None)
        self.assertEqual(self.context['install'](exe1, exe2),
                         (installed1, installed2))
        self.assertEqual(self.build['install'].explicit, [exe1, exe2])
        self.assertEqual(self.build['install'].implicit, [exe1, exe2])

    def test_install_nested_multiple(self):
        exe1 = Executable(Path('exe1', Root.srcdir), None)
        exe2 = Executable(Path('exe2', Root.srcdir), None)
        installed1 = Executable(Path('exe1', InstallRoot.bindir), None)
        installed2 = Executable(Path('exe2', InstallRoot.bindir), None)
        self.assertEqual(self.context['install'](exe1, [exe2], None),
                         (installed1, [installed2], None))
        self.assertEqual(self.build['install'].explicit, [exe1, exe2])
        self.assertEqual(self.build['install'].implicit, [exe1, exe2])

    def test_install_add_to_default(self):
        exe = Executable(Path('exe', Root.srcdir), None)
        exe.creator = 'creator'
        installed = Executable(Path('exe', InstallRoot.bindir), None)
        self.assertEqual(self.context['install'](exe), installed)
        self.assertEqual(self.build['install'].explicit, [exe])
        self.assertEqual(self.build['install'].implicit, [exe])
        self.assertEqual(self.build['defaults'].outputs, [exe])

    def test_invalid(self):
        phony = Phony('name')
        self.assertRaises(TypeError, self.context['install'], phony)

        exe = Executable(Path('/path/to/exe', Root.absolute), None)
        self.assertRaises(ValueError, self.context['install'], exe)

    def test_cant_install(self):
        with mock.patch('bfg9000.builtins.install.can_install',
                        return_value=False), \
             mock.patch('warnings.warn') as m:  # noqa
            exe = Executable(Path('exe', Root.srcdir), None)
            installed = Executable(Path('exe', InstallRoot.bindir), None)
            self.assertEqual(self.context['install'](exe), installed)
            self.assertEqual(m.call_count, 1)
