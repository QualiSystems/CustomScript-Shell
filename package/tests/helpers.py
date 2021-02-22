class Any(object):
    def __init__(self, predicate=None):
        self.predicate = predicate
    def __eq__(self, other):
        return not self.predicate or self.predicate(other)

def mocked_requests_get(*args, **kwargs):
    '''
    Helper method for mocking requests for test_script_downloader
    '''
    repo_dict = {
        "public": 'https://raw.repocontentservice.com/SomeUser/SomePublicRepo/master/bashScript.sh', 
        "private_token": 'https://raw.repocontentservice.com/SomeUser/SomePrivateTokenRepo/master/bashScript.sh',
        "private_cred": 'https://raw.repocontentservice.com/SomeUser/SomePrivateCredRepo/master/bashScript.sh',
        "content": 'SomeBashScriptContent'
    }

    class MockResponse:
        def __init__(self, json_data, status_code, headers, url):
            self.json_data = json_data
            self.status_code = status_code
            self.headers = headers
            self.url = url
        
        def json(self):
            return self.json_data

        def iter_content(self, chunk):
            return self.json_data

    if args[0] == repo_dict['public']:
        response = MockResponse(repo_dict['content'], 200, {"Content-Type": "text/plain"}, repo_dict['public'])
        return response
    
    if args[0] == repo_dict['private_token']:
        if 'headers' in kwargs:
            if kwargs["headers"]["Authorization"] == 'Bearer 551e48b030e1a9f334a330121863e48e43f58c55':
                response = MockResponse(repo_dict['content'], 200, {"Content-Type": "text/plain"}, repo_dict['private_token'])
                return response

    if args[0] == repo_dict['private_cred']:
        if 'auth' in kwargs and kwargs["auth"] is not None:
            if kwargs["auth"][0] == 'SomeUser' and kwargs["auth"][1] == 'SomePassword':
                response = MockResponse(repo_dict['content'], 200, {"Content-Type": "text/plain"}, repo_dict['private_cred'])
                return response

    return MockResponse(None, 404, None, None)