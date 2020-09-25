import base64
import json
import urllib
from logging import Logger

import re
import requests

from cloudshell.cm.customscript.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.customscript.domain.script_file import ScriptFile


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
        self.filename_pattern = "(?P<filename>\s*[\w,\s-]+\.(sh|bash|ps1)\s*)"
        self.filename_patterns = {
            "content-disposition": "\s*((?i)inline|attachment|extension-token)\s*;\s*filename=" + self.filename_pattern,
            "x-artifactory-filename": self.filename_pattern
        }

    def download(self, url, auth):
        """
        :type url: str
        :type auth: HttpAuth
        :rtype ScriptFile
        """
        if auth.username == "GITLAB":
            response = requests.get(url, headers={'PRIVATE-TOKEN': auth.password})
            json_response = json.loads(response.text)
            # get file name and validate
            file_name = self._get_file_name_gitlab(json_response)
            # get file content
            content_bytes = base64.b64decode(json_response['content'])
            file_txt = content_bytes.decode('ascii')
        else:
            response = requests.get(url, auth=(auth.username, auth.password) if auth else None, stream=True)
            file_name = self._get_filename(response)
            file_txt = ''

            for chunk in response.iter_content(ScriptDownloader.CHUNK_SIZE):
                if chunk:
                    file_txt += ''.join(chunk)
                self.cancel_sampler.throw_if_canceled()

        self._validate_response(response, file_txt)

        return ScriptFile(name=file_name, text=file_txt)

    def _get_file_name_gitlab(self, json_response):
        file_name = json_response['file_name']
        matching = re.match(self.filename_pattern, file_name)
        if not matching:
            self._raise_file_name_not_valid(file_name)
        return file_name

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
            self._raise_file_name_not_valid(file_name)
        return file_name.strip()

    def _raise_file_name_not_valid(self, file_name):
        raise Exception("Script file of supported types: '.sh', '.bash', '.ps1' was not found")
