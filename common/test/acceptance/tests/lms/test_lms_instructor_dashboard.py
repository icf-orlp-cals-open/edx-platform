# -*- coding: utf-8 -*-
"""
End-to-end tests for the LMS Instructor Dashboard.
"""

import time

from flaky import flaky
from nose.plugins.attrib import attr
from bok_choy.promise import EmptyPromise

from ..helpers import UniqueCourseTest, get_modal_alert, EventsTestMixin
from ...pages.common.logout import LogoutPage
from ...pages.lms.auto_auth import AutoAuthPage
from ...pages.studio.overview import CourseOutlinePage
from ...pages.lms.create_mode import ModeCreationPage
from ...pages.lms.courseware import CoursewarePage
from ...pages.lms.instructor_dashboard import InstructorDashboardPage
from ...fixtures.course import CourseFixture, XBlockFixtureDesc
from ...pages.lms.dashboard import DashboardPage
from ...pages.lms.problem import ProblemPage
from ...pages.lms.track_selection import TrackSelectionPage
from ...pages.lms.pay_and_verify import PaymentAndVerificationFlow, FakePaymentPage
from common.test.acceptance.tests.helpers import disable_animations
from ...fixtures.certificates import CertificateConfigFixture


class BaseInstructorDashboardTest(EventsTestMixin, UniqueCourseTest):
    """
    Mixin class for testing the instructor dashboard.
    """
    def log_in_as_instructor(self):
        """
        Logs in as an instructor and returns the id.
        """
        username = "test_instructor_{uuid}".format(uuid=self.unique_id[0:6])
        auto_auth_page = AutoAuthPage(self.browser, username=username, course_id=self.course_id, staff=True)
        return username, auto_auth_page.visit().get_user_id()

    def visit_instructor_dashboard(self):
        """
        Visits the instructor dashboard.
        """
        instructor_dashboard_page = InstructorDashboardPage(self.browser, self.course_id)
        instructor_dashboard_page.visit()
        return instructor_dashboard_page


@attr('shard_1')
class AutoEnrollmentWithCSVTest(BaseInstructorDashboardTest):
    """
    End-to-end tests for Auto-Registration and enrollment functionality via CSV file.
    """

    def setUp(self):
        super(AutoEnrollmentWithCSVTest, self).setUp()
        self.course_fixture = CourseFixture(**self.course_info).install()
        self.log_in_as_instructor()
        instructor_dashboard_page = self.visit_instructor_dashboard()
        self.auto_enroll_section = instructor_dashboard_page.select_membership().select_auto_enroll_section()

    def test_browse_and_upload_buttons_are_visible(self):
        """
        Scenario: On the Membership tab of the Instructor Dashboard, Auto-Enroll Browse and Upload buttons are visible.
            Given that I am on the Membership tab on the Instructor Dashboard
            Then I see the 'REGISTER/ENROLL STUDENTS' section on the page with the 'Browse' and 'Upload' buttons
        """
        self.assertTrue(self.auto_enroll_section.is_file_attachment_browse_button_visible())
        self.assertTrue(self.auto_enroll_section.is_upload_button_visible())

    def test_clicking_file_upload_button_without_file_shows_error(self):
        """
        Scenario: Clicking on the upload button without specifying a CSV file results in error.
            Given that I am on the Membership tab on the Instructor Dashboard
            When I click the Upload Button without specifying a CSV file
            Then I should be shown an Error Notification
            And The Notification message should read 'File is not attached.'
        """
        self.auto_enroll_section.click_upload_file_button()
        self.assertTrue(self.auto_enroll_section.is_notification_displayed(section_type=self.auto_enroll_section.NOTIFICATION_ERROR))
        self.assertEqual(self.auto_enroll_section.first_notification_message(section_type=self.auto_enroll_section.NOTIFICATION_ERROR), "File is not attached.")

    def test_uploading_correct_csv_file_results_in_success(self):
        """
        Scenario: Uploading a CSV with correct data results in Success.
            Given that I am on the Membership tab on the Instructor Dashboard
            When I select a csv file with correct data and click the Upload Button
            Then I should be shown a Success Notification.
        """
        self.auto_enroll_section.upload_correct_csv_file()
        self.assertTrue(self.auto_enroll_section.is_notification_displayed(section_type=self.auto_enroll_section.NOTIFICATION_SUCCESS))

    def test_uploading_csv_file_with_bad_data_results_in_errors_and_warnings(self):
        """
        Scenario: Uploading a CSV with incorrect data results in error and warnings.
            Given that I am on the Membership tab on the Instructor Dashboard
            When I select a csv file with incorrect data and click the Upload Button
            Then I should be shown an Error Notification
            And a corresponding Error Message.
            And I should be shown a Warning Notification
            And a corresponding Warning Message.
        """
        self.auto_enroll_section.upload_csv_file_with_errors_warnings()
        self.assertTrue(self.auto_enroll_section.is_notification_displayed(section_type=self.auto_enroll_section.NOTIFICATION_ERROR))
        self.assertEqual(self.auto_enroll_section.first_notification_message(section_type=self.auto_enroll_section.NOTIFICATION_ERROR), "Data in row #2 must have exactly four columns: email, username, full name, and country")
        self.assertTrue(self.auto_enroll_section.is_notification_displayed(section_type=self.auto_enroll_section.NOTIFICATION_WARNING))
        self.assertEqual(self.auto_enroll_section.first_notification_message(section_type=self.auto_enroll_section.NOTIFICATION_WARNING), "ename (d@a.com): (An account with email d@a.com exists but the provided username ename is different. Enrolling anyway with d@a.com.)")

    def test_uploading_non_csv_file_results_in_error(self):
        """
        Scenario: Uploading an image file for auto-enrollment results in error.
            Given that I am on the Membership tab on the Instructor Dashboard
            When I select an image file (a non-csv file) and click the Upload Button
            Then I should be shown an Error Notification
            And The Notification message should read 'Make sure that the file you upload is in CSV..'
        """
        self.auto_enroll_section.upload_non_csv_file()
        self.assertTrue(self.auto_enroll_section.is_notification_displayed(section_type=self.auto_enroll_section.NOTIFICATION_ERROR))
        self.assertEqual(self.auto_enroll_section.first_notification_message(section_type=self.auto_enroll_section.NOTIFICATION_ERROR), "Make sure that the file you upload is in CSV format with no extraneous characters or rows.")


