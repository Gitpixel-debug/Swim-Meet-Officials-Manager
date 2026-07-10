from collections import defaultdict
import json
from datetime import datetime
from django.db import transaction
from ..models import Session, SessionAssignment, DeckAssignment, User, RosterEntry, RosterCertification

# Base role counts for a single pool
ROLE_COUNTS = {
    'Starter': 1,
    'Deck Referee': 1,
    'Chief Judge': 1,
    'Stroke & Turn': 2,
    'Admin Official': 1,
}

# mapping certification codes to primary roles
CERT_ROLE_MAP = {
    'SR-C': 'Starter', 'SR-A': 'Starter',
    'DR-C': 'Deck Referee', 'DR-A': 'Deck Referee',
    'CJ-C': 'Chief Judge', 'CJ-A': 'Chief Judge',
    'ST-C': 'Stroke & Turn', 'ST-A': 'Stroke & Turn',
    'AO-C': 'Admin Official', 'AO-A': 'Admin Official',
}

# Extra roles available to Stroke & Turn officials
# Runner: needed for LCM meets (one per session)
# Relay Start Checker: needed when session has relay starts (one per pool)
ST_EXTRA_ROLES = ['Runner', 'Relay Start Checker']


def get_extra_roles(session):
    """Return list of extra roles required for this session based on meet settings."""
    extra = []
    meet = session.meet
    if getattr(meet, 'course_type', 'SCY') == 'LCM':
        extra.append('Runner')
    if getattr(session, 'has_relay_starts', False):
        extra.append('Relay Start Checker')
    return extra


def get_allowed_roles(cert_codes, session=None):
    """Return list of role names an official with these cert codes can fill."""
    roles = []
    for code in cert_codes:
        role = CERT_ROLE_MAP.get(code)
        if role and role not in roles:
            roles.append(role)
    # If official has ST cert, add extra roles when applicable
    has_st = any(c in cert_codes for c in ('ST-C', 'ST-A'))
    if has_st and session:
        for extra in get_extra_roles(session):
            if extra not in roles:
                roles.append(extra)
    return roles


def _parse_cert_date(val):
    """Parse a certification expiry date string into a date object."""
    if not val:
        return None
    for fmt in ('%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _official_cert_codes(user):
    """Return set of certification codes from user's roster entry."""
    codes = set()
    roster = RosterEntry.objects.filter(member_id__iexact=user.username).first()
    if not roster:
        return codes
    for cert in roster.certifications.all():
        nm = (cert.name or '').upper().strip()
        if nm:
            codes.add(nm)
    return codes


def _assign_pool(officials, session, pool_number, assigned_officials, extra_role_counts):
    """Assign officials to roles for a single pool. Returns dict of {official_id: info}."""
    assignments = {}

    eligible = {o.id: _official_cert_codes(o) for o in officials}

    certified_pool = defaultdict(list)
    apprentice_pool = defaultdict(list)
    for o in officials:
        if o.id in assigned_officials:
            continue
        codes = eligible.get(o.id, set())
        for code in codes:
            role = CERT_ROLE_MAP.get(code)
            if not role:
                continue
            if code.endswith('-C'):
                certified_pool[role].append(o)
            elif code.endswith('-A'):
                apprentice_pool[role].append(o)

    def sort_candidates(lst):
        return sorted(lst, key=lambda u: float(getattr(u, 'total_volunteer_hours', 0) or 0))

    for r in certified_pool:
        certified_pool[r] = sort_candidates(certified_pool[r])
    for r in apprentice_pool:
        apprentice_pool[r] = sort_candidates(apprentice_pool[r])

    newly_assigned = set()

    def try_assign(role, count):
        need = count
        assigned_here = []
        for cands in [certified_pool.get(role, []), apprentice_pool.get(role, [])]:
            while need > 0 and cands:
                o = cands.pop(0)
                if o.id in assigned_officials or o.id in newly_assigned:
                    continue
                assignments[o.id] = {'role': role, 'pool_number': pool_number, 'break_schedule': []}
                newly_assigned.add(o.id)
                assigned_here.append(o)
                need -= 1
            if need == 0:
                break
        return assigned_here

    # Standard roles
    for role, count in ROLE_COUNTS.items():
        try_assign(role, count)

    # Extra roles for this pool
    for role in extra_role_counts:
        try_assign(role, extra_role_counts[role])

    # Fill any completely unassigned officials into remaining needed slots
    unassigned = [o for o in officials if o.id not in assigned_officials and o.id not in newly_assigned]
    for role, count in ROLE_COUNTS.items():
        current = sum(1 for v in assignments.values() if v['role'] == role)
        need = count - current
        while need > 0 and unassigned:
            o = unassigned.pop(0)
            assignments[o.id] = {'role': role, 'pool_number': pool_number, 'break_schedule': []}
            newly_assigned.add(o.id)
            need -= 1

    assigned_officials.update(newly_assigned)
    return assignments


def generate_deck_assignments(session):
    """
    Generate assignments for a session per pool.
    Returns dict: {official_id: {'role': role, 'pool_number': N, 'break_schedule': [...]}}
    """
    meet = session.meet
    num_pools = max(getattr(meet, 'num_pools', 1) or 1, 1)

    # Build extra role counts per pool
    extra_role_counts = {}
    extra_roles = get_extra_roles(session)
    for role in extra_roles:
        extra_role_counts[role] = 1  # 1 per pool

    checked = SessionAssignment.objects.filter(session=session, checked_in=True).select_related('official')
    if session.status == 'in_progress':
        on_break_ids = DeckAssignment.objects.filter(session=session, on_break=True).values_list('official_id', flat=True)
        checked = checked.exclude(official_id__in=on_break_ids)

    officials = [sa.official for sa in checked]

    all_assignments = {}
    assigned_officials = set()

    for pool_num in range(1, num_pools + 1):
        pool_assignments = _assign_pool(officials, session, pool_num, assigned_officials, extra_role_counts)
        all_assignments.update(pool_assignments)

    # Add break schedule placeholders
    for idx, (oid, info) in enumerate(all_assignments.items()):
        info['break_schedule'] = [idx % 2]

    return all_assignments


@transaction.atomic
def finalize_and_save_assignments(session, assignments):
    """
    Persist assignments (replace existing DeckAssignment rows for this session).
    assignments: {official_id: {'role': ..., 'pool_number': N, 'break_schedule': [...]}}
    """
    DeckAssignment.objects.filter(session=session).delete()

    for oid, info in assignments.items():
        try:
            user = User.objects.get(pk=oid)
        except User.DoesNotExist:
            continue
        DeckAssignment.objects.create(
            session=session,
            official=user,
            role=info.get('role') or '',
            pool_number=int(info.get('pool_number') or 1),
            break_schedule=json.dumps(info.get('break_schedule', [])),
        )

    st = datetime.combine(session.date, session.start_time)
    et = datetime.combine(session.date, session.end_time)
    duration_hours = max((et - st).total_seconds() / 3600.0, 0)

    for da in DeckAssignment.objects.filter(session=session).select_related('official'):
        sa, _ = SessionAssignment.objects.get_or_create(
            session=session, official=da.official, defaults={'hours_worked': 0}
        )
        sa.hours_worked = round(duration_hours, 2)
        sa.save()