"""Comparación del §16 en las mismas velas (16-oct a 4-nov-2026), 50,000 USDT y costo 0 %, por el ciclo completo del backend:
sin LLM (regla del Avance 3), con LLM (uno por modelo) y comprar y mantener. Escribe datos/comparacion.csv y una base por estrategia.
Uso: python comparar.py [modelo ...]   (por defecto qwen3:1.7b; Ollama en 127.0.0.1:11434; N_VELAS=20 para acortar)"""
import csv, os, re, sqlite3, sys
import pytest
from app import main, paper
from tests.test_ciclo import FECHAS, H, PRECIOS, Agente   # clave de prueba del harness, no un secreto

DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
N = int(os.environ.get("N_VELAS", "20"))
FECHAS = FECHAS[:N]


def correr(modelo):
    """Una estrategia por el ciclo completo; modelo '' = sin LLM. Devuelve la ruta de su base."""
    db = os.path.join(DATOS, f"comparar-{modelo.replace(':', '-') or 'sin-llm'}.db")
    if os.path.exists(db):
        os.remove(db)
    mp = pytest.MonkeyPatch()
    mp.setenv("LLM_MODELO", modelo)
    a = Agente(mp, db)
    a.c.post("/iniciar", headers=H)
    for f in FECHAS:
        r = a.vela(f)
        assert r.status_code == 200, r.text
        print(modelo or "sin-llm", f, r.json()["accion_siguiente"], flush=True)
    mp.undo()
    return db


def metricas(curva, operaciones):
    """curva: patrimonio por vela; operaciones: rendimiento de cada viaje compra → venta (el abierto, al último cierre)."""
    pico, dd = curva[0], 0.0
    for p in curva:
        pico = max(pico, p)
        dd = max(dd, (pico - p) / pico)
    return {"rendimiento_neto_%": round(100 * (curva[-1] / paper.CAPITAL - 1), 3), "drawdown_max_%": round(100 * dd, 3),
            "win_rate_%": round(100 * sum(r > 0 for r in operaciones) / len(operaciones), 1) if operaciones else "",
            "operaciones": len(operaciones), "patrimonio_final": round(curva[-1], 2)}


def de_base(nombre, db):
    q = sqlite3.connect(db).execute
    curva = [paper.CAPITAL] + [p for (p,) in q("SELECT patrimonio FROM patrimonio ORDER BY fecha")]
    viajes, compra = [], None
    for lado, precio in q("SELECT lado, precio FROM ordenes WHERE estado='ejecutada' ORDER BY id"):
        if lado == "compra":
            compra = precio
        elif compra:
            viajes.append(precio / compra - 1)
            compra = None
    if compra:
        viajes.append(float(PRECIOS.loc[FECHAS[-1], "close"]) / compra - 1)
    # Coherencia: la posición que pide la acción contra la que pide el signo del pronóstico (regla: estimado > δ → con posición)
    filas = q("SELECT d.rendimiento_estimado, d.accion, d.motivo, p.unidades FROM decisiones d JOIN patrimonio p USING (fecha)").fetchall()
    quiere = lambda accion, u: accion == "comprar" or (accion == "mantener" and u > 0)
    coherentes = sum(quiere(acc, u) == (est > main.UMBRAL) for est, acc, _, u in filas)
    ms = [int(m) for (*_, mot, _) in filas for m in re.findall(r"· (\d+) ms:", mot)]
    return {"estrategia": nombre, **metricas(curva, viajes),
            "ordenes_rechazadas": q("SELECT COUNT(*) FROM ordenes WHERE estado='rechazada'").fetchone()[0],
            "respaldos_llm": q("SELECT COUNT(*) FROM errores WHERE etapa='llm'").fetchone()[0],
            "coherencia_con_pronostico_%": round(100 * coherentes / len(filas), 1),
            "latencia_media_ms": round(sum(ms) / len(ms)) if ms else "", "latencia_max_ms": max(ms) if ms else ""}


def comprar_y_mantener():
    """Compra a la apertura de la segunda vela (la primera en que el agente puede ejecutar) y no vende."""
    apertura, cierre = float(PRECIOS.loc[FECHAS[1], "open"]), [float(PRECIOS.loc[f, "close"]) for f in FECHAS[1:]]
    curva = [paper.CAPITAL, paper.CAPITAL] + [paper.CAPITAL / apertura * c for c in cierre]
    return {"estrategia": "comprar y mantener", **metricas(curva, [cierre[-1] / apertura - 1]),
            "ordenes_rechazadas": 0, "respaldos_llm": "", "coherencia_con_pronostico_%": "", "latencia_media_ms": "", "latencia_max_ms": ""}


if __name__ == "__main__":
    modelos = sys.argv[1:] or ["qwen3:1.7b"]
    filas = [de_base("sin LLM (regla Avance 3)", correr(""))]
    filas += [de_base(f"con LLM {m}", correr(m)) for m in modelos]
    filas.append(comprar_y_mantener())
    salida = os.path.join(DATOS, "comparacion.csv")
    with open(salida, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print(f"{FECHAS[0]} a {FECHAS[-1]} · {len(FECHAS)} velas · 50,000 USDT · costo 0 % → {salida}")
    for fila in filas:
        print(fila)
