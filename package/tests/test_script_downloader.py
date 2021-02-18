from unittest import TestCase

from cloudshell.cm.customscript.domain.script_executor import ExcutorConnectionError
from mock import patch, Mock
import mock
from cloudshell.cm.customscript.customscript_shell import CustomScriptShell
from cloudshell.cm.customscript.domain.reservation_output_writer import ReservationOutputWriter
from cloudshell.cm.customscript.domain.script_configuration import ScriptConfiguration
from cloudshell.cm.customscript.domain.script_file import ScriptFile
from cloudshell.cm.customscript.domain.script_downloader import ScriptDownloader, HttpAuth
from cloudshell.cm.customscript.domain.script_configuration import ScriptRepository
from tests.helpers import mocked_requests_get

import requests_mock

from tests.helpers import Any

class TestScriptDownloader(TestCase):
    
    def setUp(self):
        self.logger = Mock()
        self.cancel_sampler = Mock()
        self.logger_patcher = patch('cloudshell.cm.customscript.customscript_shell.LoggingSessionContext')
        self.logger_patcher.start()
        self.script_repo = ScriptRepository()
        pass
    
    @requests_mock.Mocker()
    def test_download_as_public(self, mock_requests):
        # public - url, no credentials
        public_repo_url = 'https://raw.githubusercontent.com/SomeUser/SomePublicRepo/master/bashScript.sh'
        script_content = 'SomeBashScriptContent'
        self.auth = HttpAuth('','','')

        # mock response
        mock_requests.get(public_repo_url, text=script_content)

        # set downloaded and downaload
        script_downloader = ScriptDownloader(self.logger, self.cancel_sampler)
        script_file = script_downloader.download(public_repo_url, self.auth)

        # assert name and content
        self.assertEqual(script_file.name, "bashScript.sh")
        self.assertEqual(script_file.text, "SomeBashScriptContent")

    def test_download_as_private_with_token(self):
        pass
