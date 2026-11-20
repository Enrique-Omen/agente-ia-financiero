"""Pruebas del escalón 1. Uso (desde agente/backend): ../../../../.venv/bin/python -m pytest -q
Sin red: las velas de MEXC se simulan con el CSV auditado del Avance 1 (mismo formato que /api/v3/klines)."""
import http.client, json, os, urllib.error
from types import SimpleNamespace
import numpy as np, pandas as pd, pytest
from fastapi.testclient import TestClient

from app import main, mexc
from app.variables import COLUMNAS, variables

AV5 = os.path.join(os.path.dirname(__file__), "../../../avance5/")
PRECIOS = pd.read_csv(AV5 + "data/processed/btcusdt_1d_auditado.csv", parse_dates=["fecha"]).set_index("fecha")
CONTROL = json.load(open(AV5 + "outputs/pronostico_futuro.json"))
CLAVE = "clave-de-prueba-0123456789"
DIA = mexc.DIA_MS
# 2026-11-05 17:00 UTC: la vela del 4-nov ya cerró (hace 17 h) y la del 5-nov sigue abierta
AHORA_MS = int(pd.Timestamp("2026-11-05 17:00").timestamp() * 1000)


def klines(hasta="2026-11-04", n=30, abierta=True):
    p = PRECIOS.loc[:hasta].iloc[-n:]
    filas = [[int(f.timestamp() * 1000), str(r.open), str(r.high), str(r.low), str(r.close), str(r.volume),
              int(f.timestamp() * 1000) + DIA, "0"] for f, r in p.iterrows()]
    if abierta:   # MEXC también manda la vela del día en curso
        filas.append([filas[-1][0] + DIA, "1", "1", "1", "1", "1", filas[-1][0] + 2 * DIA, "0"])
    return filas


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTE_API_KEY", CLAVE)
    monkeypatch.setenv("AGENTE_DB", str(tmp_path / "agente.db"))
    monkeypatch.setattr(mexc, "pedir_json", lambda url: klines())
    esperas = []   # reloj y esperas falsos solo dentro de mexc
    monkeypatch.setattr(mexc, "time", SimpleNamespace(time=lambda: AHORA_MS / 1000, sleep=esperas.append))
    c = TestClient(main.crear_app())
    c.esperas = esperas
    return c


def test_variables_iguales_al_cuaderno_en_fecha_fija():
    ventanas = pd.read_csv(AV5 + "data/processed/ventanas_btcusdt_1d.csv", parse_dates=["fecha_emision"]).set_index("fecha_emision")
    for t in ["2019-03-01", "2024-05-31", "2026-11-03"]:
        fila = variables(PRECIOS.close.loc[:t])
        lags = [c for c in COLUMNAS if c.startswith("r_lag")]
        assert np.allclose(fila[lags].iloc[0], ventanas.loc[t, lags], atol=1e-12, rtol=0)
    fila = variables(PRECIOS.close)
    assert str(fila.index[0].date()) == CONTROL["emitido_al_cierre_de"]
    assert abs(fila.dist_sma20.iloc[0] - CONTROL["dist_sma20"]) < 1e-12 and abs(fila.vol20.iloc[0] - CONTROL["vol20"]) < 1e-12


def test_pronostico_igual_al_cuaderno(cliente):
    r = cliente.get("/pronostico", headers={"X-API-Key": CLAVE})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["vela"] == "2026-11-04"                      # la vela abierta del 5-nov no se usa
    assert abs(d["rendimiento_estimado"] - CONTROL["rendimiento_estimado"]) < 1e-12
    assert d["cierre_base"] == CONTROL["cierre_base"]


def test_salud_sin_clave(cliente):
    assert cliente.get("/salud").json()["estado"] == "ok"


@pytest.mark.parametrize("cabecera", [{}, {"X-API-Key": "otra"}, {"X-API-Key": CLAVE + "x"}])
def test_clave_ausente_o_incorrecta_401(cliente, cabecera):
    r = cliente.get("/pronostico", headers=cabecera)
    assert r.status_code == 401 and CLAVE not in r.text


