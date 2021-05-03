import urllib.request, urllib.parse, urllib.error
from logging import Logger

import re
import requests

from cloudshell.cm.customscript.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.customscript.domain.script_file import ScriptFile
from requests.models import HTTPBasicAuth


class HttpAuth(object):
    def __init__(self, username, password, token):
        self.username = username
        self.password = password
        self.token = token


class ScriptDownloader(object):
    CHUNK_SIZE = 1024 * 1024

    def __init__(self, logger, cancel_sampler):
        """
        :type logger: Logger
        :type cancel_sampler: CancellationSampler
        """
        self.logger = logger
        self.cancel_sampler = cancel_sampler        
        self.filename_pattern = r"(?P<filename>^.*\.?[^/\\&\?]+\.(sh|bash|ps1)(?=([\?&].*$|$)))" #this regex is to extract the filename from the url, works for cases: filename is at the end, parameter token is at the end
        self.filename_patterns = {
            "content-disposition": "\s*((?i)inline|attachment|extension-token)\s*;\s*filename=" + self.filename_pattern,
            "x-artifactory-filename": self.filename_pattern
        }


    def download(self, url, auth, verify_certificate):
        """
        :type url: str
        :type auth: HttpAuth
        :rtype ScriptFile
        """
        file_txt = ''
        response_valid = False

        # assume repo is public, try to download without credentials
        self.logger.info("Starting download script as public...")
        if not verify_certificate:
            self.logger.info("Skipping server certificate")
        response = requests.get(url, auth=None, stream=True, verify=verify_certificate)
        response_valid = self._is_response_valid(response, "public")

        if response_valid:
            file_name = self._get_filename(response)

        # if fails on public and no auth - no point carry on, user need to fix his URL or add credentials
        if not response_valid and auth is None:
            raise Exception('Please make sure the URL is valid, and the credentials are correct and necessary.')

        # repo is private and token provided
        if not response_valid and auth.token is not None:
            self.logger.info("Token provided. Starting download script with Token...")
            headers = {"Authorization": "Bearer %s" % auth.token }
            response = requests.get(url, stream=True, headers=headers, verify=verify_certificate)
            
            response_valid = self._is_response_valid(response, "Token")

            if response_valid:
                file_name = self._get_filename(response)
        
        # try again with authorization {"Private-Token": "%s" % token}, since gitlab uses that pattern
        if not response_valid and auth.token is not None:
            self.logger.info("Token provided. Starting download script with Token (private-token pattern)...")
            headers = {"Private-Token": "Bearer %s" % auth.token }
            response = requests.get(url, stream=True, headers=headers, verify=verify_certificate)
            
            response_valid = self._is_response_valid(response, "Token")

            if response_valid:
                file_name = self._get_filename(response)

        # repo is private and credentials provided, and Token did not provided or did not work. this will NOT work for github. github require Token
        if not response_valid and (auth.username is not None and auth.password is not None):
            self.logger.info("username\password provided, Starting download script with username\password...")
            response = requests.get(url, auth=(auth.username, auth.password) , stream=True, verify=verify_certificate)
            file_name = self._get_filename(response)

            response_valid = self._is_response_valid(response, "username\password")

            if response_valid:
                file_name = self._get_filename(response)

        if not response_valid:
            raise Exception('Failed to download script file. please check the logs for more details.')

        for chunk in response.iter_content(ScriptDownloader.CHUNK_SIZE):
            if chunk:
                file_txt += ''.join(str(chunk.decode()))
            self.cancel_sampler.throw_if_canceled()

        self._validate_file(file_txt)

        return ScriptFile(name=file_name, text=file_txt)
    
    def _is_response_valid(self, response, request_method):
        try:
            self._validate_response(response)
            response_valid = True
        except Exception as ex:
            failure_message = "failed to Authorize repository with %s" % request_method
            self.logger.error(failure_message + " :" + str(ex))
            response_valid = False

        return response_valid

    def _validate_file(self, content):
        if content.lstrip('\n\r').lower().startswith('<!doctype html>'):
            raise Exception('Failed to download script file: url points to an html file')

    def _validate_response(self, response):
        if response.status_code < 200 or response.status_code > 300:            
            raise Exception('Failed to download script file: '+str(response.status_code)+' '+response.reason+
                              '. Please make sure the URL is valid, and the credentials are correct and necessary.')

    def _get_filename(self, response):
        file_name = None
        for header_value, pattern in self.filename_patterns.items():
            matching = re.match(pattern, response.headers.get(header_value, ""))
            if matching:
                file_name = matching.group('filename')
                break

        # fallback, couldn't find file name from header, get it from url
        if not file_name:
            file_name_from_url = urllib.parse.unquote(response.url[response.url.rfind('/') + 1:])
            matching = re.match(self.filename_pattern, file_name_from_url)
            if matching:
                file_name = matching.group('filename')

        # fallback, couldn't find file name regular URL, check gitlab structure (filename in [-2] position)
        # example for gitlab URL structure - '/repository/files/testfile%2Eps1/raw?ref=master'
        if not file_name:
            file_name_from_url = urllib.parse.unquote(response.url.split('/')[-2])
            matching = re.match(self.filename_pattern, file_name_from_url)
            if matching:
                file_name = matching.group('filename')

        if not file_name:
            raise Exception("Script file of supported types: '.sh', '.bash', '.ps1' was not found")
        return file_name.strip()