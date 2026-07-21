import datetime
import hashlib
import hmac

from crocbridge.derivation import derive_code

SECRET = bytes(range(32))


def expected(secret, name, date_iso):
    mac = hmac.new(secret, f"{date_iso}:{name}".encode(), hashlib.sha256).hexdigest()
    return "cb" + mac[:14]


def test_golden_value():
    d = datetime.date(2026, 7, 21)
    assert derive_code(SECRET, "study-mac", d) == expected(SECRET, "study-mac", "2026-07-21")


def test_shape():
    code = derive_code(SECRET, "alpha", datetime.date(2026, 1, 1))
    assert code.startswith("cb")
    assert len(code) == 16
    assert all(c in "0123456789abcdef" for c in code[2:])


def test_directionality():
    d = datetime.date(2026, 7, 21)
    assert derive_code(SECRET, "alpha", d) != derive_code(SECRET, "beta", d)


def test_daily_rotation():
    assert derive_code(SECRET, "alpha", datetime.date(2026, 7, 21)) != derive_code(
        SECRET, "alpha", datetime.date(2026, 7, 22)
    )


def test_secret_sensitivity():
    d = datetime.date(2026, 7, 21)
    other = bytes(range(1, 33))
    assert derive_code(SECRET, "alpha", d) != derive_code(other, "alpha", d)


def test_unicode_device_name():
    code = derive_code(SECRET, "café-ordinateur", datetime.date(2026, 7, 21))
    assert code.startswith("cb") and len(code) == 16


def test_default_date_is_today_utc():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    assert derive_code(SECRET, "alpha") == derive_code(SECRET, "alpha", today)
