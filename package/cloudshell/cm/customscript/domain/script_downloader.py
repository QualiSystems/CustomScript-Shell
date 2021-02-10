import base64
import json
import urllib
from logging import Logger

import re
import requests

from cloudshell.cm.customscript.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.customscript.domain.exceptions import FileTypeNotSupportedError
from cloudshell.cm.customscript.domain.gitlab_script_downloader import GitLabScriptDownloader
from cloudshell.cm.customscript.domain.github_script_downloader import GitHubScriptDownloader
from cloudshell.cm.customscript.domain.script_file import ScriptFile, ScriptsData

ALLOWED_FILES_PATTERN = "(?P<filename>\s*[\w,\s-]+\.(sh|bash|ps1)\s*)"


class HttpAuth(object):
    def __init__(self, username, password):
        self.username = username
        self.password = password


class ScriptDownloader(object):
    CHUNK_SIZE = 1024 * 1024

    def __init__(self, logger, cancel_sampler):
        """
        :type logger: Logger
        :type cancel_sampler: CancellationSampler
        """
        self.logger = logger
        self.cancel_sampler = cancel_sampler
        self.filename_pattern = ALLOWED_FILES_PATTERN
        self.filename_patterns = {
            "content-disposition": "\s*((?i)inline|attachment|extension-token)\s*;\s*filename=" + self.filename_pattern,
            "x-artifactory-filename": self.filename_pattern
        }

    def download(self, url, auth):
        """
        :type url: str
        :type auth: HttpAuth
        :rtype: ScriptsData
        """
        # identify download strategy
        if auth.username in ['GITLAB','GITHUB']:
            if auth.username == 'GITLAB':
                # GitLab strategy
                scripts_data = GitLabScriptDownloader(self.logger, ALLOWED_FILES_PATTERN, self.cancel_sampler)\
                    .download(url, auth)

            if auth.username == 'GITHUB':
                # GitLab strategy
                scripts_data = GitHubScriptDownloader(self.logger, ALLOWED_FILES_PATTERN, self.cancel_sampler) \
                    .download(url, auth)

        else:
            # http with basic auth strategy
            response = requests.get(url, auth=(auth.username, auth.password) if auth else None, stream=True)
            file_name = self._get_filename(response)
            file_txt = ''

            for chunk in response.iter_content(ScriptDownloader.CHUNK_SIZE):
                if chunk:
                    file_txt += ''.join(chunk)
                self.cancel_sampler.throw_if_canceled()

            self._validate_response(response, file_txt)

            scripts_data = ScriptsData(ScriptFile(name=file_name, text=file_txt))

        return scripts_data

    def _validate_response(self, response, content):
        if response.status_code < 200 or response.status_code > 300:
            raise Exception('Failed to download script file: '+str(response.status_code)+' '+response.reason+
                            '. Please make sure the URL is valid, and the credentials are correct and necessary.')

        if content.lstrip('\n\r').lower().startswith('<!doctype html>'):
            raise Exception('Failed to download script file: url points to an html file')

    def _get_filename(self, response):
        file_name = None
        for header_value, pattern in self.filename_patterns.iteritems():
            matching = re.match(pattern, response.headers.get(header_value, ""))
            if matching:
                file_name = matching.group('filename')
                break
        # fallback, couldn't find file name from header, get it from url
        if not file_name:
            file_name_from_url = urllib.unquote(response.url[response.url.rfind('/') + 1:])
            matching = re.match(self.filename_pattern, file_name_from_url)
            if matching:
                file_name = matching.group('filename')
        if not file_name:
            raise FileTypeNotSupportedError()
        return file_name.strip()
