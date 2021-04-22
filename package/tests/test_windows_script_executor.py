from unittest import TestCase
from mock import patch, Mock

from cloudshell.cm.customscript.domain.script_configuration import HostConfiguration
from cloudshell.cm.customscript.domain.script_executor import ErrorMsg
from cloudshell.cm.customscript.domain.script_file import ScriptFile
from cloudshell.cm.customscript.domain.windows_script_executor import WindowsScriptExecutor
from tests.helpers import Any


class TestWindowsScriptExecutor(TestCase):

    def setUp(self):
        self.logger = Mock()
        self.session = Mock()
        self.session_ctor = Mock()
        self.cancel_sampler = Mock()
        self.host = HostConfiguration()
        self.host.username = 'admin'
        self.host.password = '1234'
        self.host.ip = "1.2.3.4"

        self.session_patcher = patch('cloudshell.cm.customscript.domain.windows_script_executor.winrm.Session')
        self.session_ctor = self.session_patcher.start()
        self.session_ctor.return_value = self.session


    def tearDown(self):
        self.session_patcher.stop()

    def test_http(self):
        self.host.parameters['winrm_transport'] = 'http'
        WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session_ctor.assert_called_with('1.2.3.4', auth=('admin','1234'))

    def test_http_fallback(self):
        WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session_ctor.assert_called_with('1.2.3.4', auth=('admin','1234'), transport='ssl', server_cert_validation='ignore')

    def test_https(self):
        self.host.parameters['winrm_transport'] = 'ssl'
        WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session_ctor.assert_called_with('1.2.3.4', auth=('admin','1234'), transport='ssl', server_cert_validation='ignore')

    # Create temp folder

    def test_create_temp_folder_success(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session.protocol.get_command_output = Mock(return_value=(b'tmp123', b'', 0))
        result = executor.create_temp_folder()
        self.assertEqual('tmp123', result)

    def test_create_temp_folder_fail(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session.protocol.get_command_output = Mock(return_value=(b'', b'some error', 1))
        with self.assertRaises(Exception) as e:
            executor.create_temp_folder()
        self.assertEqual(ErrorMsg.CREATE_TEMP_FOLDER % 'some error', str(e.exception))

    # Copy script

    def test_copy_script_success(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session.protocol.get_command_output = Mock(return_value=(b'',b'',0))
        executor.copy_script('tmp123', ScriptFile('script1','some script code'))

    def test_copy_long_script_in_bulks(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session.protocol.get_command_output = Mock(return_value=(b'',b'',0))
        executor.copy_script('tmp123', ScriptFile('script1',''.join(['a' for i in range(0,4500)]))) # 3 bulks: 2000,2000,500
        self.assertEqual(3, self.session.protocol.get_command_output.call_count)

    def test_copy_script_fail(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session.protocol.get_command_output = Mock(return_value=(b'',b'some error',1))
        with self.assertRaises(Exception) as e:
            executor.copy_script('tmp123', ScriptFile('script1','some script code'))
        self.assertEqual(ErrorMsg.COPY_SCRIPT % 'some error', str(e.exception))

    # Run script

    def test_get_expected_file_extensions(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        file_extensions = executor.get_expected_file_extensions()
        self.assertTrue(len(file_extensions)==1)
        self.assertTrue('.ps1' in file_extensions)

    def test_run_script_success(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        output_writer = Mock()
        self.session.protocol.get_command_output = Mock(return_value=(b'some output', b'some error', 0))
        executor.run_script('tmp123', ScriptFile('script1', 'some script code'), {'var1':'123'}, output_writer)
        output_writer.write.assert_any_call(b'some output')
        output_writer.write.assert_any_call('some error')

    def test_run_script_fail(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        output_writer = Mock()
        self.session.protocol.get_command_output = Mock(return_value=(b'some output', b'some error', 1))
        with self.assertRaises(Exception, ) as e:
            executor.run_script('tmp123', ScriptFile('script1', 'some script code'), {}, output_writer)
        self.assertEqual(ErrorMsg.RUN_SCRIPT % 'some error', str(e.exception))
        output_writer.write.assert_any_call(b'some output')
        output_writer.write.assert_any_call('some error')

    def test_run_script_fail_with_xml_error(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        output_writer = Mock()
        err_xml = b'''#< CLIXML
                <Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">
                    <S S="Error">some error1_x000D__x000A_</S>
                    <S S="Error">some error2</S>
                    <S S="warn">some warning</S>
                </Objs>'''
        self.session.protocol.get_command_output = Mock(return_value=(b'some output', err_xml, 1))
        with self.assertRaises(Exception, ) as e:
            executor.run_script('tmp123', ScriptFile('script1', 'some script code'), {}, output_writer)
        self.assertEqual(ErrorMsg.RUN_SCRIPT % 'some error1\r\nsome error2', str(e.exception))
        output_writer.write.assert_any_call(b'some output')
        output_writer.write.assert_any_call('some error1\r\nsome error2')

    # Delete temp folder

    def test_delete_temp_folder_success(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session.protocol.get_command_output = Mock(return_value=(b'',b'',0))
        executor.delete_temp_folder('tmp123')

    def test_delete_temp_folder_fail(self):
        executor = WindowsScriptExecutor(self.logger, self.host, self.cancel_sampler)
        self.session.protocol.get_command_output = Mock(return_value=(b'',b'some error',1))
        with self.assertRaises(Exception) as e:
            executor.delete_temp_folder('tmp123')
        self.assertEqual(ErrorMsg.DELETE_TEMP_FOLDER % 'some error', str(e.exception))