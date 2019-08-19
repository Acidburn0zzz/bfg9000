import mock
from collections import namedtuple
from six import iteritems

from .common import AttrDict, BuiltinTest
from bfg9000 import file_types
from bfg9000.builtins import compile, link  # noqa
from bfg9000.environment import LibraryMode
from bfg9000.iterutils import listify, unlistify
from bfg9000.path import Path, Root

MockCompile = namedtuple('MockCompile', ['file'])


class CompileTest(BuiltinTest):
    def output_file(self, name, context={}, lang='c++', mode=None, extra={}):
        compiler = getattr(self.env.builder(lang), mode or self.mode)
        context = AttrDict(**context)

        output = compiler.output_file(name, context)
        public_output = compiler.post_build(self.build, [], output, context)

        result = [i for i in listify(public_output or output) if not i.private]
        for i in result:
            for k, v in iteritems(extra):
                setattr(i, k, v)
        return unlistify(result)


class TestObjectFile(CompileTest):
    mode = 'compiler'

    def test_identity(self):
        expected = file_types.ObjectFile(Path('object', Root.srcdir), None)
        self.assertIs(self.builtin_dict['object_file'](expected), expected)

    def test_src_file(self):
        expected = file_types.ObjectFile(
            Path('object', Root.srcdir),
            self.env.target_platform.object_format, 'c'
        )
        self.assertSameFile(self.builtin_dict['object_file']('object'),
                            expected)

    def test_make_simple(self):
        result = self.builtin_dict['object_file'](file='main.cpp')
        self.assertSameFile(result, self.output_file('main'))

        result = self.builtin_dict['object_file']('object', 'main.cpp')
        self.assertSameFile(result, self.output_file('object'))

        src = self.builtin_dict['source_file']('main.cpp')
        result = self.builtin_dict['object_file']('object', src)
        self.assertSameFile(result, self.output_file('object'))

    def test_make_no_lang(self):
        result = self.builtin_dict['object_file']('object', 'main.goofy',
                                                  lang='c++')
        self.assertSameFile(result, self.output_file('object'))

        self.assertRaises(ValueError, self.builtin_dict['object_file'],
                          'object', 'main.goofy')

        src = self.builtin_dict['source_file']('main.goofy')
        self.assertRaises(ValueError, self.builtin_dict['object_file'],
                          'object', src)

    def test_make_override_lang(self):
        src = self.builtin_dict['source_file']('main.c', 'c')
        result = self.builtin_dict['object_file']('object', src, lang='c++')
        self.assertSameFile(result, self.output_file('object'))
        self.assertEqual(result.creator.compiler.lang, 'c++')

    def test_includes(self):
        object_file = self.builtin_dict['object_file']

        result = object_file(file='main.cpp', includes='include')
        self.assertEqual(result.creator.includes, [
            file_types.HeaderDirectory(Path('include', Root.srcdir))
        ])

        hdr = self.builtin_dict['header_file']('include/main.hpp')
        result = object_file(file='main.cpp', includes=hdr)
        self.assertEqual(result.creator.includes, [
            file_types.HeaderDirectory(Path('include', Root.srcdir))
        ])

    def test_libs(self):
        self.env.library_mode = LibraryMode(True, False)

        result = self.builtin_dict['object_file'](file='main.java', libs='lib')
        self.assertEqual(result.creator.libs, [
            file_types.StaticLibrary(Path('lib', Root.srcdir), 'java')
        ])

    def test_pch(self):
        pch = file_types.PrecompiledHeader(Path('pch', Root.builddir), 'c')
        pch.object_file = 'foo'

        result = self.builtin_dict['object_file'](file='main.cpp', pch=pch)
        self.assertIs(result.creator.pch, pch)

        self.assertRaises(TypeError, self.builtin_dict['object_file'],
                          file='main.java', pch=pch)

    def test_make_no_name_or_file(self):
        self.assertRaises(TypeError, self.builtin_dict['object_file'])

    def test_description(self):
        result = self.builtin_dict['object_file'](
            file='main.cpp', description='my description'
        )
        self.assertEqual(result.creator.description, 'my description')


