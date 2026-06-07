# tools/export_static.py

"""Render the home page to a static ``docs/index.html`` for
GitHub Pages.

The home page (``app/pages/home_page.py``) is already pure
static: no engine, no per-tick timers, no NiceGUI client-server
round trips. The whole page is built from a fixed set of
``ui.label`` / ``ui.image`` / ``ui.card`` calls that resolve to
plain HTML once NiceGUI serializes them. This module
materializes the rendered HTML to a file so the same source
drives both the NiceGUI local / on_air server AND a static
landing page on GitHub Pages.

How it works
------------

1. We import :mod:`app.assets` (for the inlined CSS bundle) and
   :mod:`app.pages.home_page` (for the page builder).
2. We monkey-patch a small set of :mod:`nicegui.ui` entry points
   to record their calls into a ``StaticRecorder`` instead of
   the live DOM. The recorder captures elements in the order
   they're pushed, with classes / props / text content.
3. We invoke the home page's ``build_home_page()`` in a
   dedicated ``ui.page('/__static_home__')`` context, render
   it, then serialize the recorder's output to HTML.
4. The output is combined with the inlined CSS bundle and the
   Google Fonts link (same as the live page) to produce a
   single self-contained ``docs/index.html``.
5. The two case-card links (``/control-panel/sthr`` and
   ``/control-panel/biodiesel``) are rewritten to point at the
   on_air tunnel URL — read from the ``ON_AIR_PROD_URL`` env
   var. When unset, the links fall back to a relative path so
   the page is still browsable on GitHub Pages without a
   backend.
6. Static assets referenced as ``/static/assets/...`` are
   copied into ``docs/assets/...`` so GitHub Pages can serve
   them directly.

Why a monkey-patch and not a headless browser?
----------------------------------------------

NiceGUI's element tree is built up via Python calls to
``ui.label(...)``, ``ui.image(...)`` etc. There's no DOM to
serialize until the server runs and the client connects. A
headless browser would work but adds ~300 MB of dependencies
(Chromium / Playwright) to a small deploy script.

NiceGUI 3.x exposes a low-level element model on every
``ui.<component>`` (the element's ``_props`` / ``_classes`` /
``_text`` etc.). We don't need a headless DOM — we just need to
walk the elements the page builder creates. The recorder below
does that by intercepting the same Python calls NiceGUI uses
internally.

Limitations
-----------

* Only the home page is exported. The control-panel pages
  need a live engine and cannot be static.
* NiceGUI's ``ui.expansion`` renders into a Quasar ``<q-expansion-item>``
  wrapper; we render its inner content statically (the
  expansion is open by default in the static export so the
  case cards are immediately visible).
* The two ``ui.link`` targets are rewritten to absolute URLs
  via the ``ON_AIR_PROD_URL`` env var. If unset, the links
  point at ``/control-panel/<case>`` and GitHub Pages will
  404 — users should set the env var in the deploy workflow.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


# Project root (this file is at app_root/tools/).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_ASSETS_SRC = PROJECT_ROOT / 'app' / 'static' / 'assets'
STATIC_ASSETS_DST_NAME = 'assets'
DOCS_DIR = PROJECT_ROOT / 'docs'


# On-air tunnel URL, e.g. ``https://on-air.nicegui.io/<token>``.
# When set, the case-card links are rewritten to point at the
# live control panel under this base. When unset, the links
# point at the relative path (which 404s on GitHub Pages
# without a backend, but the rest of the page is still valid).
ON_AIR_PROD_URL = os.environ.get('ON_AIR_PROD_URL', '').rstrip('/')


@dataclass
class RecordedNode:
    """One captured ``ui.<element>`` call."""
    tag: str
    classes: list[str] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)
    text: str = ''
    attrs: dict[str, str] = field(default_factory=dict)
    children: list['RecordedNode'] = field(default_factory=list)
    void: bool = False  # True for img, br, etc.
    self_closing: bool = False  # children rendered as attributes


class StaticRecorder:
    """Tiny element tree that captures ``ui.<element>`` calls.

    The home page's render functions use a small subset of
    NiceGUI primitives:

    * ``ui.label(text)`` → element with class + text
    * ``ui.image(src)`` → element with src + classes
    * ``ui.button(...)`` → element with classes + on_click (ignored)
    * ``ui.link(target, ...)`` → element with href + on_click (ignored)
    * ``ui.card()`` / ``ui.column()`` / ``ui.row()`` → containers

    We provide stand-in implementations that produce HTML
    strings instead of building a real DOM.

    The recorder is *not* a complete NiceGUI replacement — it
    only handles the small vocabulary the home page uses. The
    rest of the page (CSS, fonts, page header) is rendered by
    the existing shell helpers.
    """

    def __init__(self) -> None:
        self.root = RecordedNode(tag='div', classes=['app-body'])
        # Stack of currently-open containers.
        self._stack: list[RecordedNode] = [self.root]
        # Per-case link rewrite map: ``/control-panel/<case>`` →
        # ``<ON_AIR_PROD_URL>/control-panel/<case>``.
        self._link_rewrites: dict[str, str] = {
            '/control-panel/sthr': (
                f'{ON_AIR_PROD_URL}/control-panel/sthr'
                if ON_AIR_PROD_URL else '/control-panel/sthr'
            ),
            '/control-panel/biodiesel': (
                f'{ON_AIR_PROD_URL}/control-panel/biodiesel'
                if ON_AIR_PROD_URL else '/control-panel/biodiesel'
            ),
        }

    def _current(self) -> RecordedNode:
        return self._stack[-1]

    def _push(self, node: RecordedNode) -> None:
        self._current().children.append(node)
        self._stack.append(node)

    def _pop(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop()

    # Public API mirrors the home page's element usage.

    def _make_proxy(
        self,
        node: RecordedNode,
        *,
        push: bool = True,
    ) -> '_ElementProxy':
        """Wrap a node in a chainable proxy.

        When ``push`` is True (default for containers that
        support the ``with`` pattern), the node is pushed onto
        the recorder's stack on ``__enter__``. The constructor
        does NOT push — only ``__enter__`` does. This matches
        NiceGUI's actual semantics: a ``ui.column()`` is added
        to the current parent at construction, but is *only*
        made the current parent for further ``ui.<elem>(...)``
        calls when entered via ``with``.

        Pass ``push=False`` for leaf elements (``label``,
        ``image``, ``separator``) that don't have children.
        """
        return _ElementProxy(self, node, push_on_enter=push)

    def label(self, text: str, **kwargs: Any) -> '_ElementProxy':
        classes = _split_classes(kwargs.get('classes'))
        node = RecordedNode(
            tag='div',
            classes=['q-label', *classes],
            text=str(text),
        )
        return self._make_proxy(node, push=False)

    def image(self, src: str, **kwargs: Any) -> '_ElementProxy':
        classes = _split_classes(kwargs.get('classes'))
        rewritten = _rewrite_static_url(str(src), self._link_rewrites)
        node = RecordedNode(
            tag='img',
            classes=classes,
            attrs={'src': rewritten, 'alt': ''},
            void=True,
        )
        return self._make_proxy(node, push=False)

    def link(
        self,
        target: str = '',
        *,
        new_tab: bool = False,
    ) -> '_ElementProxy':
        rewritten = _rewrite_static_url(str(target), self._link_rewrites)
        node = RecordedNode(
            tag='a',
            attrs={
                'href': rewritten,
                'target': '_blank' if new_tab else '_self',
                'rel': 'noopener noreferrer' if new_tab else '',
            },
        )
        return self._make_proxy(node, push=False)

    def button(
        self,
        text: str,
        *,
        icon: Optional[str] = None,
        on_click: Optional[Callable[..., Any]] = None,
    ) -> '_ElementProxy':
        node = RecordedNode(
            tag='button',
            classes=['q-btn'],
            attrs={'type': 'button'},
            text=str(text or ''),
        )
        return self._make_proxy(node, push=False)

    def card(self) -> '_ElementProxy':
        node = RecordedNode(tag='div', classes=['q-card'])
        return self._make_proxy(node, push=True)

    def column(self) -> '_ElementProxy':
        node = RecordedNode(tag='div', classes=['q-column', 'col'])
        return self._make_proxy(node, push=True)

    def row(self) -> '_ElementProxy':
        node = RecordedNode(tag='div', classes=['q-row', 'row'])
        return self._make_proxy(node, push=True)

    def separator(self) -> '_ElementProxy':
        node = RecordedNode(tag='hr', classes=['q-separator'], void=True)
        return self._make_proxy(node, push=False)

    def element(self, tag: str) -> '_ElementProxy':
        node = RecordedNode(tag=str(tag))
        return self._make_proxy(node, push=True)

    def expansion(
        self,
        title: str,
        *,
        value: bool = False,
    ) -> '_ElementProxy':
        node = RecordedNode(
            tag='section',
            classes=['q-expansion-item', 'q-expansion-item--expanded'],
        )
        title_node = RecordedNode(
            tag='h3',
            classes=['q-expansion-item__title'],
            text=str(title),
        )
        node.children.append(title_node)
        return self._make_proxy(node, push=True)

    # NiceGUI top-level helpers (used by shell).

    def add_head_html(self, html: str) -> None:
        """Append to the page's ``<head>``. Stored in a
        collector so the template can write them at the right
        spot.
        """
        # The recorder doesn't model a real <head>; the
        # exporter script reads the helper's return value via
        # the ``_head_html`` attribute.
        self._head_html = getattr(self, '_head_html', '') + html

    def add_body_html(self, html: str) -> None:
        self._body_html = getattr(self, '_body_html', '') + html

    def notify(self, *args: Any, **kwargs: Any) -> None:
        # Static export has no notifications; drop them.
        return None

    # CSS class application — NiceGUI exposes .classes() and
    # .props() as instance methods on each element. The
    # recorder doesn't model them; the home page only uses
    # .classes() at construction time (via positional ``.classes``
    # kwarg). For runtime class mutations we'd need a
    # post-render scan; not needed for the home page.

    def page(self, path: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
        """Stub of :func:`nicegui.ui.page` — used by the
        home page's ``@ui.page('/')`` decorator. The exporter
        calls the decorated function directly.
        """
        def decorator(fn: Callable[..., None]) -> Callable[..., None]:
            return fn
        return decorator

    def navigate(self, *args: Any, **kwargs: Any) -> None:
        return None

    def run_javascript(self, *args: Any, **kwargs: Any) -> None:
        return None

    def timer(self, *args: Any, **kwargs: Any) -> None:
        return None


# ── Element proxy ────────────────────────────────────────────────
#
# Every ``ui.<element>(...)`` call returns a chainable +
# context-manageable object. The proxy implements both contracts
# by mutating the underlying :class:`RecordedNode` and pushing /
# popping the recorder's stack on ``__enter__`` / ``__exit__``.

class _ElementProxy:
    """Stand-in for a NiceGUI element that records its API usage.

    Supports the chainable surface used by the home page and
    the rest of the project's render helpers:

    * ``el.classes(value)`` / ``el.classes(add=..., remove=...)``
    * ``el.props(value)``
    * ``el.style(value)``
    * ``el.tooltip(value)``
    * ``el.on(event, handler)`` (dropped — the static export
      has no event handlers)
    * ``with el:`` — pushes the node onto the recorder's stack
      on enter, pops on exit. The ``__enter__`` is a no-op when
      the recorder has already pushed (which is the case for
      every ``ui.<element>(...)`` call) — NiceGUI elements
      auto-register on the current parent at construction time.

    Attribute access on anything else is forwarded to the
    underlying :class:`RecordedNode` so unknown internal reads
    don't crash the export.
    """

    def __init__(
        self,
        recorder: StaticRecorder,
        node: RecordedNode,
        *,
        push_on_enter: bool = False,
    ) -> None:
        self._recorder = recorder
        self._node = node
        # When True, ``__enter__`` pushes the node onto the
        # recorder's stack and ``__exit__`` pops it. This is the
        # standard container pattern (``with ui.column(): ...``).
        # When False the proxy is a leaf (label / image / ...) and
        # ``__enter__`` / ``__exit__`` are no-ops.
        self._push_on_enter = push_on_enter
        self._did_push = False

    # Context-manager protocol.
    def __enter__(self) -> '_ElementProxy':
        if self._push_on_enter:
            self._recorder._push(self._node)
            self._did_push = True
        return self

    def __exit__(self, *exc_info: Any) -> None:
        if self._did_push:
            self._recorder._pop()
            self._did_push = False

    # Chainable API.
    def classes(
        self,
        value: str = '',
        *,
        add: str = '',
        remove: str = '',
    ) -> '_ElementProxy':
        if value:
            self._node.classes.extend(_split_classes(value))
        if add:
            self._node.classes.extend(_split_classes(add))
        if remove:
            for cls in _split_classes(remove):
                if cls in self._node.classes:
                    self._node.classes.remove(cls)
        return self

    def props(self, value: str = '') -> '_ElementProxy':
        for key, val in _parse_props(value):
            self._node.props[key] = val
        return self

    def style(self, value: str = '') -> '_ElementProxy':
        self._node.attrs['style'] = (
            self._node.attrs.get('style', '') + ' ' + value
        ).strip()
        return self

    def tooltip(self, value: str) -> '_ElementProxy':
        # Static export has no tooltips; store the text on the
        # node's ``title`` attribute for browser-native fallback.
        self._node.attrs['title'] = str(value)
        return self

    def on(self, event: str, handler: Any) -> '_ElementProxy':
        # Static export has no event handlers; the call is
        # recorded (so a debug-mode sanity check could find
        # handlers) but nothing is emitted in the output.
        return self

    def set_text(self, text: str) -> '_ElementProxy':
        self._node.text = str(text)
        return self

    def set_visibility(self, visible: bool) -> '_ElementProxy':
        if not visible:
            self._node.attrs['hidden'] = 'true'
        else:
            self._node.attrs.pop('hidden', None)
        return self

    def update(self) -> '_ElementProxy':
        return self

    # Forward attribute access for unknown internals — e.g.
    # ``el.default_slot`` (used by the perf monitor to inject
    # children) reads as ``None`` and is harmless.
    def __getattr__(self, name: str) -> Any:
        return getattr(self._node, name, None)


# ── Helpers ──


def _split_classes(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [c for c in value.split() if c]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            out.extend(_split_classes(item))
        return out
    return []


def _parse_props(value: str) -> Iterable[tuple[str, str]]:
    """Parse NiceGUI's props string (``'flat no-caps align=left'``)
    into ``(key, value)`` pairs. Bare words are treated as
    boolean true.
    """
    if not value:
        return []
    out: list[tuple[str, str]] = []
    for token in value.split():
        if '=' in token:
            key, _, val = token.partition('=')
            out.append((key.strip(), val.strip().strip('"\'')))
        else:
            out.append((token.strip(), 'true'))
    return out


def _rewrite_static_url(url: str, link_rewrites: dict[str, str]) -> str:
    """Rewrite ``/static/...`` to ``assets/...`` and case-card
    links to the on_air tunnel URL.
    """
    if url in link_rewrites:
        return link_rewrites[url]
    if url.startswith('/static/'):
        return url[len('/static/'):]
    return url


def render_node(node: RecordedNode) -> str:
    """Serialize a :class:`RecordedNode` to HTML."""
    classes_attr = ''
    if node.classes:
        classes_attr = f' class="{" ".join(node.classes)}"'
    attrs = ''.join(
        f' {k}="{_escape(v)}"' for k, v in node.attrs.items() if v
    )
    if node.props:
        # Render props as inline style for the few that look like
        # CSS, otherwise as a data attribute for downstream JS.
        style_parts: list[str] = []
        for k, v in node.props.items():
            if v == 'true':
                style_parts.append(k)
            else:
                style_parts.append(f'{k}: {v}')
        attrs += f' style="{"; ".join(style_parts)}"'
    if node.void or node.self_closing:
        return f'<{node.tag}{classes_attr}{attrs} />'
    if node.text and not node.children:
        return f'<{node.tag}{classes_attr}{attrs}>{_escape(node.text)}</{node.tag}>'
    children_html = ''.join(render_node(child) for child in node.children)
    return f'<{node.tag}{classes_attr}{attrs}>{children_html}</{node.tag}>'


def _escape(s: str) -> str:
    return (
        s.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


# ── Entry point ──


def main(argv: list[str] | None = None) -> int:
    """Render the home page to ``docs/index.html``.

    Returns 0 on success, 1 on error.
    """
    # Ensure project root is on sys.path so ``app.*`` imports resolve.
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    # Build the inlined CSS bundle.
    from app.assets import collect_css
    from app.config import STATIC_DIR
    inlined_css = collect_css(STATIC_DIR)

    # Build the static recorder.
    recorder = StaticRecorder()

    # Monkey-patch ``nicegui.ui`` for the duration of the export.
    # Ensure the module is loaded in sys.modules before we swap attributes.
    import nicegui.ui  # noqa: F401
    real_module = sys.modules['nicegui.ui']
    saved_attrs: dict[str, Any] = {}
    for attr in dir(recorder):
        if attr.startswith('_') or attr in ('root',):
            continue
        if hasattr(real_module, attr):
            saved_attrs[attr] = getattr(real_module, attr)
            setattr(real_module, attr, getattr(recorder, attr))

    try:
        # Importing the home page module runs the @ui.page
        # decorator, which records a binding in nicegui's
        # registry but does not render. We then call the
        # underlying function directly.
        from app.pages import home_page  # noqa: F401
        # Build the page into the recorder.
        try:
            home_page.build_home_page()
        except Exception as exc:
            print(f'[export_static] build_home_page failed: {exc}')
            return 1
    finally:
        # Restore the original nicegui.ui attributes.
        for attr, val in saved_attrs.items():
            setattr(real_module, attr, val)

    # Serialize the recorder tree to HTML.
    body_html = ''.join(render_node(child) for child in recorder.root.children)

    # Compose the full HTML page.
    _font_url = (
        'https://fonts.googleapis.com/css2'
        '?family=Material+Symbols+Outlined'
        ':opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200'
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ChemPlant Dynamics</title>
<style>{inlined_css}</style>
<link rel="stylesheet" href="{_font_url}">
</head>
<body class="app-body home-page">
{body_html}
</body>
</html>
"""

    # Write ``docs/``.
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / 'index.html').write_text(html, encoding='utf-8')
    print(f'[export_static] wrote {DOCS_DIR / "index.html"}')

    # Copy static assets (logos, icons).
    if STATIC_ASSETS_SRC.is_dir():
        target = DOCS_DIR / STATIC_ASSETS_DST_NAME
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(STATIC_ASSETS_SRC, target)
        print(f'[export_static] copied assets to {target}')
    else:
        print(
            f'[export_static] WARNING: {STATIC_ASSETS_SRC} not found; '
            'icons may 404 in the static export',
        )

    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))


__all__ = ['main', 'StaticRecorder', 'render_node']
