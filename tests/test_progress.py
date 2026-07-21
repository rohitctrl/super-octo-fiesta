import io
from pathlib import Path

from crocbridge.progress import ProgressParser, read_stream

SAMPLES = Path(__file__).parent / "samples"


def feed_lines(*lines):
    p = ProgressParser()
    for ln in lines:
        p.feed(ln)
    return p


def test_typical_progress_line():
    p = feed_lines("photo.jpg  42% |████████        | (4.2/10.0 MB, 8.3 MB/s) [1s:2s]")
    s = p.snapshot()
    assert s["pct"] == 42
    assert s["speed"] == "8.3 MB/s"
    assert s["eta"] == "2s"
    assert s["done_bytes"] == int(4.2 * 1000**2)
    assert s["total_bytes"] == int(10.0 * 1000**2)


def test_filename_line():
    p = feed_lines("Sending 'photo.jpg' (10.0 MB)")
    assert p.snapshot()["file"] == "photo.jpg"


def test_receiving_filename_line():
    p = feed_lines("Receiving 'archive.tar.gz' (1.2 GB)")
    assert p.snapshot()["file"] == "archive.tar.gz"


def test_hundred_percent():
    p = feed_lines("100% |████████████████| (10/10 MB, 12 MB/s)")
    s = p.snapshot()
    assert s["pct"] == 100
    assert s["speed"] == "12 MB/s"


def test_error_line_mapped_to_friendly_message():
    p = feed_lines("croc: could not connect to 127.0.0.1:9021: connection refused")
    assert p.snapshot()["error"] == "Can't reach the relay."


def test_bad_relay_password():
    p = feed_lines("croc: bad password")
    assert p.snapshot()["error"] == "Relay password rejected."


def test_permission_denied():
    p = feed_lines("open /root/x: permission denied")
    assert p.snapshot()["error"] == "Can't write to the download folder."


def test_junk_never_raises_and_keeps_last_progress():
    p = feed_lines(
        " 50% |████    | (5.0/10.0 MB, 9 MB/s) [1s:1s]",
        "\x1b[2K??? totally unexpected ???",
        "",
        "%%%%",
    )
    assert p.snapshot()["pct"] == 50


def test_partial_matches_are_independent():
    p = feed_lines("73%|x")  # only pct present
    s = p.snapshot()
    assert s["pct"] == 73
    assert s["speed"] is None


def test_read_stream_splits_on_cr_and_lf():
    raw = (
        b"Sending 'a.bin' (5.0 MB)\n"
        b" 10% |#  | (0.5/5.0 MB, 2 MB/s) [0s:2s]\r"
        b" 55% |###| (2.7/5.0 MB, 5 MB/s) [1s:1s]\r"
        b"100% |#####| (5.0/5.0 MB, 6 MB/s)\n"
    )
    seen = []
    read_stream(io.BytesIO(raw), seen.append)
    assert any("10%" in ln for ln in seen)
    assert any("55%" in ln for ln in seen)
    assert any("100%" in ln for ln in seen)
    p = ProgressParser()
    for ln in seen:
        p.feed(ln)
    assert p.snapshot()["pct"] == 100
    assert p.snapshot()["file"] == "a.bin"


def test_real_captured_croc_output():
    sample = SAMPLES / "croc_stderr_send.txt"
    if not sample.exists():  # captured during the e2e run
        import pytest

        pytest.skip("no captured sample yet")
    p = ProgressParser()
    read_stream(io.BytesIO(sample.read_bytes()), p.feed)
    s = p.snapshot()
    assert s["error"] is None
    assert s["pct"] is not None and s["pct"] > 0
