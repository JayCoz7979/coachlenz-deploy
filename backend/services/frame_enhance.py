"""
Adaptive SHADOW-LIFT for detection frames.

Play RECOGNITION collapses on night football (the coverage holes cluster in the
second half once the stadium lights come on). Measured on a real game, the cause is
NOT global underexposure: night frames average luma ~130 (day ~157) and actually
carry HIGHER contrast. The real difference is deep shadow — 12-33% of a night
frame's pixels sit below luma 50, versus ~0.5% in daylight — and that is exactly
where players in dark areas and black jerseys disappear. So this lifts the SHADOWS
only (bringing hidden players into a readable range) while leaving midtones and the
bright stadium lights alone. It is gated on shadow fraction, not brightness, so
daytime football and well-lit indoor (basketball) film are a strict no-op.

Pure + PIL-only (no numpy/opencv): cheap CPU, ZERO API cost, safe to import anywhere.
Env-tunable so it can be dialed or disabled in prod without a redeploy:
    LOWLIGHT_ENHANCE=0         -> disable entirely
    LOWLIGHT_DARK_FRAC=0.08    -> only enhance frames with >8% deep-shadow pixels (default 0.04)
"""
import os
from PIL import Image, ImageStat, ImageEnhance

LOWLIGHT_ENHANCE = os.environ.get("LOWLIGHT_ENHANCE", "1").strip().lower() not in ("0", "false", "no", "")
# Luma below this counts as "deep shadow" where players hide.
SHADOW_CUTOFF = int(os.environ.get("LOWLIGHT_SHADOW_CUTOFF", "50"))
# Enhance only when at least this fraction of the frame is deep shadow. Day ~0.005,
# night ~0.13, so 0.04 cleanly separates them.
LOWLIGHT_DARK_FRAC = float(os.environ.get("LOWLIGHT_DARK_FRAC", "0.04"))
# Dark fraction at which the lift reaches full strength.
_DARK_FRAC_FULL = 0.30


def frame_mean_luma(img: "Image.Image") -> float:
    """Perceptual brightness of a frame, 0 (black) to 255 (white)."""
    return ImageStat.Stat(img.convert("L")).mean[0]


def shadow_fraction(img: "Image.Image", cutoff: int = None) -> float:
    """Fraction of pixels (0-1) darker than the shadow cutoff — the players-in-the-dark
    proxy that separates night film from day."""
    if cutoff is None:
        cutoff = SHADOW_CUTOFF
    hist = img.convert("L").histogram()
    total = sum(hist) or 1
    return sum(hist[:cutoff]) / total


def enhance_lowlight_frame(img: "Image.Image", dark_frac_min: float = None):
    """Return (image, changed).

    On a night frame (enough deep shadow): gamma-lift the low end so players hidden in
    the dark come up into a readable range, leaving highlights near their value so the
    bright bulbs do not bloom, plus a touch of sharpness for edges. Strength scales
    with the shadow fraction. On a day / well-lit frame: returns (img, False) unchanged.
    """
    if dark_frac_min is None:
        dark_frac_min = LOWLIGHT_DARK_FRAC
    img = img.convert("RGB")
    dark = shadow_fraction(img)
    if dark < dark_frac_min:
        return img, False

    # strength in [0,1]: 0 at the gate, 1 once ~30% of the frame is crushed to shadow.
    strength = max(0.0, min(1.0, (dark - dark_frac_min) / max(_DARK_FRAC_FULL - dark_frac_min, 1e-3)))

    # Tone curve out = 255*(in/255)**p. A power p < 1 RAISES shadows/midtones the most
    # while a highlight near 255 stays near 255, so the dark field and dark jerseys lift
    # without the stadium lights blooming. Smaller p = stronger lift.
    p = 1.0 - 0.40 * strength                 # gate -> 1.0 (none); heavy shadow -> ~0.60
    lut = [min(255, int(((i / 255.0) ** p) * 255 + 0.5)) for i in range(256)] * 3
    out = img.point(lut)
    out = ImageEnhance.Sharpness(out).enhance(1.0 + 0.15 * strength)
    return out, True
