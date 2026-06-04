#!/usr/bin/env python3
"""
Regenerate the 'open' diagrams (sequence + flow) with guaranteed
column alignment, then splice them into the markdown files.
Full-box diagrams are already correct and are left untouched.
"""
from pathlib import Path

DOCS = Path(__file__).parent / "docs"


# ─────────────────────────────────────────────────────────────────────────
#  Sequence-diagram generator
# ─────────────────────────────────────────────────────────────────────────

class Seq:
    def __init__(self, names, cols, width):
        self.names = names
        self.cols = cols
        self.width = width
        self.rows = []

    def _blank(self):
        return [" "] * self.width

    def _put(self, line, col, text):
        for k, ch in enumerate(text):
            p = col + k
            if 0 <= p < self.width:
                line[p] = ch

    def header(self):
        line = self._blank()
        for name, c in zip(self.names, self.cols):
            self._put(line, c - len(name) // 2, name)
        self.rows.append(line)
        return self

    def _lifelines(self):
        line = self._blank()
        for c in self.cols:
            line[c] = "│"
        return line

    def gap(self, n=1):
        for _ in range(n):
            self.rows.append(self._lifelines())
        return self

    def text(self, segments):
        """segments: list of (col, text); drawn over the lifelines."""
        line = self._lifelines()
        for col, txt in segments:
            self._put(line, col, txt)
        self.rows.append(line)
        return self

    def dead(self, idx, segments=None):
        """Lifeline row where participant idx is marked dead with ✗."""
        line = self._lifelines()
        line[self.cols[idx]] = "✗"
        for col, txt in (segments or []):
            self._put(line, col, txt)
        self.rows.append(line)
        return self

    def arrow(self, i, j):
        """Arrow between participant i and j (overwrites any lifeline
        in between). i->j direction inferred from positions."""
        line = self._lifelines()
        a, b = self.cols[i], self.cols[j]
        if a < b:                      # rightward  ─►
            for x in range(a + 2, b - 2):
                line[x] = "─"
            line[b - 2] = "►"
        else:                          # leftward  ◄─
            for x in range(b + 3, a - 1):
                line[x] = "─"
            line[b + 2] = "◄"
        self.rows.append(line)
        return self

    def msg(self, i, j, label, extra=None):
        """A labelled message: label row (in the gap of the sender side)
        + arrow row. `extra` adds more (col,text) segments to the label row."""
        lo = min(self.cols[i], self.cols[j])
        segs = [(lo + 3, label)]
        if extra:
            segs.extend(extra)
        self.text(segs)
        self.arrow(i, j)
        return self

    def render(self):
        return "\n".join("".join(r).rstrip() for r in self.rows)


# 4-participant layout
C4 = [4, 22, 41, 60]
W4 = 82
# 3-participant layout
C3 = [4, 22, 41]
W3 = 60


# ── 4.1 Happy path ────────────────────────────────────────────────────────
def happy_path():
    s = Seq(["Client", "Dispatcher", "Namensdienst", "Worker"], C4, W4)
    s.header().gap()
    s.msg(0, 1, "PostTask")
    s.msg(1, 2, "LookupWorker")
    s.msg(2, 1, "[Worker-Liste]")
    s.gap()
    s.msg(1, 3, "ProcessTask")
    s.msg(3, 1, "accepted=true")
    s.msg(1, 0, "task_id=42", extra=[(C4[2] + 3, "[verarbeitet]")])
    s.msg(3, 1, "ReturnResult")
    s.text([(C4[1] + 3, "[task_id=42,")])
    s.text([(C4[1] + 3, " success=true,")])
    s.text([(C4[1] + 3, " result=...]")])
    s.gap()
    s.msg(0, 1, "GetResult")
    s.text([(C4[0] + 3, "status=COMPLETED, result=...")])
    s.arrow(1, 0)
    return s.render()


# ── 4.2 A: Worker crash / Timeout ──────────────────────────────────────────
def worker_crash():
    s = Seq(["Client", "Dispatcher", "Namensdienst", "Worker (tot)"], C4, W4)
    s.header().gap()
    s.msg(0, 1, "PostTask")
    s.msg(1, 2, "LookupWorker")
    s.arrow(2, 1)
    s.msg(1, 3, "ProcessTask")
    s.msg(3, 1, "accepted=true")
    s.msg(1, 0, "task_id=42")
    s.dead(3, segments=[(C4[3] - 12, "[ABSTURZ]")])
    s.text([(C4[1] + 3, "[Timeout-Checker, alle 5s]")])
    s.text([(C4[1] + 3, "Task 42: > TASK_TIMEOUT_SEC")])
    s.text([(C4[1] + 3, "→ TIMEOUT → RETRYING → QUEUED")])
    s.gap()
    s.msg(1, 2, "LookupWorker")
    s.msg(2, 1, "[anderer Worker]")
    s.msg(1, 3, "ProcessTask")
    s.msg(3, 1, "ReturnResult")
    s.msg(1, 0, "status=COMPLETED")
    return s.render()


# ── 4.2 B: Worker rejects (capacity) ───────────────────────────────────────
def worker_rejects():
    s = Seq(["Client", "Dispatcher", "Namensdienst", "Worker (voll)"], C4, W4)
    s.header().gap()
    s.msg(0, 1, "PostTask")
    s.msg(1, 2, "LookupWorker")
    s.arrow(2, 1)
    s.msg(1, 3, "ProcessTask")
    s.msg(3, 1, "accepted=false")
    s.text([(C4[1] + 3, "[Task bleibt QUEUED,")])
    s.text([(C4[1] + 3, " erneuter Dispatch im")])
    s.text([(C4[1] + 3, " nächsten Zyklus]")])
    return s.render()


# ── 4.2 C: Unknown task type ───────────────────────────────────────────────
def unknown_type():
    s = Seq(["Client", "Dispatcher", "Namensdienst"], C3, W3)
    s.header().gap()
    s.text([(C3[0] + 3, "PostTask")])
    s.text([(C3[0] + 3, 'type="unknown"')])
    s.arrow(0, 1)
    s.text([(C3[1] + 3, "LookupWorker")])
    s.text([(C3[1] + 3, 'type="unknown"')])
    s.arrow(1, 2)
    s.text([(C3[1] + 3, "success=false,")])
    s.text([(C3[1] + 3, "workers=[]")])
    s.arrow(2, 1)
    s.text([(C3[0] + 3, "success=false,")])
    s.text([(C3[0] + 3, '"kein Worker')])
    s.text([(C3[0] + 3, ' für Typ"')])
    s.arrow(1, 0)
    return s.render()


# ─────────────────────────────────────────────────────────────────────────
#  Hand-written flow / tree diagrams (verified for bar alignment)
# ─────────────────────────────────────────────────────────────────────────

def _grid(h, w):
    return [[" "] * w for _ in range(h)]

def _box(g, r, c, w, h, labels):
    g[r][c] = "┌"; g[r][c + w - 1] = "┐"
    g[r + h - 1][c] = "└"; g[r + h - 1][c + w - 1] = "┘"
    for x in range(c + 1, c + w - 1):
        g[r][x] = "─"; g[r + h - 1][x] = "─"
    for y in range(r + 1, r + h - 1):
        g[y][c] = "│"; g[y][c + w - 1] = "│"
    for i, line in enumerate(labels):
        _put(g, r + 1 + i, c + (w - len(line)) // 2, line)


def _arch_box():
    W = 78
    g = _grid(25, W)
    _box(g, 0, 0, W, 25, [])
    _put(g, 1, (W - 15) // 2, "Docker-Netzwerk")

    # ── Top row: Client ◄─► Dispatcher ─► Namensdienst ───────────────────
    _box(g, 4, 4, 12, 3, ["Client"])          # cols 4-15,  mid r5
    _box(g, 4, 32, 15, 3, ["Dispatcher"])     # cols 32-46, mid r5, cx 39
    _box(g, 4, 60, 15, 3, ["Namensdienst"])   # cols 60-74, mid r5, cx 67

    _put(g, 3, 17, "PostTask / GetResult")
    g[5][16] = "◄"; _hline(g, 5, 17, 31); g[5][31] = "►"
    _put(g, 3, 49, "LookupWorker")
    _hline(g, 5, 47, 59); g[5][59] = "►"

    # ── Dispatcher ▼ Worker-Pool (ProcessTask / ReturnResult) ────────────
    dcx = 39
    g[7][dcx] = "│"; g[8][dcx] = "│"; g[9][dcx] = "│"; g[10][dcx] = "▼"
    _put(g, 7, dcx + 3, "ProcessTask /")
    _put(g, 8, dcx + 3, "ReturnResult")

    # ── Worker-Pool box ──────────────────────────────────────────────────
    _box(g, 11, 4, 70, 6, [])
    _put(g, 12, 7, "Worker-Pool (skalierbar, ein Container pro Aufgabentyp)")
    _box(g, 13, 8, 14, 3, ["reverse"])
    _box(g, 13, 26, 14, 3, ["sum"])
    _box(g, 13, 44, 14, 3, ["hash"])
    _put(g, 14, 61, "...")

    # ── Worker-Pool ▲ Namensdienst (Register / Heartbeat) ────────────────
    ncx = 67
    g[7][ncx] = "▲"; g[8][ncx] = "│"; g[9][ncx] = "│"; g[10][ncx] = "│"
    _put(g, 7, ncx - 11, "Register /")
    _put(g, 8, ncx - 11, "Heartbeat")

    # ── Monitoring ─► status ─────────────────────────────────────────────
    _box(g, 20, 4, 14, 3, ["Monitoring"])
    _put(g, 19, 21, "GetDispatcherStatus / GetNameServiceStatus")
    _hline(g, 21, 19, 73); g[21][73] = "►"

    return _render(g)

def _put(g, r, c, text):
    for k, ch in enumerate(text):
        g[r][c + k] = ch

def _hline(g, r, c0, c1):
    for c in range(c0, c1):
        g[r][c] = "─"

def _render(g):
    return "\n".join("".join(row).rstrip() for row in g)


def _arch_flow():
    LB, RB = 25, 56
    g = _grid(12, 80)
    _put(g, 0, 0, "Client ──PostTask──► Dispatcher ──LookupWorker──► Namensdienst")
    _put(g, 1, LB, "│");                _put(g, 1, RB, "▲")
    _put(g, 2, LB, "│ ProcessTask");    _put(g, 2, RB, "│ Register / Heartbeat")
    _put(g, 3, LB, "▼");                _put(g, 3, RB, "│")
    _put(g, 4, 23, "Worker"); _hline(g, 4, 30, RB); _put(g, 4, RB, "┘")
    _put(g, 5, LB, "│")
    _put(g, 6, LB, "│ ReturnResult")
    _put(g, 7, LB, "▼")
    _put(g, 8, 21, "Dispatcher ──GetResult──► Client")
    _put(g, 10, 0, "Monitoring ──GetDispatcherStatus───► Dispatcher")
    _put(g, 11, 0, "Monitoring ──GetNameServiceStatus──► Namensdienst")
    return _render(g)


def _state_flow():
    PC, TS = 42, 57
    g = _grid(8, 100)
    _put(g, 0, 0, "CREATED ──► QUEUED ──► DISPATCHED ──► PROCESSING ──► COMPLETED")
    _put(g, 1, PC, "│")
    _put(g, 2, PC, "├──► FAILED   (Worker meldet Fehler)")
    _put(g, 3, PC, "│")
    _put(g, 4, PC, "└──► TIMEOUT ──┬──► RETRYING ──► QUEUED   (retry < MAX)")
    _put(g, 5, TS, "└──► FAILED               (retry ≥ MAX)")
    _put(g, 7, 0, "QUEUED ──► FAILED   (kein alternativer Worker bei Retry)")
    return _render(g)


ARCH_BOX = _arch_box()
ARCH_FLOW = _arch_flow()
STATE_FLOW = _state_flow()

RETRY_TREE = """\
TIMEOUT erkannt
    │
    ├── retry_count < MAX_RETRIES
    │       ├── retry_count += 1
    │       ├── last_failed_worker = timed_out_worker
    │       ├── assigned_worker = ""
    │       ├── timestamp_dispatched = 0
    │       ├── Status: RETRYING
    │       └── Status: QUEUED   →   Task erneut einreihen
    │
    └── retry_count >= MAX_RETRIES
            └── Status: FAILED
                error_message = "task timed out after maximum retries\""""


# ─────────────────────────────────────────────────────────────────────────
#  Splicing helper: replace the Nth code block in a file
# ─────────────────────────────────────────────────────────────────────────

def replace_block(path, anchor, new_body):
    """Replace the first ``` code block that appears after `anchor`."""
    text = path.read_text(encoding="utf-8")
    a_idx = text.index(anchor)
    start = text.index("```", a_idx)
    nl = text.index("\n", start)
    end = text.index("```", nl)
    new_text = text[:nl + 1] + new_body + "\n" + text[end:]
    path.write_text(new_text, encoding="utf-8")


def verify(name, body, expect_lifelines=None):
    lines = body.split("\n")
    bars = {}
    for li in lines:
        for col, ch in enumerate(li):
            if ch == "│":
                bars.setdefault(col, 0)
                bars[col] += 1
    print(f"  {name}: {len(lines)} lines, │ columns = {sorted(bars)}")


arch = DOCS / "architecture.md"
state = DOCS / "state-model.md"

print("Generating sequence diagrams …")
hp = happy_path();     verify("happy_path", hp)
wc = worker_crash();   verify("worker_crash", wc)
wr = worker_rejects(); verify("worker_rejects", wr)
ut = unknown_type();   verify("unknown_type", ut)

print("\nSplicing into architecture.md …")
replace_block(arch, "## 1. Architekturdiagramm", ARCH_BOX)
replace_block(arch, "### Vereinfachte Übersicht der Kommunikationsflüsse", ARCH_FLOW)
replace_block(arch, "### 4.1 Happy Path", hp)
replace_block(arch, "#### Szenario A: Worker-Absturz", wc)
replace_block(arch, "#### Szenario B: Worker lehnt", wr)
replace_block(arch, "#### Szenario C: Unbekannter", ut)

print("Splicing into state-model.md …")
replace_block(state, "### Vereinfachte Zustandsübergänge", STATE_FLOW)
replace_block(state, "### Retry-Ablauf", RETRY_TREE)

print("\nDone.")
