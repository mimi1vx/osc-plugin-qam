"""This module contains all models that are required by the QAM plugin to keep
everything in a consistent state.

"""
import logging
import os
import re
import urllib
try:
    from xml.etree import cElementTree as ET
except ImportError:
    import cElementTree as ET
import osc.core
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class RemoteFacade(object):
    def __init__(self, remote):
        """Initialize a new RemoteOscRemote that points to the given remote.
        """
        self.remote = remote
        
    def get(self, endpoint, callback, params=None):
        """Retrieve information at the given endpoint with the parameters.

        Call the callback function with the result.

        """
        if params:
            params = urllib.urlencode(params)
        url = '/'.join([self.remote, endpoint])
        remote = osc.core.http_GET(url, data=params)
        xml = remote.read()
        return callback(self, xml)


class XmlFactoryMixin(object):
    """Can generate an object from xml by recursively parsing the structure.

    It will set properties to the text-property of a node if there are no
    children.

    Otherwise it will parse the children into another node and set the property
    to a list of these new parsed nodes.
    """
    def __init__(self, remote, attributes, children):
        """Will set every element in kwargs to a property of the class.
        """
        attributes.update(children)
        for kwarg in attributes:
            setattr(self, kwarg, attributes[kwarg])

    @staticmethod
    def listify(dictionary, key):
        """Will wrap an existing dictionary key in a list.
        """
        if not isinstance(dictionary[key], list):
            value = dictionary[key]
            del dictionary[key]
            dictionary[key] = [value]

    @classmethod
    def parse_et(cls, remote, et, tag, wrapper_cls=None):
        """Recursively parses an element-tree instance.

        Will iterate over the tag as root-level.
        """
        if not wrapper_cls:
            wrapper_cls = cls
        objects = []
        for request in et.iter(tag):
            attribs = {}
            for attribute in request.attrib:
                attribs[attribute] = request.attrib[attribute]
            kwargs = {}
            for child in request:
                key = child.tag
                subchildren = list(child)
                if subchildren or child.attrib:
                    # Prevent that all children have the same class as the parent.
                    # This might lead to providing methods that make no sense.
                    value = cls.parse_et(remote, child, key, XmlFactoryMixin)
                    if len(value) == 1:
                        value = value[0]
                else:
                    if child.text:
                        value = child.text.strip()
                    else:
                        value = None
                if key in kwargs:
                    XmlFactoryMixin.listify(kwargs, key)
                    kwargs[key].append(value)
                else:
                    kwargs[key] = value
            kwargs.update(attribs)
            objects.append(wrapper_cls(remote, attribs, kwargs))
        return objects
    
    @classmethod
    def parse(cls, remote, xml, tag):
        root = ET.fromstring(xml)
        return cls.parse_et(remote, root, tag, cls)


class Group(XmlFactoryMixin):
    """A group object from the build service.
    """
    endpoint = 'group'
    
    def __init__(self, remote, attributes, children):
        super(Group, self).__init__(remote, attributes, children)
        self.remote = remote

    @classmethod
    def all(cls, remote):
        group_entries = remote.get(cls.endpoint, Group.parse_entry)
        groups = [Group.for_name(remote, g.name) for g in group_entries]
        return groups

    @classmethod
    def for_name(cls, remote, group_name):
        url = '/'.join([Group.endpoint, group_name])
        group = remote.get(url, Group.parse)
        if group:
            # We set name to title to ensure equality.  This allows us to
            # prevent having to query *all* groups we need via this method,
            # which could use very many requests.
            group[0].name = group[0].title
            return group[0]
        else:
            raise AttributeError(
                "No group found for name: {0}".format(
                    group_name
                )
            )

    @classmethod
    def for_user(cls, remote, user):
        params = {'login': user.login}
        group_entries = remote.get(cls.endpoint, Group.parse_entry, params)
        groups = [Group.for_name(remote, g.name) for g in group_entries]
        return groups

    @classmethod
    def parse(cls, remote, xml):
        return super(Group, cls).parse(remote, xml, 'group')

    @classmethod
    def parse_entry(cls, remote, xml):
        return super(Group, cls).parse(remote, xml, 'entry')

    def __hash__(self):
        # We don't want to hash to the same as only the string.
        return hash(self.name) + hash(type(self))
        
    def __eq__(self, other):
        return self.name == other.name
        
    def __str__(self):
        return self.name

    def __unicode__(self):
        return str(self).encode('utf-8')


