"""Pruebas del escalón 2 (Paper + riesgo + SQLite). Sin red: las velas salen del CSV auditado, como en test_backend.
El replay compara el ciclo completo (HTTP → MEXC simulado → modelo → riesgo → Paper → SQLite) con la regla del Avance 3."""
import dataclasses, os, sqlite3
from types import SimpleNamespace
import joblib, numpy as np, pandas as pd, pytest
from fastapi.testclient import TestClient

from app import main, mexc, paper, riesgo
from app.variables import variables
from tests.test_backend import CLAVE, PRECIOS, klines

H = {"X-API-Key": CLAVE}
FECHAS = [str(f.date()) for f in PRECIOS.loc[:"2026-11-04"].index[-20:]]   # 20 velas históricas: 16-oct a 4-nov-2026


class Agente:
    """El backend con un reloj falso: `vela(f)` hace que MEXC devuelva hasta la vela f, ya cerrada, y corre /ciclo."""
    def __init__(self, monkeypatch, db):
        self.mp, self.db = monkeypatch, db
        monkeypatch.setenv("AGENTE_API_KEY", CLAVE)
        monkeypatch.setenv("AGENTE_DB", db)
        self.reiniciar()

    def reiniciar(self):
        self.c = TestClient(main.crear_app())

    def vela(self, fecha):
        ahora = (pd.Timestamp(fecha) + pd.Timedelta(hours=41)).timestamp()   # 17:00 UTC del día siguiente
        self.mp.setattr(mexc, "pedir_json", lambda url: klines(hasta=fecha, abierta=False))
        self.mp.setattr(mexc, "time", SimpleNamespace(time=lambda: ahora, sleep=lambda s: None))
        return self.c.post("/ciclo", headers=H)

    def sql(self, q):
        return sqlite3.connect(self.db).execute(q).fetchall()


@pytest.fixture
def agente(monkeypatch, tmp_path):
    a = Agente(monkeypatch, str(tmp_path / "agente.db"))
    assert a.c.post("/iniciar", headers=H).json()["estado"] == "activo"
    return a


def regla_avance3(fechas, capital=paper.CAPITAL, costo=0.0, umbral=main.UMBRAL):
    """La regla del Avance 3 (avance3/construir.py, simular) con 50,000 y 0 %, sin la liquidación final."""
    art = joblib.load(os.path.join(main.MODELO, "modelo.joblib"))
    est = {f: float(art["escY"].inverse_transform(art["modelo"].predict(art["escX"].transform(variables(PRECIOS.close.loc[:f])))
                                                   .reshape(-1, 1))[0, 0]) for f in fechas}
    efectivo, unidades, filas = float(capital), 0.0, {}
    for previa, f in zip(fechas, fechas[1:]):
        s, apertura, cierre = est[previa] > umbral, PRECIOS.loc[f, "open"], PRECIOS.loc[f, "close"]
        if s and unidades == 0:
            unidades, efectivo = efectivo / (apertura * (1 + costo)), 0.0
        elif not s and unidades > 0:
            efectivo, unidades = unidades * apertura * (1 - costo), 0.0
        filas[f] = (int(unidades > 0), efectivo + unidades * cierre)
    return est, filas


@pytest.mark.replay
def test_replay_20_velas_igual_a_la_regla_del_avance3(agente):
    for f in FECHAS:
        r = agente.vela(f)
        assert r.status_code == 200, r.text
    est, ref = regla_avance3(FECHAS)
    dec = dict(agente.sql("SELECT fecha, rendimiento_estimado FROM decisiones"))
    assert all(abs(dec[f] - est[f]) < 1e-12 for f in FECHAS)
    acciones = [a for (a,) in agente.sql("SELECT accion FROM decisiones ORDER BY fecha")]
    assert {"comprar", "efectivo"} <= set(acciones)                     # la ventana ejercita compras y ventas
    pat = {f: (int(u > 0), p) for f, u, p in agente.sql("SELECT fecha, unidades, patrimonio FROM patrimonio")}
    for f, (pos, p) in ref.items():
        assert pat[f][0] == pos, f
        assert abs(pat[f][1] - p) < 1.0, (f, pat[f][1], p)   # < 1 USDT: residuo de redondear la cantidad a 0.000001 BTC
    assert len(agente.sql("SELECT 1 FROM ordenes WHERE estado='ejecutada'")) > 0
    assert agente.sql("SELECT COUNT(*) FROM velas")[0][0] == 20


def test_vela_duplicada_no_repite_orden(agente):
    for f in FECHAS[:5]:
        agente.vela(f)
    antes = agente.sql("SELECT * FROM ordenes")
    r = agente.vela(FECHAS[4])
    assert r.status_code == 409 and "ya procesada" in r.json()["detail"]
    assert agente.sql("SELECT * FROM ordenes") == antes
    assert agente.sql("SELECT COUNT(*) FROM velas")[0][0] == 5
    assert "duplicada" in agente.sql("SELECT detalle FROM errores")[-1][0]


def test_vela_mas_vieja_que_la_ultima_no_se_procesa(agente):
    for f in FECHAS[:5] + FECHAS[6:8]:                                   # se salta FECHAS[5]
        agente.vela(f)
    antes = agente.sql("SELECT * FROM ordenes"), agente.sql("SELECT * FROM control")
    r = agente.vela(FECHAS[5])                                           # llega tarde
    assert r.status_code == 409 and "más vieja" in r.json()["detail"]
    assert (agente.sql("SELECT * FROM ordenes"), agente.sql("SELECT * FROM control")) == antes
    assert agente.sql(f"SELECT COUNT(*) FROM velas WHERE fecha='{FECHAS[5]}'")[0][0] == 0


