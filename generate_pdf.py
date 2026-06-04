#!/usr/bin/env python3
"""
Generate the TaskGrid+ submission PDF.
Fixes: clickable ToC, Unicode arrow alignment, concise content.
"""
import os, re
import markdown
from weasyprint import HTML, CSS
from pathlib import Path

BASE = Path(__file__).parent
DOCS = BASE / "docs"
OUT  = BASE / "docs" / "taskgrid_dokumentation.pdf"

MD_EXT = ["fenced_code", "tables", "sane_lists"]

# ── Helpers ───────────────────────────────────────────────────────────────

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def fix_pre_unicode(html: str) -> str:
    """Replace wide Unicode arrows in <pre> blocks with ASCII equivalents."""
    def _fix(m):
        code = m.group(1)
        code = code.replace("►", "&gt;").replace("◄", "&lt;")
        code = code.replace("▶", "&gt;").replace("◀", "&lt;")
        code = code.replace("▼", "v").replace("▲", "^")
        return f"<pre>{code}</pre>"
    return re.sub(r"<pre>(.*?)</pre>", _fix, html, flags=re.DOTALL)

def md(text: str) -> str:
    return fix_pre_unicode(markdown.markdown(text, extensions=MD_EXT))

def drop_sections(text: str, headings: list[str]) -> str:
    """Remove h2 sections whose title starts with one of the given strings."""
    lines = text.splitlines(keepends=True)
    out, skip = [], False
    for line in lines:
        if line.startswith("## "):
            skip = any(line.strip().startswith(f"## {h}") for h in headings)
        if not skip:
            out.append(line)
    return "".join(out)

def keep_sections(text: str, headings: list[str]) -> str:
    """Keep only h2 sections whose title starts with one of the given strings,
    plus any content before the first h2."""
    lines = text.splitlines(keepends=True)
    out, keep = [], True   # keep preamble
    for line in lines:
        if line.startswith("## "):
            keep = any(line.strip().startswith(f"## {h}") for h in headings)
        if keep:
            out.append(line)
    return "".join(out)

def truncate_after(text: str, marker: str) -> str:
    idx = text.find(marker)
    return text[:idx] if idx != -1 else text

# ── ToC builder ───────────────────────────────────────────────────────────

def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

TOC_ENTRIES: list[tuple[int, str, str]] = []   # (level, title, id)

def add_ids_and_collect_toc(html: str, level: int = 1) -> str:
    """Add id= to h1/h2 tags and record them for ToC."""
    def _replace(m):
        tag   = m.group(1)   # "h1" or "h2"
        attrs = m.group(2)   # existing attributes (may be empty)
        title = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        lvl   = int(tag[1])
        if lvl > 2:
            return m.group(0)
        sid = slugify(title)
        # ensure unique
        existing = {e[2] for e in TOC_ENTRIES}
        base, n = sid, 1
        while sid in existing:
            sid = f"{base}-{n}"
            n += 1
        TOC_ENTRIES.append((lvl, title, sid))
        return f"<{tag}{attrs} id=\"{sid}\">{m.group(3)}</{tag}>"
    return re.sub(r"<(h[12])([^>]*)>(.*?)</h[12]>", _replace, html,
                  flags=re.DOTALL)

def build_toc_html() -> str:
    # Only show h1-level entries — keeps ToC on one page
    h1_entries = [(title, sid) for lvl, title, sid in TOC_ENTRIES if lvl == 1]
    items = []
    for i, (title, sid) in enumerate(h1_entries, 1):
        items.append(f'<li><a href="#{sid}">{title}</a></li>')
    return f"""
<div class="toc-page">
  <h1 class="toc-title">Inhaltsverzeichnis</h1>
  <ol class="toc-list">{''.join(items)}</ol>
</div>
<div class="page-break"></div>
"""

# ── CSS ───────────────────────────────────────────────────────────────────

