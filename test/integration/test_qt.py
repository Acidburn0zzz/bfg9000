from . import *


@skip_if(env.host_platform.family == 'windows', 'not supported on windows yet')
class TestQt(IntegrationTest):
    def run_executable(self, exe):
        if env.host_platform.genus == 'linux':
            output = self.assertPopen([exe], env={'DISPLAY': ''},
                                      returncode='fail')
            self.assertRegex(output,
                             r'QXcbConnection: Could not connect to display')

    def __init__(self, *args, **kwargs):
        super().__init__(os.path.join(examples_dir, '13_qt'), env={
            'CPPFLAGS': '-Wno-inconsistent-missing-override',
        }, *args, **kwargs)

    def test_designer(self):
        self.build('qt-designer')
        self.run_executable(executable('qt-designer'))

    def test_qml(self):
        self.build('qt-qml')
        self.run_executable(executable('qt-qml'))
