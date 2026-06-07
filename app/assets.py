# app/assets.py

"""Static-asset bundling helpers.

Collects CSS files from the local ``static/css/`` tree and returns them as
a single concatenated string. This is used by :func:`app.layouts.shell.setup_page_shell`
to inline all styles in the page ``<head>`` instead of relying on
``<link rel="stylesheet" href="/static/css/...">`` tags.

Why inline?
-----------
In NiceGUI's ``on_air`` mode the app is exposed via the ``on-air.nicegui.io``
relay. Browser requests for ``/static/css/...`` are forwarded through the
relay to the local ASGI app, and in practice they are frequently 404'd or
cross-origin-blocked — leaving the page unstyled. Inlining the CSS
removes the round-trip entirely and works identically in local and
on_air mode.

Determinism
-----------
The CSS files are concatenated in **sorted relative path** order so the
cascade is reproducible across runs. This matches the alphabetical order
the original ``<link>`` tags relied on (later rules override earlier ones).

``@import`` handling
--------------------
Some CSS files (``app.css``, ``control_panel.css``) declare ``@import``
rules that point at sibling files in the same ``css/`` tree. Those sibling
files are *already* part of the bundle (they're discovered by
``rglob('*.css')``), so leaving the ``@import`` lines in would make the
browser try to fetch them as relative URLs (e.g. ``/tokens.css``) — which
404 in both local and on_air mode, and a single failed ``@import`` is
enough to make the browser drop the whole imported stylesheet. We strip
``@import`` lines during bundling; the content they would have pulled in
is already inline.
"""

from __future__ import annotations

import re
from pathlib import Path

# Comment marker we insert between files. Keeps the bundled CSS readable
# when inspecting the page source, and helps the dev tools "go to source"
# jump to the right file.
_FILE_SEPARATOR_FMT = "\n\n/* ===== {rel} ===== */\n"

# Matches ``@import`` rules — both ``url("...")`` and bare ``"..."`` forms,
# terminated by a semicolon. We strip the whole statement (with trailing
# whitespace) to keep the output clean.
_IMPORT_RE = re.compile(r"@import\s+[^;]+;\s*")


def _strip_imports(css: str) -> str:
    """Remove ``@import`` statements that would point at sibling files
    inside the same ``css/`` tree. The sibling content is already inlined
    by the bundler, so the ``@import`` would only cause a 404.
    """
    return _IMPORT_RE.sub("", css)


def collect_css(static_dir: Path) -> str:
    """Walk ``<static_dir>/css/`` recursively and return one big CSS string.

    :param static_dir: path to the project's ``app/static`` directory
    :return: concatenated CSS, with a banner comment between each file.
             ``@import`` statements that point at sibling files are
             stripped (their content is already in the bundle).
             Empty string if the ``css/`` directory is missing or empty.
    """
    css_root = Path(static_dir) / "css"
    if not css_root.is_dir():
        return ""

    # rglob('*.css') in deterministic (sorted) order — important because
    # the cascade depends on the order rules appear in the final stylesheet.
    css_files = sorted(p for p in css_root.rglob("*.css") if p.is_file())

    chunks: list[str] = []
    for path in css_files:
        rel = path.relative_to(css_root).as_posix()
        chunks.append(_FILE_SEPARATOR_FMT.format(rel=rel))
        try:
            chunks.append(_strip_imports(path.read_text(encoding="utf-8")))
        except OSError:
            # Skip unreadable files rather than crashing the whole app.
            # A missing CSS file is far less damaging than a hard 500.
            continue

    return "".join(chunks)


__all__ = ["collect_css"]