CSS_STYLE = """
@page {
  size: A4;
  margin: 2.2cm 2.2cm 2.5cm 2.2cm;
  @bottom-center {
    content: counter(page);
    font-size: 9pt; color: #888;
  }
  @top-right {
    content: "TaskGrid+";
    font-size: 8pt; color: #bbb;
  }
}
@page :first { @bottom-center{content:none} @top-right{content:none} }

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: "Liberation Sans", "Arial", sans-serif;
  font-size: 10.5pt;
  line-height: 1.55;
  color: #1a1a2e;
}

/* ── Title page ── */
.title-page {
  page-break-after: always;
  text-align: center;
  padding-top: 3.5cm;
}
.title-logo { font-size: 44pt; font-weight: 700; color: #1a56a0; }
.title-sub  { font-size: 13pt; color: #555; margin: 0.5cm 0 1.8cm; }
.title-meta { margin: 0 auto 2cm; display: inline-block; }
.title-meta table { border-collapse: collapse; }
.title-meta th { text-align: right; padding: 3px 14px 3px 0; color: #777;
                 font-weight: 600; font-size: 10pt; }
.title-meta td { text-align: left; padding: 3px 0; font-size: 10pt; }

/* ── ToC page ── */
.toc-page { padding-top: 0.5cm; }
.toc-title { font-size: 18pt; font-weight: 700; color: #1a56a0;
             border-bottom: 2px solid #1a56a0; padding-bottom: 6px; margin-bottom: 20px; }
.toc-list  { list-style: none; padding: 0; margin: 0; }
.toc-list li {
  font-size: 11.5pt; font-weight: 600;
  padding: 7px 0; border-bottom: 1px solid #e8edf5;
  counter-increment: toc-item;
}
.toc-list li::before {
  content: counter(toc-item) ".";
  display: inline-block; width: 24px;
  color: #1a56a0; font-weight: 700;
}
.toc-list a { text-decoration: none; color: #1a1a2e; }
.toc-list a:hover { color: #1a56a0; }
.toc-list { counter-reset: toc-item; }

/* ── Page break ── */
.page-break { page-break-after: always; }

/* ── Headings ── */
h1 {
  font-size: 17pt; font-weight: 700; color: #1a56a0;
  border-bottom: 2px solid #1a56a0;
  padding-bottom: 4px; margin: 0 0 14px;
  page-break-after: avoid;
}
h2 {
  font-size: 12.5pt; font-weight: 700; color: #1a56a0;
  margin: 20px 0 8px; page-break-after: avoid;
}
h3 {
  font-size: 11pt; font-weight: 600; color: #2c4a7a;
  margin: 14px 0 5px; page-break-after: avoid;
}
h4 {
  font-size: 10.5pt; font-weight: 600; color: #2c4a7a;
  margin: 10px 0 4px; page-break-after: avoid;
}

/* ── Code ── */
pre {
  background: #f4f6fa;
  border: 1px solid #d0d8e8;
  border-left: 4px solid #1a56a0;
  border-radius: 3px;
  padding: 9px 12px;
  font-family: "Liberation Mono", "Courier New", monospace;
  font-size: 7.6pt;
  line-height: 1.35;
  white-space: pre;
  overflow-x: hidden;
  margin: 8px 0;
}
code {
  font-family: "Liberation Mono", "Courier New", monospace;
  font-size: 8.8pt;
  background: #eef1f8;
  padding: 1px 4px;
  border-radius: 2px;
}
pre code { background: none; padding: 0; font-size: 7.6pt; }

/* ── Tables ── */
table {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0 12px;
  font-size: 9.5pt;
}
th {
  background: #1a56a0; color: white;
  padding: 5px 9px; text-align: left; font-weight: 600;
}
td { padding: 4px 9px; border-bottom: 1px solid #dde3ef; }
tr:nth-child(even) td { background: #f7f9fd; }

/* ── Misc ── */
ul, ol { margin: 5px 0 9px 20px; }
li     { margin-bottom: 2px; }
p      { margin: 4px 0 7px; }
hr     { border: none; border-top: 1px solid #ccc; margin: 16px 0; }
img    { max-width: 100%; border: 1px solid #d0d8e8; border-radius: 3px; margin: 8px 0; }
blockquote {
  border-left: 4px solid #1a56a0; background: #eef3fc;
  margin: 8px 0; padding: 7px 13px; color: #333;
}
strong { font-weight: 700; }

/* ── ADR colour scheme ── */
.adr-section h1 { color: #7b2f8a; border-color: #7b2f8a; }
.adr-section h2 { color: #7b2f8a; }
.adr-section pre { border-left-color: #7b2f8a; }
/* ── Test protocol ── */
.test-section h1 { color: #1a7a3a; border-color: #1a7a3a; }
.test-section h2, .test-section h3 { color: #1a7a3a; }
.test-section pre { border-left-color: #1a7a3a; }
"""

