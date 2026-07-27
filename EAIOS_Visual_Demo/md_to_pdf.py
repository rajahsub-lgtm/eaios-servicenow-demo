"""Render a markdown document to PDF via headless Chrome.

No LibreOffice on this machine and no pandoc, but Chrome and Edge both ship a
print-to-PDF that honours real CSS — including page breaks, running headers
and widow control, which the lighter Python HTML-to-PDF libraries handle
poorly. The intermediate HTML is kept next to the PDF so a failed render can
be opened and inspected rather than guessed at.

    python md_to_pdf.py DESIGN.md
    python md_to_pdf.py DESIGN.md ARCHITECTURE.md DEMO_SCRIPT.md
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import markdown


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"

BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)

# Print stylesheet. Sized for A4 with a generous measure, because this is a
# reference document someone reads rather than a slide someone glances at.
CSS = """
@page {
  size: A4;
  /* Chrome draws its own page numbering in headless print, so no counter
     rule here. Margins leave room for it without crowding the text. */
  margin: 18mm 17mm 18mm;
}
:root {
  --ink: #14181D;
  --soft: #444E58;
  --faint: #6B7683;
  --rule: #D5DBE1;
  --deep: #0B4F6C;
  --wash: #F2F5F7;
}
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", -apple-system, system-ui, sans-serif;
  font-size: 10.2pt;
  line-height: 1.52;
  color: var(--ink);
  margin: 0;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
h1, h2, h3, h4 {
  font-family: Cambria, Georgia, serif;
  line-height: 1.22;
  color: var(--ink);
  margin: 0 0 .4em;
  break-after: avoid;
  page-break-after: avoid;
}
h1 {
  font-size: 23pt;
  letter-spacing: -.01em;
  padding-bottom: .35em;
  border-bottom: 2px solid var(--deep);
  margin-bottom: .7em;
}
h2 {
  font-size: 15pt;
  color: var(--deep);
  margin-top: 1.9em;
  padding-top: .5em;
  border-top: 1px solid var(--rule);
  break-before: auto;
}
h3 { font-size: 11.8pt; margin-top: 1.4em; }
h4 { font-size: 10.5pt; margin-top: 1.1em; color: var(--soft); }

p, ul, ol { margin: 0 0 .78em; }
li { margin-bottom: .22em; }
strong { font-weight: 650; }

/* Keep a heading with the block that follows it. */
h2 + p, h2 + table, h3 + p, h3 + table, h3 + ul { break-before: avoid; }

table {
  border-collapse: collapse;
  width: 100%;
  margin: .5em 0 1.1em;
  font-size: 9.2pt;
  break-inside: auto;
}
thead { display: table-header-group; }
tr { break-inside: avoid; page-break-inside: avoid; }
th, td {
  text-align: left;
  padding: .38em .6em;
  border-bottom: 1px solid var(--rule);
  vertical-align: top;
}
th {
  font-size: 7.6pt;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: var(--faint);
  font-weight: 600;
  border-bottom: 1.5px solid var(--rule);
}
tbody tr:nth-child(even) { background: var(--wash); }

code {
  font-family: Consolas, "Cascadia Mono", monospace;
  font-size: 8.9pt;
  background: var(--wash);
  padding: .08em .3em;
  border-radius: 2px;
  color: var(--deep);
}
pre {
  background: var(--wash);
  border: 1px solid var(--rule);
  border-radius: 3px;
  padding: .7em .9em;
  overflow-x: auto;
  font-size: 8.4pt;
  line-height: 1.42;
  break-inside: avoid;
  page-break-inside: avoid;
  margin: .5em 0 1em;
}
pre code { background: none; padding: 0; color: var(--ink); }

blockquote {
  margin: .8em 0;
  padding: .5em 0 .5em 1em;
  border-left: 3px solid var(--deep);
  color: var(--soft);
  break-inside: avoid;
}
blockquote p { margin: 0; }

hr { border: 0; border-top: 1px solid var(--rule); margin: 1.6em 0; }

a { color: var(--deep); text-decoration: none; }

/* The status block under the title. */
body > p:first-of-type {
  color: var(--soft);
  font-size: 9.4pt;
  padding: .7em .9em;
  background: var(--wash);
  border-left: 3px solid var(--deep);
  margin-bottom: 1.6em;
}
"""

SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>{css}</style></head><body>{body}</body></html>"""


def _settled(path: Path, *, timeout: float = 20.0) -> bool:
    """Wait for a file to appear and stop growing.

    Two consecutive identical non-zero sizes count as done. Polling the file
    is the only reliable signal here; the browser process exiting is not one.
    """
    deadline = time.monotonic() + timeout
    previous = -1
    while time.monotonic() < deadline:
        if path.exists():
            size = path.stat().st_size
            if size > 1024 and size == previous:
                return True
            previous = size
        time.sleep(0.4)
    return False


def browsers() -> list[str]:
    """Every browser worth trying, in preference order.

    More than one, because a browser already running with another profile can
    hand the invocation to the existing instance, return zero, and write
    nothing. The exit code is not evidence that a PDF exists.
    """
    found = [path for path in BROWSERS if Path(path).exists()]
    found += [
        path
        for path in (shutil.which("chrome"), shutil.which("msedge"))
        if path and path not in found
    ]
    if not found:
        raise SystemExit(
            "No Chrome or Edge found. Both ship a headless print-to-PDF; "
            "without one, open the generated .html and print from a browser."
        )
    return found


def render(source: Path) -> Path:
    html_body = markdown.markdown(
        source.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )
    OUT.mkdir(exist_ok=True)
    html_path = OUT / f"{source.stem}.html"
    html_path.write_text(
        SHELL.format(title=source.stem, css=CSS, body=html_body),
        encoding="utf-8",
    )

    pdf_path = OUT / f"{source.stem}.pdf"
    pdf_path.unlink(missing_ok=True)

    attempts = []
    for browser in browsers():
        for headless in ("--headless=new", "--headless"):
            # Chrome keeps the profile lockfile open briefly after exit,
            # so cleanup races it on Windows. The directory is temporary
            # either way; failing the render over it would be absurd.
            with tempfile.TemporaryDirectory(
                ignore_cleanup_errors=True
            ) as profile:
                result = subprocess.run(
                    [
                        browser,
                        headless,
                        "--disable-gpu",
                        "--no-sandbox",
                        "--disable-extensions",
                        f"--user-data-dir={profile}",
                        f"--print-to-pdf={pdf_path}",
                        html_path.as_uri(),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            # The file, not the exit code, is the test — and the file arrives
            # after the process exits. Chrome returns as soon as printing is
            # dispatched and the write completes behind it, so checking once
            # immediately reports failure on a render that succeeded a moment
            # later. Wait for the size to settle rather than for the process.
            if _settled(pdf_path):
                return pdf_path
            attempts.append(
                f"{Path(browser).name} {headless}: rc={result.returncode} "
                f"{(result.stderr or '').strip()[:120]}"
            )

    detail = "\n".join(f"  {line}" for line in attempts)
    raise SystemExit(
        f"No browser produced a PDF for {source.name}.\n{detail}\n"
        f"The HTML is at {html_path} — open it and print from a browser."
    )


def main() -> None:
    names = sys.argv[1:] or ["DESIGN.md"]
    for name in names:
        source = ROOT / name
        if not source.exists():
            raise SystemExit(f"No such document: {name}")
        pdf = render(source)
        size = pdf.stat().st_size / 1024
        print(f"{source.name:24} -> {pdf.relative_to(ROOT)}  ({size:.0f} KB)")


if __name__ == "__main__":
    main()