@attr('shard_1')
class ProctoredExamsTest(BaseInstructorDashboardTest):
    """
    End-to-end tests for Proctoring Sections of the Instructor Dashboard.
    """

    USERNAME = "STUDENT_TESTER"
    EMAIL = "student101@example.com"

    def setUp(self):
        super(ProctoredExamsTest, self).setUp()

        self.courseware_page = CoursewarePage(self.browser, self.course_id)

        self.course_outline = CourseOutlinePage(
            self.browser,
            self.course_info['org'],
            self.course_info['number'],
            self.course_info['run']
        )

        course_fixture = CourseFixture(**self.course_info)
        course_fixture.add_advanced_settings({
            "enable_proctored_exams": {"value": "true"}
        })

        course_fixture.add_children(
            XBlockFixtureDesc('chapter', 'Test Section 1').add_children(
                XBlockFixtureDesc('sequential', 'Test Subsection 1').add_children(
                    XBlockFixtureDesc('problem', 'Test Problem 1')
                )
            )
        ).install()

        self.track_selection_page = TrackSelectionPage(self.browser, self.course_id)
        self.payment_and_verification_flow = PaymentAndVerificationFlow(self.browser, self.course_id)
        self.immediate_verification_page = PaymentAndVerificationFlow(
            self.browser, self.course_id, entry_point='verify-now'
        )
        self.upgrade_page = PaymentAndVerificationFlow(self.browser, self.course_id, entry_point='upgrade')
        self.fake_payment_page = FakePaymentPage(self.browser, self.course_id)
        self.dashboard_page = DashboardPage(self.browser)
        self.problem_page = ProblemPage(self.browser)

        # Add a verified mode to the course
        ModeCreationPage(
            self.browser, self.course_id, mode_slug=u'verified', mode_display_name=u'Verified Certificate',
            min_price=10, suggested_prices='10,20'
        ).visit()

        # Auto-auth register for the course.
        self._auto_auth(self.USERNAME, self.EMAIL, False)

    def _auto_auth(self, username, email, staff):
        """
        Logout and login with given credentials.
        """
        AutoAuthPage(self.browser, username=username, email=email,
                     course_id=self.course_id, staff=staff).visit()

    def _login_as_a_verified_user(self):
        """
        login as a verififed user
        """

        self._auto_auth(self.USERNAME, self.EMAIL, False)

        # the track selection page cannot be visited. see the other tests to see if any prereq is there.
        # Navigate to the track selection page
        self.track_selection_page.visit()

        # Enter the payment and verification flow by choosing to enroll as verified
        self.track_selection_page.enroll('verified')

        # Proceed to the fake payment page
        self.payment_and_verification_flow.proceed_to_payment()

        # Submit payment
        self.fake_payment_page.submit_payment()

    def _create_a_proctored_exam_and_attempt(self):
        """
        Creates a proctored exam and makes the student attempt it so that
        the associated allowance and attempts are visible on the Instructor Dashboard.
        """
        # Visit the course outline page in studio
        LogoutPage(self.browser).visit()
        self._auto_auth("STAFF_TESTER", "staff101@example.com", True)
        self.course_outline.visit()

        # open the exam settings to make it a proctored exam.
        self.course_outline.open_exam_settings_dialog()
        self.course_outline.make_exam_proctored()

        # login as a verified student and visit the courseware.
        LogoutPage(self.browser).visit()
        self._login_as_a_verified_user()
        self.courseware_page.visit()

        # Start the proctored exam.
        self.courseware_page.start_proctored_exam()

    def _create_a_timed_exam_and_attempt(self):
        """
        Creates a timed exam and makes the student attempt it so that
        the associated allowance and attempts are visible on the Instructor Dashboard.
        """
        # Visit the course outline page in studio
        LogoutPage(self.browser).visit()
        self._auto_auth("STAFF_TESTER", "staff101@example.com", True)
        self.course_outline.visit()

        # open the exam settings to make it a proctored exam.
        self.course_outline.open_exam_settings_dialog()
        self.course_outline.make_exam_timed()

        # login as a verified student and visit the courseware.
        LogoutPage(self.browser).visit()
        self._login_as_a_verified_user()
        self.courseware_page.visit()

        # Start the timed exam.
        self.courseware_page.start_timed_exam()

        # Stop the timed exam.
        self.courseware_page.stop_timed_exam()

    @flaky  # TODO fix this SOL-1182
    def test_can_add_remove_allowance(self):
        """
        Make sure that allowances can be added and removed.
        """
        # Given that an exam has been configured to be a timed exam.
        self._create_a_timed_exam_and_attempt()

        # When I log in as an instructor,
        __, __ = self.log_in_as_instructor()

        # And visit the Allowance Section of Instructor Dashboard's Special Exams tab
        instructor_dashboard_page = self.visit_instructor_dashboard()
        allowance_section = instructor_dashboard_page.select_special_exams().select_allowance_section()

        # Then I can add Allowance to that exam for a student
        self.assertTrue(allowance_section.is_add_allowance_button_visible)

    @flaky  # TODO fix this SOL-1182
    def test_can_reset_attempts(self):
        """
        Make sure that Exam attempts are visible and can be reset.
        """
        # Given that an exam has been configured to be a proctored exam.
        self._create_a_timed_exam_and_attempt()

        # When I log in as an instructor,
        __, __ = self.log_in_as_instructor()

        # And visit the Student Proctored Exam Attempts Section of Instructor Dashboard's Special Exams tab
        instructor_dashboard_page = self.visit_instructor_dashboard()
        exam_attempts_section = instructor_dashboard_page.select_special_exams().select_exam_attempts_section()

        # Then I can see the search text field
        self.assertTrue(exam_attempts_section.is_search_text_field_visible)

        # And I can see one attempt by a student.
        self.assertTrue(exam_attempts_section.is_student_attempt_visible)

        # And I can remove the attempt by clicking the "x" at the end of the row.
        exam_attempts_section.remove_student_attempt()
        self.assertFalse(exam_attempts_section.is_student_attempt_visible)


