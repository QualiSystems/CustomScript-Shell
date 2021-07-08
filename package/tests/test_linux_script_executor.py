from unittest import TestCase
from mock import patch, Mock
#from scpclient import SCPError
from scp import SCPException

from cloudshell.cm.customscript.domain.script_configuration import HostConfiguration
from cloudshell.cm.customscript.domain.script_executor import ErrorMsg
from cloudshell.cm.customscript.domain.script_file import ScriptFile
from cloudshell.cm.customscript.domain.linux_script_executor import LinuxScriptExecutor
from tests.helpers import Any
import io

class TestLinuxScriptExecutor(TestCase):

    def setUp(self):
        self.logger = Mock()
        self.cancel_sampler = Mock()
        self.session = Mock()
        self.scp = Mock()
        self.scp_ctor = Mock()
        self.host = HostConfiguration()
        self.host.ip = "1.2.3.4"

        self.session_patcher = patch('cloudshell.cm.customscript.domain.linux_script_executor.SSHClient')
        self.session_patcher.start().return_value = self.session
        self.scp_patcher = patch('cloudshell.cm.customscript.domain.linux_script_executor.SCPClient')
        self.scp_ctor = self.scp_patcher.start()
        self.scp_ctor.return_value = self.scp

        self.executor = LinuxScriptExecutor(self.logger, self.host, self.cancel_sampler)

    def tearDown(self):
        self.session_patcher.stop()
        self.scp_patcher.stop()

    def _mock_session_answer(self, exit_code, stdout, stderr):
        stdout_mock = Mock()
        stderr_mock = Mock()
        stdout_mock.channel.recv_exit_status = Mock(return_value=exit_code)
        stdout_mock.readlines = Mock(return_value=stdout)
        stderr_mock.readlines = Mock(return_value=stderr)
        self.session.exec_command = Mock(return_value=(None, stdout_mock, stderr_mock))

    def test_user_password(self):
        self.host.username = 'root'
        self.host.password = '1234'
        executor = LinuxScriptExecutor(self.logger, self.host, self.cancel_sampler)
        executor.connect()
        self.session.connect.assert_called_with('1.2.3.4',  username='root', password='1234')

    def test_pem_file(self):
        self.host.username = 'root'
        self.host.access_key = 'just an access key'
        key_obj = Mock()
        with patch('cloudshell.cm.customscript.domain.linux_script_executor.RSAKey.from_private_key') as from_private_key:
            from_private_key.return_value = key_obj
            executor = LinuxScriptExecutor(self.logger, self.host, self.cancel_sampler)
            executor.connect()
        self.session.connect.assert_called_with('1.2.3.4', username='root', pkey=key_obj)

    def test_no_password_nor_pen_file(self):
        self.host.username = 'root'
        executor = LinuxScriptExecutor(self.logger, self.host, self.cancel_sampler)
        with self.assertRaises(Exception) as e:
            executor.connect()
        self.assertEqual('Both password and access key are empty.', str(e.exception.inner_error))

    def test_no_password_no_pen_file_no_username(self):
        executor = LinuxScriptExecutor(self.logger, self.host, self.cancel_sampler)
        with self.assertRaises(Exception) as e:
            executor.connect()
        self.assertEqual('Machine credentials are empty.', str(e.exception.inner_error))

    def test_create_temp_folder_success(self):
        self._mock_session_answer(0,'tmp123','')
        result = self.executor.create_temp_folder()
        self.assertEqual('tmp123', result)

    def test_create_temp_folder_fail(self):
        self._mock_session_answer(1,'','some error')
        with self.assertRaises(Exception) as e:
            self.executor.create_temp_folder()
        self.assertEqual(ErrorMsg.CREATE_TEMP_FOLDER % 'some error', str(e.exception))

    def test_copy_script_success(self):
        transport = Mock()
        self.session.get_transport.return_value = transport
        self.executor.copy_script('tmp123', ScriptFile('script1','some script code'))
        self.scp_ctor.assert_called_once_with(transport)
        self.scp.putfo.assert_called_once_with(Any(type(io.BytesIO)), remote_path='tmp123/script1')
        self.scp.close.assert_called_once()

    def test_copy_script_fail(self):
        self.scp.putfo.side_effect = SCPException('some error')
        with self.assertRaises(Exception) as e:
            self.executor.copy_script('tmp123', ScriptFile('script1','some script code'))
        self.assertIn(ErrorMsg.COPY_SCRIPT % '', str(e.exception))
        self.assertIn('some error', str(e.exception))
        self.scp.close.assert_called_once()

    def test_run_script_success(self):
        output_writer = Mock()
        self._mock_session_answer(0, 'some output', '')
        self.executor.run_script('tmp123', ScriptFile('script1', 'some script code'), {'var1':'123'}, output_writer)
        output_writer.write.assert_any_call('some output')

    def test_run_script_converts_escapes_characters_correctly(self):
        # escapes characters when passed into terminal, used to set arguments of bash script
        # using export var; should appear as escaped C style characters see more here:
        # https://en.wikipedia.org/wiki/Escape_sequences_in_C (hexadecimal)
        res = self.executor._escape('a')
        self.assertEquals(res, "$'\\x61'")
        res = self.executor._escape(1)
        self.assertEquals(res, "$'\\x31'")
        res = self.executor._escape(None)
        self.assertEquals(res, "$'\\x4e\\x6f\\x6e\\x65'")
        res = self.executor._escape('$')
        self.assertEquals(res, "$'\\x24'")

    def test_run_script_fail(self):
        output_writer = Mock()
        self._mock_session_answer(1, 'some output', 'some error')
        with self.assertRaises(Exception, ) as e:
            self.executor.run_script('tmp123', ScriptFile('script1', 'some script code'), None, output_writer)
        self.assertEqual(ErrorMsg.RUN_SCRIPT % 'some error', str(e.exception))
        output_writer.write.assert_any_call('some output')
        output_writer.write.assert_any_call('some error')

    def test_delete_temp_folder_success(self):
        self._mock_session_answer(0,'','')
        self.executor.delete_temp_folder('tmp123')

    def test_delete_temp_folder_fail(self):
        self._mock_session_answer(1,'','some error')
        with self.assertRaises(Exception) as e:
            self.executor.delete_temp_folder('tmp123')
        self.assertEqual(ErrorMsg.DELETE_TEMP_FOLDER % 'some error', str(e.exception))