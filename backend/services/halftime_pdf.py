"""The free printable Halftime Sheet tracker (PDF), emailed only after double opt-in.

A blank paper charting sheet a coach can print and fill in on the sideline: page 1
for Football / Flag Football, page 2 for Basketball. Each page ends with a Halftime
Sheet box (score, what is working, their tendencies, second-half adjustments).

Built with a tiny hand-written PDF 1.4 writer (built-in Helvetica, lines, text) so it
adds no dependency. Deterministic: the same bytes every call, cached after the first.
It makes no product claims and quotes no price.
"""
from functools import lru_cache

PAGE_W, PAGE_H = 612, 792  # US Letter, points
MARGIN = 36


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Page:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(self, x: float, y: float, s: str, size: float = 10, bold: bool = False) -> None:
        font = "F2" if bold else "F1"
        self.ops.append(f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({_esc(s)}) Tj ET")

    def line(self, x1: float, y1: float, x2: float, y2: float, w: float = 0.6) -> None:
        self.ops.append(f"{w} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def rect(self, x: float, y: float, w: float, h: float, lw: float = 0.8) -> None:
        self.ops.append(f"{lw} w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S")

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def _header(p: _Page, title: str, sport_line: str) -> float:
    top = PAGE_H - MARGIN
    p.text(MARGIN, top - 14, "CoachLenz Halftime Sheet", 18, bold=True)
    p.text(MARGIN, top - 32, f"{title}  |  {sport_line}", 10)
    y = top - 54
    p.text(MARGIN, y, "Us: ____________________   Them: ____________________   Date: __________   Home / Away", 9)
    return y - 14


def _grid(p: _Page, y_top: float, cols: list[tuple[str, float]], rows: int, row_h: float) -> float:
    x0 = MARGIN
    width = sum(w for _, w in cols)
    p.rect(x0, y_top - row_h * (rows + 1), width, row_h * (rows + 1))
    # header row
    x = x0
    for label, w in cols:
        p.text(x + 3, y_top - row_h + 5, label, 8, bold=True)
        x += w
    for r in range(1, rows + 1):
        yy = y_top - row_h * r
        p.line(x0, yy, x0 + width, yy, 0.8 if r == 1 else 0.4)
    x = x0
    for _, w in cols[:-1]:
        x += w
        p.line(x, y_top, x, y_top - row_h * (rows + 1), 0.4)
    return y_top - row_h * (rows + 1)


def _halftime_box(p: _Page, y_top: float, prompts: list[str]) -> None:
    width = PAGE_W - 2 * MARGIN
    h = y_top - (MARGIN + 18)
    p.rect(MARGIN, MARGIN + 18, width, h, 1.2)
    p.text(MARGIN + 6, y_top - 14, "HALFTIME SHEET", 11, bold=True)
    p.text(MARGIN + 140, y_top - 14, "Score at the half:  Us ______   Them ______", 9)
    col_w = width / 2
    box_h = (h - 26) / 2
    for i, label in enumerate(prompts[:4]):
        cx = MARGIN + (i % 2) * col_w
        cy = y_top - 22 - (i // 2) * box_h
        p.text(cx + 6, cy - 10, label, 8, bold=True)
        for k in range(1, 4):
            ly = cy - 10 - k * 14
            if ly > MARGIN + 22:
                p.line(cx + 6, ly, cx + col_w - 8, ly, 0.3)


def _footer(p: _Page, n: int) -> None:
    p.text(MARGIN, MARGIN, f"CoachLenz  |  Powered by Cosby AI Solutions (cosbyaisolutions.com)  |  Page {n} of 2", 7)


def _football_page() -> _Page:
    p = _Page()
    y = _header(p, "Play Chart", "Football / Flag Football")
    cols = [("#", 22), ("Qtr", 26), ("Dn & Dist", 52), ("Field Pos", 50), ("Formation", 74),
            ("Play / Route", 92), ("Gap / Dir", 52), ("Result", 92), ("Yds", 80)]
    y = _grid(p, y, cols, rows=26, row_h=16)
    _halftime_box(p, y - 10, [
        "What is working for us", "Their tendencies (formation / play)",
        "Players to watch", "Second-half adjustments",
    ])
    _footer(p, 1)
    return p


def _basketball_page() -> _Page:
    p = _Page()
    y = _header(p, "Game Chart", "Basketball")
    p.text(MARGIN, y - 2, "Shots by zone (tally makes / attempts)", 9, bold=True)
    zones = [("Zone", 120), ("Us makes", 100), ("Us attempts", 100), ("Them makes", 110), ("Them attempts", 110)]
    y = _grid(p, y - 8, zones, rows=6, row_h=16)
    labels = ["At the rim", "Paint", "Mid-range", "Corner 3", "Wing / top 3", "Free throws"]
    for i, lab in enumerate(labels):
        p.text(MARGIN + 3, y + 16 * (6 - i) - 11, lab, 8)
    y -= 14
    p.text(MARGIN, y, "Player tracker (fouls / turnovers / notes)", 9, bold=True)
    players = [("#", 30), ("Player", 130), ("Fouls", 70), ("TO", 60), ("Notes", 250)]
    y = _grid(p, y - 6, players, rows=12, row_h=16)
    _halftime_box(p, y - 10, [
        "What is working for us", "Their go-to actions / shooters",
        "Foul trouble (us / them)", "Second-half adjustments",
    ])
    _footer(p, 2)
    return p


def _build(pages: list[_Page]) -> bytes:
    objs: list[bytes] = []
    # 1 catalog, 2 pages, 3 F1, 4 F2, then per page: page obj, content obj
    n_pages = len(pages)
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for i, pg in enumerate(pages):
        content_id = 6 + 2 * i
        objs.append((
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode())
        data = pg.stream()
        objs.append(f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


PDF_FILENAME = "CoachLenz-Halftime-Sheet.pdf"


@lru_cache(maxsize=1)
def halftime_sheet_pdf() -> bytes:
    """The printable Halftime Sheet tracker, as PDF bytes."""
    return _build([_football_page(), _basketball_page()])
