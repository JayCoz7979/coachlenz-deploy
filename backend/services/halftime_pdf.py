"""
The free printable Halftime Sheet tracker (PDF), offered on /live-tracker in exchange
for a name and a validated email.

A blank, pen-and-paper charting sheet: page 1 for Football / Flag Football, page 2 for
Basketball. It is generated here with a tiny hand-rolled PDF writer (standard
Helvetica fonts, lines, and boxes) so there is no new dependency and nothing to store
in object storage. The bytes are deterministic and built once per process.

Copy follows the /live-tracker fact lock: it names the three sports and the $7 one-time
Live Tracker, and makes no other claims or prices.
"""
from __future__ import annotations

from functools import lru_cache

PAGE_W, PAGE_H = 612, 792  # US Letter, points
MARGIN = 36

FOOTER_OFFER = ("Want it charted live instead? The CoachLenz Live Tracker builds your "
                "Halftime Sheet from the plays you log: $7 USD, one time.")
FOOTER_URL = "app.coachlenz.com/live-tracker"
FOOTER_BRAND = "Powered by Cosby AI Solutions"


def _esc(text: str) -> str:
    """Escape a string for a PDF literal; keep to printable ASCII (WinAnsi-safe)."""
    out = []
    for ch in text:
        if ch in "\\()":
            out.append("\\" + ch)
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


class _Page:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(self, x: float, y: float, s: str, size: float = 9, bold: bool = False, gray: float = 0.0) -> None:
        font = "F2" if bold else "F1"
        self.ops.append(f"{gray:.2f} g BT /{font} {size:g} Tf {x:.1f} {y:.1f} Td ({_esc(s)}) Tj ET 0 g")

    def line(self, x1: float, y1: float, x2: float, y2: float, w: float = 0.5, gray: float = 0.0) -> None:
        self.ops.append(f"{gray:.2f} G {w:g} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S 0 G")

    def rect(self, x: float, y: float, w: float, h: float, lw: float = 0.6, fill: float | None = None) -> None:
        if fill is not None:
            self.ops.append(f"{fill:.2f} g {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f 0 g")
        self.ops.append(f"{lw:g} w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S")

    def field(self, x: float, y: float, label: str, width: float) -> None:
        """A label followed by a write-in underline."""
        self.text(x, y, label, 9, bold=True)
        lx = x + 6 + len(label) * 5.2
        self.line(lx, y - 2, x + width, y - 2)

    def table(self, x: float, top: float, cols: list[tuple[str, float]], rows: int, row_h: float = 17) -> float:
        """Header row (shaded) + empty rows. Returns the y of the table bottom."""
        total_w = sum(w for _, w in cols)
        self.rect(x, top - row_h, total_w, row_h, fill=0.88)
        cx = x
        for label, w in cols:
            self.text(cx + 3, top - row_h + 5, label, 7.5, bold=True)
            cx += w
        bottom = top - row_h * (rows + 1)
        for r in range(rows + 1):
            y = top - row_h * (r + 1)
            self.line(x, y, x + total_w, y, 0.4, gray=0.35)
        self.line(x, top, x + total_w, top, 0.6)
        cx = x
        for _, w in cols:
            self.line(cx, top, cx, bottom, 0.4, gray=0.35)
            cx += w
        self.line(x + total_w, top, x + total_w, bottom, 0.4, gray=0.35)
        return bottom

    def box(self, x: float, top: float, w: float, h: float, title: str, lines: int = 0) -> None:
        self.rect(x, top - h, w, h)
        self.text(x + 6, top - 13, title, 8.5, bold=True)
        if lines:
            gap = (h - 22) / (lines + 1)
            for i in range(1, lines + 1):
                y = top - 18 - gap * i
                self.line(x + 6, y, x + w - 6, y, 0.3, gray=0.55)

    def header(self, title: str, sports: str) -> float:
        self.text(MARGIN, PAGE_H - MARGIN - 14, "CoachLenz", 16, bold=True)
        self.text(MARGIN + 92, PAGE_H - MARGIN - 14, f"Halftime Sheet: {title}", 14, bold=True)
        self.text(MARGIN, PAGE_H - MARGIN - 30, sports, 9, gray=0.35)
        self.line(MARGIN, PAGE_H - MARGIN - 38, PAGE_W - MARGIN, PAGE_H - MARGIN - 38, 1.2)
        y = PAGE_H - MARGIN - 58
        w = (PAGE_W - 2 * MARGIN) / 3
        self.field(MARGIN, y, "Us", w - 12)
        self.field(MARGIN + w, y, "Opponent", w - 12)
        self.field(MARGIN + 2 * w, y, "Date", w)
        y -= 22
        self.field(MARGIN, y, "Location", w - 12)
        self.field(MARGIN + w, y, "Home / Away", w - 12)
        self.field(MARGIN + 2 * w, y, "Charted by", w)
        return y - 24

    def footer(self, page_no: int, pages: int) -> None:
        y = MARGIN + 20
        self.line(MARGIN, y + 12, PAGE_W - MARGIN, y + 12, 0.6, gray=0.5)
        self.text(MARGIN, y, FOOTER_OFFER, 7.5, gray=0.25)
        self.text(MARGIN, y - 11, FOOTER_URL, 7.5, bold=True)
        self.text(PAGE_W - MARGIN - 130, y - 11, FOOTER_BRAND, 7.5, gray=0.35)
        self.text(PAGE_W - MARGIN - 40, y - 22, f"Page {page_no} of {pages}", 7, gray=0.45)

    def content(self) -> bytes:
        return ("\n".join(self.ops)).encode("latin-1")


