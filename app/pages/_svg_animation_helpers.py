# app/pages/_svg_animation_helpers.py

"""Shared JS helpers for toggling P&ID SVG animations and Run-button
state. Used by both ``sthr_page`` and ``biodiesel_page``.

The CSS keyframes inside the P&ID SVG use ``!important`` rules on
``animation-play-state`` so a plain inline ``style.animationPlayState``
cannot override them. The supported pattern is to toggle a wrapper
class (e.g. ``.pid-animation-running``) on the SVG container instead.

Centralising the JS keeps the per-case pages from carrying two
duplicated ``ui.run_javascript`` blobs each.
"""

from __future__ import annotations

from nicegui import ui


_RUN_BTN_ACTIVE_CLASS = 'pid-navbar-run-btn-active'
_RUN_BTN_DISABLED_CLASS = 'pid-navbar-run-btn-disabled'
_ANIMATION_RUNNING_CLASS = 'pid-animation-running'


def toggle_svg_animations(wrapper_class: str, *, play: bool) -> None:
    """Add or remove the ``pid-animation-running`` class on every SVG
    wrapper matching ``wrapper_class``.

    ``wrapper_class`` is the case-specific wrapper class (e.g.
    ``'sthr-pid-svg'`` or ``'biodiesel-pid-svg'``). Setting ``play``
    to ``True`` adds the class (resumes animations); ``False`` removes
    it (pauses).
    """
    play_literal = 'true' if play else 'false'
    ui.run_javascript(f'''
        (function() {{
            const wrappers = document.querySelectorAll('.{wrapper_class}');
            wrappers.forEach(function(wrap) {{
                if ({play_literal}) {{
                    wrap.classList.add('{_ANIMATION_RUNNING_CLASS}');
                }} else {{
                    wrap.classList.remove('{_ANIMATION_RUNNING_CLASS}');
                }}
            }});
        }})();
    ''')


def toggle_run_button(*, active: bool) -> None:
    """Add or remove the active CSS class on every PID-navbar Run button.

    There can be at most one Run button on a page, but we still use
    ``querySelectorAll`` so a hot-reload that mounts the navbar twice
    does not leave one button out of sync.
    """
    active_literal = 'true' if active else 'false'
    ui.run_javascript(f'''
        (function() {{
            const btns = document.querySelectorAll('.pid-navbar-run-btn');
            btns.forEach(function(btn) {{
                if ({active_literal}) {{
                    btn.classList.add('{_RUN_BTN_ACTIVE_CLASS}');
                }} else {{
                    btn.classList.remove('{_RUN_BTN_ACTIVE_CLASS}');
                }}
            }});
        }})();
    ''')


def set_run_button_disabled(*, disabled: bool, reason: str = '') -> None:
    """Force the PID-navbar Run button into a disabled / enabled state.

    Used by the control-panel page to block ``Run`` once the simulation
    has reached ``time_end`` (see :func:`_is_simulation_finished` in
    ``control_panel_page.py``). The reverse — re-enabling — is called
    after Reset or after the user extends End Time so the worker has
    new ground to cover.

    Why a JS shim instead of mutating the Python ``ui.button`` ref?
    The Run button is built once by ``pid_navbar.render_simulation_control_buttons``
    and the page handler doesn't currently capture a reference to it
    (the button is fire-and-forget). Routing through a class selector
    keeps the navbar API additive — no signature change needed.

    What we set, and why each one:

    * ``disabled`` attribute → Quasar's ``q-btn`` reads this and stops
      firing ``click`` events. This is the actual block.
    * ``aria-disabled="true"`` → screen-reader signal, mirrors the
      attribute for assistive tech that doesn't trust ``disabled`` on
      a custom button element.
    * ``.pid-navbar-run-btn-disabled`` class → visual hook so the CSS
      can dim the button and switch the cursor without overlapping
      the existing ``-active`` styling.
    * ``title`` attribute → native browser tooltip describing WHY the
      button is blocked, so a hover gives the user an actionable hint
      ("extend End Time or Reset") without us mounting a separate
      ``q-tooltip`` for every state change.
    """
    disabled_literal = 'true' if disabled else 'false'
    # JSON-encode the reason so quotes / newlines in the message don't
    # break the JS literal. Empty string when there is no reason.
    import json
    reason_literal = json.dumps(reason or '')
    ui.run_javascript(f'''
        (function() {{
            const btns = document.querySelectorAll('.pid-navbar-run-btn');
            btns.forEach(function(btn) {{
                if ({disabled_literal}) {{
                    btn.setAttribute('disabled', 'disabled');
                    btn.setAttribute('aria-disabled', 'true');
                    btn.classList.add('{_RUN_BTN_DISABLED_CLASS}');
                    if ({reason_literal}) {{
                        btn.setAttribute('title', {reason_literal});
                    }}
                }} else {{
                    btn.removeAttribute('disabled');
                    btn.removeAttribute('aria-disabled');
                    btn.classList.remove('{_RUN_BTN_DISABLED_CLASS}');
                    btn.removeAttribute('title');
                }}
            }});
        }})();
    ''')


__all__ = [
    'toggle_svg_animations',
    'toggle_run_button',
    'set_run_button_disabled',
]
