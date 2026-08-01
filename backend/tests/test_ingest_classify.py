"""
Guard for the paste-a-link classifier — the truth behind the "no Hudl account
needed" badge. The badge (POST /ingest/check-url) and the ingest worker MUST agree,
or a coach gets promised no-login on a link that then fails on private film.

Run:  python -m backend.tests.test_ingest_classify
"""
from backend.services.ingest_classify import classify_ingest_url, is_hudl_no_login

REAL_BULK_LINK = (
    "https://www.hudl.com/notifications-tracking/tracker/"
    "BulkDownloadReady-6a5fbf525b2b1529dcfa1d3c-3b762233-a8be-4403-808c-5abc8f0d4a1d-17092970/"
    "email/landing?forward=https%3a%2f%2fvtemp.hudl.com%2f76702%2f134216%2f675%2f"
    "69869474c01d15e0b28f6675%2f69869474c01d15e0b28f6675.mp4%3fv%3dEFE0BD5B00000000"
)


def run():
    # YouTube: no login (global cookie unlocks HD for everyone).
    c = classify_ingest_url("https://www.youtube.com/watch?v=abc123")
    assert c["source_type"] == "youtube" and c["status"] == "no_login", c

    # Hudl emailed Download link: no login, flagged as the direct path.
    c = classify_ingest_url(REAL_BULK_LINK)
    assert c["source_type"] == "hudl" and c["status"] == "no_login" and c["hudl_direct"], c

    # Directly-pasted Hudl direct file (vtemp/vcloud): no login, direct path.
    for host in ("vtemp.hudl.com", "vcloud.hudl.com", "vg.hudl.com"):
        c = classify_ingest_url(f"https://{host}/a/b/film.mp4?v=1")
        assert c["status"] == "no_login" and c["hudl_direct"], (host, c)
        assert is_hudl_no_login(f"https://{host}/a/b/film.mp4?v=1"), host

    # Hudl WATCH page (no forward param): NOT a guaranteed no-login promise.
    # This is the false-green we're preventing.
    c = classify_ingest_url(
        "https://fan.hudl.com/usa/al/hoover/organization/9144/team/22016/watch?hr=XYZ&ot=TEAM"
    )
    assert c["source_type"] == "hudl" and c["status"] == "public_ok", c
    assert c["hudl_direct"] is False, c
    assert not is_hudl_no_login(
        "https://fan.hudl.com/usa/al/hoover/organization/9144/team/22016/watch?hr=XYZ&ot=TEAM"
    )

    # A bare hudl.com watch page with '/download' in the PATH but no forward target
    # must NOT be promised as no-login (the old client heuristic wrongly greenlit this).
    c = classify_ingest_url("https://www.hudl.com/video/3/12345/67890/download")
    assert c["status"] == "public_ok" and not c["hudl_direct"], c

    # NFHS: subscription-gated by default -> public_ok, not a no-login promise.
    c = classify_ingest_url("https://www.nfhsnetwork.com/events/school/gam123")
    assert c["source_type"] == "nfhs" and c["status"] == "public_ok", c

    # Public hosts: import directly, no account.
    for url, st in (
        ("https://vimeo.com/123456", "vimeo"),
        ("https://drive.google.com/file/d/abc/view", "google_drive"),
        ("https://www.dropbox.com/s/abc/game.mp4", "dropbox"),
        ("https://example.com/game.mp4", "generic"),
    ):
        c = classify_ingest_url(url)
        assert c["source_type"] == st and c["status"] == "no_login", (url, c)

    # Garbage / non-http: flagged invalid, never a green promise.
    for bad in ("", "   ", "not a url", "ftp://x/y", "javascript:alert(1)"):
        c = classify_ingest_url(bad)
        assert c["status"] == "invalid", (bad, c)

    print("INGEST CLASSIFY GUARD PASSED")


if __name__ == "__main__":
    run()
