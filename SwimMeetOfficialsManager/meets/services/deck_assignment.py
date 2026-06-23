from collections import defaultdict
import json
from datetime import datetime
from django.db import transaction
from ..models import Session, SessionAssignment, DeckAssignment, User, RosterEntry, RosterCertification

# role constants and required counts
ROLE_COUNTS = {
    'Starter': 1,
    'Deck Referee': 1,
    'Chief Judge': 1,
    'Stroke & Turn': 2,
    'Admin Official': 1,
}

# mapping certification codes to roles
CERT_ROLE_MAP = {
    'SR-C': 'Starter', 'SR-A': 'Starter',
    'DR-C': 'Deck Referee', 'DR-A': 'Deck Referee',
    'CJ-C': 'Chief Judge', 'CJ-A': 'Chief Judge',
    'ST-C': 'Stroke & Turn', 'ST-A': 'Stroke & Turn',
    'AO-C': 'Admin Official', 'AO-A': 'Admin Official',
}


def _official_cert_codes(user):
    # return set of certification codes (e.g. 'SR-C', 'AO-A') from user's certifications
    # Certifications are stored in RosterCertification linked to RosterEntry
    codes = set()
    
    # Find the RosterEntry for this user (username == member_id)
    roster = RosterEntry.objects.filter(member_id__iexact=user.username).first()
    if not roster:
        return codes
    
    # Get all certifications for this roster entry
    for cert in roster.certifications.all():
        nm = (cert.name or '').upper().strip()
        if nm:
            # RosterCertification.name is already a full code like 'ao-a', 'dr-a', etc. from CSV
            code = nm
            codes.add(code)
    
    return codes


def generate_deck_assignments(session):
    """
    Generate assignments for a session.
    Returns dict: {official_id: {'role': role, 'break_schedule': [...]} }
    """
    # Consider all officials associated with the session
    checked = SessionAssignment.objects.filter(session=session).select_related('official')
    officials = [sa.official for sa in checked]

    # build eligibility
    eligible = {}
    for o in officials:
        codes = _official_cert_codes(o)
        eligible[o.id] = codes

    # helper: find officials eligible for a role with certified vs apprentice separation
    certified_pool = defaultdict(list)
    apprentice_pool = defaultdict(list)
    for o in officials:
        codes = eligible.get(o.id, set())
        for code in codes:
            # map code to role if possible
            role = CERT_ROLE_MAP.get(code)
            if not role:
                continue
            if code.endswith('-C'):
                certified_pool[role].append(o)
            elif code.endswith('-A'):
                apprentice_pool[role].append(o)

    # sorting by historical volunteer hours ascending (prefer low hours)
    def sort_candidates(lst):
        return sorted(lst, key=lambda u: float(getattr(u, 'total_volunteer_hours', 0) or 0))

    for r in certified_pool:
        certified_pool[r] = sort_candidates(certified_pool[r])
    for r in apprentice_pool:
        apprentice_pool[r] = sort_candidates(apprentice_pool[r])

    assignments = {}
    assigned_officials = set()

    # 1) satisfy required certified roles first
    for role, count in ROLE_COUNTS.items():
        need = count
        assigned = []
        certs = certified_pool.get(role, [])
        while need > 0 and certs:
            o = certs.pop(0)
            if o.id in assigned_officials:
                continue
            assignments[o.id] = {'role': role, 'break_schedule': []}
            assigned_officials.add(o.id)
            assigned.append(o)
            need -= 1

        # 2) if still need, fill with apprentices only if at least one certified already exists
        if need > 0:
            apps = apprentice_pool.get(role, [])
            # allow apprentices only if we already have >=1 certified assigned for this role
            if assigned or (count > 1 and any(v.get('role') == role for v in assignments.values())):
                while need > 0 and apps:
                    o = apps.pop(0)
                    if o.id in assigned_officials:
                        continue
                    assignments[o.id] = {'role': role, 'break_schedule': []}
                    assigned_officials.add(o.id)
                    need -= 1

    # 3) fill remaining slots (if any roles not satisfied) with any available officials not yet assigned, trying to avoid conflicts
    unassigned_officials = [o for o in officials if o.id not in assigned_officials]
    unassigned_officials = sort_candidates(unassigned_officials)
    for role, count in ROLE_COUNTS.items():
        current = len([1 for v in assignments.values() if v['role'] == role])
        need = count - current
        while need > 0 and unassigned_officials:
            o = unassigned_officials.pop(0)
            if o.id in assigned_officials:
                continue
            # check if this official conflicts (already assigned another role)
            if o.id in assignments:
                continue
            assignments[o.id] = {'role': role, 'break_schedule': []}
            assigned_officials.add(o.id)
            need -= 1

    # 4) create break schedules: naive even spacing — for simplicity, assign one break slot per official where possible
    # determine session length and default break windows (not precise times)
    total_slots = sum(ROLE_COUNTS.values())
    for idx, (oid, info) in enumerate(assignments.items()):
        # simple pattern: distribute break positions as indices
        info['break_schedule'] = [idx % 2]  # placeholder: single break pattern

    return assignments


@transaction.atomic
def finalize_and_save_assignments(session, assignments):
    """
    Persist assignments (replace existing DeckAssignment rows for this session)
    `assignments` is a dict {official_id: {'role': ..., 'break_schedule': [...]}}
    Also update session assignment hours proportionally.
    """
    # clear previous
    DeckAssignment.objects.filter(session=session).delete()

    # create new
    for oid, info in assignments.items():
        try:
            user = User.objects.get(pk=oid)
        except User.DoesNotExist:
            continue
        DeckAssignment.objects.create(
            session=session,
            official=user,
            role=info.get('role') or '',
            break_schedule=json.dumps(info.get('break_schedule', []))
        )

    # update hours: estimate session hours
    st = datetime.combine(session.date, session.start_time)
    et = datetime.combine(session.date, session.end_time)
    duration_hours = max((et - st).total_seconds() / 3600.0, 0)

    # per-official workload = duration_hours (can be adjusted by role multipliers if desired)
    role_multiplier = 1.0

    for da in DeckAssignment.objects.filter(session=session).select_related('official'):
        # find or create sessionassignment linking official to session
        sa, created = SessionAssignment.objects.get_or_create(session=session, official=da.official, defaults={'hours_worked': 0})
        # assign hours if not already set or overwrite to match role
        sa.hours_worked = round(duration_hours * role_multiplier, 2)
        sa.save()

        # update user's total_volunteer_hours (recompute from assignments to avoid double-count)
    # recompute totals for involved users
    user_ids = DeckAssignment.objects.filter(session=session).values_list('official_id', flat=True).distinct()
    for uid in user_ids:
        total = SessionAssignment.objects.filter(official_id=uid).aggregate(models_sum=models.Sum('hours_worked'))['models_sum'] or 0
        u = User.objects.get(pk=uid)
        u.total_volunteer_hours = total
        u.save()