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

GitHubFileData = collections.namedtuple('GitHubFileData', 'account_id repo_id branch_id path api_dl_url')

class GitHubScriptDownloader(object):
    GITHUB_REP_FILES_API_PATTERN = "^https://.+?/(?P<account_id>.+?)/(?P<repo_id>.+?)/blob/(?P<branch_id>.+?)/(?P<path>.*?)$"

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
        self._validate_github_url(url)
        url_data = self._extract_data_from_url(url)

        if self.is_url_to_file(url_data.path):
            self.logger.info('We got a URL to a file directly,'
                             ' will download single file')
            self.logger.info('api_dl_url='+url_data.api_dl_url)
            file_name, file_txt = self._download_single_file(auth, url_data.api_dl_url)
            self.logger.info('Done')
            return ScriptsData(main_script=ScriptFile(file_name, file_txt))
        else:
            self.logger.info('URL is not for a direct file, dir option (multiple files) is not currently supported')

    def _download_single_file(self, auth, url):
        # download file in URL directly
        self.logger.info('Downloading file from {}'.format(url))
        response = requests.get(url, headers=self._get_auth_header(auth))
        self.logger.info("Response status code from download file {} was {}".format(url,response.status_code))
        json_response = json.loads(response.text)

        self._validate_response_single_file(response)

        # get file name and validate
        file_name = self._get_file_name_from_github_response(json_response)
        self.logger.info('Downloaded file name: {}'.format(file_name))

        # get file content
        file_txt = base64.b64decode(json_response['content'])

        self.cancel_sampler.throw_if_canceled()

        return file_name, file_txt

    def _validate_response_single_file(self, response):
        if response.status_code < 200 or response.status_code > 300:
            raise Exception('Failed to download script file: '+str(response.status_code)+' '+response.reason+
                            '. Please make sure the URL is valid, and the credentials are correct.')

    def _get_auth_header(self, auth):
        return {'Authorization': 'token ' + auth.password}

    def _get_file_name_from_github_response(self, json_response):
        file_name = json_response['path']
        if file_name[-1] != "/":
            file_name = file_name.split("/")[-1]
        matching = re.match(self.filename_pattern, file_name)
        if not matching:
            raise FileTypeNotSupportedError()

        return file_name

    def _extract_data_from_url(self, url):
        """
        :param str url:
        :rtype: GitHubFileData
        """
        matching = re.match(self.GITHUB_REP_FILES_API_PATTERN, url)
        if matching:

            matched_groups = matching.groupdict()

            account_id = matched_groups['account_id']
            repo_id = matched_groups['repo_id']
            branch_id = matched_groups['branch_id']
            path = matched_groups['path']

            parsed_url = urlparse(url)
            api_dl_url = '{}://api.{}/repos/{}/{}/contents/{}'.format(parsed_url.scheme, parsed_url.netloc,account_id,repo_id,path)
            self.logger.info('API Call will use the following address {}'.format(api_dl_url))
            return GitHubFileData(account_id, repo_id,branch_id,path, api_dl_url)
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

    def _validate_github_url(self, url):
        matching = re.match(self.GITHUB_REP_FILES_API_PATTERN, url)
        if not matching:
            self._raise_url_syntax_error()

    def _raise_url_syntax_error(self):
        raise ValueError("Provided GitHub URL is not in the correct format. "
                         "Expected format is the GitHub API syntax. "
                         "Example: 'https://github.com/:account_id/:repo/blob/:branch/:path'")