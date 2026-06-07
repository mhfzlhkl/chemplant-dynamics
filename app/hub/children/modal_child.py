# app/hub/children/modal_child.py

"""Child that refreshes open controller modals and adapts modal writes.

The existing controller modals (``app/pid/<case>/controller_modal.py``)
expect a store object with a LocalStore-compatible API:

::

    store.get(key, default) -> float
    store.set(key, value)   -> None
    store.all()             -> dict[str, float]

The v2 hub keeps a single canonical snapshot. To plug existing
modals in **without modifying them**, this module exposes
:class:`HubStoreAdapter` — a tiny LocalStore look-alike whose:

- ``get`` reads from the hub snapshot.
- ``set`` calls ``SignalHub.request_write`` (so SP/OP edits route
  via the canonical bidirectional path).
- ``all`` returns a copy of the snapshot.

The :class:`ModalChild` itself just walks the open modals once
per tick and calls their existing ``refresh_modal_values`` —
identical contract to legacy ``BaseLiveFlusher._refresh_open_modals``.

Local **control**:

- ``modal.control.commit(modal_key, value)`` — one-line edit commit
  that delegates to ``hub.request_write``. Used by the v2 page when
  it wires its own buttons (the existing modal classes already use
  ``store.set`` internally, which the adapter routes the same way).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping

from app.hub.local_store import LocalStore
from app.hub.signal_hub import SignalHub, TickMeta


logger = logging.getLogger(__name__)


class HubStoreAdapter(LocalStore):
    """LocalStore-compatible facade over :class:`SignalHub`.

    Drop-in replacement for ``app.pid._shared.local_store.LocalStore``
    and the legacy ``BaseBridgeStore`` — every existing modal class
    that takes a ``store`` argument works unchanged with this adapter.

    Inheriting from :class:`LocalStore` is intentional: the modal
    constructors declare ``store: LocalStore``, and the two value
    sources (``LocalStore`` for pure-UI cases, ``HubStoreAdapter`` for
    engine-connected cases) are meant to be interchangeable. We do
    not call ``LocalStore.__init__`` because the two have different
    constructors (``Dict[str, float]`` vs ``SignalHub``); the
    override below keeps the adapter's own init signature.
    """

    def __init__(self, hub: SignalHub) -> None:
        self._hub = hub

    def get(self, key: str, default: float = 0.0) -> float:
        return self._hub.get(key, default)

    def set(self, key: str, value: float) -> None:
        self._hub.request_write(key, value)

    def all(self) -> Dict[str, float]:
        return dict(self._hub.snapshot())


class _ModalChildControl:
    """Local control surface for modal-side actions."""

    def __init__(self, owner: 'ModalChild') -> None:
        self._owner = owner

    def commit(self, modal_key: str, value: float) -> None:
        """One-line write commit — same path the modal's
        ``_apply_numeric_value`` already takes via the adapter.
        """
        self._owner._hub.request_write(modal_key, value)

    def refresh_now(self) -> None:
        """Force-refresh every open modal (used by the page after
        a reset or scenario change to repaint inputs immediately).
        """
        self._owner._refresh(force=True)


class ModalChild:
    """Subscriber that refreshes open controller modals each tick."""

    def __init__(
        self,
        hub: SignalHub,
        modals: Mapping[str, Any] | None = None,
    ) -> None:
        self._hub = hub
        # tag_lower / svg_id → modal instance. We deliberately accept
        # the same dict the legacy ``html_element.controller_modals``
        # exposes, so the v2 page can drop the existing modal set in
        # without a rebuild.
        self._modals: Dict[str, Any] = dict(modals or {})
        self._control = _ModalChildControl(self)
        self._unsubscribe: Any = None
        self._last_reset_counter: int = 0

    # ---------------------------------------------------------------
    # Public
    # ---------------------------------------------------------------

    @property
    def control(self) -> _ModalChildControl:
        return self._control

    @property
    def modals(self) -> Mapping[str, Any]:
        return self._modals

    def register(self, key: str, modal: Any) -> None:
        """Add a modal to the dispatch table (key is typically
        the SVG controller id, e.g. ``'tic-100'``).
        """
        self._modals[key] = modal

    def register_all(self, modals: Mapping[str, Any]) -> None:
        for key, modal in modals.items():
            self.register(key, modal)

    def attach(self) -> None:
        if self._unsubscribe is None:
            self._unsubscribe = self._hub.subscribe(self)

    def detach(self) -> None:
        unsubscribe = self._unsubscribe
        self._unsubscribe = None
        if unsubscribe is not None:
            try:
                unsubscribe()
            except Exception:
                pass

    # ---------------------------------------------------------------
    # Subscriber protocol
    # ---------------------------------------------------------------

    def on_tick(
        self,
        delta_keys: frozenset[str],
        snapshot: Mapping[str, float],
        meta: TickMeta,
    ) -> None:
        # One-tick suppress on reset — same protocol as the legacy
        # stack: the modal checks ``_suppress_input_push`` and skips
        # writing to its inputs.
        suppress_inputs = meta.reset_counter != self._last_reset_counter
        if suppress_inputs:
            self._last_reset_counter = meta.reset_counter

        # Avoid useless refreshes when no data changed. The faceplate's
        # input mirror lives in :class:`FaceplateChild`; this child
        # only services the modal dialog inputs.
        if not delta_keys and not suppress_inputs:
            return

        self._refresh(force=False, suppress_inputs=suppress_inputs)

    # ---------------------------------------------------------------
    # Internal
    # ---------------------------------------------------------------

    def _refresh(
        self,
        *,
        force: bool = False,
        suppress_inputs: bool = False,
    ) -> None:
        for key, modal in self._modals.items():
            try:
                is_open = bool(getattr(modal, 'dialog_is_open', False))
            except Exception:
                is_open = False
            if not is_open and not force:
                continue

            if suppress_inputs:
                try:
                    setattr(modal, '_suppress_input_push', True)
                except Exception:
                    pass

            try:
                refresh = getattr(modal, 'refresh_modal_values', None)
                if callable(refresh):
                    refresh(force_op_refresh=False, force_sp_refresh=False)
            except Exception:
                logger.exception(
                    'ModalChild: refresh_modal_values failed for %s', key,
                )

            if suppress_inputs:
                try:
                    setattr(modal, '_suppress_input_push', False)
                except Exception:
                    pass


__all__ = ['HubStoreAdapter', 'ModalChild']
