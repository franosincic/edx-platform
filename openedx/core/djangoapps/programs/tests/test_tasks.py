"""
Tests for programs celery tasks.
"""

import ddt
from django.test import TestCase
from edx_rest_api_client.client import EdxRestApiClient
import httpretty
import json
import mock

from oauth2_provider.tests.factories import ClientFactory
from openedx.core.djangoapps.credentials.tests.mixins import CredentialsApiConfigMixin
from openedx.core.djangoapps.programs.tests.mixins import ProgramsApiConfigMixin
from openedx.core.djangoapps.programs import tasks
from student.tests.factories import UserFactory


class GetApiClientTestCase(TestCase, ProgramsApiConfigMixin):
    """
    Test the get_api_client function
    """

    @mock.patch('openedx.core.djangoapps.programs.tasks.get_id_token')
    def test_get_api_client(self, mock_get_id_token):
        """
        Ensure the function is making the right API calls based on inputs
        """
        student = UserFactory()
        ClientFactory.create(name='programs')
        api_config = self.create_programs_config(
            internal_service_url='http://foo',
            api_version_number=99,
        )
        mock_get_id_token.return_value = 'test-token'

        api_client = tasks.get_api_client(api_config, student)
        self.assertEqual(mock_get_id_token.call_args[0], (student, 'programs'))
        self.assertEqual(api_client._store['base_url'], 'http://foo/api/v99/')  # pylint: disable=protected-access
        self.assertEqual(api_client._store['session'].auth.token, 'test-token')  # pylint: disable=protected-access


class GetCompletedCoursesTestCase(TestCase):
    """
    Test the get_completed_courses function
    """

    def make_cert_result(self, **kwargs):
        """
        Helper to create dummy results from the certificates API
        """
        result = {
            'username': 'dummy-username',
            'course_key': 'dummy-course',
            'type': 'dummy-type',
            'status': 'dummy-status',
            'download_url': 'http://www.example.com/cert.pdf',
            'grade': '0.98',
            'created': '2015-07-31T00:00:00Z',
            'modified': '2015-07-31T00:00:00Z',
        }
        result.update(**kwargs)
        return result

    @mock.patch('openedx.core.djangoapps.programs.tasks.get_certificates_for_user')
    def test_get_completed_courses(self, mock_get_certs_for_user):
        """
        Ensure the function correctly calls to and handles results from the
        certificates API
        """
        student = UserFactory(username='test-username')
        mock_get_certs_for_user.return_value = [
            self.make_cert_result(status='downloadable', type='verified', course_key='downloadable-course'),
            self.make_cert_result(status='generating', type='prof-ed', course_key='generating-course'),
            self.make_cert_result(status='unknown', type='honor', course_key='unknown-course'),
        ]

        result = tasks.get_completed_courses(student)
        self.assertEqual(mock_get_certs_for_user.call_args[0], (student.username, ))
        self.assertEqual(result, [
            {'course_id': 'downloadable-course', 'mode': 'verified'},
            {'course_id': 'generating-course', 'mode': 'prof-ed'},
        ])


class GetCompletedProgramsTestCase(TestCase):
    """
    Test the get_completed_programs function
    """

    @httpretty.activate
    def test_get_completed_programs(self):
        """
        Ensure the correct API call gets made
        """
        test_client = EdxRestApiClient('http://test-server', jwt='test-token')
        httpretty.register_uri(
            httpretty.POST,
            'http://test-server/programs/complete/',
            body='{"program_ids": [1, 2, 3]}',
            content_type='application/json',
        )
        payload = [
            {'course_id': 'test-course-1', 'mode': 'verified'},
            {'course_id': 'test-course-2', 'mode': 'prof-ed'},
        ]
        result = tasks.get_completed_programs(test_client, payload)
        self.assertEqual(httpretty.last_request().body, json.dumps({'completed_courses': payload}))
        self.assertEqual(result, [1, 2, 3])


