"""Finding #7: the ingest worker shares one event loop with the co-located
detection worker, so its blocking subprocess calls (yt-dlp download, ffprobe)
must run via asyncio.to_thread, never directly on the loop."""
import inspect

import backend.workers.worker_ingest as wi


def test_download_runs_yt_dlp_off_loop():
    src = inspect.getsource(wi.IngestWorker._ingest_from_url_inner)
    assert "asyncio.to_thread(" in src, "yt-dlp download must be dispatched off-loop"
    # subprocess.run must only appear as an argument to to_thread, never called
    # directly on the loop.
    assert "subprocess.run(cmd" not in src, "subprocess.run must not block the event loop"


def test_probe_is_called_off_loop_in_async_paths():
    for method in (wi.IngestWorker._ingest_uploaded_file_inner,
                   wi.IngestWorker._ingest_from_url_inner):
        src = inspect.getsource(method)
        # ffprobe must be dispatched off-loop and never called directly (a direct
        # call would read as `self._probe(` with an open paren).
        assert "asyncio.to_thread(self._probe" in src, (
            f"{method.__name__} must probe via asyncio.to_thread"
        )
        assert "self._probe(" not in src, (
            f"{method.__name__} calls self._probe directly on the loop"
        )