def _score_grid(p: _Page, x: float, top: float, periods: list[str]) -> float:
    cols = [("", 70)] + [(q, 46) for q in periods]
    bottom = p.table(x, top, cols, rows=2, row_h=18)
    p.text(x + 4, top - 31, "Us", 8.5, bold=True)
    p.text(x + 4, top - 49, "Them", 8.5, bold=True)
    return bottom


def _football_page() -> _Page:
    p = _Page()
    y = p.header("Football / Flag Football", "Chart every snap in the first half. Fill the summary at the break.")
    p.text(MARGIN, y, "SCORE", 8.5, bold=True)
    _score_grid(p, MARGIN, y - 4, ["Q1", "Q2", "Half"])
    p.text(MARGIN + 270, y, "TIMEOUTS LEFT", 8.5, bold=True)
    p.text(MARGIN + 270, y - 22, "Us:   O  O  O          Them:   O  O  O", 9)
    y -= 66

    p.text(MARGIN, y, "PLAY CHART  (Side: O = our offense, D = their offense, ST = special teams)", 8.5, bold=True)
    cols = [("#", 22), ("Qtr", 26), ("Side", 30), ("Dn", 24), ("Dist", 30), ("Yd Ln", 36),
            ("Formation", 82), ("Run/Pass", 50), ("Gap / Route / Target", 110), ("Result", 66), ("Yds", 64)]
    bottom = p.table(MARGIN, y - 4, cols, rows=20, row_h=16)
    for i in range(20):
        p.text(MARGIN + 6, y - 4 - 16 * (i + 1) - 12, str(i + 1), 7, gray=0.45)

    top = bottom - 12
    w = (PAGE_W - 2 * MARGIN - 12) / 2
    p.text(MARGIN, top, "HALFTIME SUMMARY", 8.5, bold=True)
    top -= 6
    p.box(MARGIN, top, w, 70, "Run / Pass split   (Us: ___ / ___    Them: ___ / ___)", lines=2)
    p.box(MARGIN + w + 12, top, w, 70, "Their top plays / formations", lines=3)
    top -= 78
    p.box(MARGIN, top, w, 70, "What is working for us", lines=3)
    p.box(MARGIN + w + 12, top, w, 70, "Adjustments for the 2nd half", lines=3)
    p.footer(1, 2)
    return p


def _basketball_page() -> _Page:
    p = _Page()
    y = p.header("Basketball", "Tally as you go. Fill the summary at the break.")
    p.text(MARGIN, y, "SCORE", 8.5, bold=True)
    _score_grid(p, MARGIN, y - 4, ["Q1 / H1", "Q2", "Half"])
    p.text(MARGIN + 270, y, "TEAM FOULS", 8.5, bold=True)
    p.text(MARGIN + 270, y - 22, "Us:   Q1 ______   Q2 ______", 9)
    p.text(MARGIN + 270, y - 40, "Them: Q1 ______   Q2 ______", 9)
    y -= 66

    cols = [("#", 28), ("Player", 112), ("2PT M-A", 58), ("3PT M-A", 58), ("FT M-A", 58),
            ("Reb", 40), ("TO", 40), ("Fouls", 46), ("Pts", 100)]
    p.text(MARGIN, y, "US", 8.5, bold=True)
    bottom = p.table(MARGIN, y - 4, cols, rows=10, row_h=16)
    y = bottom - 14
    p.text(MARGIN, y, "THEM", 8.5, bold=True)
    bottom = p.table(MARGIN, y - 4, cols, rows=8, row_h=16)

    top = bottom - 12
    w = (PAGE_W - 2 * MARGIN - 12) / 2
    p.text(MARGIN, top, "HALFTIME SUMMARY", 8.5, bold=True)
    top -= 6
    p.box(MARGIN, top, w, 64, "Where their shots come from (paint / mid / 3)", lines=2)
    p.box(MARGIN + w + 12, top, w, 64, "Their key players / foul trouble", lines=2)
    top -= 72
    p.box(MARGIN, top, w, 64, "What is working for us", lines=2)
    p.box(MARGIN + w + 12, top, w, 64, "Adjustments for the 2nd half", lines=2)
    p.footer(2, 2)
    return p


def _assemble(pages: list[_Page]) -> bytes:
    objs: list[bytes] = []
    n_pages = len(pages)
    # 1 catalog, 2 pages tree, 3 F1, 4 F2, then (page, content) pairs, then info.
    page_ids = [5 + 2 * i for i in range(n_pages)]
    info_id = 5 + 2 * n_pages
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for i, page in enumerate(pages):
        content_id = page_ids[i] + 1
        objs.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                     f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>").encode())
        data = page.content()
        objs.append(f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream")
    objs.append(b"<< /Title (CoachLenz Halftime Sheet - printable tracker) /Author (CoachLenz) "
                b"/Producer (CoachLenz) >>")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {info_id} 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


@lru_cache(maxsize=1)
def halftime_sheet_pdf() -> bytes:
    """The printable tracker (2 pages: Football / Flag Football, Basketball)."""
    return _assemble([_football_page(), _basketball_page()])


PDF_FILENAME = "CoachLenz-Halftime-Sheet.pdf"