# ── Content assembly ──────────────────────────────────────────────────────

def section(html_body: str, cls: str = "") -> str:
    return f'<section class="doc-section {cls}">{html_body}</section>\n'

def pb() -> str:
    return '<div class="page-break"></div>\n'

parts = [f"<html><head><meta charset='utf-8'><style>{CSS_STYLE}</style></head><body>"]

# Title page
parts.append("""
<div class="title-page">
  <div class="title-logo">TaskGrid+</div>
  <div class="title-sub">Erweiterbares Aufgabenverarbeitungssystem in Containern</div>
  <div class="title-meta">
    <table>
      <tr><th>Kurs</th><td>Verteilte Systeme &mdash; TIK23</td></tr>
      <tr><th>Dozent</th><td>Kevin Dallmann</td></tr>
      <tr><th>Abgabe</th><td>08.06.2026</td></tr>
    </table>
  </div>
</div>
""")

# ── ToC placeholder (filled after body is assembled) ─────────────────────
TOC_PLACEHOLDER = "<!-- TOC_PLACEHOLDER -->"
parts.append(TOC_PLACEHOLDER)

# ── 1. Architecture ───────────────────────────────────────────────────────
arch = read(DOCS / "architecture.md")
# Keep diagrams, justification, flow diagrams; drop verbose §3 component detail
arch = keep_sections(arch, ["1.", "2.", "4."])
# Trim arch justification — stop before the long component table
arch = truncate_after(arch, "## 3.")   # already dropped but safety net
parts.append(section(md(arch)))
parts.append(pb())

# ── 2. Interfaces & Protocol ──────────────────────────────────────────────
iface = read(DOCS / "interfaces.md")
# Keep protocol intro, data structures, RPC docs, port overview; drop extensibility (§5)
iface = keep_sections(iface, ["1.", "2.", "3.", "4."])
parts.append(section(md(iface)))
parts.append(pb())

# ── 3. State model ────────────────────────────────────────────────────────
state = read(DOCS / "state-model.md")
# Drop long code-heavy §4 (guards) and §5 (retry code); keep diagrams + tables
state = keep_sections(state, ["1.", "2.", "3."])
parts.append(section(md(state)))
parts.append(pb())

# ── 4. Extensibility ──────────────────────────────────────────────────────
ext = read(DOCS / "ADDING_TASK_TYPES.md")
# Keep architecture overview + steps 1–4, drop full code examples section
ext = keep_sections(ext, ["Architecture", "Adding a New Handler", "Testing"])
parts.append(section(md(ext)))
parts.append(pb())

# ── 5. Start guide ────────────────────────────────────────────────────────
start = read(DOCS / "startanleitung.md")
parts.append(section(md(start)))
parts.append(pb())

# ── 6. Test protocol — successful ─────────────────────────────────────────
def fix_img(text: str) -> str:
    return re.sub(
        r'!\[([^\]]*)\]\((?!http)(img/[^)]+)\)',
        lambda m: f'![{m.group(1)}](file://{DOCS / m.group(2)})',
        text,
    )

tp = fix_img(read(DOCS / "testprotokoll.md"))
parts.append(section(md(tp), "test-section"))
parts.append(pb())

# ── 7. Test protocol — robustness ─────────────────────────────────────────
tr = fix_img(read(DOCS / "testprotokoll-robustness.md"))
parts.append(section(md(tr), "test-section"))
parts.append(pb())

# ── 8. ADRs ──────────────────────────────────────────────────────────────
for adr_path in sorted((DOCS / "adr").glob("ADR-*.md")):
    parts.append(section(md(read(adr_path)), "adr-section"))

parts.append("</body></html>")

# ── Inject IDs and build ToC ──────────────────────────────────────────────
body = "\n".join(parts)
body = add_ids_and_collect_toc(body)
toc  = build_toc_html()
body = body.replace(TOC_PLACEHOLDER, toc)

# ── Render ────────────────────────────────────────────────────────────────
print("Rendering PDF …")
HTML(string=body, base_url=str(DOCS)).write_pdf(str(OUT))
print(f"Done → {OUT}  ({OUT.stat().st_size // 1024} KB)")
