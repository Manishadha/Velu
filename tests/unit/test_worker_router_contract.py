# tests/unit/test_worker_router_contract.py
from __future__ import annotations

import types

import pytest

import services.worker.main as worker_mod


def _monkey_route(monkeypatch, fn):
    """
    Replace orchestrator.router_client.route with our stub.
    """
    stub_mod = types.SimpleNamespace(route=fn)
    monkeypatch.setitem(worker_mod.__dict__, "route", stub_mod.route)
    # also ensure the name used inside worker_mod resolves to this route
    monkeypatch.setattr("services.worker.main.route", stub_mod.route, raising=True)


def test_dict_signature_supported(monkeypatch):
    # route expects a single dict argument
    def route_single_arg(arg):
        assert isinstance(arg, dict)
        assert arg["task"] == "plan"
        assert arg["payload"] == {"idea": "x"}
        return {"ok": True, "via": "single"}

    _monkey_route(monkeypatch, route_single_arg)
    rec = {"task": "plan", "payload": {"idea": "x"}}
    out = worker_mod.process_job(rec)
    assert out["ok"] is True
    assert out["via"] == "single"


def test_pair_signature_supported(monkeypatch):
    # route expects (name, payload)
    def route_pair(name, payload):
        assert name == "plan"
        assert payload == {"idea": "y"}
        return {"ok": True, "via": "pair"}

    _monkey_route(monkeypatch, route_pair)
    rec = {"task": "plan", "payload": {"idea": "y"}}
    out = worker_mod.process_job(rec)
    assert out["ok"] is True
    assert out["via"] == "pair"


@pytest.mark.parametrize(
    "raw, expected",
    [
        (b'{"ok": true, "z": 1}', {"ok": True, "z": 1}),  # bytes JSON -> dict
        ("plain text", {"ok": True, "data": "plain text"}),  # str non-JSON -> box
        ('["a", 1]', {"ok": True, "data": ["a", 1]}),  # str JSON list -> box
        (["a", 1], {"ok": True, "data": ["a", 1]}),  # list -> box
    ],
)
def test_normalization(monkeypatch, raw, expected):
    def route_single_arg(arg):
        return raw

    _monkey_route(monkeypatch, route_single_arg)
    rec = {"task": "plan", "payload": {"idea": "z"}}
    out = worker_mod.process_job(rec)
    assert out == expected


def test_raises_original_typeerror_when_both_signatures_fail(monkeypatch):
    # First call (dict) raises TypeError; fallback raises ValueError.
    def route_flaky(*args, **kwargs):
        # Simulate different exceptions depending on call form
        if args and isinstance(args[0], dict) and len(args) == 1:
            raise TypeError("bad signature")
        raise ValueError("other issue")

    _monkey_route(monkeypatch, route_flaky)
    rec = {"task": "plan", "payload": {}}
    with pytest.raises(TypeError) as ei:
        worker_mod.process_job(rec)
    assert "bad signature" in str(ei.value)


def test_passthrough_dict(monkeypatch):
    def route_single_arg(arg):
        return {"ok": True, "nested": {"a": 1}}

    _monkey_route(monkeypatch, route_single_arg)
    rec = {"task": "plan", "payload": {}}
    out = worker_mod.process_job(rec)
    assert out["ok"] is True
    assert out["nested"] == {"a": 1}
