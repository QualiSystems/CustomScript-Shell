class FileTypeNotSupportedError(Exception):
    def __init__(self):
        self.message = "Script file of supported types: '.sh', '.bash', '.ps1' was not found"
        super(FileTypeNotSupportedError, self).__init__(self.message)