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

from tests.helpers import Any

def print_logs(message):
    print(message)

class TestScriptDownloader(TestCase):
    
    def setUp(self):
        self.logger = Mock()
        self.cancel_sampler = Mock()
        self.logger_patcher = patch('cloudshell.cm.customscript.customscript_shell.LoggingSessionContext')
        self.logger_patcher.start()
        self.script_repo = ScriptRepository()
        pass
    
    @mock.patch('cloudshell.cm.customscript.domain.script_downloader.requests.get', side_effect=mocked_requests_get)
    def test_download_as_public(self, mock_requests):
        # public - url, no credentials
        public_repo_url = 'https://raw.repocontentservice.com/SomeUser/SomePublicRepo/master/bashScript.sh'
        self.auth = HttpAuth('','','')

        # set downloaded and downaload
        self.logger.info = print_logs
        script_downloader = ScriptDownloader(self.logger, self.cancel_sampler)
        script_file = script_downloader.download(public_repo_url, self.auth, True)

        # assert name and content
        self.assertEqual(script_file.name, "bashScript.sh")
        self.assertEqual(script_file.text, "SomeBashScriptContent")
    
    @mock.patch('cloudshell.cm.customscript.domain.script_downloader.requests.get', side_effect=mocked_requests_get)
    def test_download_as_private_with_token(self, mocked_requests_get):
        # private - url, with token
        private_repo_url = 'https://raw.repocontentservice.com/SomeUser/SomePrivateTokenRepo/master/bashScript.sh'
        self.auth = HttpAuth('','','551e48b030e1a9f334a330121863e48e43f58c55')

        # set downloaded and downaload
        self.logger.info = print_logs
        script_downloader = ScriptDownloader(self.logger, self.cancel_sampler)
        script_file = script_downloader.download(private_repo_url, self.auth, True)

        # assert name and content
        self.assertEqual(script_file.name, "bashScript.sh")
        self.assertEqual(script_file.text, "SomeBashScriptContent")

    @mock.patch('cloudshell.cm.customscript.domain.script_downloader.requests.get', side_effect=mocked_requests_get)
    def test_download_as_private_with_token_with_private_token_pattern(self, mocked_requests_get):
        # private - url, with token
        private_repo_url = 'https://gitlab.mock.com/api/v4/SomeUser/SomePrivateTokenRepo/master/bashScript.sh'
        self.auth = HttpAuth('','','551e48b030e1a9f334a330121863e48e43f58c55')

        # set downloaded and downaload
        self.logger.info = print_logs
        script_downloader = ScriptDownloader(self.logger, self.cancel_sampler)
        script_file = script_downloader.download(private_repo_url, self.auth, True)

        # assert name and content
        self.assertEqual(script_file.name, "bashScript.sh")
        self.assertEqual(script_file.text, "SomeBashScriptContent")

    @mock.patch('cloudshell.cm.customscript.domain.script_downloader.requests.get', side_effect=mocked_requests_get)
    def test_download_as_private_with_token_with_gitlab_url_structure(self, mocked_requests_get):
        # private - url, with token
        private_repo_url = 'https://gitlab.mock.com/api/v4/SomeUser/SomePrivateTokenRepo/master/bashScript%2Esh/raw?ref=master'
        self.auth = HttpAuth('','','551e48b030e1a9f334a330121863e48e43f58c55')

        # set downloaded and downaload
        self.logger.info = print_logs
        script_downloader = ScriptDownloader(self.logger, self.cancel_sampler)
        script_file = script_downloader.download(private_repo_url, self.auth, True)

        # assert name and content
        self.assertEqual(script_file.name, "bashScript.sh")
        self.assertEqual(script_file.text, "SomeBashScriptContent")

    @mock.patch('cloudshell.cm.customscript.domain.script_downloader.requests.get', side_effect=mocked_requests_get)
    def test_download_as_private_with_credentials_and_failed_token(self, mocked_requests_get):
        # private - url, with token that fails and user\password. note - this is will not work on GitHub repo, they require token
        private_repo_url = 'https://raw.repocontentservice.com/SomeUser/SomePrivateCredRepo/master/bashScript.sh'
        self.auth = HttpAuth('SomeUser','SomePassword','551e48b030e1a9f334a330121863e48e43f0000')

        # set downloaded and downaload
        self.logger.info = print_logs
        script_downloader = ScriptDownloader(self.logger, self.cancel_sampler)
        script_file = script_downloader.download(private_repo_url, self.auth, True)

        # assert name and content
        self.assertEqual(script_file.name, "bashScript.sh")
        self.assertEqual(script_file.text, "SomeBashScriptContent")

    @mock.patch('cloudshell.cm.customscript.domain.script_downloader.requests.get', side_effect=mocked_requests_get)
    def test_download_fails_public_with_no_credentials_throws_exception(self, mocked_requests_get):
        # private - url, with token that fails and user\password. note - this is will not work on GitHub repo, they require token
        private_repo_url = 'https://badurl.mock.com/SomePublicRepo/master/bashScript.sh'
        self.auth = None

        # set downloaded and downaload
        self.logger.info = print_logs
        script_downloader = ScriptDownloader(self.logger, self.cancel_sampler)
        # script_file = script_downloader.download(private_repo_url, self.auth, True)

        with self.assertRaises(Exception) as context:
            script_downloader.download(private_repo_url, self.auth, True)

        self.assertIn('Please make sure the URL is valid, and the credentials are correct and necessary.', str(context.exception))

        # assert name and content
        #self.assertEqual(script_file.name, "bashScript.sh")
        #self.assertEqual(script_file.text, "SomeBashScriptContent")