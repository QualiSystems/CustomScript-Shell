import json
import numbers


class ScriptConfiguration(object):
    def __init__(self, script_repo = None, host_conf = None, timeout_minutes = None, print_output = True):
        """
        :type script_repo: ScriptRepository
        :type host_conf: HostConfiguration
        :type timeout_minutes: float
        :type print_output: bool
        """
        self.timeout_minutes = timeout_minutes or 0.0
        self.script_repo = script_repo or ScriptRepository()
        self.host_conf = host_conf or HostConfiguration()
        self.print_output = print_output
        self.verify_certificate = True


class ScriptRepository(object):
    def __init__(self):
        self.url = None
        self.username = None
        self.password = None
        self.token = None


class HostConfiguration(object):
    def __init__(self):
        self.ip = None
        self.connection_method = None
        self.connection_secured = None
        self.username = None
        self.password = None
        self.access_key = None
        self.parameters = {}


class ScriptConfigurationParser(object):

    def __init__(self, api):
        """
        :type api: CloudShellAPISession
        """
        self.api = api

    def json_to_object(self, json_str):
        """
        Decodes a json string to an ScriptConfigurationParser instance.
        :type json_str: str
        :rtype ScriptConfiguration
        """
        json_obj = json.loads(json_str)
        ScriptConfigurationParser._validate(json_obj)

        script_conf = ScriptConfiguration()
        script_conf.timeout_minutes = json_obj.get('timeoutMinutes', 0.0)
        script_conf.print_output = bool_parse(json_obj.get('printOutput', True))
        script_conf.verify_certificate = json_obj.get('verifyCertificate', 'true').lower()=='true'

        repo = json_obj['repositoryDetails']
        script_conf.script_repo.url = repo.get('url')
        script_conf.script_repo.username = repo.get('username')
        script_conf.script_repo.password = repo.get('password')
        script_conf.script_repo.token = repo.get('token')

        host = json_obj['hostsDetails'][0]
        script_conf.host_conf = HostConfiguration()
        script_conf.host_conf.ip = host.get('ip')
        script_conf.host_conf.connection_method = host['connectionMethod'].lower()
        script_conf.host_conf.connection_secured = bool_parse(host.get('connectionSecured'))
        script_conf.host_conf.username = host.get('username')
        script_conf.host_conf.password = self._get_password(host)
        script_conf.host_conf.access_key = self._get_access_key(host)
        if host.get('parameters'):
            script_conf.host_conf.parameters = dict((i['name'], i['value']) for i in host['parameters'])

        return script_conf

    def _get_password(self, json_host):
        pw = json_host.get('password')
        if pw:
            return self.api.DecryptPassword(pw).Value
        else:
            return pw

    def _get_access_key(self, json_host):
        key = json_host.get('accessKey')
        if key:
            return self.api.DecryptPassword(key).Value
        else:
            return key

    @staticmethod
    def _validate(json_obj):
        """
        :type json_obj: json
        :rtype bool
        """
        basic_msg = 'Failed to parse script configuration input json: '

        if json_obj.get('timeoutMinutes'):

            if not isinstance(json_obj.get('timeoutMinutes'), numbers.Number):
                raise SyntaxError(basic_msg + 'Node "timeoutMinutes" must be numeric type.')

            if json_obj.get('timeoutMinutes') < 0:
                raise SyntaxError(basic_msg + 'Node "timeoutMinutes" must be greater/equal to zero.')

        if json_obj.get('repositoryDetails') is None:
            raise SyntaxError(basic_msg + 'Missing "repositoryDetails" node.')

        if not json_obj.get('repositoryDetails').get('url'):
            raise SyntaxError(basic_msg + 'Missing/Empty "repositoryDetails.url" node.')

        if not json_obj.get('hostsDetails'):
            raise SyntaxError(basic_msg + 'Missing/Empty "hostsDetails" node.')

        if len(json_obj.get('hostsDetails')) > 1:
            raise SyntaxError(basic_msg + 'Node "hostsDetails" must contain only one item.')

        if not json_obj.get('hostsDetails')[0].get('ip'):
            raise SyntaxError(basic_msg + 'Missing/Empty "hostsDetails[0].ip" node.')

        if not json_obj.get('hostsDetails')[0].get('connectionMethod'):
            raise SyntaxError(basic_msg + 'Missing/Empty "hostsDetails[0].connectionMethod" node.')


def bool_parse(b):
    if b is None:
        return None
    else:
        return str(b).lower() == 'true'