from unittest import TestCase, skip
from urlparse import urlparse, parse_qs

from mock import Mock, MagicMock, call, ANY

from cloudshell.cm.customscript.domain.gitlab_script_downloader import GitLabScriptDownloader
from cloudshell.cm.customscript.domain.script_downloader import ALLOWED_FILES_PATTERN


class TestGitLabScriptDownloader(TestCase):
    def setUp(self):
        self.gitlab_downloader = GitLabScriptDownloader(Mock(), ALLOWED_FILES_PATTERN, Mock())


    def test_validate_gitlab_url_passes(self):
        # arrange
        url1 = "https://blabla/api/v4/projects/xxx/repository/files/folder1/some_file.txt"
        url2 = "https://subdomain.blabla.com/api/v4/projects/xxx/repository/files/some_file.txt"
        url3 = "https://subdomain.blabla.com/api/v4/projects/xxx/repository/files/some_file.txt?ref=release_tag"
        url4 = "https://blabla/api/v4/projects/xxx/repository/files/"  # repo root

        # act
        self.gitlab_downloader._validate_gitlab_url(url1)
        self.gitlab_downloader._validate_gitlab_url(url2)
        self.gitlab_downloader._validate_gitlab_url(url3)
        self.gitlab_downloader._validate_gitlab_url(url4)

    def test_validate_gitlab_url_throws(self):
        # arrange
        url1 = "xxx"

        # act and assert
        with self.assertRaisesRegexp(ValueError, "not in the correct format"):
            self.gitlab_downloader._validate_gitlab_url(url1)

    def test_extract_data_from_url_with_ref(self):
        # arrange
        url1 = "https://sub.blabla.com/api/v4/projects/xxx/repository/files/folder1/some_file.txt?ref=master"

        # act
        data = self.gitlab_downloader._extract_data_from_url(url1)

        # assert
        self.assertEqual(data.project_id, 'xxx')
        self.assertEqual(data.file_path, 'folder1/some_file.txt')
        self.assertEqual(data.ref, 'master')

    def test_extract_data_from_url_no_ref(self):
        # arrange
        url1 = "https://sub.blabla:8080/api/v4/projects/xxx/repository/files/folder1/some_file.txt"

        # act
        data = self.gitlab_downloader._extract_data_from_url(url1)

        # assert
        self.assertEqual(data.project_id, 'xxx')
        self.assertEqual(data.file_path, 'folder1/some_file.txt')
        self.assertIsNone(data.ref)
        self.assertEqual(data.base_url, 'https://sub.blabla:8080')

    def test_extract_data_from_url_repo_root(self):
        # arrange
        url1 = "https://sub.blabla:8080/api/v4/projects/xxx/repository/files/"

        # act
        data = self.gitlab_downloader._extract_data_from_url(url1)

        # assert
        self.assertEqual(data.project_id, 'xxx')
        self.assertEqual(data.file_path, '')
        self.assertIsNone(data.ref)
        self.assertEqual(data.base_url, 'https://sub.blabla:8080')

    def test_extract_data_from_url_extra_query_string_ignored(self):
        # arrange
        url1 = "https://blabla/api/v4/projects/xxx/repository/files/folder1/some_file.txt?bla1=bla1&bla2=bla2"

        # act
        data = self.gitlab_downloader._extract_data_from_url(url1)

        # assert
        self.assertEqual(data.project_id, 'xxx')
        self.assertEqual(data.file_path, 'folder1/some_file.txt')
        self.assertIsNone(data.ref)

    def test_is_url_to_file_returns_true_with_folders(self):
        # arrange
        file_path = "folder1/some_file.ps1"

        # act
        result = self.gitlab_downloader.is_url_to_file(file_path)

        # assert
        self.assertTrue(result)

    def test_is_url_to_file_returns_true_no_folders(self):
        # arrange
        file_path = "some_file.ps1"

        # act
        result = self.gitlab_downloader.is_url_to_file(file_path)

        # assert
        self.assertTrue(result)

    def test_is_url_to_file_returns_false_repo_root(self):
        # arrange
        file_path = ''

        # act
        result = self.gitlab_downloader.is_url_to_file(file_path)

        # assert
        self.assertFalse(result)

    def test_is_url_to_file_returns_false(self):
        # arrange
        file_path = "folder1/folder2"

        # act
        result = self.gitlab_downloader.is_url_to_file(file_path)

        # assert
        self.assertFalse(result)

    def test_build_url_to_list_files_in_path_with_ref_and_folder(self):
        # arrange
        url_data = Mock(base_url='https://sub.bla.com', project_id='xxx', ref='master', file_path='folder1/folder2')

        # act
        result = self.gitlab_downloader._build_url_to_list_files_in_path(url_data)

        # assert
        self.assertIn('https://sub.bla.com/api/v4/projects/xxx/repository/tree', result, )
        parsed_url = urlparse(result)
        params = parse_qs(parsed_url.query)
        self.assertEqual(['folder1/folder2'], params.get('path'))
        self.assertEqual(['master'], params.get('ref'))
        self.assertEqual(['100'], params.get('per_page'))

    def test_build_url_to_list_files_in_path_with_ref_and_no_path(self):
        # arrange
        url_data = Mock(base_url='https://sub.bla.com', project_id='xxx', ref='master', file_path='')

        # act
        result = self.gitlab_downloader._build_url_to_list_files_in_path(url_data)

        # assert
        self.assertEqual(result, 'https://sub.bla.com/api/v4/projects/xxx/repository/tree?per_page=100&ref=master')

    def test_build_url_to_list_files_in_path_no_ref_no_path(self):
        # arrange
        url_data = Mock(base_url='https://sub.bla.com', project_id='xxx', ref=None, file_path='')

        # act
        result = self.gitlab_downloader._build_url_to_list_files_in_path(url_data)

        # assert
        self.assertEqual(result, 'https://sub.bla.com/api/v4/projects/xxx/repository/tree?per_page=100')

    def test_remove_junk_files_from_files_list(self):
        # arrange
        files_list = [{'name': '.gitignore', 'type': 'blob'},
                      {'name': '.git', 'type': 'blob'},
                      {'name': 'main.ps1', 'type': 'blob'},
                      {'name': 'folder1', 'type': 'tree'},
                      {'name': 'README.md', 'type': 'blob'}]

        # act
        approved_list = self.gitlab_downloader._remove_junk_files_and_folders_from_files_list(files_list)

        # assert
        self.assertListEqual([{'name': 'main.ps1', 'type': 'blob'}], approved_list)

    def test_get_main_file_ps1(self):
        # arrange
        files_list = [{'name': 'main.ps1'}, {'name': 'bla1.sh'}]

        # act
        main = self.gitlab_downloader.get_main_file(files_list)

        # assert
        self.assertEqual({'name': 'main.ps1'}, main)

    def test_get_main_file_sh(self):
        # arrange
        files_list = [{'name': 'main.sh'}, {'name': 'bla1.sh'}]

        # act
        main = self.gitlab_downloader.get_main_file(files_list)

        # assert
        self.assertEqual({'name': 'main.sh'}, main)

    def test_get_main_file_bash(self):
        # arrange
        files_list = [{'name': 'main.bash'}, {'name': 'bla1.sh'}]

        # act
        main = self.gitlab_downloader.get_main_file(files_list)

        # assert
        self.assertEqual({'name': 'main.bash'}, main)

    def test_get_main_file_raises_no_main(self):
        # arrange
        files_list = [{'name': 'main.ps2'}, {'name': 'bla1.sh'}]

        # act & assert
        with self.assertRaisesRegexp(Exception, "Main file doesn't exist"):
            self.gitlab_downloader.get_main_file(files_list)

    def test_download_single_file(self):
        # arrange
        file_name = Mock()
        file_txt = Mock()
        self.gitlab_downloader._download_single_file = Mock(return_value=(file_name, file_txt))
        url = 'https://gitlab.com/api/v4/projects/21915601/repository/files/test_dir/bla.sh?ref=master'

        # act
        result = self.gitlab_downloader.download(url, Mock())

        # assert
        self.assertEqual(result.main_script.name, file_name)
        self.assertEqual(result.main_script.text, file_txt)
        self.assertIsNone(result.additional_files)

    def test_download_single_dir(self):
        # arrange

        main_file_info = MagicMock()
        files_list_in_path = [MagicMock(), MagicMock(), main_file_info]
        self.gitlab_downloader._get_list_of_files_in_path = Mock()
        self.gitlab_downloader._remove_junk_files_and_folders_from_files_list = Mock(return_value=files_list_in_path)
        self.gitlab_downloader.get_main_file = Mock(return_value=main_file_info)
        self.gitlab_downloader._build_url_to_download_single_file = Mock()

        file_name = Mock()
        file_txt = Mock()
        self.gitlab_downloader._download_single_file = Mock(return_value=(file_name, file_txt))

        url = 'https://gitlab.com/api/v4/projects/21915601/repository/files/test_dir/?ref=master'

        # act
        result = self.gitlab_downloader.download(url, Mock())

        # assert
        self.assertEqual(result.main_script.name, file_name)
        self.assertEqual(result.main_script.text, file_txt)
        self.assertEqual(len(result.additional_files), 2)
        self.gitlab_downloader._build_url_to_download_single_file.assert_has_calls([call(ANY, files_list_in_path[0]),
                                                                               call(ANY, files_list_in_path[1])])


    @skip
    def test_integration_download_folder(self):
        token = 'FvUPwseibwU8fxJ469Z_'
        auth = Mock(password=token)

        self.gitlab_downloader.download('https://gitlab.com/api/v4/projects/21915601/repository/files/test_dir', auth)

        # example_response = '[{"id":"bc7527545915f1c5268dbef625eb1664a20d9d00","name":"test_dir","type":"tree","path":"test_dir","mode":"040000"},{"id":"3441bff973b1ea0f124c1a7dfac7e835e7f82bae","name":"README.md","type":"blob","path":"README.md","mode":"100644"},{"id":"58e4c32f3c1b84e80b1c5fa44f0cc61e2a0af869","name":"bla1.ps1","type":"blob","path":"bla1.ps1","mode":"100644"},{"id":"88ffb70e9a3a29a36f99531cb5c1c48dfb5e6f93","name":"bla2.ps1","type":"blob","path":"bla2.ps1","mode":"100644"}]'
