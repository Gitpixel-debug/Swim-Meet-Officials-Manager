# models.py

import uuid
from datetime import datetime, date

from django.db import models
from django.contrib.auth.models import AbstractUser


# =====================================================
# USER (Officials)
# =====================================================

class User(AbstractUser):
    """
    Your officials.
    Extends Django auth user.
    """
    phone = models.CharField(max_length=20, blank=True)

    certifications = models.ManyToManyField(
        'Certification',
        blank=True,
        related_name='officials'
    )

    # accumulated volunteering hours across all meets (computed from SessionAssignment.hours_worked)
    # NOTE: this was intentionally left computed; do not add persistent field here to avoid migration issues.

    def __str__(self):
        return self.get_full_name() or self.username


# =====================================================
# CERTIFICATIONS (your "Meet Official DB")
# =====================================================

class Certification(models.Model):
    name = models.CharField(max_length=100)
    level = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.name} {self.level}".strip()


# =====================================================
# MEET (MAIN OBJECT — Meet Creation)
# =====================================================

class Meet(models.Model):
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=255)

    start_date = models.DateField()
    end_date = models.DateField()

    description = models.TextField(blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_meets"
    )

    join_code = models.CharField(max_length=10, unique=True, editable=False)

    num_sessions = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.join_code:
            self.join_code = uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# =====================================================
# SESSIONS (Session DB in your diagram)
# =====================================================

class Session(models.Model):
    meet = models.ForeignKey(
        Meet,
        on_delete=models.CASCADE,
        related_name='sessions'
    )

    session_number = models.PositiveIntegerField(default=1)

    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    join_code = models.CharField(max_length=10, editable=False, default='')

    class Meta:
        unique_together = ("meet", "session_number")
        ordering = ["session_number"]
    
    def save(self, *args, **kwargs):
        if not self.join_code:
            self.join_code = uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.meet.name} - Session {self.session_number}"


# =====================================================
# SESSION ASSIGNMENTS (dynamic hours tracking)
# =====================================================

class SessionAssignment(models.Model):
    """
    Tracks which official worked which session + hours.
    """
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    official = models.ForeignKey(User, on_delete=models.CASCADE)

    hours_worked = models.DecimalField(max_digits=4, decimal_places=2)
    # metadata for CSV imports and check-in flow
    created_via_csv = models.BooleanField(default=False)
    join_code_sent = models.BooleanField(default=False)
    checked_in = models.BooleanField(default=False)

    # link to imported row (if created via CSV import)
    imported_official = models.ForeignKey(
        'ImportedOfficial',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments'
    )

    class Meta:
        unique_together = ("session", "official")

    def __str__(self):
        return f"{self.official} - {self.session} ({self.hours_worked}h)"

# meets/models.py

class Official(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone_number = models.CharField(max_length=15)
    certification = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class ImportedOfficial(models.Model):
    """Stores one row from an uploaded CSV mapped to fields we care about."""
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='imported_officials')
    first_name = models.CharField(max_length=200, blank=True)
    last_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    member_id = models.CharField(max_length=100, blank=True)
    club = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} <{self.email}>"


class ImportedCertification(models.Model):
    imported = models.ForeignKey(ImportedOfficial, on_delete=models.CASCADE, related_name='certifications')
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.imported}: {self.name}={self.value}"


class RosterEntry(models.Model):
    member_id = models.CharField(max_length=100, unique=True)
    first_name = models.CharField(max_length=200, blank=True)
    last_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    club = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.member_id}: {self.first_name} {self.last_name} <{self.email}>"


class RosterCertification(models.Model):
    roster = models.ForeignKey(RosterEntry, on_delete=models.CASCADE, related_name='certifications')
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.roster.member_id}: {self.name}={self.value}"


class DeckAssignment(models.Model):
    """Assignment of an official to a deck role for a session."""
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='deck_assignments')
    official = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deck_assignments')
    role = models.CharField(max_length=100)
    # JSON-like break schedule stored as text: list of break slot strings or indices
    break_schedule = models.TextField(blank=True, default='[]')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'official')

    def __str__(self):
        return f"{self.session} - {self.official} as {self.role}"
