"""
The detection-quality gate math. Pure and deterministic, so we lock the recall
proxy, the labeled-count upgrade, the label-edit verdict bands, the film-quality
cut, and the honest empty state.
"""
from backend.services import detection_quality as dq


def test_empty_reads_no_data_not_a_fake_pass():
    sc = dq.build_scorecard([])
    assert sc["overall"]["recall"] is None
    assert sc["overall"]["recall_verdict"] == "no_data"
    assert sc["by_film_quality"] == []
    assert sc["games"] == []


def test_recall_proxy_counts_coach_added_as_misses():
    # 90 of 100 plays auto-detected, 10 the coach added back -> 90% recall (pass).
    sc = dq.build_scorecard([{"game_id": "g1", "sport": "football",
                              "auto_plays": 90, "coach_added_plays": 10,
                              "film_height": 1080}])
    g = sc["games"][0]
    assert g["recall"] == 0.9
    assert g["measurement"] == "proxy"
    assert g["recall_verdict"] == "pass"
    assert g["film_quality"] == "hd"


def test_recall_below_watch_line_stops():
    # Single-cam night ceiling: found 68 of ~100 -> stop.
    sc = dq.build_scorecard([{"game_id": "g", "auto_plays": 68, "coach_added_plays": 32,
                              "film_height": 480}])
    g = sc["games"][0]
    assert g["recall"] == 0.68
    assert g["recall_verdict"] == "stop"
    assert g["film_quality"] == "sd"


def test_true_count_upgrades_proxy_to_labeled_recall():
    # Coach added nothing, but the film truly had 100 snaps and we chopped 80.
    # The proxy would lie (100%); the labeled true count tells the truth (80%).
    sc = dq.build_scorecard([{"game_id": "g", "auto_plays": 80, "coach_added_plays": 0,
                              "true_plays": 100, "film_height": 720}])
    g = sc["games"][0]
    assert g["measurement"] == "labeled"
    assert g["recall"] == 0.8
    assert g["recall_verdict"] == "watch"


def test_label_edit_rate_bands():
    # 10 corrections over 100 auto plays = 10% -> pass (<=15%).
    good = dq.build_scorecard([{"game_id": "g", "auto_plays": 100, "coach_added_plays": 0,
                                "corrections": 10}])["games"][0]
    assert good["label_edit_rate"] == 0.1
    assert good["label_verdict"] == "pass"
    # 40 corrections over 100 = 40% -> stop (>30%).
    bad = dq.build_scorecard([{"game_id": "g", "auto_plays": 100, "coach_added_plays": 0,
                               "corrections": 40}])["games"][0]
    assert bad["label_verdict"] == "stop"


def test_timeliness_is_reported_from_elapsed_and_film_length():
    g = dq.build_scorecard([{"game_id": "g", "auto_plays": 50, "coach_added_plays": 0,
                             "elapsed_seconds": 300.0, "film_seconds": 3600.0}])["games"][0]
    assert g["realtime_ratio"] == round(300 / 3600, 3)
    assert g["sec_per_play"] == 6.0


def test_film_quality_cut_pools_recall_play_weighted():
    # HD film chops clean; SD film misses a third. The cut must surface that the
    # leak is SD film, not the model, and pooling is play-weighted.
    sc = dq.build_scorecard([
        {"game_id": "hd1", "auto_plays": 95, "coach_added_plays": 5, "film_height": 1080},
        {"game_id": "sd1", "auto_plays": 66, "coach_added_plays": 34, "film_height": 480},
    ])
    by = {b["label"]: b for b in sc["by_film_quality"]}
    assert by["HD film (>=720p)"]["recall"] == 0.95
    assert by["HD film (>=720p)"]["recall_verdict"] == "pass"
    assert by["SD film (<720p)"]["recall"] == 0.66
    assert by["SD film (<720p)"]["recall_verdict"] == "stop"
    # Overall pools both: 161 found of 200 total = 80.5%.
    assert sc["overall"]["recall"] == 0.805


def test_basketball_shot_recall_against_true_fga():
    # 96 detected shot events vs a scorebook 120 FGA -> 80% shot recall (watch).
    sc = dq.build_scorecard([{"game_id": "bb", "sport": "basketball",
                              "auto_plays": 240, "coach_added_plays": 0,
                              "shots_detected": 96, "true_shots": 120,
                              "film_height": 720}])
    g = sc["games"][0]
    assert g["shots_detected"] == 96
    assert g["shot_recall"] == 0.8
    assert g["shot_recall_verdict"] == "watch"
    # Pooled into the bucket too.
    assert sc["overall"]["shot_recall"] == 0.8


def test_shot_recall_is_none_without_a_true_fga_count():
    g = dq.build_scorecard([{"game_id": "bb", "sport": "basketball",
                             "auto_plays": 240, "coach_added_plays": 0,
                             "shots_detected": 96}])["games"][0]
    assert g["shot_recall"] is None
    assert g["shot_recall_verdict"] == "no_data"


def test_unknown_resolution_bucketed_separately():
    sc = dq.build_scorecard([{"game_id": "g", "auto_plays": 10, "coach_added_plays": 0,
                              "film_height": None}])
    assert sc["games"][0]["film_quality"] == "unknown"
    assert [b["label"] for b in sc["by_film_quality"]] == ["Unknown resolution"]
