from unittest import TestCase, skip
from urlparse import urlparse, parse_qs

from mock import Mock, MagicMock, call, ANY

from cloudshell.cm.customscript.domain.github_script_downloader import GitHubScriptDownloader
from cloudshell.cm.customscript.domain.script_downloader import ALLOWED_FILES_PATTERN


class TestGitHubScriptDownloader(TestCase):
    def setUp(self):
        self.github_downloader = GitHubScriptDownloader(Mock(), ALLOWED_FILES_PATTERN, Mock())

    def test_validate_github_url_passes(self):
        # arrange
        url1 = "https://blabla/a/b/blob/master/simple.sh"
        url2 = "https://blabla/a/b/blob/master/plaster/simple.sh"
        url3 = "https://a.b/a/b/blob/dev/simple.sh"

        # act
        self.github_downloader._validate_github_url(url1)
        self.github_downloader._validate_github_url(url2)
        self.github_downloader._validate_github_url(url3)

    def test_validate_github_url_throws(self):
        # arrange
        url1 = "https://blabla/a/b/master/plaster/simple.sh"
        url2 = "https://a.b/a/blob/dev/simple.sh"
        url3 = "https://blabla/blob/master/simple.sh"
        url4 = "https://blabla/blob/simple.sh"
        url5 = "https://blabla/simple.sh"


        # act and assert
        for url in [url1,url2,url3,url4,url5]:
            with self.assertRaisesRegexp(ValueError, "not in the correct format"):
                self.github_downloader._validate_github_url(url)

    def test_extract_data_from_url(self):
        # arrange
        url1 = "https://github.com/acc/rep/blob/bra/fol/f.sh"

        # act
        data = self.github_downloader._extract_data_from_url(url1)

        # assert
        self.assertEqual(data.account_id, 'acc')
        self.assertEqual(data.branch_id, 'bra')
        self.assertEqual(data.path, 'fol/f.sh')
        self.assertEqual(data.repo_id, 'rep')
        self.assertEqual(data.api_dl_url, 'https://api.github.com/repos/acc/rep/contents/fol/f.sh?ref=bra')

    def test_is_url_to_file_returns_true_with_folders(self):
        # arrange
        file_path = "folder1/some_file.ps1"

        # act
        result = self.github_downloader.is_url_to_file(file_path)

        # assert
        self.assertTrue(result)

    def test_is_url_to_file_returns_true_no_folders(self):
        # arrange
        file_path = "some_file.ps1"

        # act
        result = self.github_downloader.is_url_to_file(file_path)

        # assert
        self.assertTrue(result)

    def test_is_url_to_file_returns_false_repo_root(self):
        # arrange
        file_path = ''

        # act
        result = self.github_downloader.is_url_to_file(file_path)

        # assert
        self.assertFalse(result)

    def test_is_url_to_file_returns_false(self):
        # arrange
        file_path = "folder1/folder2"

        # act
        result = self.github_downloader.is_url_to_file(file_path)

        # assert
        self.assertFalse(result)

    def test_download_single_file(self):
        # arrange
        file_name = Mock()
        file_txt = Mock()
        self.github_downloader._download_single_file = Mock(return_value=(file_name, file_txt))
        url = "https://blabla/a/b/blob/master/simple.sh"

        # act
        result = self.github_downloader.download(url, Mock())

        # assert
        self.assertEqual(result.main_script.name, file_name)
        self.assertEqual(result.main_script.text, file_txt)
        self.assertIsNone(result.additional_files)