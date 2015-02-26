from __future__ import print_function
from .utils import load_fixture


class MockRemote(object):
    """Replacement for L{oscqam.models.Remote} that maps HTTP requests to
    file-paths.

    The mapping between a request and filepath is determined by the requested
    URL: the last part of the url is expected to be the identifier, the
    previous part to the object-type.

    Files should be named accordingly: {object_type}_{identifier}.xml

    """
    def __init__(self):
        self.post_calls = []

    def _load(self, prefix, id):
        name = "%s_%s.xml" % (prefix, id)
        return load_fixture(name)

    def get(self, *args, **kwargs):
        """Replacement for HTTP-get requests.

        Special handling for groups, as it does not use an identifier as part
        of the URL.
        """
        try:
            cls, identifier = args[0].split("/")
        except ValueError:
            if args[0] == 'group':
                cls = 'group'
                identifier = args[1]['login']
            else:
                raise
        return self._load(cls, identifier)

    def post(self, *args, **kwargs):
        called = "Call-Args: %s. Call-Kwargs: %s" % (args, kwargs)
        self.post_calls.append(called)
