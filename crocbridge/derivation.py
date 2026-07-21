"""Derived, directional, daily-rotating croc codes.

The code is never shown to the user and never passed on a command line —
it travels only via the CROC_SECRET environment variable.
"""

import datetime
import hashlib
import hmac


def derive_code(secret: bytes, receiver_name: str, date: datetime.date | None = None) -> str:
    """code = "cb" + hex(hmac_sha256(secret, utc_date + ":" + receiver_name))[:14]

    Directionality: a receiver listens on the code derived from its OWN
    name; a sender uses the code derived from the PEER's name. The `date`
    parameter exists for tests; production callers omit it to get today
    in UTC.
    """
    if date is None:
        date = datetime.datetime.now(datetime.timezone.utc).date()
    msg = f"{date.isoformat()}:{receiver_name}".encode()
    return "cb" + hmac.new(secret, msg, hashlib.sha256).hexdigest()[:14]