class User(XmlFactoryMixin):
    """Wraps a user of the obs in an object.

    """
    endpoint = 'person'
    qam_regex = re.compile(".*qam.*")
    
    def __init__(self, remote, attributes, children):
        super(User, self).__init__(remote, attributes, children)
        self.remote = remote
        self._groups = None
                                    
    @property
    def groups(self):
        """Read-only property for groups a user is part of.
        """
        # Maybe use a invalidating cache as a trade-off between current
        # information and slow response.
        if not self._groups:
            self._groups = Group.for_user(self.remote, self)
        return self._groups

    @property
    def qam_groups(self):
        """Return only the groups that are part of the qam-workflow."""
        return [group for group in self.groups
                if User.qam_regex.match(group.name)]

    def __str__(self):
        return unicode(self)

    def __unicode__(self):
        return u"{0} ({1})".format(self.realname, self.email)

    @classmethod
    def by_name(cls, remote, name):
        url = '/'.join([User.endpoint, name])
        users = remote.get(url, User.parse)
        if users:
            return users[0]
        raise AttributeError("User not found.")

    @classmethod
    def parse(cls, remote, xml):
        return super(User, cls).parse(remote, xml, cls.endpoint)
            

class Request(XmlFactoryMixin):
    endpoint = 'request'

    open_states = ['new', 'review']
    
    def __init__(self, remote, **kwargs):
        super(Request, self).__init__(**kwargs)
        self.remote = remote
        self._groups = None

    def open_reviews(self):
        def name_review(r):
            if r.exists('by_group'):
                r.name = r.by_group
            elif r.exists('by_user'):
                r.name = r.by_user
            elif r.exists('who'):
                r.name = r.who
            else:
                r.name = ''
        if not self.review:
            return []
        if isinstance(self.review, list):
            open_reviews = [r for r in self.review if hasattr(r, 'state') and
                            r.state in Request.open_states]
            for r in open_reviews:
                name_review(r)
        else:
            name_review(self.review)
            open_reviews = [self.review]
        return open_reviews

    @property
    def groups(self):
        # Maybe use a invalidating cache as a trade-off between current
        # information and slow response.
        if not self._groups:
            self._groups = Group.for_request(self.remote, self)
        return self._groups

    @classmethod
    def for_user(cls, remote, user):
        params={'user': user.login,
                'view': 'collection',
                'types': 'review'}
        return remote.get(cls.endpoint, cls.parse, params)

    @classmethod
    def open_for_groups(cls, remote, groups):
        """Will return all requests of the given type for the given groups
        that are still open: the state of the review should be in state 'new'.

        Args:
            - remote: The remote facade to use.
            - groups: The groups that should be used.
        """
        def get_group_name(group):
            if isinstance(group, str):
                return group
            return group.name
        xpaths = ["(state/@name='{0}')".format('review')]
        for group in groups:
            name = get_group_name(group)
            xpaths.append(
                "(review[@by_group='{0}' and @state='new'])".format(name)
            )
        xpath = " and ".join(xpaths)
        params = {'match': xpath}
        search = "/".join(["search", cls.endpoint])
        return remote.get(search, cls.parse, params)

    @classmethod
    def by_id(cls, remote, req_id):
        endpoint = "/".join([cls.endpoint, req_id])
        return remote.get(endpoint, cls.parse)

    @classmethod
    def parse(cls, remote, xml):
        return super(Request, cls).parse(remote, xml, cls.endpoint)

    def __eq__(self, other):
        return self.id == other.id

    def __str__(self):
        return self.id

    def unicode(self):
        return str(self)


class Template(object):
    """Facade to filesystem-based templates.
    The templates can be found in:

    ``/mounts/qam/testreports/``
    """
    template_base_path = "/mounts/qam/testreports/"
    template_name_regex = "SUSE:Maintenance:(\d+):{request_id}"

    def __init__(self, directory, request):
        """Create a new template from the given directory.
        """
        self.directory = directory
        self.request = request
        self.log_entries = {}
        self.parse_log()

    def parse_log(self):
        """Parses the header of the log into the log_entries dictionary.
        """
        log_path = os.path.join(self.directory, "log")
        if not os.path.exists(log_path):
            raise AttributeError("Template does not contain log file.")
        with open(log_path, 'r') as log_file:
            for line in log_file:
                # We end parsing at the results block.
                # We only need the header information.
                if "Test results by" in line:
                    break
                try:
                    key, value = line.split(":", 1)
                    if key == 'Packages':
                        value = [v.strip() for v in value.split(",")]
                    elif key == 'Products':
                        value = value.replace("SLE-","").strip()
                    else:
                        value = value.strip()
                    self.log_entries[key] = value
                except ValueError:
                    pass
    
    @classmethod
    def for_request(cls, request):
        """Load the template for the given request.
        """
        request_id = request.id
        regex = re.compile(
            Template.template_name_regex.format(request_id=request_id)
        )
        for dir in os.listdir(Template.template_base_path):
            if re.match(regex, dir):
                fullpath = os.path.join(Template.template_base_path, dir)
                return Template(fullpath, request)
        logger.error(
            "No template could be found for request {0}".format(
                request
            )
        )
