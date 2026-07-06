"""
Scouting RBAC role definitions — deliberately free of any web-framework import so
the role logic is testable and reusable without pulling in FastAPI.

auth.py re-exports these and adds the `require_scout_reviewer` FastAPI dependency.
"""

# Roles that carry authority to REVIEW / sign off a scouting report (Gate 2 dual
# review). The org owner always qualifies; owners can promote staff into the coach
# roles. A plain "member"/"analyst" can build a scout but cannot review one — that
# is what gives the dual-review gate teeth.
SCOUT_REVIEWER_ROLES = frozenset({"owner", "head_coach", "coordinator", "reviewer"})

# Roles an owner is allowed to assign to their staff (the assignable scouting set).
SCOUT_ASSIGNABLE_ROLES = frozenset({"member", "analyst", "coordinator", "head_coach", "reviewer"})


def can_review_scout(user) -> bool:
    """True if the user's role carries scouting review authority."""
    return getattr(user, "role", None) in SCOUT_REVIEWER_ROLES
