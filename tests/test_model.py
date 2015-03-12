import os
import unittest
from oscqam.models import Request, Template, MissingSourceProjectError
from .mockremote import MockRemote


path = os.path.join(os.path.dirname(__file__), 'data')


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.req_1_xml = open('%s/%s' % (path, 'request_12345.xml')).read()
        cls.req_2_xml = open('%s/%s' % (path, 'request_23456.xml')).read()
        cls.req_3_xml = open('%s/%s' % (path, 'request_52542.xml')).read()
        cls.req_search = open('%s/%s' % (path, 'request_search.xml')).read()
        cls.req_search_none = open(
            '%s/%s' % (path, 'request_search_none_proj.xml')
        ).read()
        cls.req_no_src = open('%s/%s' % (path, 'request_no_src.xml')).read()
        cls.req_assign = open('%s/%s' % (path, 'request_assign.xml')).read()
        cls.req_unassign = open('%s/%s' % (path, 'request_unassign.xml')).read()
        cls.req_invalid = open('%s/%s' % (path, 'request_no_src.xml')).read()
        cls.template = open('%s/%s' % (path, 'template.txt')).read()
        cls.template_rh = open('%s/%s' % (path, 'template_rh.txt')).read()

    def create_template(self, request_data=None, template_data=None):
        if not request_data:
            request_data = self.req_1_xml
        if not template_data:
            template_data = self.template
        request = Request.parse(self.remote, request_data)[0]
        template = Template(request, tr_getter=lambda x: template_data)
        return template

    def setUp(self):
        self.remote = MockRemote()

    def test_merge_requests(self):
        request_1 = Request.parse(self.remote, self.req_1_xml)[0]
        request_2 = Request.parse(self.remote, self.req_1_xml)[0]
        requests = set([request_1, request_2])
        self.assertEqual(len(requests), 1)

    def test_search(self):
        """Only requests that are part of SUSE:Maintenance projects should be
        used.
        """
        requests = Request.parse(self.remote, self.req_search)
        self.assertEqual(len(requests), 2)
        requests = Request.filter_by_project("SUSE:Maintenance", requests)
        self.assertEqual(len(requests), 1)

    def test_search_empty_source_project(self):
        """Projects with empty source project should be handled gracefully.

        """
        requests = Request.parse(self.remote, self.req_search_none)
        requests = Request.filter_by_project("SUSE:Maintenance", requests)
        self.assertEqual(len(requests), 0)

    def test_project_without_source_project(self):
        """When project attribute can be found in a source tag the API should
        just return an empty string and not fail.
        """
        requests = Request.parse(self.remote, self.req_no_src)
        self.assertEqual(requests[0].src_project, '')
        requests = Request.filter_by_project("SUSE:Maintenance", requests)
        self.assertEqual(len(requests), 0)

    def test_assigned_roles_request(self):
        request = Request.parse(self.remote, self.req_assign)[0]
        assigned = request.assigned_roles
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0].user, 'anonymous')
        self.assertEqual(assigned[0].group.name, 'qam-sle')
        request = Request.parse(self.remote, self.req_3_xml)[0]
        assigned = request.assigned_roles
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0].user, 'anonymous')
        self.assertEqual(assigned[0].group.name, 'qam-sle')

    def test_unassigned_removes_roles(self):
        request = Request.parse(self.remote, self.req_unassign)[0]
        assigned = request.assigned_roles
        self.assertEqual(len(assigned), 0)

    def test_parse_request_id(self):
        test_id = "SUSE:Maintenance:123:45678"
        req_id = Request.parse_request_id(test_id)
        self.assertEqual(req_id, "45678")

    def test_template_splits_srcrpms(self):
        self.assertEqual(
            self.create_template().log_entries['SRCRPMs'],
            ["glibc", "glibc-devel"]
        )

    def test_template_splits_products(self):
        self.assertEqual(
            self.create_template().log_entries['Products'],
            ["SERVER 11-SP3 (i386, ia64, ppc64, s390x, x86_64)",
             "DESKTOP 11-SP3 (i386, x86_64)"]
        )

    def test_template_splits_non_sle_products(self):
        self.assertEqual(
            self.create_template(template_data=self.template_rh)
            .log_entries['Products'],
            ["RHEL-TEST (i386)",
             "SERVER 11-SP3 (i386, ia64, ppc64, s390x, x86_64)"]
        )

    def test_replacing_sle_prefix(self):
        template_data = "Products: SLE-PSLE-SP3 (i386)"
        self.assertEqual(
            self.create_template(template_data=template_data)
            .log_entries['Products'],
            ['PSLE-SP3 (i386)']
        )

    def test_template_for_invalid_request(self):
        request = Request.parse(self.remote, self.req_invalid)[0]
        self.assertRaises(MissingSourceProjectError, Template, request)