@attr('shard_1')
class EntranceExamGradeTest(BaseInstructorDashboardTest):
    """
    Tests for Entrance exam specific student grading tasks.
    """

    def setUp(self):
        super(EntranceExamGradeTest, self).setUp()
        self.course_info.update({"settings": {"entrance_exam_enabled": "true"}})
        CourseFixture(**self.course_info).install()
        self.student_identifier = "johndoe_saee@example.com"
        # Create the user (automatically logs us in)
        AutoAuthPage(
            self.browser,
            username="johndoe_saee",
            email=self.student_identifier,
            course_id=self.course_id,
            staff=False
        ).visit()

        LogoutPage(self.browser).visit()

        # go to the student admin page on the instructor dashboard
        self.log_in_as_instructor()
        self.student_admin_section = self.visit_instructor_dashboard().select_student_admin()

    def test_input_text_and_buttons_are_visible(self):
        """
        Scenario: On the Student admin tab of the Instructor Dashboard, Student Email input box,
        Reset Student Attempt, Rescore Student Submission, Delete Student State for entrance exam
            and Show Background Task History for Student buttons are visible
            Given that I am on the Student Admin tab on the Instructor Dashboard
            Then I see Student Email input box, Reset Student Attempt, Rescore Student Submission,
            Delete Student State for entrance exam and Show Background Task History for Student buttons
        """
        self.assertTrue(self.student_admin_section.is_student_email_input_visible())
        self.assertTrue(self.student_admin_section.is_reset_attempts_button_visible())
        self.assertTrue(self.student_admin_section.is_rescore_submission_button_visible())
        self.assertTrue(self.student_admin_section.is_delete_student_state_button_visible())
        self.assertTrue(self.student_admin_section.is_background_task_history_button_visible())

    def test_clicking_reset_student_attempts_button_without_email_shows_error(self):
        """
        Scenario: Clicking on the Reset Student Attempts button without entering student email
        address or username results in error.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the Reset Student Attempts Button  under Entrance Exam Grade
            Adjustment without enter an email address
            Then I should be shown an Error Notification
            And The Notification message should read 'Please enter a student email address or username.'
        """
        self.student_admin_section.click_reset_attempts_button()
        self.assertEqual(
            'Please enter a student email address or username.',
            self.student_admin_section.top_notification.text[0]
        )

    def test_clicking_reset_student_attempts_button_with_success(self):
        """
        Scenario: Clicking on the Reset Student Attempts button with valid student email
        address or username should result in success prompt.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the Reset Student Attempts Button under Entrance Exam Grade
            Adjustment after entering a valid student
            email address or username
            Then I should be shown an alert with success message
        """
        self.student_admin_section.set_student_email(self.student_identifier)
        self.student_admin_section.click_reset_attempts_button()
        alert = get_modal_alert(self.student_admin_section.browser)
        alert.dismiss()

    def test_clicking_reset_student_attempts_button_with_error(self):
        """
        Scenario: Clicking on the Reset Student Attempts button with email address or username
        of a non existing student should result in error message.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the Reset Student Attempts Button  under Entrance Exam Grade
            Adjustment after non existing student email address or username
            Then I should be shown an error message
        """
        self.student_admin_section.set_student_email('non_existing@example.com')
        self.student_admin_section.click_reset_attempts_button()
        self.student_admin_section.wait_for_ajax()
        self.assertGreater(len(self.student_admin_section.top_notification.text[0]), 0)

    def test_clicking_rescore_submission_button_with_success(self):
        """
        Scenario: Clicking on the Rescore Student Submission button with valid student email
        address or username should result in success prompt.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the Rescore Student Submission Button  under Entrance Exam Grade
            Adjustment after entering a valid student email address or username
            Then I should be shown an alert with success message
        """
        self.student_admin_section.set_student_email(self.student_identifier)
        self.student_admin_section.click_rescore_submissions_button()
        alert = get_modal_alert(self.student_admin_section.browser)
        alert.dismiss()

    def test_clicking_rescore_submission_button_with_error(self):
        """
        Scenario: Clicking on the Rescore Student Submission button with email address or username
        of a non existing student should result in error message.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the Rescore Student Submission Button under Entrance Exam Grade
            Adjustment after non existing student email address or username
            Then I should be shown an error message
        """
        self.student_admin_section.set_student_email('non_existing@example.com')
        self.student_admin_section.click_rescore_submissions_button()
        self.student_admin_section.wait_for_ajax()
        self.assertGreater(len(self.student_admin_section.top_notification.text[0]), 0)

    def test_clicking_skip_entrance_exam_button_with_success(self):
        """
        Scenario: Clicking on the  Let Student Skip Entrance Exam button with
        valid student email address or username should result in success prompt.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the  Let Student Skip Entrance Exam Button under
            Entrance Exam Grade Adjustment after entering a valid student
            email address or username
            Then I should be shown an alert with success message
        """
        self.student_admin_section.set_student_email(self.student_identifier)
        self.student_admin_section.click_skip_entrance_exam_button()
        #first we have window.confirm
        alert = get_modal_alert(self.student_admin_section.browser)
        alert.accept()

        # then we have alert confirming action
        alert = get_modal_alert(self.student_admin_section.browser)
        alert.dismiss()

    def test_clicking_skip_entrance_exam_button_with_error(self):
        """
        Scenario: Clicking on the Let Student Skip Entrance Exam button with
        email address or username of a non existing student should result in error message.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the Let Student Skip Entrance Exam Button under
            Entrance Exam Grade Adjustment after entering non existing
            student email address or username
            Then I should be shown an error message
        """
        self.student_admin_section.set_student_email('non_existing@example.com')
        self.student_admin_section.click_skip_entrance_exam_button()
        #first we have window.confirm
        alert = get_modal_alert(self.student_admin_section.browser)
        alert.accept()

        self.student_admin_section.wait_for_ajax()
        self.assertGreater(len(self.student_admin_section.top_notification.text[0]), 0)

    def test_clicking_delete_student_attempts_button_with_success(self):
        """
        Scenario: Clicking on the Delete Student State for entrance exam button
        with valid student email address or username should result in success prompt.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the Delete Student State for entrance exam Button
            under Entrance Exam Grade Adjustment after entering a valid student
            email address or username
            Then I should be shown an alert with success message
        """
        self.student_admin_section.set_student_email(self.student_identifier)
        self.student_admin_section.click_delete_student_state_button()
        alert = get_modal_alert(self.student_admin_section.browser)
        alert.dismiss()

    def test_clicking_delete_student_attempts_button_with_error(self):
        """
        Scenario: Clicking on the Delete Student State for entrance exam button
        with email address or username of a non existing student should result
        in error message.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the Delete Student State for entrance exam Button
            under Entrance Exam Grade Adjustment after non existing student
            email address or username
            Then I should be shown an error message
        """
        self.student_admin_section.set_student_email('non_existing@example.com')
        self.student_admin_section.click_delete_student_state_button()
        self.student_admin_section.wait_for_ajax()
        self.assertGreater(len(self.student_admin_section.top_notification.text[0]), 0)

    def test_clicking_task_history_button_with_success(self):
        """
        Scenario: Clicking on the Show Background Task History for Student
        with valid student email address or username should result in table of tasks.
            Given that I am on the Student Admin tab on the Instructor Dashboard
            When I click the Show Background Task History for Student Button
            under Entrance Exam Grade Adjustment after entering a valid student
            email address or username
            Then I should be shown an table listing all background tasks
        """
        self.student_admin_section.set_student_email(self.student_identifier)
        self.student_admin_section.click_task_history_button()
        self.assertTrue(self.student_admin_section.is_background_task_history_table_visible())


