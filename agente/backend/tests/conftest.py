import pytest


@pytest.fixture(autouse=True)
def sin_llm(monkeypatch):
    """Por defecto las pruebas corren sin LLM (regla del Avance 3); test_llm.py lo prende con Ollama simulado."""
    monkeypatch.setenv("LLM_MODELO", "")