class TestPrecompiledHeader(CompileTest):
    class MockFile(object):
        def write(self, data):
            pass

    mode = 'pch_compiler'
    context = {'pch_source':
               file_types.SourceFile(Path('main.cpp', Root.srcdir), 'c++')}

    def test_identity(self):
        ex = file_types.PrecompiledHeader(Path('header', Root.srcdir), None)
        self.assertIs(self.builtin_dict['precompiled_header'](ex), ex)

    def test_src_file(self):
        expected = file_types.PrecompiledHeader(
            Path('header', Root.srcdir), 'c'
        )
        self.assertSameFile(self.builtin_dict['precompiled_header']('header'),
                            expected)

    def test_make_simple(self):
        with mock.patch('bfg9000.builtins.file_types.generated_file',
                        return_value=self.MockFile()):
            pch = self.builtin_dict['precompiled_header']

            result = pch(file='main.hpp')
            self.assertSameFile(result, self.output_file(
                'main.hpp', self.context
            ))

            result = pch('object', 'main.hpp')
            self.assertSameFile(result, self.output_file(
                'object', self.context
            ))

            src = self.builtin_dict['header_file']('main.hpp')
            result = pch('object', src)
            self.assertSameFile(result, self.output_file(
                'object', self.context
            ))

    def test_make_no_lang(self):
        with mock.patch('bfg9000.builtins.file_types.generated_file',
                        return_value=self.MockFile()):
            pch = self.builtin_dict['precompiled_header']

            result = pch('object', 'main.goofy', lang='c++')
            self.assertSameFile(result, self.output_file(
                'object', self.context
            ))
            self.assertRaises(ValueError, pch, 'object', 'main.goofy')

            src = self.builtin_dict['header_file']('main.goofy')
            self.assertRaises(ValueError, pch, 'object', src)

    def test_make_override_lang(self):
        with mock.patch('bfg9000.builtins.file_types.generated_file',
                        return_value=self.MockFile()):
            pch = self.builtin_dict['precompiled_header']

            src = self.builtin_dict['header_file']('main.h', 'c')
            result = pch('object', src, lang='c++')
            self.assertSameFile(result, self.output_file(
                'object', self.context
            ))
            self.assertEqual(result.creator.compiler.lang, 'c++')

    def test_make_no_name_or_file(self):
        self.assertRaises(TypeError, self.builtin_dict['precompiled_header'])

    def test_description(self):
        result = self.builtin_dict['precompiled_header'](
            file='main.hpp', description='my description'
        )
        self.assertEqual(result.creator.description, 'my description')


class TestObjectFiles(BuiltinTest):
    def make_object_files(self, make_src=False):
        files = [file_types.ObjectFile(Path(i, Root.srcdir), None)
                 for i in ['obj1', 'obj2']]
        if make_src:
            src_files = [file_types.SourceFile(Path(i, Root.srcdir), None)
                         for i in ['src1', 'src2']]
            for f, s in zip(files, src_files):
                f.creator = MockCompile(s)

        obj_files = self.builtin_dict['object_files'](files)

        if make_src:
            return obj_files, files, src_files
        return obj_files, files

    def test_initialize(self):
        obj_files, files = self.make_object_files()
        self.assertEqual(list(obj_files), files)

    def test_getitem_index(self):
        obj_files, files = self.make_object_files()
        self.assertEqual(obj_files[0], files[0])

    def test_getitem_string(self):
        obj_files, files, src_files = self.make_object_files(True)
        self.assertEqual(obj_files['src1'], files[0])

    def test_getitem_path(self):
        obj_files, files, src_files = self.make_object_files(True)
        self.assertEqual(obj_files[src_files[0].path], files[0])

    def test_getitem_file(self):
        obj_files, files, src_files = self.make_object_files(True)
        self.assertEqual(obj_files[src_files[0]], files[0])

    def test_getitem_not_found(self):
        obj_files, files, src_files = self.make_object_files(True)
        self.assertRaises(IndexError, lambda: obj_files[2])
        self.assertRaises(IndexError, lambda: obj_files['src3'])
        self.assertRaises(IndexError, lambda: obj_files[Path(
            'src3', Root.srcdir
        )])
