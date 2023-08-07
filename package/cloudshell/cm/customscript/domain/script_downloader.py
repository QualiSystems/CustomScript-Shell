import logging
import urllib.request
import urllib.parse
import urllib.error
import re
import requests

from cloudshell.cm.customscript.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.customscript.domain.script_file import ScriptFile


class HttpAuth(object):
    def __init__(self, username, password, token):
        self.username = username
        self.password = password
        self.token = token


class ScriptDownloader(object):
    CHUNK_SIZE = 1024 * 1024
    GITLAB_API_TEMPLATE = "{protocol}://{domain}/api/v4/projects/{project}/repository/files/{file_path}/raw"

    def __init__(self, logger, cancel_sampler):
        """
        :type logger: Logger
        :type cancel_sampler: CancellationSampler
        """
        self.logger = logger
        self.cancel_sampler = cancel_sampler        
        self.filename_pattern = r"(?P<filename>^.*\.?[^/\\&\?]+\.(sh|bash|ps1)(?=([\?&].*$|$)))"  # this regex is to extract the filename from the url, works for cases: filename is at the end, parameter token is at the end
        self.filename_patterns = {
            "content-disposition": "\s*((?i)inline|attachment|extension-token)\s*;\s*filename=" + self.filename_pattern,
            "x-artifactory-filename": self.filename_pattern
        }

    def download(self, url, auth, verify_certificate):
        """ Download script file.
        :type url: str
        :type auth: HttpAuth
        :rtype ScriptFile
        """
        self.logger.debug("URL: {}".format(url))
        self.logger.debug("Verify Certificate: {}".format(verify_certificate))
        self.logger.debug("Username: {}".format(auth.username))
        # self.logger.debug("Password: {}".format(auth.password))
        # self.logger.debug("Token: {}".format(auth.token))

        if not verify_certificate:
            self.logger.info("Skipping server certificate")

        if auth and auth.token:
            # GitLab uses {"Private-Token": token}
            self.logger.info(
                "Token provided. Starting download script with Private-Token ..."
            )
            gitlab_api_url = self._convert_gitlab_url(url=url)
            if gitlab_api_url:
                headers = {"Private-Token": auth.token}
                response = requests.get(
                    gitlab_api_url,
                    stream=True,
                    headers=headers,
                    verify=verify_certificate
                )
                response_valid = self._is_response_valid(response, "Token")
            else:
                # cannot assemble GitLab API URL that means it's not GitLab
                response_valid = False

            if not response_valid and auth.token is not None:
                self.logger.info(
                    "Token provided. Starting download script with Bearer Token..."
                )
                headers = {"Authorization": "Bearer {}".format(auth.token)}
                response = requests.get(
                    url,
                    stream=True,
                    headers=headers,
                    verify=verify_certificate,
                    allow_redirects=False
                )
                while response.status_code == 302:
                    response = requests.get(
                        response.headers["location"],
                        stream=True,
                        headers=headers,
                        verify=verify_certificate,
                        allow_redirects=False
                    )

                response_valid = self._is_response_valid(response, "Token")

        elif auth and auth.username and auth.password is not None:
            self.logger.info(
                "Username and Password provided. "
                "Starting download script with username/password..."
            )
            response = requests.get(
                url,
                auth=(auth.username, auth.password),
                stream=True,
                verify=verify_certificate
            )
            response_valid = self._is_response_valid(response, "Username/Password")

        else:
            self.logger.info("Starting download script as public...")
            response = requests.get(
                url,
                auth=None,
                stream=True,
                verify=verify_certificate
            )
            response_valid = self._is_response_valid(response, "Public")

        if response_valid:
            file_name = self._get_filename(response)
        else:
            raise Exception(
                "Failed to download script file. "
                "Please make sure the URL is valid, "
                "and the credentials are correct and necessary."
            )

        file_txt = ""
        for chunk in response.iter_content(ScriptDownloader.CHUNK_SIZE):
            if chunk:
                file_txt += "".join(str(chunk.decode()))
            self.cancel_sampler.throw_if_canceled()

        self._validate_file(file_txt)

        return ScriptFile(name=file_name, text=file_txt)

    def _convert_gitlab_url(self, url):
        """Try to convert URL to Gitlab API URL.

        Input example:
        http://192.168.85.27/api/v4/projects/root%2Fmy_project/repository/files/bash_scripts%2Fsimple%2Ebash/raw?ref=main
        http://192.168.85.27/api/v4/projects/root%2Fmy_project/repository/files/bash_scripts%2Fsimple%2Ebash/raw
        http://192.168.85.27/root/my_project/-/raw/main/bash_scripts/simple.bash
        http://192.168.85.27/root/my_project/-/blob/main/bash_scripts/simple.bash

        Output example:
        http://192.168.85.27/api/v4/projects/root%2Fmy_project/repository/files/bash_scripts%2Fsimple%2Ebash/raw?ref=main

        """
        self.logger.debug("URL to convert: {}".format(url))
        api_url = None
        if "api/v4/projects" in url:
            regex = r"(?P<protocol>https?)://(?P<domain>[^/]+)/api/v4/projects/" \
                    r"(?P<project>.+)/repository/files/(?P<file>.+(sh|bash|ps1))" \
                    r"(.+ref=(?P<branch>[^/]+))?"
        else:
            regex = r"(?P<protocol>https?)://(?P<domain>[^/]+)/(?P<project>.+)/" \
                    r"-/(blob|raw)/(?P<branch>[^/]+)/(?P<file>.+\.(sh|bash|ps1))"

        match = re.search(
            regex,
            url,
            re.IGNORECASE
        )

        if match:
            self.logger.debug("Protocol: {}".format(match.group("protocol")))
            self.logger.debug("Domain: {}".format(match.group("domain")))
            self.logger.debug("Project: {}".format(match.group("project")))
            self.logger.debug("Branch: {}".format(match.group("branch")))
            self.logger.debug("File: {}".format(match.group("file")))
            api_url = self.GITLAB_API_TEMPLATE.format(
                protocol=match.group("protocol"),
                domain=match.group("domain"),
                project=match.group("project").replace("/", "%2F").replace(".", "%2E"),
                branch=match.group("branch"),
                file_path=match.group("file").replace("/", "%2F").replace(".", "%2E")
            )
            if match.group("branch"):
                api_url += "?ref={branch}".format(branch=match.group("branch"))

        self.logger.debug("Possible GitLab API URL: {}".format(api_url))
        return api_url

    def _is_response_valid(self, response, request_method):
        try:
            self._validate_response(response)
            response_valid = True
        except Exception as ex:
            self.logger.error(
                "Failed to Authorize repository with '{method}': {error}".format(
                    method=request_method,
                    error=str(ex)
                )
            )
            response_valid = False

        return response_valid

    def _validate_response(self, response):
        self.logger.debug("Response code: {}".format(response.status_code))
        if response.status_code < 200 or response.status_code > 300:
            raise Exception(
                "Failed to download script file: {code} {reason}."
                "Please make sure the URL is valid,"
                "and the credentials are correct and necessary.".format(
                    code=str(response.status_code),
                    reason=response.reason
                )
            )

    def _validate_file(self, content):
        if content.lstrip("\n\r").lower().startswith("<!doctype html>"):
            raise Exception(
                "Failed to download script file: url points to an html file"
            )

    def _get_filename(self, response):
        file_name = None
        for header_value, pattern in self.filename_patterns.items():
            matching = re.match(pattern, response.headers.get(header_value, ""))
            if matching:
                file_name = matching.group("filename")
                break

        # fallback, couldn't find file name from header, get it from url
        if not file_name:
            file_name_from_url = urllib.parse.unquote(
                response.url[response.url.rfind("/") + 1:]
            )
            matching = re.match(self.filename_pattern, file_name_from_url)
            if matching:
                file_name = matching.group("filename")

        # fallback, couldn't find file name regular URL, check gitlab structure (filename in [-2] position)
        # example for gitlab URL structure - '/repository/files/testfile%2Eps1/raw?ref=master'
        # if not file_name:
        #     file_name_from_url = urllib.parse.unquote(response.url.split("/")[-2])
        #     matching = re.match(self.filename_pattern, file_name_from_url)
        #     if matching:
        #         file_name = matching.group("filename")

        if not file_name:
            self.logger.debug("Response URL: {}".format(response.url))
            unquote_url = urllib.parse.unquote(response.url)
            matching = re.match(r".*/(?P<filename>.+\.(sh|bash|ps1))", unquote_url)
            if matching:
                file_name = matching.group("filename")

        if not file_name:
            raise Exception(
                "Script file of supported types: '.sh', '.bash', '.ps1' was not found"
            )
        return file_name.strip()
