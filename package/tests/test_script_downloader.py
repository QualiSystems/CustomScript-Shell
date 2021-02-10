from unittest import TestCase

from mock import Mock, patch

from cloudshell.cm.customscript.domain.script_downloader import ScriptDownloader


class TestScriptDownloader(TestCase):

    def setUp(self):
        self.downloader = ScriptDownloader(Mock(), Mock())

    @patch('cloudshell.cm.customscript.domain.script_downloader.GitLabScriptDownloader')
    def test_download_strategy_gitlab(self, gitlab_downloader_class_patch):
        # arrange
        url = Mock()
        auth = Mock(username='GITLAB',password=Mock())
        scripts_data = Mock()
        gitalb_downloader = Mock()
        gitalb_downloader.download.return_value = scripts_data
        gitlab_downloader_class_patch.return_value = gitalb_downloader

        # act
        result = self.downloader.download(url, auth)

        # assert
        gitalb_downloader.download.assert_called_once_with(url, auth)
        self.assertEqual(result, scripts_data)
