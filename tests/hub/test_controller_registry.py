# tests/hub/test_controller_registry.py

"""Registry indexing & formatting invariants.

These guard the "single source of truth" property — if a future
edit accidentally introduces a duplicate modal_key or a stale
lookup, the assertions here fail.
"""

from __future__ import annotations

import pytest

from app.hub.controller_registry import ControllerRegistry, ControllerSpec


def _make_registry() -> ControllerRegistry:
    return ControllerRegistry([
        ControllerSpec(
            modal_key='pv', engine_tag='STHR.T', svg_id='tic-100',
            unit='°F', decimals=1, role='pv', writable=False,
        ),
        ControllerSpec(
            modal_key='sp', engine_tag='TSP-100.SP', svg_id=None,
            unit='°F', decimals=1, role='sp', writable=True,
        ),
        ControllerSpec(
            modal_key='kc', engine_tag='TC-100.Kc', svg_id=None,
            unit='', decimals=2, role='tuning', writable=True,
        ),
        ControllerSpec(
            modal_key='tic_status', engine_tag=None, svg_id=None,
            unit='', decimals=0, role='status', writable=True,
        ),
        ControllerSpec(
            modal_key='fi102_pv', engine_tag=None, svg_id='fi-102',
            unit='ft³/min', decimals=1, role='pv', writable=False,
            derived_from='fi101_pv',
        ),
    ])


def test_by_modal_key_and_by_engine_tag_round_trip() -> None:
    reg = _make_registry()
    spec = reg.by_modal_key('pv')
    assert spec.engine_tag == 'STHR.T'
    assert reg.by_engine_tag('STHR.T') is spec


def test_by_svg_id_returns_only_specs_with_svg() -> None:
    reg = _make_registry()
    assert reg.by_svg_id('tic-100').modal_key == 'pv'
    assert reg.by_svg_id('fi-102').modal_key == 'fi102_pv'
    # sp has no svg_id — must not appear
    assert reg.by_svg_id('sp') is None


def test_writable_and_status_keys() -> None:
    reg = _make_registry()
    assert set(reg.writable_keys()) == {'sp', 'kc', 'tic_status'}
    assert set(reg.status_keys()) == {'tic_status'}


def test_output_to_pv_and_input_field_to_override() -> None:
    reg = _make_registry()
    # Only specs with engine_tag and role in {pv, op} go into output_to_pv.
    assert dict(reg.output_to_pv()) == {'STHR.T': 'pv'}
    # Only writable specs with an engine_tag go into input_field_to_override.
    assert dict(reg.input_field_to_override()) == {
        'sp': 'TSP-100.SP',
        'kc': 'TC-100.Kc',
    }


def test_derived_pairs_picked_up() -> None:
    reg = _make_registry()
    assert ('fi101_pv', 'fi102_pv') in reg.derived_pairs()


def test_format_rounds_and_appends_unit() -> None:
    reg = _make_registry()
    assert reg.format('pv', 150.0) == '150.0 °F'
    assert reg.format('pv', 150.04) == '150.0 °F'
    assert reg.format('pv', 150.06) == '150.1 °F'
    assert reg.format('kc', 6.1234) == '6.12'
    assert reg.format('pv', None) == '—'


def test_duplicate_modal_key_raises() -> None:
    with pytest.raises(ValueError):
        ControllerRegistry([
            ControllerSpec(modal_key='dup', engine_tag=None, role='pv'),
            ControllerSpec(modal_key='dup', engine_tag=None, role='sp'),
        ])
