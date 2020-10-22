class ScriptFile(object):
    def __init__(self, name=None, text=None):
        self.name = name
        self.text = text


class ScriptsData(object):
    def __init__(self, main_script, additional_files=None):
        """
        :param ScriptFile main_script:
        :param list[ScriptFile] additional_files:
        """
        self.main_script = main_script
        self.additional_files = additional_files
