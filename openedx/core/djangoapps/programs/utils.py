"""
Helper methods for Programs.
"""
import logging

from edx_rest_api_client.client import EdxRestApiClient

from openedx.core.djangoapps.programs.models import ProgramsApiConfig
from openedx.core.djangoapps.util.helpers import get_id_token


log = logging.getLogger(__name__)


def programs_api_client(api_url, jwt_access_token):
    """ Returns an Programs API client setup with authentication for the
    specified user.
    """
    return EdxRestApiClient(
        api_url,
        jwt=jwt_access_token
    )


def get_programs(user):
    """Given a user, get programs from the Programs service.

    Arguments:
        user (User): The user to authenticate as when requesting programs.

    Returns:
        list of dict, representing programs returned by the Programs service.
    """
    programs_config = ProgramsApiConfig.current()
    no_programs = []

    if not programs_config.enabled:
        log.warning('Programs configuration is disabled.')
        return no_programs

    try:
        jwt = get_id_token(user, programs_config.OAUTH2_CLIENT_NAME)
        api = EdxRestApiClient(programs_config.internal_api_url, jwt=jwt)
    except Exception:  # pylint: disable=broad-except
        log.exception('Failed to initialize the Programs API client.')
        return no_programs

    try:
        response = api.programs.get()
    except Exception:  # pylint: disable=broad-except
        log.exception('Failed to retrieve programs from the Programs API.')
        return no_programs

    return response.get('results', no_programs)


def get_programs_for_dashboard(user, course_keys):
    """Build a dictionary of programs, keyed by course.

    Given a user and an iterable of course keys, find all the programs relevant
    to the user's dashboard and return them in a dictionary keyed by course key.

    Arguments:
        user (User): The user to authenticate as when requesting programs.
        course_keys (list): List of course keys representing the courses in which
            the given user has active enrollments.

    Returns:
        dict, containing programs keyed by course. Empty if programs cannot be retrieved.
    """
    programs_config = ProgramsApiConfig.current()
    course_programs = {}

    if not programs_config.is_student_dashboard_enabled:
        log.warning('Display of programs on the student dashboard is disabled.')
        return course_programs

    programs = get_programs(user)
    if not programs:
        log.warning('No programs found for the user with ID %d.', user.id)
        return course_programs

    # Reindex the result returned by the Programs API from:
    #     program -> course code -> course run
    # to:
    #     course run -> program
    # Ignore course runs not present in the user's active enrollments.
    for program in programs:
        try:
            for course_code in program['course_codes']:
                for run in course_code['run_modes']:
                    course_key = run['course_key']
                    if course_key in course_keys:
                        course_programs[course_key] = program
        except KeyError:
            log.exception('Unable to parse Programs API response: %r', program)

    return course_programs
