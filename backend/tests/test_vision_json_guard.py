"""Findings #14 and #15 for the detection worker:
  #14 an empty/refusal/truncated response must not crash the batch — _first_text
     degrades to '' instead of indexing content[0].text.
  #15 vision clients must set an explicit request timeout + retry cap so a hung
     call can't park a batch under a self-renewing lock."""
import inspect
from types import SimpleNamespace

import backend.workers.worker_ai_detect as w


def _msg(blocks):
    return SimpleNamespace(content=blocks)


def test_first_text_empty_or_missing_content_is_blank():
    assert w.AiDetectWorker._first_text(_msg([])) == ""
    assert w.AiDetectWorker._first_text(SimpleNamespace(content=None)) == ""


def test_first_text_reads_a_text_block():
    blk = SimpleNamespace(type="text", text='{"plays": []}')
    assert w.AiDetectWorker._first_text(_msg([blk])) == '{"plays": []}'


def test_first_text_skips_a_nontext_block_without_crashing():
    blk = SimpleNamespace(type="tool_use")  # no .text attribute
    assert w.AiDetectWorker._first_text(_msg([blk])) == ""


def test_vision_json_uses_the_safe_extractor():
    src = inspect.getsource(w.AiDetectWorker._vision_json)
    assert "self._first_text(response)" in src
    assert "response.content[0].text" not in src


def test_vision_clients_set_timeout_and_retries():
    for name in ("_analyze_batch", "_grade_plays", "_read_jerseys"):
        src = inspect.getsource(getattr(w.AiDetectWorker, name))
        assert "timeout=DETECT_TIMEOUT_S" in src, f"{name} missing request timeout"
        assert "max_retries=DETECT_MAX_RETRIES" in src, f"{name} missing retry cap"
    assert w.DETECT_TIMEOUT_S == 180.0 and w.DETECT_MAX_RETRIES == 2
