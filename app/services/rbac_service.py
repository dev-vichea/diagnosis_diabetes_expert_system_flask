from typing import Set
from app.models import User

def get_user_permission_codes(user_id: int) -> Set[str]:
    """
    Load permissions from: user -> roles -> permissions
    Returns set of permission codes.
    """
    user = User.query.get(user_id)
    if not user:
        return set()

    codes = set()
    for role in user.roles:
        for perm in role.permissions:
            codes.add(perm.code)
    return codes
