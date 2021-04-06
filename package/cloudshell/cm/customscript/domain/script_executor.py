import os
from abc import abstractmethod, ABCMeta

from cloudshell.cm.customscript.domain.script_file import ScriptFile


class IScriptExecutor(object, metaclass=ABCMeta):
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def get_expected_file_extensions(self):
        """
        :rtype list[str]
        """
        pass

    @abstractmethod
    def execute(self, script_file, env_vars, output_writer, print_output):
        """
        :type script_file: ScriptFile
        :type output_writer: ReservationOutputWriter
        """
        pass


class ErrorMsg(object):
    CREATE_TEMP_FOLDER = 'Failed to create temp folder on target machine. Error: ' + os.linesep + '%s'
    DELETE_TEMP_FOLDER = 'Failed to delete the temp folder from target machine. Error: ' + os.linesep + '%s'
    COPY_SCRIPT = 'Failed to copy the script to target machine. Error: ' + os.linesep + '%s'
    RUN_SCRIPT = 'Failed to run the script on target machine. Error: ' + os.linesep + '%s'


class ExcutorConnectionError(EnvironmentError):
    def __init__(self, error_code, inner_error):
        self.errno = error_code
        self.inner_error = inner_error
