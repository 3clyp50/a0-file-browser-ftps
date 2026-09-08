from helpers.extension import Extension
from usr.plugins.file_browser_ftps.backend import Provider


class Register(Extension):
    def execute(self, providers, **kwargs):
        providers[Provider.id] = Provider()
