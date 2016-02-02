"""
This file contains celery tasks for programs-related functionality.
"""

from celery import task
from celery.utils.log import get_task_logger  # pylint: disable=no-name-in-module, import-error
from django.contrib.auth.models import User
from edx_rest_api_client.client import EdxRestApiClient

from lms.djangoapps.certificates.api import get_certificates_for_user, is_passing_status

from openedx.core.djangoapps.credentials.models import CredentialsApiConfig
from openedx.core.djangoapps.credentials.utils import get_user_credentials
from openedx.core.djangoapps.programs.models import ProgramsApiConfig
from openedx.core.lib.token_utils import get_id_token


LOGGER = get_task_logger(__name__)


def get_api_client(api_config, student):
    """
    Create and configure an API client for authenticated HTTP requests.

    Args:
        api_config: ProgramsApiConfig or CredentialsApiConfig object
        student: User object as whom to authenticate to the API

    Returns:
        EdxRestApiClient

    """
    id_token = get_id_token(student, api_config.OAUTH2_CLIENT_NAME)
    return EdxRestApiClient(api_config.internal_api_url, jwt=id_token)


def get_completed_courses(student):
    """
    Determine which courses have been completed by the user.

    Args:
        student:
            User object representing the student

    Returns:
        iterable of dicts with structure {'course_id': course_key, 'mode': cert_type}

    """
    all_certs = get_certificates_for_user(student.username)
    return [
        {'course_id': cert['course_key'], 'mode': cert['type']}
        for cert in all_certs
        if is_passing_status(cert['status'])
    ]


def get_completed_programs(client, course_certificates):
    """
    Given a set of completed courses, determine which programs are completed.

    Args:
        client:
            programs API client (EdxRestApiClient)
        course_certificates:
            iterable of dicts with structure {'course_id': course_key, 'mode': cert_type}

    Returns:
        list of program ids

    """
    return client.programs.complete.post({'completed_courses': course_certificates})['program_ids']


def get_awarded_certificate_programs(student):
    """
    Find the ids of all the programs for which the student has already been awarded
    a certificate.

    Args:
        student:
            User object representing the student

    Returns:
        ids of the programs for which the student has been awarded a certificate

    """
    return [
        credential['credential']['program_id']
        for credential in get_user_credentials(student)
        if 'program_id' in credential['credential'] and credential['status'] == 'awarded'
    ]


def award_program_certificate(client, username, program_id):
    """
    Issue a new certificate of completion to the given student for the given program.

    Args:
        client:
            credentials API client (EdxRestApiClient)
        username:
            The username of the student
        program_id:
            id of the completed program

    Returns:
        None

    """
    client.user_credentials.post({'program_id': program_id, 'username': username})


@task
def award_program_certificates(username):
    """
    This task is designed to be called whenever a user's completion status
    changes with respect to one or more courses (primarily, when a course
    certificate is awarded).

    It will consult with a variety of APIs to determine whether or not the
    specified user should be awarded a certificate in one or more programs, and
    use the credentials service to create said certificates if so.

    This task may also be invoked independently of any course completion status
    change - for example, to backpopulate missing program credentials for a
    user.
    """

    student = User.objects.get(username=username)

    # fetch the set of all course runs for which the user has earned a certificate
    course_certs = get_completed_courses(student)

    # invoke the Programs API completion check endpoint to identify any programs
    # that are satisfied by these course completions
    programs_client = get_api_client(ProgramsApiConfig.current(), student)
    program_ids = get_completed_programs(programs_client, course_certs)

    # determine which program certificates the user has already been awarded, if
    # any, and remove those, since they already exist.
    existing_program_ids = get_awarded_certificate_programs(student)

    new_program_ids = list(set(program_ids) - set(existing_program_ids))

    # generate a new certificate for each of the remaining programs.
    if new_program_ids:
        credentials_client = get_api_client(
            CredentialsApiConfig.current(),
            User.objects.get(username='FIXME-NO-SERVICE-USER')
        )
        for program_id in new_program_ids:
            LOGGER.info(
                'calling credentials service to issue certificate for user %s in program %s',
                username,
                program_id,
            )
            award_program_certificate(credentials_client, student.username, program_id)