def test_sin_clave_en_servidor_no_arranca(monkeypatch):
    monkeypatch.delenv("AGENTE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        main.crear_app()


@pytest.mark.parametrize("falla", [urllib.error.URLError("sin red"),
                                   urllib.error.HTTPError(mexc.FUENTE, 429, "Too Many Requests", None, None),
                                   TimeoutError("lento"), ConnectionResetError("corte"),
                                   http.client.RemoteDisconnected("cerró"), http.client.IncompleteRead(b"[[1")])
def test_mexc_caida_o_con_limite_error_controlado(cliente, monkeypatch, falla):
    intentos = []
    def caida(url):
        intentos.append(url)
        raise falla
    monkeypatch.setattr(mexc, "pedir_json", caida)
    r = cliente.get("/pronostico", headers={"X-API-Key": CLAVE})
    assert r.status_code == 503 and "MEXC sin respuesta" in r.json()["detail"]
    assert len(intentos) == 3 and cliente.esperas == [0.5, 1.0]        # reintentos limitados, espera creciente


def test_dato_atrasado_se_rechaza(cliente, monkeypatch):
    monkeypatch.setattr(mexc, "pedir_json", lambda url: klines(hasta="2026-11-01", abierta=False))
    r = cliente.get("/pronostico", headers={"X-API-Key": CLAVE})
    assert r.status_code == 503 and "atrasado" in r.json()["detail"]


def test_huecos_o_desorden_se_rechazan(monkeypatch):
    k = klines(abierta=False)
    for malas in [k[:10] + k[11:], k[:5] + [k[6], k[5]] + k[7:], k + [k[-1]]]:
        monkeypatch.setattr(mexc, "pedir_json", lambda url, m=malas: m)
        with pytest.raises(mexc.ErrorDatos):
            mexc.velas("BTCUSDT", ahora_ms=AHORA_MS)
    monkeypatch.setattr(mexc, "pedir_json", lambda url: k)
    assert len(mexc.velas("BTCUSDT", ahora_ms=AHORA_MS)) == 30


@pytest.mark.parametrize("campo,valor", [(4, "NaN"), (4, None), (4, "inf"), (4, "1e9"), (1, "0"), (3, "-1"), (5, "-3")])
def test_valores_imposibles_se_rechazan(monkeypatch, campo, valor):
    k = klines(abierta=False)
    k[-5][campo] = valor     # 4 close (1e9 > high), 1 open, 3 low, 5 volumen
    monkeypatch.setattr(mexc, "pedir_json", lambda url: k)
    with pytest.raises(mexc.ErrorDatos):
        mexc.velas("BTCUSDT", ahora_ms=AHORA_MS)


def test_frecuencia_distinta_de_un_dia_se_rechaza(monkeypatch):
    k = klines(abierta=False)
    k = [[f[0] + 3_600_000, *f[1:6], f[6] + 3_600_000, f[7]] for f in k]     # velas que abren a la 01:00 UTC
    monkeypatch.setattr(mexc, "pedir_json", lambda url: k)
    with pytest.raises(mexc.ErrorDatos, match="Frecuencia"):
        mexc.velas("BTCUSDT", ahora_ms=AHORA_MS)


def test_simbolo_sin_modelo_no_arranca(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTE_DB", str(tmp_path / "agente.db"))
    monkeypatch.setenv("AGENTE_API_KEY", CLAVE)
    monkeypatch.setenv("SIMBOLO", "ETHUSDT")
    with pytest.raises(RuntimeError, match="SIMBOLO"):
        main.crear_app()


def test_simbolo_no_permitido():
    with pytest.raises(mexc.ErrorDatos, match="no permitido"):
        mexc.velas("ETHUSDT")


def test_no_hay_ruta_de_ordenes(cliente):
    rutas = {r.path for r in cliente.app.routes}
    assert not any(p in ruta.lower() for ruta in rutas for p in ["orden", "order", "trade"])
