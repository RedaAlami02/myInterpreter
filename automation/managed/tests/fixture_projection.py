"""In-memory transport fixtures; these identities are deliberately invented."""
URL = "https://" + "a" * 20 + ".supabase.co/functions/v1/private-projection-publisher"
TOKEN = "proj_publish_" + "a" * 64


class Response:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, size=1024):
        yield self.body


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **options):
        self.calls.append((url, options))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