class DataDownloadsTest(BaseInstructorDashboardTest):
    """
    Bok Choy tests for the "Data Downloads" tab.
    """
    def setUp(self):
        super(DataDownloadsTest, self).setUp()
        self.course_fixture = CourseFixture(**self.course_info).install()
        self.instructor_username, self.instructor_id = self.log_in_as_instructor()
        instructor_dashboard_page = self.visit_instructor_dashboard()
        self.data_download_section = instructor_dashboard_page.select_data_download()

    def verify_report_requested_event(self, report_type):
        """
        Verifies that the correct event is emitted when a report is requested.
        """
        self.assert_matching_events_were_emitted(
            event_filter={'name': u'edx.instructor.report.requested', 'report_type': report_type}
        )

    def verify_report_downloaded_event(self, report_url):
        """
        Verifies that the correct event is emitted when a report is downloaded.
        """
        self.assert_matching_events_were_emitted(
            event_filter={'name': u'edx.instructor.report.downloaded', 'report_url': report_url}
        )

    def verify_report_download(self, report_name):
        """
        Verifies that a report can be downloaded and an event fired.
        """
        download_links = self.data_download_section.report_download_links
        self.assertEquals(len(download_links), 1)
        download_links[0].click()
        expected_url = download_links.attrs('href')[0]
        self.assertIn(report_name, expected_url)
        self.verify_report_downloaded_event(expected_url)

    def test_student_profiles_report_download(self):
        """
        Scenario: Verify that an instructor can download a student profiles report

        Given that I am an instructor
        And I visit the instructor dashboard's "Data Downloads" tab
        And I click on the "Download profile information as a CSV" button
        Then a report should be generated
        And a report requested event should be emitted
        When I click on the report
        Then a report downloaded event should be emitted
        """
        report_name = u"student_profile_info"
        self.data_download_section.generate_student_report_button.click()
        self.data_download_section.wait_for_available_report()
        self.verify_report_requested_event(report_name)
        self.verify_report_download(report_name)

    def test_grade_report_download(self):
        """
        Scenario: Verify that an instructor can download a grade report

        Given that I am an instructor
        And I visit the instructor dashboard's "Data Downloads" tab
        And I click on the "Generate Grade Report" button
        Then a report should be generated
        And a report requested event should be emitted
        When I click on the report
        Then a report downloaded event should be emitted
        """
        report_name = u"grade_report"
        self.data_download_section.generate_grade_report_button.click()
        self.data_download_section.wait_for_available_report()
        self.verify_report_requested_event(report_name)
        self.verify_report_download(report_name)

    def test_problem_grade_report_download(self):
        """
        Scenario: Verify that an instructor can download a problem grade report

        Given that I am an instructor
        And I visit the instructor dashboard's "Data Downloads" tab
        And I click on the "Generate Problem Grade Report" button
        Then a report should be generated
        And a report requested event should be emitted
        When I click on the report
        Then a report downloaded event should be emitted
        """
        report_name = u"problem_grade_report"
        self.data_download_section.generate_problem_report_button.click()
        self.data_download_section.wait_for_available_report()
        self.verify_report_requested_event(report_name)
        self.verify_report_download(report_name)


