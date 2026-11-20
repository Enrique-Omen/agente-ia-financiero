"""Pruebas del escalón 3 (LLM local): sin red, Ollama simulado. Caído, JSON inválido, acción o campos fuera del contrato,
símbolo o fecha distintos → error registrado y decide la regla del Avance 3 («respaldo»). Una propuesta válida sí manda."""
import http.client, json, threading, urllib.error
import pytest

from app import llm
from tests.test_ciclo import FECHAS, H, Agente


@pytest.fixture
def agente(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODELO", "qwen2.5:1.5b")
    a = Agente(monkeypatch, str(tmp_path / "agente.db"))
    a.c.post("/iniciar", headers=H)
    return a


def ollama(monkeypatch, responde):
    """responde(datos) → dict con la propuesta, texto crudo o una excepción."""
    def falso(url, cuerpo, timeout):
        if url.endswith("/api/version"):
            return {"version": "0.0-prueba"}
        d = json.loads(cuerpo["messages"][1]["content"])
        assert url.endswith("/api/chat") and timeout > 0
        assert cuerpo["format"]["properties"]["accion"]["enum"] == d["acciones_permitidas"]   # Ollama solo puede elegir esas
        r = responde(d)
        if isinstance(r, Exception):
            raise r
        return {"message": {"content": r if isinstance(r, (str, type(None), int)) else json.dumps(r)}}
    monkeypatch.setattr(llm, "pedir_json", falso)


def ok(d, accion, justificacion="x"):
    return {"accion": accion, "simbolo": d["simbolo"], "fecha_vela": d["fecha_vela"], "justificacion": justificacion}


def ultima(agente):
    return agente.sql("SELECT accion, motivo FROM decisiones ORDER BY fecha DESC LIMIT 1")[0]


@pytest.mark.parametrize("responde, error", [
    (lambda d: urllib.error.URLError("Connection refused"), "Ollama no respondió"),
    (lambda d: TimeoutError("timed out"), "Ollama no respondió"),
    (lambda d: http.client.IncompleteRead(b"{"), "Ollama no respondió"),            # se corta a media respuesta
    (lambda d: "esto no es JSON", "JSON inválido"),
    (lambda d: None, "no es texto"),
    (lambda d: ok(d, "apalancar"), "JSON inválido"),
    (lambda d: {**ok(d, "comprar"), "perdida_diaria_max": 0.9}, "JSON inválido"),   # no puede colar un cambio de límites
    (lambda d: ok(d, "vender"), "no permitida"),                                    # vender sin posición
    (lambda d: {"accion": "comprar", "simbolo": "ETHUSDT", "fecha_vela": d["fecha_vela"], "justificacion": "x"}, "Propuesta para"),
    (lambda d: {"accion": "comprar", "simbolo": d["simbolo"], "fecha_vela": "2020-01-01", "justificacion": "x"}, "Propuesta para"),
])
def test_propuesta_rechazada_cae_a_la_regla(agente, monkeypatch, responde, error):
    ollama(monkeypatch, responde)
    r = agente.vela(FECHAS[0])
    assert r.status_code == 200, r.text
    accion, motivo = ultima(agente)
    est = r.json()["rendimiento_estimado"]
    assert accion == ("comprar" if est > 0.0005 else "efectivo") and motivo.startswith("respaldo · regla Avance 3")
    assert error in agente.sql("SELECT detalle FROM errores WHERE etapa='llm'")[-1][0]


def test_propuesta_valida_manda_y_riesgo_ejecuta(agente, monkeypatch):
    plan = iter(["comprar", "mantener", "vender", "mantener"])
    ollama(monkeypatch, lambda d: ok(d, next(plan), f"estimado {d['rendimiento_estimado_pct']} %"))
    for f in FECHAS[:4]:
        assert agente.vela(f).status_code == 200
    acciones = [a for (a,) in agente.sql("SELECT accion FROM decisiones ORDER BY fecha")]
    assert acciones == ["comprar", "mantener", "vender", "mantener"]
    assert all(m.startswith("LLM qwen2.5:1.5b · Ollama 0.0-prueba · CPU ") for (m,) in agente.sql("SELECT motivo FROM decisiones"))
    lados = agente.sql("SELECT fecha, lado FROM ordenes WHERE estado='ejecutada' ORDER BY id")
    assert lados == [(FECHAS[1], "compra"), (FECHAS[3], "venta")]           # mantener no genera orden; vender sí
    assert not agente.sql("SELECT 1 FROM errores WHERE etapa='llm'")


def test_detener_y_estado_responden_mientras_piensa_el_llm(agente, monkeypatch):
    """El LLM tarda (15-17 s reales): la base no queda tomada; /detener entra y /liquidar espera al ciclo."""
    vistas = {}
    def lento(d):
        for ruta, metodo in (("/detener", "post"), ("/estado", "get"), ("/liquidar", "post")):
            t = threading.Thread(target=lambda r=ruta, m=metodo: vistas.__setitem__(r, getattr(agente.c, m)(r, headers=H).status_code))
            t.start(); t.join(5)
        foto.update(vistas)                     # lo que respondió MIENTRAS el LLM pensaba (un hilo trabado no llega a la foto)
        return ok(d, "comprar")
    foto = {}
    ollama(monkeypatch, lento)
    assert agente.vela(FECHAS[0]).status_code == 200
    assert foto == {"/detener": 200, "/estado": 200, "/liquidar": 409}
    assert agente.c.get("/estado", headers=H).json()["estado"] == "detenido"


def test_detenido_bloquea_aunque_el_llm_proponga_comprar(agente, monkeypatch):
    ollama(monkeypatch, lambda d: ok(d, "comprar"))
    agente.vela(FECHAS[0])
    agente.c.post("/detener", headers=H)
    r = agente.vela(FECHAS[1])
    assert r.json()["ordenes"][0]["estado"] == "rechazada" and "detenido" in r.json()["ordenes"][0]["motivo"]


def test_salud_reporta_llm_local(agente, monkeypatch):
    ollama(monkeypatch, lambda d: None)
    s = agente.c.get("/salud").json()["llm"]
    assert s["modelo"] == "qwen2.5:1.5b" and s["ollama"] == "0.0-prueba" and s["url"].startswith("http://127.0.0.1") and s["hardware"].startswith("CPU")
