"""Finding #23: the Hudl capture spawns a detached task per network response to
read its body. Those tasks must be tracked and drained before browser.close(),
and body reads must be size-bounded. Verified against source (the module imports
Playwright, which isn't needed to assert these structural guarantees)."""
import ast
import pathlib

SRC = (pathlib.Path(__file__).resolve().parents[1] / "services" / "hudl_capture.py").read_text(encoding="utf-8")


def test_source_parses():
    ast.parse(SRC)  # guards the indentation-sensitive edits


def test_response_tasks_are_tracked_and_drained():
    assert "_pending_bodies" in SRC
    assert "add_done_callback(_pending_bodies.discard)" in SRC
    # Drained before the browser is closed.
    drain = SRC.index("asyncio.gather(*_pending_bodies")
    close = SRC.index("await browser.close()")
    assert drain < close, "pending body reads must be drained before browser.close()"


def test_response_body_reads_are_size_bounded():
    assert "content-length" in SRC
    assert "5_000_000" in SRC


def test_no_untracked_create_task_on_response():
    # The old untracked spawn form must be gone.
    assert "asyncio.create_task(on_response(resp))" not in SRC \
        or "_spawn_on_response" in SRC
    assert 'page.on("response", _spawn_on_response)' in SRC
