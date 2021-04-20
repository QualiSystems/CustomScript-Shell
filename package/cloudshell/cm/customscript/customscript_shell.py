import json
import os

import errno

import time
from cloudshell.core.context.error_handling_context import ErrorHandlingContext
from cloudshell.shell.core.session.cloudshell_session import CloudShellSessionContext
from cloudshell.shell.core.session.logging_session import LoggingSessionContext

from cloudshell.cm.customscript.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.customscript.domain.reservation_output_writer import ReservationOutputWriter
from cloudshell.cm.customscript.domain.script_configuration import ScriptConfigurationParser, ScriptRepository, \
    HostConfiguration
from cloudshell.cm.customscript.domain.script_downloader import ScriptDownloader, HttpAuth
from cloudshell.cm.customscript.domain.script_executor import IScriptExecutor, ExcutorConnectionError
from cloudshell.cm.customscript.domain.script_executor_selector import ScriptExecutorSelector
from cloudshell.cm.customscript.domain.script_file import ScriptFile


class CustomScriptShell(object):

    def __init__(self):
        pass

    def execute_script(self, command_context, script_conf_json, cancellation_context):
        """
        :type command_context: ResourceCommandContext
        :type ansi_conf_json: str
        :type cancellation_context: CancellationContext
        :rtype str
        """
        with LoggingSessionContext(command_context) as logger:
            logger.debug('\'execute_script\' is called with the configuration json: \n' + script_conf_json)

            with ErrorHandlingContext(logger):
                with CloudShellSessionContext(command_context) as api:
                    cancel_sampler = CancellationSampler(cancellation_context)
                    script_conf = ScriptConfigurationParser(api).json_to_object(script_conf_json)

                    output_writer = ReservationOutputWriter(api, command_context)

                    logger.info('Downloading file from \'%s\' ...' % script_conf.script_repo.url)
                    script_file = self._download_script(script_conf.script_repo, logger, cancel_sampler, script_conf.verify_certificate)
                    logger.info('Done (%s, %s chars).' % (script_file.name, len(script_file.text)))

                    service = ScriptExecutorSelector.get(script_conf.host_conf, logger, cancel_sampler)

                    self._warn_for_unexpected_file_type(script_conf.host_conf, service, script_file, output_writer)

                    logger.info('Connecting ...')
                    self._connect(service, cancel_sampler, script_conf.timeout_minutes)
                    logger.info('Done.')

                    service.execute(script_file, script_conf.host_conf.parameters, output_writer, script_conf.print_output)

    def _download_script(self, script_repo, logger, cancel_sampler, verify_certificate):
        """
        :type script_repo: ScriptRepository
        :type logger: Logger
        :type cancel_sampler: CancellationSampler
        :rtype ScriptFile
        """
        url = script_repo.url
        auth = None
        if script_repo.username or script_repo.token:
            auth = HttpAuth(script_repo.username, script_repo.password, script_repo.token)
        return ScriptDownloader(logger, cancel_sampler).download(url, auth, verify_certificate)

    def _warn_for_unexpected_file_type(self, target_host, service, script_file, output_writer):
        """
        :type target_host: HostConfiguration
        :type service: IScriptExecutor
        :type script_file: ScriptFile
        :type output_writer: ReservationOutputWriter
        """
        file_name, file_ext = os.path.splitext(script_file.name)
        if not file_ext in service.get_expected_file_extensions():
            output_writer.write_warning('Trying to run "%s" file via %s on host %s' % (file_ext, target_host.connection_method, target_host.ip))

    def _connect(self, executor, cancel_sampler, timeout_minutes):
        """
        :type executor: IScriptExecutor
        :type cancel_sampler: CancellationSampler
        """
        # 10060  ETIMEDOUT                      Operation timed out
        # 10061  ECONNREFUSED                   Connection refused (happense when host found, port not)
        # 10064  EHOSTDOWN                      Host is down
        # 10065  EHOSTUNREACH                   Host is unreachable
        # 500                                   Bad http response (winrm)
        # 113    EHOSTUNREACH                   No route to host (winrm - OpenStack)
        # 111    ERROR_SSH_APPLICATION_CLOSED   User on the other side of connection closed application that led to disconnection
        # 110    ERROR_SSH_CONNECTION_LOST      Connection was lost by some reason
        valid_errnos = [10060, 10061, 10064, 10065, 500, 113, 111, 110]
        interval_seconds = 10
        start_time = time.time()
        while True:
            cancel_sampler.throw_if_canceled()
            try:
                executor.connect()
                break
            except ExcutorConnectionError as e:
                if not e.errno in valid_errnos:
                    raise e.inner_error
                if time.time() - start_time >= timeout_minutes*60:
                    raise e.inner_error
                time.sleep(interval_seconds)

# conf = '''{
# 	"repositoryDetails": {
# 		"url": "http://192.168.30.108:8081/artifactory/LinuxScripts/ls.sh"
# 	},
# 	"hostDetails": {
# 		"ip": "192.168.85.20",
# 		"username": "root",
# 		"password": "qs1234",
# 		"connectionMethod": "ssh"
# 	}
# }'''
# context = ResourceCommandContext()
# context.resource = ResourceContextDetails()
# context.resource.name = 'TEST Resource'
# context.reservation = ReservationContextDetails()
# context.reservation.reservation_id = '8cc5bc1a-ae62-43c6-8772-3cd2bde5dbd8'
#
# shell = CustomScriptShell()
#
# shell.execute_script(context, conf)