@attr('shard_1')
class CertificatesTest(BaseInstructorDashboardTest):
    """
    Tests for Certificates functionality on instructor dashboard.
    """

    def setUp(self):
        super(CertificatesTest, self).setUp()
        self.test_certificate_config = {
            'id': 1,
            'name': 'Certificate name',
            'description': 'Certificate description',
            'course_title': 'Course title override',
            'signatories': [],
            'version': 1,
            'is_active': True
        }
        CourseFixture(**self.course_info).install()
        self.cert_fixture = CertificateConfigFixture(self.course_id, self.test_certificate_config)
        self.cert_fixture.install()
        self.user_name, self.user_id = self.log_in_as_instructor()
        self.instructor_dashboard_page = self.visit_instructor_dashboard()
        self.certificates_section = self.instructor_dashboard_page.select_certificates()
        disable_animations(self.certificates_section)

    def test_generate_certificates_buttons_is_disable(self):
        """
        Scenario: On the Certificates tab of the Instructor Dashboard, Generate Certificates button is disable.
            Given that I am on the Certificates tab on the Instructor Dashboard
            The instructor-generation and cert_html_view_enabled feature flags have been enabled
            But the certificate is not active in settings.
            Then I see a 'Generate Certificates' button disabled
        """
        self.test_certificate_config['is_active'] = False
        self.cert_fixture.update_certificate(1)
        self.browser.refresh()
        self.assertFalse(self.certificates_section.generate_certificates_button.visible)
        self.assertTrue(self.certificates_section.generate_certificates_disabled_button.visible)

    def test_generate_certificates_buttons_is_visible(self):
        """
        Scenario: On the Certificates tab of the Instructor Dashboard, Generate Certificates button is visible.
            Given that I am on the Certificates tab on the Instructor Dashboard
            And the instructor-generation feature flag has been enabled
            Then I see a 'Generate Certificates' button
            And when I click on the 'Generate Certificates' button
            Then I should see a status message and 'Generate Certificates' button should be disabled.
        """
        self.assertTrue(self.certificates_section.generate_certificates_button.visible)
        self.certificates_section.generate_certificates_button.click()
        alert = get_modal_alert(self.certificates_section.browser)
        alert.accept()

        self.certificates_section.wait_for_ajax()
        EmptyPromise(
            lambda: self.certificates_section.certificate_generation_status.visible,
            'Certificate generation status shown'
        ).fulfill()
        disabled = self.certificates_section.generate_certificates_button.attrs('disabled')
        self.assertEqual(disabled[0], 'true')

    def test_pending_tasks_section_is_visible(self):
        """
        Scenario: On the Certificates tab of the Instructor Dashboard, Pending Instructor Tasks section is visible.
            Given that I am on the Certificates tab on the Instructor Dashboard
            Then I see 'Pending Instructor Tasks' section
        """
        self.assertTrue(self.certificates_section.pending_tasks_section.visible)

    def test_certificate_exceptions_section_is_visible(self):
        """
        Scenario: On the Certificates tab of the Instructor Dashboard, Certificate Exceptions section is visible.
            Given that I am on the Certificates tab on the Instructor Dashboard
            Then I see 'CERTIFICATE EXCEPTIONS' section
        """
        self.assertTrue(self.certificates_section.certificate_exceptions_section.visible)

    def test_instructor_can_add_certificate_exception(self):
        """
        Scenario: On the Certificates tab of the Instructor Dashboard, Instructor can added new certificate
        exception to list

            Given that I am on the Certificates tab on the Instructor Dashboard
            When I fill in student username and click 'Add Exception' button
            Then new certificate exception should be visible in certificate exceptions list
        """
        # Add a student to Certificate exception list
        self.certificates_section.add_certificate_exception(self.user_name, '')
        self.assertIn(self.user_name, self.certificates_section.last_certificate_exception.text)

    def test_error_on_duplicate_certificate_exception(self):
        """
        Scenario: On the Certificates tab of the Instructor Dashboard,
        Error message appears if student being added already exists in certificate exceptions list

            Given that I am on the Certificates tab on the Instructor Dashboard
            When I fill in student username that already is in the list and click 'Add Exception' button
            Then Error Message should say 'username/email already in exception list'
        """
        # Add a student to Certificate exception list
        self.certificates_section.add_certificate_exception(self.user_name, '')

        # Add duplicate student to Certificate exception list
        self.certificates_section.add_certificate_exception(self.user_name, '')

        self.assertIn(
            'username/email already in exception list',
            self.certificates_section.message.text
        )

    def test_error_on_empty_user_name(self):
        """
        Scenario: On the Certificates tab of the Instructor Dashboard,
        Error message appears if no username/email is entered while clicking "Add Exception" button

            Given that I am on the Certificates tab on the Instructor Dashboard
            When I click on 'Add Exception' button
            AND student username/email field is empty
            Then Error Message should say 'Student username/email is required.'
        """
        # Click 'Add Exception' button without filling username/email field
        self.certificates_section.wait_for_certificate_exceptions_section()
        self.certificates_section.click_add_exception_button()

        self.assertIn(
            'Student username/email is required.',
            self.certificates_section.message.text
        )

    def test_generate_certificate_exception(self):
        """
        Scenario: On the Certificates tab of the Instructor Dashboard, when user clicks
        'Generate Exception Certificates' newly added certificate exceptions should be synced on server

            Given that I am on the Certificates tab on the Instructor Dashboard
            When I click 'Generate Exception Certificates'
            Then newly added certificate exceptions should be synced on server
        """
        # Add a student to Certificate exception list
        self.certificates_section.add_certificate_exception(self.user_name, '')

        # Click 'Generate Exception Certificates' button
        self.certificates_section.click_generate_certificate_exceptions_button()
        self.certificates_section.wait_for_ajax()

        # Revisit Page
        self.certificates_section.refresh()

        # wait for the certificate exception section to render
        self.certificates_section.wait_for_certificate_exceptions_section()

        # validate certificate exception synced with server is visible in certificate exceptions list
        self.assertIn(self.user_name, self.certificates_section.last_certificate_exception.text)

    def test_invalid_user_on_generate_certificate_exception(self):
        """
        Scenario: On the Certificates tab of the Instructor Dashboard, when user clicks
        'Generate Exception Certificates' error message should appear if user does not exist

            Given that I am on the Certificates tab on the Instructor Dashboard
            When I click 'Generate Exception Certificates'
            AND the user specified by instructor does not exist
            Then an error message "Student (username/email=test_user) does not exist" is displayed
        """
        invalid_user = 'test_user_non_existent'
        # Add a student to Certificate exception list
        self.certificates_section.add_certificate_exception(invalid_user, '')

        # Click 'Generate Exception Certificates' button
        self.certificates_section.click_generate_certificate_exceptions_button()
        self.certificates_section.wait_for_ajax()

        # validate certificate exception synced with server is visible in certificate exceptions list
        self.assertIn(
            'Student (username/email={}) does not exist'.format(invalid_user),
            self.certificates_section.message.text
        )
