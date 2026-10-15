"""User account changes made from the sysadmin Users page.

Setting users.user_active = 0 is enough to lock an account out: /login
refuses inactive users, and load_user() builds the session user with that
flag, so AuthBaseUser.is_authenticated turns False on the user's next
request and any open session ends.
"""

from osprey.db import run_query

# deactivate_user() / reactivate_user() results, mapped to messages by the view.
OK = 'ok'
NOT_FOUND = 'not_found'
ALREADY_INACTIVE = 'already_inactive'
ALREADY_ACTIVE = 'already_active'
SELF = 'self'


def deactivate_user(user_id: int, actor_username: str):
    """Set user_active = 0. Returns (result, username).

    A sysadmin cannot deactivate their own account. That also guarantees at
    least one active sysadmin remains (whoever is acting), so the page can
    never lock everyone out.
    """
    rows = run_query(
        "SELECT user_id, username, user_active FROM users WHERE user_id = %(uid)s",
        {'uid': user_id},
    )
    if not rows:
        return NOT_FOUND, None
    user = rows[0]
    if user['username'] == actor_username:
        return SELF, user['username']
    if not user['user_active']:
        return ALREADY_INACTIVE, user['username']
    # The user_active = 1 condition keeps a double submit from rewriting the row.
    run_query(
        "UPDATE users SET user_active = 0 WHERE user_id = %(uid)s AND user_active = 1",
        {'uid': user_id}, return_val=False,
    )
    return OK, user['username']


def reactivate_user(user_id: int):
    """Set user_active = 1. Returns (result, username).

    No self-check: a deactivated account's session already ended (/login
    refuses inactive users), so an inactive sysadmin cannot be the actor
    reactivating themselves through this page.
    """
    rows = run_query(
        "SELECT user_id, username, user_active FROM users WHERE user_id = %(uid)s",
        {'uid': user_id},
    )
    if not rows:
        return NOT_FOUND, None
    user = rows[0]
    if user['user_active']:
        return ALREADY_ACTIVE, user['username']
    # The user_active = 0 condition keeps a double submit from rewriting the row.
    run_query(
        "UPDATE users SET user_active = 1 WHERE user_id = %(uid)s AND user_active = 0",
        {'uid': user_id}, return_val=False,
    )
    return OK, user['username']
