"""
Guard for the adaptive shadow-lift used on detection frames.

Night football buries players (esp. dark jerseys) in deep shadow, which is where
recognition drops. The lift must: brighten the shadows on night frames, be a strict
no-op on day/well-lit frames, and NOT darken or bloom the highlights (stadium lights).

Run:  python -m backend.tests.test_frame_enhance
"""
from PIL import Image
from backend.services.frame_enhance import (
    enhance_lowlight_frame, shadow_fraction, frame_mean_luma,
)


def run():
    # 1. Dark (night-like) frame: fires, brightens, and REDUCES deep-shadow pixels.
    dark = Image.new("RGB", (32, 32), (30, 30, 30))
    out, changed = enhance_lowlight_frame(dark)
    assert changed is True, "dark frame should be enhanced"
    assert frame_mean_luma(out) > frame_mean_luma(dark) + 10, "should brighten shadows"
    assert shadow_fraction(out) < shadow_fraction(dark), "should lift pixels out of deep shadow"

    # 2. Bright (day-like) frame: strict no-op.
    day = Image.new("RGB", (32, 32), (160, 160, 160))
    out2, ch2 = enhance_lowlight_frame(day)
    assert ch2 is False, "day frame must be untouched"
    assert frame_mean_luma(out2) == frame_mean_luma(day)

    # 3. Highlights survive the lift (a bright block stays bright — no darkening/bloom).
    mixed = Image.new("RGB", (32, 32), (20, 20, 20))
    for x in range(8):
        for y in range(8):
            mixed.putpixel((x, y), (250, 250, 250))
    out3, ch3 = enhance_lowlight_frame(mixed)
    assert ch3 is True
    assert out3.getpixel((0, 0))[0] >= 235, "highlights must not be darkened by the lift"

    # 4. Gate: a frame with only ~2% shadow (below the 4% gate) is untouched.
    light = Image.new("RGB", (100, 100), (120, 120, 120))
    for i in range(200):  # 2% of 10000 px pushed to deep shadow
        light.putpixel((i % 100, i // 100), (10, 10, 10))
    _, ch4 = enhance_lowlight_frame(light)
    assert ch4 is False, "must not fire below the shadow-fraction gate"

    print("FRAME ENHANCE GUARD PASSED")


if __name__ == "__main__":
    run()
