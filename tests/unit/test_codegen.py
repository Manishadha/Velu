from services.agents.codegen import handle


def test_codegen_python_hello():
    out = handle("codegen", {"lang": "python", "spec": "CLI greeter"})
    assert out["ok"] is True
    art = out["artifact"]
    assert art["language"] == "python"
    assert "hello from codegen: CLI greeter" in art["code"]


def test_codegen_rejects_unsupported_lang():
    out = handle("codegen", {"lang": "haskell", "spec": "x"})
    assert out["ok"] is False
    assert "unsupported lang" in out["error"]
