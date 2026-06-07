# app/hub/children/modals/placement.py

"""Manual-anchor placement for controller modals.

Aligns the dialog to a viewport corner (top-left, top-right,
bottom-left, bottom-right) so it never overlaps the originating
controller element on the P&ID canvas.

Uses Quasar's flexbox ``.q-dialog__inner`` alignment instead of
fighting it with ``position: fixed`` on the card. This avoids
containing-context problems when Quasar's show-transition applies
a ``transform`` to the dialog ancestors.
"""

from __future__ import annotations

from typing import Any, Dict

from nicegui import ui


# Per-controller manual anchor map.
# Inverted placement rule:
#   - Controllers at the *top* of the canvas → modal at ``bottom-left``.
#   - Controllers at the *bottom* of the canvas → modal at ``top-left``.
#   - Unknown tags fall back to ``bottom-left``.
MANUAL_ANCHORS: Dict[str, str] = {
    'TIC-100': 'bottom-left',
    'FI-100':  'top-left',
    'FI-101':  'bottom-left',
    'TI-100':  'bottom-left',
    'LI-100':  'bottom-left',
    'FI-102':  'bottom-left',
    'VP-100':  'bottom-left',
    'LIC-100':  'bottom-left',
    'FIC-100':  'top-left',
    'FIC-101':  'top-left',
    'FIC-102':  'top-left',
    'TI-101':   'top-left',
    'TI-102':   'top-left',
    'TI-103':   'bottom-left',
    'TI-104':   'bottom-left',
    'PI-100':   'bottom-left',
    'LV-100':   'bottom-left',
    'TV-100':   'bottom-left',
    'FV-100':   'bottom-left',
    'FV-101':   'bottom-left',
    'FV-102':   'bottom-left',
}


class _SmartPlacementMixin:
    """Mixin that pins the dialog card to a viewport corner.

    Requires the host class to expose ``self.dialog_card``,
    ``self._dialog_uid``, and ``self.controller_tag``.

    Inline ``!important`` styles outrank Quasar's utility classes,
    which is why the earlier ``@layer pages`` approach silently
    failed (layered declarations lose to unlayered ones regardless
    of specificity).
    """

    dialog: Any
    dialog_card: Any
    controller_tag: str
    _dialog_uid: str

    def _resolve_anchor(self) -> str:
        return MANUAL_ANCHORS.get(self.controller_tag, 'bottom-left')

    def _apply_manual_position_js(self) -> None:
        """Align ``.q-dialog__inner`` to the manual-anchor corner.

        Uses flexbox alignment (``justify-content`` / ``align-items``)
        on the Quasar inner so the card is inset from the viewport
        edge without fighting Quasar's own positioning.
        """
        anchor = self._resolve_anchor()
        inset = 16
        card_id = getattr(self.dialog_card, 'id', None) or ''
        js = f'''
        (() => {{
            const cardId = {card_id!r};
            const anchor = {anchor!r};
            const inset = {inset};

            function place() {{
                const card = cardId
                    ? document.getElementById(cardId)
                    : document.querySelector('.tic-param-dialog-card');
                if (!card) {{
                    console.log('[anchor] card not found, cardId=', cardId);
                    return false;
                }}
                console.log('[anchor] placing card', cardId, 'at', anchor);

                const inner = card.classList.contains('q-dialog__inner')
                    ? card
                    : card.closest('.q-dialog__inner');
                if (!inner) {{
                    console.log('[anchor] inner not found for card', cardId);
                    return false;
                }}

                inner.style.setProperty('padding', inset + 'px', 'important');

                if (anchor === 'top-left') {{
                    inner.style.setProperty('justify-content', 'flex-start', 'important');
                    inner.style.setProperty('align-items',     'flex-start', 'important');
                }} else if (anchor === 'top-right') {{
                    inner.style.setProperty('justify-content', 'flex-end',   'important');
                    inner.style.setProperty('align-items',     'flex-start', 'important');
                }} else if (anchor === 'bottom-left') {{
                    inner.style.setProperty('justify-content', 'flex-start', 'important');
                    inner.style.setProperty('align-items',     'flex-end',   'important');
                }} else {{
                    inner.style.setProperty('justify-content', 'flex-end',   'important');
                    inner.style.setProperty('align-items',     'flex-end',   'important');
                }}

                card.style.setProperty('margin', '0', 'important');
                card.style.setProperty('align-self', 'auto', 'important');
                card.style.removeProperty('position');
                card.style.removeProperty('top');
                card.style.removeProperty('left');
                card.style.removeProperty('right');
                card.style.removeProperty('bottom');

                card.dataset.ticAnchor = anchor;
                return true;
            }}

            function tryPlace(attempts) {{
                if (place()) return;
                if (attempts > 300) return;
                requestAnimationFrame(() => tryPlace(attempts + 1));
            }}
            requestAnimationFrame(() => requestAnimationFrame(() => tryPlace(0)));
        }})();
        '''
        try:
            ui.run_javascript(js)
        except Exception:
            pass


__all__ = ['MANUAL_ANCHORS', '_SmartPlacementMixin']
