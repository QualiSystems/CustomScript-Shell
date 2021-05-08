import os
import socket
import sys
from StringIO import StringIO
from multiprocessing.pool import ThreadPool
from threading import Thread

import time
from paramiko import SSHClient, AutoAddPolicy, RSAKey
from paramiko.ssh_exception import NoValidConnectionsError
from scpclient import Write, SCPError

from cloudshell.cm.customscript.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.customscript.domain.reservation_output_writer import ReservationOutputWriter
from cloudshell.cm.customscript.domain.script_configuration import HostConfiguration
from cloudshell.cm.customscript.domain.script_executor import IScriptExecutor, ErrorMsg, ExcutorConnectionError
from cloudshell.cm.customscript.domain.script_file import ScriptFile, ScriptsData


class LinuxScriptExecutor(IScriptExecutor):
    PasswordEnvVarName = 'cs_machine_pass'

    class ExecutionResult(object):
        def __init__(self, exit_code, std_out, std_err):
            self.std_err = std_err
            self.std_out = std_out
            self.success = exit_code == 0

    def __init__(self, logger, target_host, cancel_sampler):
        """
        :type logger: Logger
        :type target_host: HostConfiguration
        :type cancel_sampler: CancellationSampler
        """
        self.logger = logger
        self.cancel_sampler = cancel_sampler
        self.pool = ThreadPool(processes=1)
        self.session = SSHClient()
        self.session.set_missing_host_key_policy(AutoAddPolicy())
        self.target_host = target_host

    def connect(self):
        try:
            if self.target_host.password:
                self.session.connect(self.target_host.ip, username=self.target_host.username, password=self.target_host.password)
            elif self.target_host.access_key:
                key_stream = StringIO(self.target_host.access_key)
                key_obj = RSAKey.from_private_key(key_stream)
                self.session.connect(self.target_host.ip, username=self.target_host.username, pkey=key_obj)
            elif self.target_host.username:
                raise Exception('Both password and access key are empty.')
            else:
                raise Exception('Machine credentials are empty.')
        except NoValidConnectionsError as e:
            error_code = next(e.errors.itervalues(), type('e', (object,), {'errno': 0})).errno
            raise ExcutorConnectionError(error_code, e)
        except socket.error as e:
            raise ExcutorConnectionError(e.errno, e)
        except Exception as e:
            raise ExcutorConnectionError(0, e)

    def get_expected_file_extensions(self):
        """
        :rtype list[str]
        """
        return ['.sh','.bash']
        # file_name, file_ext = os.path.splitext(script_file.name)
        # if file_ext and file_ext != '.sh' and file_ext != '.bash':
        #     output_writer.write_warning('Trying to run "%s" file via ssh on host %s' % (file_ext, self.target_host.ip))

    def execute(self, scripts_data, env_vars, output_writer, print_output=True):
        """
        :type scripts_data: ScriptsData
        :type output_writer: ReservationOutputWriter
        :type print_output: bool
        """
        self.logger.info('Creating temp folder on target machine ...')
        tmp_folder = self.create_temp_folder()
        self.logger.info('Done (%s).' % tmp_folder)

        try:
            self._copy_all_scripts(scripts_data, tmp_folder)

            self.logger.info('Running "%s" on target machine ...' % scripts_data.main_script.name)
            self.run_script(tmp_folder, scripts_data.main_script, env_vars, output_writer, print_output)
            self.logger.info('Done.')

        finally:
            self.logger.info('Deleting "%s" folder from target machine ...' % tmp_folder)
            self.delete_temp_folder(tmp_folder)
            self.logger.info('Done.')

    def _copy_all_scripts(self, scripts_data, tmp_folder):
        self.logger.info('Copying files to target machine')

        self.logger.info('Copying main script "%s" (%s chars) to "%s" target machine ...' % (
            scripts_data.main_script.name, len(scripts_data.main_script.text), tmp_folder))
        self.copy_script(tmp_folder, scripts_data.main_script)
        self.logger.info('Done.')

        if scripts_data.additional_files:
            for script_file in scripts_data.additional_files:
                self.logger.info('Copying "%s" (%s chars) to "%s" target machine ...' % (
                    script_file.name, len(script_file.text), tmp_folder))
                self.copy_script(tmp_folder, script_file)
                self.logger.info('Done.')


    def create_temp_folder(self):
        """
        :rtype str
        """
        result = self._run_cancelable('mktemp -d')
        if not result.success:
            raise Exception(ErrorMsg.CREATE_TEMP_FOLDER % result.std_err)
        return result.std_out.rstrip('\n')

    def copy_script(self, tmp_folder, script_file):
        """
        :type tmp_folder: str
        :type script_file: ScriptFile
        """
        file_stream = StringIO(script_file.text)
        file_size = len(file_stream.getvalue())
        scp = None
        try:
            scp = Write(self.session.get_transport(), tmp_folder)
            scp.send(file_stream, script_file.name, '0601', file_size)
        except SCPError as e:
            raise Exception,ErrorMsg.COPY_SCRIPT % str(e),sys.exc_info()[2]
        finally:
            if scp:
                scp.close()

    def run_script(self, tmp_folder, script_file, env_vars, output_writer, print_output=True):
        """
        :type tmp_folder: str
        :type script_file: ScriptFile
        :type env_vars: dict
        :type output_writer: ReservationOutputWriter
        :type print_output: bool
        """
        code = ''
        for key, value in (env_vars or {}).iteritems():
            code += 'export %s=%s;' % (key,self._escape(value))
        if self.target_host.password:
            code += 'export %s=%s;' % (self.PasswordEnvVarName, self._escape(self.target_host.password))
        # add temp folder path as an env var
        code += 'export %s=%s;' % (self.TempFolderEnvVarName, self._escape(tmp_folder))

        code += 'sh '+tmp_folder+'/'+script_file.name
        result = self._run_cancelable(code)
        if print_output:
            output_writer.write(result.std_out)
            output_writer.write(result.std_err)
        if not result.success:
            raise Exception(ErrorMsg.RUN_SCRIPT % result.std_err)

    def delete_temp_folder(self, tmp_folder):
        """
        :type tmp_folder: str
        """
        result = self._run_cancelable('rm -rf '+tmp_folder)
        if not result.success:
            raise Exception(ErrorMsg.DELETE_TEMP_FOLDER % result.std_err)

    def _run(self, code):
        #self.logger.debug('BashScript:' + code)

        #stdin, stdout, stderr = self._run_cancelable(code)
        stdin, stdout, stderr = self.session.exec_command(code)

        exit_code = stdout.channel.recv_exit_status()
        stdout_txt = ''.join(stdout.readlines())
        stderr_txt = ''.join(stderr.readlines())

        self.logger.debug('ReturnedCode:' + str(exit_code))
        self.logger.debug('Stdout:' + stdout_txt)
        self.logger.debug('Stderr:' + stderr_txt)

        return LinuxScriptExecutor.ExecutionResult(exit_code, stdout_txt, stderr_txt)

    def _run_cancelable(self, txt, *args):
        async_result = self.pool.apply_async(self._run, kwds={'code': txt % args})

        while not async_result.ready():
            if self.cancel_sampler.is_cancelled():
                self.session.close()
                self.cancel_sampler.throw()
            time.sleep(1)

        return async_result.get()

    def _escape(self, value):
        escaped_str = "$'" + '\\x' + '\\x'.join([x.encode("hex") for x in str(value).encode("utf-8")]) + "'"
        return escaped_str
