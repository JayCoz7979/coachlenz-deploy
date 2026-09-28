"""
duration_from_probe: robust ffprobe duration extraction.

Regression for the prod Sentry error "[ai_detect] ... Could not determine video
duration": some containers leave format.duration empty and only carry the duration on
the video stream or in a "DURATION" tag, which used to store 0 at ingest and then
hard-crash detection.

Run:  python -m backend.tests.test_media_duration
"""
from backend.utils.media import duration_from_probe


def test_duration_sources():
    # format.duration (the common case)
    assert duration_from_probe({"format": {"duration": "2880.5"}}) == 2880.5
    # empty format -> video stream duration
    assert duration_from_probe({"format": {}, "streams": [{"codec_type": "video", "duration": "1500.0"}]}) == 1500.0
    # empty format + stream -> HH:MM:SS.mmm DURATION tag (webm/mkv)
    assert duration_from_probe({"format": {}, "streams": [
        {"codec_type": "video", "tags": {"DURATION": "00:48:12.500"}}]}) == 48 * 60 + 12.5
    # no video duration but an audio stream carries it
    assert duration_from_probe({"format": {"duration": "0"}, "streams": [{"codec_type": "audio", "duration": "10"}]}) == 10.0
    # truly nothing
    assert duration_from_probe({}) == 0.0
    assert duration_from_probe(None) == 0.0
    assert duration_from_probe({"format": {"duration": "0"}, "streams": []}) == 0.0
    # malformed values never raise
    assert duration_from_probe({"format": {"duration": "N/A"}}) == 0.0
    print("duration_from_probe: format / stream / tag / audio / empty / malformed all handled")


def run():
    test_duration_sources()
    print("ALL MEDIA-DURATION ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
