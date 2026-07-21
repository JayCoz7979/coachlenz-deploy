"""
Guard for the Hudl bulk-download unwrap — the no-Hudl-account import path.

Hudl's "Download"/bulk-download email link is a tracking/landing page that needs a
Hudl login, but it wraps a pre-signed direct MP4 (vtemp.hudl.com) that any coach
the film was shared with can fetch WITHOUT an account. `unwrap_hudl_direct_url`
must peel the wrapper so the ingest worker downloads the file directly and skips
the browser capture. If this regresses, no-account coaches lose that path.

Run:  python -m backend.tests.test_hudl_unwrap
"""
from backend.services.hudl_capture import unwrap_hudl_direct_url


# The exact shape Hudl emails (from the reported failing import).
REAL_BULK_LINK = (
    "https://www.hudl.com/notifications-tracking/tracker/"
    "BulkDownloadReady-6a5fbf525b2b1529dcfa1d3c-3b762233-a8be-4403-808c-5abc8f0d4a1d-17092970/"
    "email/landing?forward=https%3a%2f%2fvtemp.hudl.com%2f76702%2f134216%2f675%2f"
    "69869474c01d15e0b28f6675%2f69869474c01d15e0b28f6675.mp4%3fv%3dEFE0BD5B00000000"
)
EXPECTED_DIRECT = (
    "https://vtemp.hudl.com/76702/134216/675/"
    "69869474c01d15e0b28f6675/69869474c01d15e0b28f6675.mp4?v=EFE0BD5B00000000"
)


def run():
    # 1. The real emailed bulk-download link unwraps to its direct MP4.
    got = unwrap_hudl_direct_url(REAL_BULK_LINK)
    assert got == EXPECTED_DIRECT, f"expected direct MP4, got: {got!r}"

    # 2. A plain forward= to an .mp4 on any hudl host unwraps.
    got = unwrap_hudl_direct_url(
        "https://www.hudl.com/redirect?forward=https://vg.hudl.com/a/b/clip.mp4"
    )
    assert got == "https://vg.hudl.com/a/b/clip.mp4", got

    # 3. Double-encoded forward value still unwraps.
    got = unwrap_hudl_direct_url(
        "https://www.hudl.com/email/landing?forward=https%253a%252f%252fvtemp.hudl.com%252fx%252ffilm.mp4"
    )
    assert got == "https://vtemp.hudl.com/x/film.mp4", got

    # 4. A normal Hudl watch page has no forward target — must NOT unwrap
    #    (it needs the browser-capture/login path, not a direct download).
    assert unwrap_hudl_direct_url("https://www.hudl.com/video/3/12345/67890") is None

    # 5. Non-Hudl links are ignored entirely.
    assert unwrap_hudl_direct_url("https://youtube.com/watch?v=abc") is None

    # 6. A forward= that points at another login page (not a video) does NOT unwrap.
    assert unwrap_hudl_direct_url(
        "https://www.hudl.com/landing?forward=https://www.hudl.com/login"
    ) is None

    print("HUDL UNWRAP GUARD PASSED")


if __name__ == "__main__":
    run()
