from urllib2 import HTTPError
from StringIO import StringIO
import unittest
import osc
from oscqam.models import (Request, Template, MissingSourceProjectError, User,
                           Group, Assignment)
from .utils import load_fixture
from .mockremote import MockRemote


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.req_1_xml = load_fixture('request_12345.xml')
        cls.req_2_xml = load_fixture('request_23456.xml')
        cls.req_3_xml = load_fixture('request_52542.xml')
        cls.req_4_xml = load_fixture('request_56789.xml')
        cls.req_search = load_fixture('request_search.xml')
        cls.req_search_none = load_fixture('request_search_none_proj.xml')
        cls.req_no_src = load_fixture('request_no_src.xml')
        cls.req_assign = load_fixture('request_assign.xml')
        cls.req_unassign = load_fixture('request_unassign.xml')
        cls.req_unassigned = load_fixture('request_unassigned.xml')
        cls.req_invalid = load_fixture('request_no_src.xml')
        cls.req_sle11sp4 = load_fixture('request_sle11sp4.xml')
        cls.template = load_fixture('template.txt')
        cls.template_rh = load_fixture('template_rh.txt')
        cls.user = load_fixture('person_anonymous.xml')
        cls.group = load_fixture('group_qam-sle.xml')

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
        self.assertEqual(assigned[0].user.login, 'anonymous')
        self.assertEqual(assigned[0].group.name, 'qam-sle')
        request = Request.parse(self.remote, self.req_3_xml)[0]
        assigned = request.assigned_roles
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0].user.login, 'anonymous')
        self.assertEqual(assigned[0].group.name, 'qam-sle')

    def test_assigned_roles_sle11_sp4(self):
        request = Request.parse(self.remote, self.req_sle11sp4)[0]
        assigned = request.assigned_roles
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0].user.login, 'anonymous')
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
        self.assertRaises(MissingSourceProjectError, request.get_template,
                          Template)

    def test_assignment_equality(self):
        user = User.parse(self.remote, self.user)[0]
        group = Group.parse(self.remote, self.group)[0]
        a1 = Assignment(user, group)
        a2 = Assignment(user, group)
        self.assertEqual(a1, a2)

    def test_assignment_inference_single_group(self):
        """Test that assignments can be inferred from a single group even
        if the comments are not used.
        """
        request = Request.parse(self.remote, self.req_4_xml)[0]
        assignments = Assignment.infer(request)
        self.assertEqual(len(assignments), 1)
        assignment = assignments[0]
        self.assertEqual(assignment.user.login, 'anonymous')
        self.assertEqual(assignment.group.name, 'qam-sle')

    def test_incident_priority(self):
        request = Request.parse(self.remote, self.req_1_xml)[0]
        src_project = request.src_project
        endpoint = "/source/{0}/_attribute/OBS:IncidentPriority".format(
            src_project
        )
        self.remote.register_url(endpoint, lambda: (
            "<attributes>"
            "<attribute name='IncidentPriority' namespace='OBS'>"
            "<value>100</value>"
            "</attribute>"
            "</attributes>"
        ))
        incident_priority = request.incident_priority
        self.assertEqual(incident_priority, Request.Priority(100))

    def test_incident_priority_empty(self):
        request = Request.parse(self.remote, self.req_1_xml)[0]
        src_project = request.src_project
        endpoint = "/source/{0}/_attribute/OBS:IncidentPriority".format(
            src_project
        )
        self.remote.register_url(endpoint, lambda: "<attributes/>")
        incident_priority = request.incident_priority
        self.assertEqual(incident_priority, Request.UnknownPriority())

    def test_no_incident_priority(self):
        def raise_http():
            raise HTTPError('test', 500, 'test', '', StringIO(''))
        request = Request.parse(self.remote, self.req_1_xml)[0]
        src_project = request.src_project
        endpoint = "/source/{0}/_attribute/OBS:IncidentPriority".format(
            src_project
        )
        self.remote.register_url(endpoint, raise_http)
        request = Request.parse(self.remote, self.req_1_xml)[0]
        self.assertEqual(request.incident_priority, Request.UnknownPriority())

    def test_priority_str(self):
        priority = Request.UnknownPriority()
        self.assertEqual("None", str(priority))
        priority = Request.Priority(100)
        self.assertEqual("100", str(priority))

    def test_unassigned_roles(self):
        request = Request.parse(self.remote, self.req_unassigned)[0]
        open_reviews = request.review_list_open()
        self.assertEqual(len(open_reviews), 2)
        self.assertEqual(open_reviews[0].reviewer.name, 'qam-cloud')
        self.assertEqual(open_reviews[1].reviewer.name, 'qam-sle')

    def test_obs27_workaround_pre_152(self):
        def raise_wrong_args(self, request):
                raise osc.oscerr.WrongArgs("acceptinfo")
        original_version = osc.core.get_osc_version
        original_read = Request.read
        osc.core.get_osc_version = lambda: '0.151'
        Request.read = raise_wrong_args
        try:
            request = Request.parse(self.remote, self.req_unassigned)
            self.assertEqual(request, [])
        finally:
            Request.read = original_read
            osc.core.get_osc_version = original_version

    def test_obs27_workaround_post_152(self):
        def raise_wrong_args(self, request):
                raise osc.oscerr.WrongArgs("acceptinfo")
        original_read = Request.read
        Request.read = raise_wrong_args
        try:
            self.assertRaises(osc.oscerr.WrongArgs, Request.parse,
                              self.remote, self.req_unassigned)
        finally:
            Request.read = original_read

    def test_request_str(self):
        request = Request.parse(self.remote, self.req_1_xml)[0]
        self.assertEqual(str(request), '12345')
        self.assertEqual(unicode(request), u'12345')

    def test_test_plan_reviewer(self):
        reviewer_singular = self.create_template(
            template_data = 'Test Plan Reviewer: a'
        )
        reviewer_plural = self.create_template(
            template_data = 'Test Plan Reviewers: a'
        )
        self.assertEqual(reviewer_singular.testplanreviewer(), 'a')
        self.assertEqual(reviewer_plural.testplanreviewer(), 'a')