class GetAwardedCertificateProgramsTestCase(TestCase):
    """
    Test the get_awarded_certificate_programs function
    """

    def make_credential_result(self, **kwargs):
        """
        Helper to make dummy results from the credentials API
        """
        result = {
            'id': 1,
            'username': 'dummy-username',
            'credential': {
                'credential_id': None,
                'program_id': None,
            },
            'status': 'dummy-status',
            'uuid': 'dummy-uuid',
            'certificate_url': 'http://credentials.edx.org/credentials/dummy-uuid/'
        }
        result.update(**kwargs)
        return result

    @mock.patch('openedx.core.djangoapps.programs.tasks.get_user_credentials')
    def test_get_awarded_certificate_programs(self, mock_get_user_credentials):
        """
        Ensure the API is called and results handled correctly.
        """
        student = UserFactory(username='test-username')
        mock_get_user_credentials.return_value = [
            self.make_credential_result(status='awarded', credential={'program_id': 1}),
            self.make_credential_result(status='awarded', credential={'course_id': 2}),
            self.make_credential_result(status='revoked', credential={'program_id': 3}),
        ]

        result = tasks.get_awarded_certificate_programs(student)
        self.assertEqual(mock_get_user_credentials.call_args[0], (student, ))
        self.assertEqual(result, [1])


class AwardProgramCertificateTestCase(TestCase):
    """
    Test the award_program_certificate function
    """

    @httpretty.activate
    def test_award_program_certificate(self):
        """
        Ensure the correct API call gets made
        """
        test_username = 'test-username'
        test_client = EdxRestApiClient('http://test-server', jwt='test-token')
        httpretty.register_uri(
            httpretty.POST,
            'http://test-server/user_credentials/',
        )
        tasks.award_program_certificate(test_client, test_username, 123)
        self.assertEqual(httpretty.last_request().body, json.dumps({'program_id': 123, 'username': test_username}))


@ddt.ddt
@mock.patch('openedx.core.djangoapps.programs.tasks.award_program_certificate')
@mock.patch('openedx.core.djangoapps.programs.tasks.get_awarded_certificate_programs')
@mock.patch('openedx.core.djangoapps.programs.tasks.get_completed_programs')
@mock.patch('openedx.core.djangoapps.programs.tasks.get_completed_courses')
class AwardProgramCertificatesTestCase(TestCase, ProgramsApiConfigMixin, CredentialsApiConfigMixin):
    """
    Tests for the 'award_program_certificates' celery task.
    """

    def setUp(self):
        super(AwardProgramCertificatesTestCase, self).setUp()
        self.programs_config = self.create_programs_config()
        self.credentials_config = self.create_credentials_config()
        self.student = UserFactory.create(username='test-student')

        ClientFactory.create(name='programs')
        ClientFactory.create(name='credentials')
        UserFactory.create(username='FIXME-NO-SERVICE-USER')  # temporary hack for credentials API call

    def test_completion_check(
            self,
            mock_get_completed_courses,
            mock_get_completed_programs,
            mock_get_awarded_certificate_programs,  # pylint: disable=unused-argument
            mock_award_program_certificate,  # pylint: disable=unused-argument
    ):
        """
        Checks that the Programs API is used correctly to determine completed
        programs.
        """
        completed_courses = [
            {'course_id': 'course-1', 'type': 'verified'},
            {'course_id': 'course-2', 'type': 'prof-ed'},
        ]
        mock_get_completed_courses.return_value = completed_courses

        tasks.award_program_certificates(self.student.username)

        self.assertEqual(
            mock_get_completed_programs.call_args[0][1],
            completed_courses
        )

    @ddt.data(
        ([1], [2, 3]),
        ([], [1, 2, 3]),
        ([1, 2, 3], []),
    )
    @ddt.unpack
    def test_awarding_certs(
            self,
            already_awarded_program_ids,
            expected_awarded_program_ids,
            mock_get_completed_courses,  # pylint: disable=unused-argument
            mock_get_completed_programs,
            mock_get_awarded_certificate_programs,
            mock_award_program_certificate,
    ):
        """
        Checks that the Credentials API is used to award certificates for
        the proper programs.
        """
        mock_get_completed_programs.return_value = [1, 2, 3]
        mock_get_awarded_certificate_programs.return_value = already_awarded_program_ids

        tasks.award_program_certificates(self.student.username)

        # TODO ensure using service account for awarding certs

        actual_program_ids = [call[0][2] for call in mock_award_program_certificate.call_args_list]
        self.assertEqual(actual_program_ids, expected_awarded_program_ids)
