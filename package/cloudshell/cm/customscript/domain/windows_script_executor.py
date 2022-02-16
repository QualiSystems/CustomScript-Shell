import base64
import os

import time
from multiprocessing.pool import ThreadPool
from uuid import uuid4

import re
import winrm
from logging import Logger
import xml.etree.ElementTree as ET
from winrm.exceptions import WinRMTransportError

from cloudshell.cm.customscript.domain.reservation_output_writer import ReservationOutputWriter
from cloudshell.cm.customscript.domain.script_configuration import HostConfiguration
from cloudshell.cm.customscript.domain.script_executor import IScriptExecutor, ErrorMsg, ExcutorConnectionError
from requests import ConnectionError, ConnectTimeout


class WindowsScriptExecutor(IScriptExecutor):
    COPY_BULK_SIZE = 2000

    def __init__(self, logger, target_host, cancel_sampler):
        """
        :type logger: Logger
        :type target_host: HostConfiguration
        :type cancel_sampler: CancellationContext
        """
        self.logger = logger
        self.cancel_sampler = cancel_sampler
        self.pool = ThreadPool(processes=1)

        # if parameter does not specify winrm_transport, try ssl, then fall back to http
        if target_host.parameters.get('winrm_transport')=='ssl':
            self.logger.info('SSL only WinRM session')
            self.session = winrm.Session(target_host.ip, auth=(target_host.username, target_host.password), transport='ssl', server_cert_validation='ignore')
        elif target_host.parameters.get('winrm_transport')=='http':
            self.logger.info('http only WinRM session')
            self.session = winrm.Session(target_host.ip, auth=(target_host.username, target_host.password))
        else:
            self.logger.info('identifying whether host is ssl or http')
            self.session = winrm.Session(target_host.ip, auth=(target_host.username, target_host.password), transport='ssl', server_cert_validation='ignore')
            try:
                self.session.run_cmd('@echo connected')
                self.logger.info('connecting via ssl')
            except ConnectionError:
                self.session = winrm.Session(target_host.ip, auth=(target_host.username, target_host.password))
                self.logger.info('falling back to http')

    def connect(self):
        try:
            uid = str(uuid4())
            result = self.session.run_cmd('@echo '+uid)
            stdout = result.std_out.decode('utf-8')
            self.logger.info(stdout)
            assert uid in stdout
        except ConnectTimeout as e:
            self.logger.error(e.response)
            raise ExcutorConnectionError(10060, e) #10060=Timeout
        except ConnectionError as e:
            match = re.search(r'\[Errno (?P<errno>\d+)\]', str(e))
            error_code = int(match.group('errno')) if match else 0
            raise ExcutorConnectionError(error_code, e)
        except WinRMTransportError as e:
            match = re.search(r'Code (?P<errno>\d+)', str(e))
            error_code = int(match.group('errno')) if match else 0
            raise ExcutorConnectionError(error_code, e)
        except Exception as e:
            raise ExcutorConnectionError(0, e)

    def get_expected_file_extensions(self):
        """
        :rtype list[str]
        """
        return ['.ps1']
        # file_name, file_ext = os.path.splitext(script_file.name)
        # return file_ext != '.ps1':
        #     output_writer.write_warning('Trying to run "%s" file via ssh on host %s' % (file_ext, self.target_host.ip))

    def execute(self, script_file, env_vars, output_writer, print_output=True):
        """
        :type script_file: ScriptFile
        :type output_writer: ReservationOutputWriter
        :type print_output: bool
        """
        self.logger.info('Creating temp folder on target machine ...')
        tmp_folder = self.create_temp_folder()
        self.logger.info('Done (%s).' % tmp_folder)

        try:
            self.logger.info('Copying "%s" (%s chars) to "%s" target machine ...' % (
            script_file.name, len(script_file.text), tmp_folder))
            self.copy_script(tmp_folder, script_file)
            self.logger.info('Done.')

            self.logger.info('Running "%s" on target machine ...' % script_file.name)
            self.run_script(tmp_folder, script_file, env_vars, output_writer, print_output)
            self.logger.info('Done.')

        finally:
            self.logger.info('Deleting "%s" folder from target machine ...' % tmp_folder)
            self.delete_temp_folder(tmp_folder)
            self.logger.info('Done.')

    def create_temp_folder(self):
        """
        :rtype str
        """
        code = """
$fullPath = Join-Path $env:Temp ([System.Guid]::NewGuid().ToString())
New-Item $fullPath -type directory | Out-Null
Write-Output $fullPath
"""
        result = self._run_cancelable(code)
        if result.status_code != 0:
            raise Exception(ErrorMsg.CREATE_TEMP_FOLDER % result.std_err)
        return result.std_out.decode('utf-8').rstrip('\r\n')

    def copy_script(self, tmp_folder, script_file):
        """
        :type tmp_folder: str
        :type script_file: ScriptFile
        """
        all_size = len(script_file.text)
        bulk_zise = WindowsScriptExecutor.COPY_BULK_SIZE
        bulks = [script_file.text[i:min(all_size,i+bulk_zise)] for i in range(0, all_size, bulk_zise)]
        self.logger.debug("Bulks sizes (%s): %s" % (len(bulks), ', '.join([str(len(b)) for b in bulks])))

        for bulk in bulks:
            encoded_bulk = base64.b64encode(bulk.encode("utf-8"))
            code = """
$path   = Join-Path "{0}" "{1}"
$data   = [System.Convert]::FromBase64String("{2}")
Add-Content -value $data -encoding byte -path $path
""".format(tmp_folder, script_file.name, encoded_bulk.decode('utf-8'))
            result = self._run_cancelable(code)
            if result.status_code != 0:
                raise Exception(ErrorMsg.COPY_SCRIPT % result.std_err)

    def run_script(self, tmp_folder, script_file, env_vars, output_writer, print_output=True):
        """
        :type tmp_folder: str
        :type script_file: ScriptFile
        :type env_vars: dict
        :type output_writer: ReservationOutputWriter
        :type print_output: bool
        """
        code = ''
        for key, value in (env_vars or {}).items():
            code += '\n$env:%s = "%s"' % (key, str(value))
        code += """
$path = Join-Path "{0}" "{1}"
Invoke-Expression "& '$path'"
""".format(tmp_folder, script_file.name)
        result = self._run_cancelable(code)
        if print_output:
            output_writer.write(result.std_out)
            output_writer.write(result.std_err)
        if result.status_code != 0:
            raise Exception(ErrorMsg.RUN_SCRIPT % result.std_err)

    def delete_temp_folder(self, tmp_folder):
        """
        :type tmp_folder: str
        """
        code = """
$path = "%s"
Remove-Item $path -recurse
"""
        result = self._run_cancelable(code % tmp_folder)
        if result.status_code != 0:
            raise Exception(ErrorMsg.DELETE_TEMP_FOLDER % result.std_err)

    # def _run_ps(self, code):
    #     result = self.session.run_ps(code)
    #     self.logger.debug('ReturnedCode:' + str(result.status_code))
    #     self.logger.debug('Stdout:' + result.std_out)
    #     self.logger.debug('Stderr:' + result.std_err)
    #     return result

    def _run_cancelable(self, ps_code):
        """
        :type ps_code: str
        """
        self.logger.debug('PowerShellScript:' + ps_code)

        bat_code = 'powershell -encodedcommand %s' % base64.b64encode(ps_code.encode('utf_16_le')).decode('ascii')
        shell_id = self.session.protocol.open_shell()
        command_id = self.session.protocol.run_command(shell_id, bat_code)

        async_result = self.pool.apply_async(self.session.protocol.get_command_output, kwds={'shell_id': shell_id, 'command_id': command_id})
        try:
            while not async_result.ready():
                if self.cancel_sampler.is_cancelled():
                    self.cancel_sampler.throw()
                time.sleep(1)
            result = winrm.Response(async_result.get())
        finally:
            self.session.protocol.cleanup_command(shell_id, command_id)
            self.session.protocol.close_shell(shell_id)

        self.logger.debug('ReturnedCode:' + str(result.status_code))
        self.logger.debug('Stdout:' + result.std_out.decode('utf-8'))
        self.logger.debug('Stderr:' + result.std_err.decode('utf-8'))
        result.std_err = self._try_decode_error_xml(result.std_err.decode('utf-8'))
        self.logger.debug('Stderr(Decoded):' + result.std_err)
        return result

    def _try_decode_error_xml(self, str):
        if str:
            try:
                str = re.sub(re.escape('#< CLIXML'), '', str, 1)
                root = ET.fromstring(str)
                str = ''.join([e.text for e in root.findall('*/[@S="Error"]')])
                str = re.sub('_x([0-9a-fA-F]{4})_', lambda match: chr(int(match.group(1), 16)), str)
                self.logger.error('Succeeded to decode stderr : ' + str)
            except Exception as e:
                self.logger.error('Failed to decode stderr. Error: %s' % e.msg)
        return str
