
class Any(object):
    def __init__(self, predicate=None):
        self.predicate = predicate
    def __eq__(self, other):
        return not self.predicate or self.predicate(other)

def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code, headers):
            self.json_data = json_data
            self.status_code = status_code
            self.headers = headers
            self.url = 'https://raw.githubusercontent.com/SomeUser/SomePublicRepo/master/bashScript.sh'

        
        def json(self):
            return self.json_data

    if args[0] == 'https://raw.githubusercontent.com/SomeUser/SomePublicRepo/master/bashScript.sh':
        return MockResponse("SomeBashScriptContent", 200, {"header1": "value1"})
    elif args[0] == 'http://someotherurl.com/anothertest.json':
        return MockResponse({"key2": "value2"}, 200)

    return MockResponse(None, 404)