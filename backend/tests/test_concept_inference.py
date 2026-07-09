"""
Test the deterministic concept-recovery layer (concept_taxonomy.fill_concepts).

Concept detection asks the vision model to name run_concept / pass_concept, but on
single-camera film it often returns null and the tendency is lost. fill_concepts
recovers a null concept from the play_description the model already wrote, then
from structural signals — never overwriting a confident model read.

Run:  python -m backend.tests.test_concept_inference
"""
from backend.services.tendency_engine.concept_taxonomy import (
    fill_concepts, infer_run_concept, infer_pass_concept,
    postsnap_concept_guidance, RUN_CONCEPT_NAMES, PASS_CONCEPT_NAMES,
)

passed, failed = 0, 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")


def run():
    # ── Description mining: the model named the concept in prose. ──
    p = {"run_pass": "Run", "run_concept": None,
         "play_description": "Power right to the B-gap, back-side guard pulls and kicks out."}
    fill_concepts(p)
    check("run: 'Power' mined from description", p["run_concept"] == "Power")
    check("run: source=description, conf 0.75", p["concept_source"] == "description" and p["concept_confidence"] == 0.75)

    p = {"run_pass": "Run", "run_concept": None,
         "play_description": "Counter GT, guard kicks and tackle wraps through the C-gap."}
    fill_concepts(p)
    check("run: 'Counter' mined from description", p["run_concept"] == "Counter")

    p = {"play_type": "Pass", "pass_concept": None,
         "play_description": "Mesh concept, two crossers underneath, back-side sit for 7."}
    fill_concepts(p)
    check("pass: 'Mesh' mined from description", p["pass_concept"] == "Mesh")

    # ── Structural fallback: no description, infer from signals. ──
    p = {"run_pass": "Run", "run_concept": None, "run_gap": "A", "run_direction": "Middle"}
    fill_concepts(p)
    check("run: interior gap -> Inside Zone (signals)",
          p["run_concept"] == "Inside Zone" and p["concept_source"] == "signals")

    p = {"run_pass": "Run", "run_concept": None, "run_gap": "D/Edge", "run_direction": "Right"}
    fill_concepts(p)
    check("run: edge gap -> Outside Zone (signals)", p["run_concept"] == "Outside Zone")

    p = {"play_type": "Pass", "pass_concept": None, "screen_subtype": "Bubble Screen"}
    fill_concepts(p)
    check("pass: screen subtype -> Screen (signals)",
          p["pass_concept"] == "Screen" and p["concept_source"] == "signals")

    p = {"play_type": "Pass", "pass_concept": None, "is_play_action": True}
    fill_concepts(p)
    check("pass: play-action -> PA Boot (signals)", p["pass_concept"] == "PA Boot")

    p = {"play_type": "Pass", "pass_concept": None, "pass_depth": "Deep (20+)", "target_area": "Seam Left"}
    fill_concepts(p)
    check("pass: deep seam -> Four Verticals (signals)", p["pass_concept"] == "Four Verticals")

    # ── A confident model read is preserved, never overwritten. ──
    p = {"run_pass": "Run", "run_concept": "Duo",
         "play_description": "Power right"}   # description says Power, but model said Duo
    fill_concepts(p)
    check("run: model read preserved over description", p["run_concept"] == "Duo")
    check("run: preserved read tagged source=model", p["concept_source"] == "model")

    # ── Unknowable stays null (honest). ──
    p = {"run_pass": "Run", "run_concept": None, "run_gap": None, "run_direction": None,
         "play_description": "Handoff, stuffed at the line, no read on the blocking."}
    fill_concepts(p)
    check("run: truly unreadable stays null", p.get("run_concept") in (None, ""))

    # ── Non-run/pass plays are untouched. ──
    p = {"play_type": "Punt", "side": "special_teams"}
    fill_concepts(p)
    check("special teams untouched", "run_concept" not in p and "pass_concept" not in p)

    # ── Inferred concepts are always in the taxonomy. ──
    r = infer_run_concept({"play_description": "Outside zone stretch to the right"})
    check("inferred run concept is canonical", r and r[0] in RUN_CONCEPT_NAMES)
    pc = infer_pass_concept({"play_description": "Four verticals, hit the seam"})
    check("inferred pass concept is canonical", pc and pc[0] in PASS_CONCEPT_NAMES)

    # ── Word boundaries: substring look-alikes must NOT fire a false concept. ──
    check("'drawn up' does not false-match Draw",
          (infer_run_concept({"play_description": "a well-designed play, drawn up perfectly"}) or (None,))[0] != "Draw")
    check("'bootstrapped' does not false-match PA Boot",
          infer_pass_concept({"play_description": "they bootstrapped a new tempo look"}) is None)
    check("real 'bootleg' still fires PA Boot",
          (infer_pass_concept({"play_description": "QB ran a clean bootleg to the right"}) or (None,))[0] == "PA Boot")
    # ── Broadened classification: freeform play_type variants still recover. ──
    p = {"play_type": "handoff", "run_gap": "A"}
    fill_concepts(p)
    check("play_type 'handoff' classifies as run and recovers a concept", p.get("run_concept") == "Inside Zone")
    p = {"play_type": "dropback", "pass_depth": "Deep (20+)", "target_area": "Seam Left"}
    fill_concepts(p)
    check("play_type 'dropback' classifies as pass and recovers a concept", p.get("pass_concept") == "Four Verticals")

    # ── Prompt guidance carries names AND recognition cues. ──
    guide = postsnap_concept_guidance()
    check("guidance includes run + pass concepts", "Power" in guide and "Mesh" in guide)
    check("guidance includes recognition cues (not just names)",
          "PULLS" in guide or "pull" in guide.lower())
    check("guidance asks for concept_confidence", "concept_confidence" in guide)

    print(f"\n{'='*52}\n  {passed} passed, {failed} failed\n{'='*52}")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
