import base64
import collections
import json
import re
import urllib

import requests
from urlparse import urlparse, parse_qs

from cloudshell.cm.customscript.domain.exceptions import FileTypeNotSupportedError
from cloudshell.cm.customscript.domain.script_file import ScriptFile, ScriptsData
from cloudshell.cm.customscript.domain.cancellation_sampler import CancellationSampler

GitLabFileData = collections.namedtuple('GitLabFileData', 'project_id file_path ref base_url')


class GitLabScriptDownloader(object):
    GITLAB_REP_FILES_API_PATTERN = "^https://.+?/api/v4/projects/(?P<project_id>.+?)/repository/files/(?P<file_path>.*?)$"

    # todo - add support for cancellations
    def __init__(self, logger, allowed_filename_pattern, cancel_sampler):
        """
        :type logger: Logger
        :type allowed_filename_pattern: str
        :type cancel_sampler: CancellationSampler
        """
        self.logger = logger
        self.filename_pattern = allowed_filename_pattern
        self.cancel_sampler = cancel_sampler

    def download(self, url, auth):
        """
        :type url: str
        :type auth: HttpAuth
        :rtype: ScriptsData
        """
        self._validate_gitlab_url(url)
        url_data = self._extract_data_from_url(url)

        if self.is_url_to_file(url_data.file_path):
            self.logger.info('We got a URL to a file directly, will download single file')
            file_name, file_txt = self._download_single_file(auth, url)
            self.logger.info('Done')
            return ScriptsData(main_script=ScriptFile(file_name, file_txt))

        else:
            # download all files in folder
            self.logger.info('URL is not for a direct file, will try to treat as a dir')

            # 1. list files in repo
            files_list_in_path = self._get_list_of_files_in_path(auth, url_data)

            # 2. filter out junk files from list
            files_list_in_path = self._remove_junk_files_and_folders_from_files_list(files_list_in_path)

            # 3. get & verify main.ps1/sh/bash exists
            main_file_info = self.get_main_file(files_list_in_path)

            # 4. download main file
            main_file_url = self._build_url_to_download_single_file(url_data, main_file_info)
            self.logger.info('Downloading main file {} from {}'.format(main_file_info['name'], main_file_url))
            main_file_name, main_file_txt = self._download_single_file(auth, main_file_url)
            self.logger.info('Done downloading main file')

            # 5. download additional files
            # todo: download in parallel
            additional_files = []
            for file_info in files_list_in_path:
                # ignore main file
                if file_info['name'] == main_file_info['name']:
                    continue

                file_url = self._build_url_to_download_single_file(url_data, file_info)
                self.logger.info('Downloading single file {} from {}'.format(file_info['name'], file_url))
                file_name, file_txt = self._download_single_file(auth, file_url)
                additional_files.append(ScriptFile(name=file_name, text=file_txt))
                self.logger.info('Done downloading file {}'.format(file_name))

            return ScriptsData(ScriptFile(main_file_name, main_file_txt), additional_files)

    def _get_list_of_files_in_path(self, auth, url_data):
        list_folder_url = self._build_url_to_list_files_in_path(url_data)
        self.logger.info('Requesting list of file in directory. API request: {}'.format(list_folder_url))
        response = requests.get(list_folder_url, headers=self._get_auth_header(auth))
        files_list_in_path = json.loads(response.text)
        self._validate_response_list_files(response)
        self.logger.info('Done getting list of files in dir')

        self.cancel_sampler.throw_if_canceled()

        return files_list_in_path

    def _download_single_file(self, auth, url):
        # download file in URL directly
        self.logger.info('Downloading file from {}'.format(url))
        response = requests.get(url, headers=self._get_auth_header(auth))
        json_response = json.loads(response.text)

        self._validate_response_single_file(response)

        # get file name and validate
        file_name = self._get_file_name_from_gitlab_response(json_response)
        self.logger.info('Downloaded file name: {}'.format(file_name))

        # get file content
        content_bytes = base64.b64decode(json_response['content'])
        file_txt = content_bytes.decode('ascii')

        self.cancel_sampler.throw_if_canceled()

        return file_name, file_txt

    def _remove_junk_files_and_folders_from_files_list(self, files_list_in_path):
        approved_files = []
        for item in files_list_in_path:
            if item['type'] == 'blob' and not item['name'].startswith('.') and not item['name'] == 'README.md':
                approved_files.append(item)
        return approved_files

    def get_main_file(self, files_list_in_path):
        for item in files_list_in_path:
            m = re.match("^main\.(sh|bash|ps1)$", item['name'])
            if m:
                return item

        raise Exception("Main file doesn't exist. When providing url to directory a script file with the "
                        "name main.ps1|main.sh|main.bash must exist in the folder.")

    def _validate_response_list_files(self, response):
        if response.status_code < 200 or response.status_code > 300:
            raise Exception('Failed to list files in path: ' + str(response.status_code) + ' ' + response.reason +
                            '. Please make sure the URL is valid, and the credentials are correct.')

    def _validate_response_single_file(self, response):
        if response.status_code < 200 or response.status_code > 300:
            raise Exception('Failed to download script file: '+str(response.status_code)+' '+response.reason+
                            '. Please make sure the URL is valid, and the credentials are correct.')

    def _build_url_to_download_single_file(self, url_data, main_file_info):
        # need to url encode the file path
        file_path_encoded = urllib.quote(main_file_info['path'], safe='')
        download_file_url = '{base_url}/api/v4/projects/{id}/repository/files/{file_path}'.format(
            base_url=url_data.base_url, id=url_data.project_id, file_path=file_path_encoded)

        request_vars = {'ref': url_data.ref if url_data.ref else 'master'}
        query_string = urllib.urlencode(request_vars)
        if query_string:
            download_file_url = download_file_url + '?' + query_string

        return download_file_url

    def _build_url_to_list_files_in_path(self, url_data):
        list_folder_url = '{base_url}/api/v4/projects/{id}/repository/tree'.format(
            base_url=url_data.base_url, id=url_data.project_id)
        request_vars = {'per_page': 100}
        if url_data.ref:
            request_vars['ref'] = url_data.ref
        if url_data.file_path:
            request_vars['path'] = url_data.file_path
        query_string = urllib.urlencode(request_vars)
        if query_string:
            list_folder_url = list_folder_url + '?' + query_string

        return list_folder_url

    def _get_auth_header(self, auth):
        return {'PRIVATE-TOKEN': auth.password}

    def _get_file_name_from_gitlab_response(self, json_response):
        file_name = json_response['file_name']
        matching = re.match(self.filename_pattern, file_name)
        if not matching:
            raise FileTypeNotSupportedError()

        return file_name

    def _extract_data_from_url(self, url):
        """
        :param str url:
        :rtype: GitLabFileData
        """
        matching = re.match(self.GITLAB_REP_FILES_API_PATTERN, url)
        if matching:
            matched_groups = matching.groupdict()
            project_id = matched_groups['project_id']

            file_path_raw = matched_groups['file_path']
            file_path = file_path_raw.split('?')[0]

            parsed_url = urlparse(url)
            params = parse_qs(parsed_url.query)
            ref = params.get('ref', None)
            if isinstance(ref, list):
                ref = ref[0]
            base_url = '{}://{}'.format(parsed_url.scheme, parsed_url.netloc)

            return GitLabFileData(project_id, file_path, ref, base_url)
        else:
            self._raise_url_syntax_error()

    def is_url_to_file(self, file_path):
        """
        :param str file_path:
        :rtype: bool
        """
        # get only file name and remove any folders in path
        file_name = file_path.split('/')[-1]

        # match to allowed file names pattern
        return re.match(self.filename_pattern, file_name)

    def _validate_gitlab_url(self, url):
        matching = re.match(self.GITLAB_REP_FILES_API_PATTERN, url)
        if not matching:
            self._raise_url_syntax_error()

    def _raise_url_syntax_error(self):
        raise ValueError("Provided GitLab URL is not in the correct format. "
                         "Expected format is the GitLab API syntax. "
                         "Example: 'https://*/api/v4/projects/:id/repository/files/:file_path?ref=master'")
