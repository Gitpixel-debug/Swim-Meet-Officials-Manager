"""
Tests for the UI/UX redesign.
Verifies all pages render correctly with the new sidebar layout,
design system classes, and proper template inheritance.
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from meets.models import (
    Meet, Session, SessionAssignment, Certification,
    DeckAssignment, VolunteerLog, RosterEntry, RosterCertification,
)

User = get_user_model()


class BaseTestCase(TestCase):
    """Shared setup: creates a referee, an official, a meet, and a session."""

    def setUp(self):
        self.client = Client()
        self.referee = User.objects.create_user(
            username="referee1", password="pass1234",
            first_name="Ref", last_name="Eree", email="ref@test.com",
        )
        self.official = User.objects.create_user(
            username="official1", password="pass1234",
            first_name="Off", last_name="Icial", email="off@test.com",
            phone="555-0100",
        )
        self.cert = Certification.objects.create(name="S&T-C", level="")
        self.official.certifications.add(self.cert)
        # RosterEntry + RosterCertification (used by official_dashboard)
        self.roster_entry = RosterEntry.objects.create(
            member_id="official1", first_name="Off", last_name="Icial",
            email="off@test.com", club="TEST",
        )
        RosterCertification.objects.create(
            roster=self.roster_entry, name="st-c", value="2026-01-01",
        )

        self.meet = Meet.objects.create(
            name="Spring Classic",
            location="Pool Center",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=1),
            created_by=self.referee,
            num_sessions=1,
            course_type="SCY",
            num_pools=1,
        )
        self.session = Session.objects.create(
            meet=self.meet,
            session_number=1,
            date=date.today(),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        self.assignment = SessionAssignment.objects.create(
            session=self.session,
            official=self.official,
            hours_worked=Decimal("0"),
            checked_in=False,
        )


# ── Auth pages (unauthenticated) ──────────────────────────

class AuthPagesTest(TestCase):
    """Login, register, and index pages use auth-card layout."""

    def test_login_page_renders(self):
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "auth-card")
        self.assertContains(resp, "Sign In")

    def test_register_page_redirects_to_login(self):
        resp = self.client.get(reverse("register"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_index_unauthenticated_redirects_to_login(self):
        resp = self.client.get(reverse("index"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_login_page_has_no_sidebar(self):
        resp = self.client.get(reverse("login"))
        self.assertNotContains(resp, "sidebar")


# ── Sidebar layout for authenticated pages ─────────────────

class SidebarLayoutTest(BaseTestCase):
    """All authenticated pages include the sidebar structure."""

    def test_dashboard_has_sidebar(self):
        self.client.login(username="official1", password="pass1234")
        resp = self.client.get(reverse("official-dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "app-container")
        self.assertContains(resp, '<aside class="sidebar"')
        self.assertContains(resp, "main-content")

    def test_meet_home_has_sidebar(self):
        self.client.login(username="referee1", password="pass1234")
        resp = self.client.get(reverse("meet-home", args=[self.meet.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "app-container")

    def test_session_home_has_sidebar(self):
        self.client.login(username="referee1", password="pass1234")
        resp = self.client.get(reverse("session-home", args=[self.session.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "app-container")


# ── Dashboard page ─────────────────────────────────────────

class DashboardPageTest(BaseTestCase):
    """Official dashboard displays stat cards, certs, and meets."""

    def setUp(self):
        super().setUp()
        self.client.login(username="official1", password="pass1234")

    def test_dashboard_renders(self):
        resp = self.client.get(reverse("official-dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_stat_cards(self):
        resp = self.client.get(reverse("official-dashboard"))
        self.assertContains(resp, "stat-card")
        self.assertContains(resp, "Volunteer Hours")

    def test_dashboard_certifications(self):
        resp = self.client.get(reverse("official-dashboard"))
        self.assertContains(resp, "cert-badge")
        self.assertContains(resp, "st-c")

    def test_dashboard_empty_state_no_meets(self):
        # officials with no available meets should see empty state
        self.meet.delete()
        resp = self.client.get(reverse("official-dashboard"))
        self.assertContains(resp, "empty-state")

    def test_dashboard_enrollments_filter(self):
        resp = self.client.get(reverse("official-dashboard") + "?filter=present")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "My Enrollments")

    def test_dashboard_extends_layout(self):
        """Dashboard should use layout.html, not its own HTML skeleton."""
        resp = self.client.get(reverse("official-dashboard"))
        # Should NOT contain a standalone <html> tag (it extends layout.html)
        content = resp.content.decode()
        # Count <html> occurrences — should be exactly 1 (from layout.html)
        self.assertEqual(content.lower().count("<html"), 1)

    def test_dashboard_nav_active(self):
        resp = self.client.get(reverse("official-dashboard"))
        self.assertContains(resp, "active")


# ── Meet home page ─────────────────────────────────────────

class MeetHomePageTest(BaseTestCase):
    """meet_home.html renders sessions table with new design classes."""

    def setUp(self):
        super().setUp()
        self.client.login(username="referee1", password="pass1234")

    def test_meet_home_renders(self):
        resp = self.client.get(reverse("meet-home", args=[self.meet.id]))
        self.assertEqual(resp.status_code, 200)

    def test_meet_home_header_card(self):
        resp = self.client.get(reverse("meet-home", args=[self.meet.id]))
        self.assertContains(resp, "header-card")
        self.assertContains(resp, "Spring Classic")

    def test_meet_home_sessions_table(self):
        resp = self.client.get(reverse("meet-home", args=[self.meet.id]))
        self.assertContains(resp, "session-row")
        self.assertContains(resp, "Session 1")

    def test_meet_home_add_session_button(self):
        resp = self.client.get(reverse("meet-home", args=[self.meet.id]))
        self.assertContains(resp, "Add Session")
        self.assertContains(resp, "addSessionModal")

    def test_meet_home_no_data_aos(self):
        """Old data-aos attributes should be removed."""
        resp = self.client.get(reverse("meet-home", args=[self.meet.id]))
        self.assertNotContains(resp, "data-aos")


# ── Session home page ──────────────────────────────────────

class SessionHomePageTest(BaseTestCase):
    """session_home.html with header card and action buttons."""

    def setUp(self):
        super().setUp()
        self.client.login(username="referee1", password="pass1234")

    def test_session_home_renders(self):
        resp = self.client.get(reverse("session-home", args=[self.session.id]))
        self.assertEqual(resp.status_code, 200)

    def test_session_home_header_card(self):
        resp = self.client.get(reverse("session-home", args=[self.session.id]))
        self.assertContains(resp, "header-card")

    def test_session_home_status_badge(self):
        resp = self.client.get(reverse("session-home", args=[self.session.id]))
        self.assertContains(resp, "status-badge")

    def test_session_home_action_buttons(self):
        resp = self.client.get(reverse("session-home", args=[self.session.id]))
        self.assertContains(resp, "Back to Meet")
        self.assertContains(resp, "Manage Deck Assignments")

    def test_session_home_empty_officials(self):
        resp = self.client.get(reverse("session-home", args=[self.session.id]))
        self.assertContains(resp, "empty-state")

    def test_session_home_checked_official(self):
        self.assignment.checked_in = True
        self.assignment.save()
        resp = self.client.get(reverse("session-home", args=[self.session.id]))
        self.assertContains(resp, "Off Icial")
        self.assertContains(resp, "Checked In")


# ── Deck assignments page ──────────────────────────────────

class DeckAssignmentsPageTest(BaseTestCase):
    """deck_assignments.html renders with new design."""

    def setUp(self):
        super().setUp()
        self.assignment.checked_in = True
        self.assignment.save()
        self.client.login(username="referee1", password="pass1234")

    def test_deck_assignments_renders(self):
        resp = self.client.get(reverse("deck-assignments", args=[self.session.id]))
        self.assertEqual(resp.status_code, 200)

    def test_deck_assignments_header_card(self):
        resp = self.client.get(reverse("deck-assignments", args=[self.session.id]))
        self.assertContains(resp, "header-card")
        self.assertContains(resp, "Deck Assignments")

    def test_deck_assignments_generate_button(self):
        resp = self.client.get(reverse("deck-assignments", args=[self.session.id]))
        self.assertContains(resp, "Generate Deck")

    def test_deck_assignments_save_button(self):
        resp = self.client.get(reverse("deck-assignments", args=[self.session.id]))
        self.assertContains(resp, "Save Changes")


# ── Meet create page ───────────────────────────────────────

class MeetCreatePageTest(BaseTestCase):
    """meet_create.html form card."""

    def setUp(self):
        super().setUp()
        self.client.login(username="referee1", password="pass1234")

    def test_meet_create_renders(self):
        resp = self.client.get(reverse("meet-create"))
        self.assertEqual(resp.status_code, 200)

    def test_meet_create_title(self):
        resp = self.client.get(reverse("meet-create"))
        self.assertContains(resp, "Create New Meet")

    def test_meet_create_has_form_fields(self):
        resp = self.client.get(reverse("meet-create"))
        self.assertContains(resp, "Meet Name")
        self.assertContains(resp, "Course Type")
        self.assertContains(resp, "Has Relay Events")

    def test_meet_create_no_shadow_lg(self):
        """Old card classes should be replaced."""
        resp = self.client.get(reverse("meet-create"))
        self.assertNotContains(resp, "shadow-lg")
        self.assertNotContains(resp, "rounded-4")


# ── Join meet page ─────────────────────────────────────────

class JoinMeetPageTest(BaseTestCase):
    """join_meet.html renders with new layout."""

    def setUp(self):
        super().setUp()
        self.client.login(username="official1", password="pass1234")

    def test_join_meet_renders(self):
        resp = self.client.get(reverse("join-meet"))
        self.assertEqual(resp.status_code, 200)

    def test_join_meet_title(self):
        resp = self.client.get(reverse("join-meet"))
        self.assertContains(resp, "Join a Session")

    def test_join_meet_form(self):
        resp = self.client.get(reverse("join-meet"))
        self.assertContains(resp, "join_code")

    def test_join_meet_no_data_aos(self):
        resp = self.client.get(reverse("join-meet"))
        self.assertNotContains(resp, "data-aos")


# ── Referee dashboard ──────────────────────────────────────

class RefereeDashboardPageTest(BaseTestCase):
    """referee_dashboard.html with meet grid cards."""

    def setUp(self):
        super().setUp()
        self.client.login(username="referee1", password="pass1234")

    def test_referee_dashboard_renders(self):
        resp = self.client.get(reverse("referee-dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_referee_dashboard_meet_cards(self):
        resp = self.client.get(reverse("referee-dashboard"))
        self.assertContains(resp, "meet-grid-card")
        self.assertContains(resp, "Spring Classic")

    def test_referee_dashboard_empty_state(self):
        self.meet.delete()
        resp = self.client.get(reverse("referee-dashboard"))
        self.assertContains(resp, "empty-state")


# ── Results page ───────────────────────────────────────────

class ResultsPageTest(BaseTestCase):
    """results.html renders with new design."""

    def setUp(self):
        super().setUp()
        self.session.status = "ended"
        self.session.save()
        VolunteerLog.objects.create(
            session=self.session,
            official=self.official,
            role="Stroke & Turn",
            hours_worked=Decimal("2.5"),
        )
        self.client.login(username="referee1", password="pass1234")

    def test_results_renders(self):
        resp = self.client.get(reverse("session-results", args=[self.session.id]))
        self.assertEqual(resp.status_code, 200)

    def test_results_header_card(self):
        resp = self.client.get(reverse("session-results", args=[self.session.id]))
        self.assertContains(resp, "header-card")

    def test_results_table(self):
        resp = self.client.get(reverse("session-results", args=[self.session.id]))
        self.assertContains(resp, "Off Icial")
        self.assertContains(resp, "Save Changes")


# ── Check-in status pages ─────────────────────────────────

class CheckInPagesTest(BaseTestCase):
    """check_in_success and check_in_fail use card layout."""

    def test_check_in_success_structure(self):
        """Verify the success template contains the new card structure."""
        from django.template.loader import render_to_string
        html = render_to_string("meets/check_in_success.html", {
            "assignment": self.assignment,
        })
        self.assertIn("card", html)
        self.assertIn("Checked In", html)

    def test_check_in_fail_structure(self):
        from django.template.loader import render_to_string
        html = render_to_string("meets/check_in_fail.html", {})
        self.assertIn("card", html)
        self.assertIn("Check-In Failed", html)


# ── CSS design system classes across all pages ─────────────

class DesignSystemConsistencyTest(BaseTestCase):
    """Spot-check that old Bootstrap workaround classes are gone."""

    def setUp(self):
        super().setUp()
        self.client.login(username="referee1", password="pass1234")

    def test_no_old_custom_btn_classes(self):
        for url in [reverse("official-dashboard"), reverse("meet-create"), reverse("join-meet")]:
            resp = self.client.get(url)
            self.assertNotContains(resp, "btn-custom", msg_prefix=url)
            self.assertNotContains(resp, "btn-referee", msg_prefix=url)
            self.assertNotContains(resp, "btn-official", msg_prefix=url)

    def test_uses_fade_in_up(self):
        """Authenticated pages use the new fade-in-up animation class."""
        resp = self.client.get(reverse("official-dashboard"))
        self.assertContains(resp, "fade-in-up")

    def test_no_data_aos_anywhere(self):
        """All data-aos attributes should have been removed."""
        pages = [
            reverse("official-dashboard"),
            reverse("meet-home", args=[self.meet.id]),
            reverse("session-home", args=[self.session.id]),
            reverse("meet-create"),
            reverse("join-meet"),
        ]
        for url in pages:
            resp = self.client.get(url)
            self.assertNotContains(resp, "data-aos", msg_prefix=url)