def test_reinicio_recupera_estado_sin_duplicar(agente, monkeypatch, tmp_path):
    for f in FECHAS[:10]:
        agente.vela(f)
    agente.reiniciar()                                                   # proceso nuevo, misma base
    assert agente.vela(FECHAS[9]).status_code == 409
    for f in FECHAS[10:]:
        assert agente.vela(f).status_code == 200
    seguido = Agente(monkeypatch, str(tmp_path / "seguido.db"))
    seguido.c.post("/iniciar", headers=H)
    for f in FECHAS:
        seguido.vela(f)
    q = "SELECT fecha, efectivo, unidades, patrimonio FROM patrimonio ORDER BY fecha"
    assert agente.sql(q) == seguido.sql(q)


def test_pausa_no_procesa_y_detener_bloquea_ordenes_sin_liquidar(agente):
    agente.c.post("/pausar", headers=H)
    assert agente.vela(FECHAS[0]).status_code == 409
    agente.c.post("/iniciar", headers=H)
    for f in FECHAS:
        agente.vela(f)
        if agente.c.get("/estado", headers=H).json()["unidades"] > 0:
            break
    unidades = agente.c.get("/estado", headers=H).json()["unidades"]
    assert unidades > 0
    assert agente.c.post("/detener", headers=H).json()["estado"] == "detenido"
    resto = FECHAS[FECHAS.index(f) + 1:]
    for g in resto:
        assert agente.vela(g).status_code == 200                       # sigue registrando, no opera
    e = agente.c.get("/estado", headers=H).json()
    assert e["unidades"] == unidades                                    # detener no liquida
    rech = agente.sql(f"SELECT motivo FROM ordenes WHERE estado='rechazada' AND fecha > '{f}'")
    hechas = agente.sql(f"SELECT 1 FROM ordenes WHERE estado='ejecutada' AND fecha > '{f}'")
    assert not hechas and rech and all("detenido" in m for (m,) in rech)
    r = agente.c.post("/liquidar", headers=H)                           # liquidar es aparte
    assert r.status_code == 200 and agente.c.get("/estado", headers=H).json()["unidades"] == 0
    assert agente.c.post("/liquidar", headers=H).status_code == 409


def test_saldo_insuficiente_rechazada_y_registrada():
    c = paper.Cartera(efectivo=0.5)
    with pytest.raises(paper.OrdenRechazada, match="bajo el mínimo"):
        paper.comprar(c, 70_000.0, 0.5)
    with pytest.raises(paper.OrdenRechazada, match="pide 100.00 USDT y hay 0.50"):
        paper.comprar(c, 70_000.0, 100.0)
    assert c == paper.Cartera(efectivo=0.5)


def test_saldo_insuficiente_en_el_ciclo(agente):
    # la cartera vive en SQLite: se vacía a mano para simular que no hay saldo
    sqlite3.connect(agente.db, isolation_level=None).execute("UPDATE control SET valor='0.5' WHERE clave='efectivo'")
    agente.reiniciar()
    for f in FECHAS:
        agente.vela(f)
    rech = agente.sql("SELECT lado, motivo FROM ordenes")
    assert rech and all(l == "compra" and "bajo el mínimo" in m for l, m in rech)   # el ciclo pide todo el efectivo: falla el mínimo
    assert agente.c.get("/estado", headers=H).json()["unidades"] == 0


def test_cantidad_redondeada_al_paso_del_exchange():
    c = paper.Cartera()
    o = paper.comprar(c, 68_123.45, c.efectivo)
    assert o["cantidad"] == round(o["cantidad"], 6) and 0 <= c.efectivo < 68_123.45 * 1e-6
    assert paper.MERCADO["leido"] and paper.MERCADO["paso_cantidad"] == "0.000001"


def test_limite_de_perdida_detiene_y_la_orden_siguiente_se_rechaza(agente, monkeypatch):
    lim = riesgo.Limites(perdida_diaria_max=0.10)
    assert riesgo.freno_por_perdida(-0.11, lim).startswith("Pérdida del día")
    assert riesgo.freno_por_perdida(-0.05, lim) is None and riesgo.freno_por_perdida(None, lim) is None
    monkeypatch.setenv("PERDIDA_DIARIA_MAX", "0.0001")                  # límite casi nulo: el primer día en rojo frena
    agente.reiniciar()
    for f in FECHAS:
        r = agente.vela(f).json()
        if r["freno"]:
            break
    assert r["estado"] == "detenido" and "Pérdida del día" in agente.sql("SELECT detalle FROM errores")[-1][0]
    unidades = r["unidades"]
    for g in FECHAS[FECHAS.index(f) + 1:]:
        agente.vela(g)
    rech = agente.sql(f"SELECT motivo FROM ordenes WHERE fecha > '{f}'")
    assert rech and all("detenido" in m for (m,) in rech)                # rechazadas y registradas
    assert agente.c.get("/estado", headers=H).json()["unidades"] == unidades   # frenar no liquida


def test_limites_inmutables_y_validados(monkeypatch):
    lim = riesgo.Limites()
    with pytest.raises(dataclasses.FrozenInstanceError):
        lim.exposicion_max = 2.0
    for var, val in [("EXPOSICION_MAX", "1.5"), ("PERDIDA_DIARIA_MAX", "0"), ("MAX_ANTIGUEDAD_H", "-1")]:
        monkeypatch.setenv(var, val)
        with pytest.raises(RuntimeError, match="fuera de rango"):
            riesgo.Limites.del_entorno()
        monkeypatch.delenv(var)


def test_rutas_nuevas_piden_clave(agente):
    for metodo, ruta in [("post", "/ciclo"), ("get", "/estado"), ("post", "/iniciar"), ("post", "/pausar"),
                         ("post", "/detener"), ("post", "/liquidar")]:
        assert getattr(agente.c, metodo)(ruta).status_code == 401
