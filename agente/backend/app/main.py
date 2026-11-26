"""API del agente: /salud, /pronostico y el ciclo Paper (/ciclo, /estado, /historial, /iniciar, /pausar, /detener, /liquidar).
Arranque: uvicorn app.main:crear_app --factory. La clave vive solo en el servidor (AGENTE_API_KEY); nunca se registra ni se devuelve.
Órdenes reales: ninguna ruta. Todo es Paper."""
import hmac, json, logging, os, threading, time
from dataclasses import asdict
import joblib, pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException

from app import llm, mexc, paper, riesgo
from app.registro import Registro
from app.variables import COLUMNAS, variables

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELO = os.path.join(BACKEND, "modelo", "v1")
UMBRAL = 0.0005   # regla provisional del Avance 3 (δ = 0.05 %) mientras no hay LLM
log = logging.getLogger("agente")


def crear_app():
    clave = os.environ.get("AGENTE_API_KEY", "")
    if len(clave) < 16:
        raise RuntimeError("Falta AGENTE_API_KEY (16 caracteres o más) en el entorno del servidor")
    limites = riesgo.Limites.del_entorno()
    simbolo = os.environ.get("SIMBOLO", "BTCUSDT")
    if simbolo not in mexc.SIMBOLOS:
        raise RuntimeError(f"SIMBOLO={simbolo} no tiene modelo entrenado (permitidos: {sorted(mexc.SIMBOLOS)})")
    art = joblib.load(os.path.join(MODELO, "modelo.joblib"))
    meta = json.load(open(os.path.join(MODELO, "meta.json")))
    if not art["columnas"] == COLUMNAS == meta["columnas"]:
        raise RuntimeError("El modelo no corresponde al contrato de variables")
    reg = Registro(os.environ.get("AGENTE_DB", os.path.join(BACKEND, "datos", "agente.db")))
    ollama = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    llm_modelo = os.environ.get("LLM_MODELO", "qwen3:1.7b")   # vacío = sin LLM (solo la regla del Avance 3, para comparar)
    llm_timeout = float(os.environ.get("LLM_TIMEOUT_S", "60"))
    en_curso = threading.Lock()   # un ciclo (o liquidar) a la vez; el candado de la base se suelta mientras piensa el LLM

    def exigir_clave(x_api_key: str = Header(default="")):
        if not hmac.compare_digest(x_api_key.encode(), clave.encode()):
            log.warning("acceso rechazado: clave ausente o incorrecta")
            raise HTTPException(401, "Clave ausente o incorrecta")

    app = FastAPI(title="Agente BTCUSDT · Paper", version=meta["version"])

    @app.get("/salud")
    def salud():
        return {"estado": "ok", "modelo": meta["version"], "simbolo": simbolo,
                "llm": llm.info(ollama, llm_modelo) if llm_modelo else "sin LLM (regla del Avance 3)"}

    def leer_y_pronosticar():
        try:
            v = mexc.velas(simbolo, limites.max_antiguedad_h)
            fila = variables(v.close)
        except (mexc.ErrorDatos, ValueError) as e:
            log.error("pronóstico detenido: %s", e)
            with reg.candado:
                reg.error("datos", e)
            raise HTTPException(503, f"Sin datos válidos: {e}. No se decide con este dato.")
        est = float(art["escY"].inverse_transform(art["modelo"].predict(art["escX"].transform(fila)).reshape(-1, 1))[0, 0])
        return v, fila, est

    @app.get("/pronostico", dependencies=[Depends(exigir_clave)])
    def pronostico():
        t0 = time.perf_counter()
        v, fila, est = leer_y_pronosticar()
        cierre = float(v.close.iloc[-1])
        return {"simbolo": simbolo, "vela": str(fila.index[0].date()), "cierre_base": cierre,
                "rendimiento_estimado": est, "cierre_estimado": cierre * (1 + est),
                "variables": {k: float(fila[k].iloc[0]) for k in COLUMNAS},
                "modelo": meta["version"], "latencia_ms": round(1000 * (time.perf_counter() - t0), 1)}

    @app.post("/ciclo", dependencies=[Depends(exigir_clave)])
    def ciclo():
        """Una vela t: ejecuta a su apertura la decisión de t-1, valora al cierre de t y decide para t+1.
        El LLM se consulta fuera del candado de la base: /detener, /pausar y /estado responden mientras piensa."""
        if not en_curso.acquire(blocking=False):
            raise HTTPException(409, "Ya hay un ciclo en curso: no se procesa dos veces")
        try:
            return _ciclo()
        finally:
            en_curso.release()

    def _ciclo():
        with reg.candado:
            if reg.estado() == "pausado":
                raise HTTPException(409, "Agente en pausa: no se procesa la vela")
            v, fila, est = leer_y_pronosticar()
            fecha = str(fila.index[0].date())
            if reg.ya_procesada(fecha):
                reg.error("ciclo", f"vela duplicada {fecha}")
                raise HTTPException(409, f"Vela {fecha} ya procesada: no se repite ninguna orden")
            ultima = reg.uno("SELECT MAX(fecha) FROM velas")[0]
            if ultima and fecha < ultima:
                reg.error("ciclo", f"vela {fecha} más vieja que la última procesada {ultima}")
                raise HTTPException(409, f"Vela {fecha} más vieja que la última procesada ({ultima}): no se procesa")
            apertura, cierre = float(v.open.iloc[-1]), float(v.close.iloc[-1])
            cartera, ordenes, pend = reg.cartera(), [], reg.ultima_decision()
            if pend and str((v.index[-1] - pd.Timedelta(days=1)).date()) == pend["fecha"]:
                lado = "compra" if pend["accion"] == "comprar" and cartera.unidades == 0 else \
                       "venta" if pend["accion"] in ("vender", "efectivo") and cartera.unidades > 0 else None
                if lado:
                    motivo = riesgo.revisar(reg.estado())
                    try:
                        if motivo:
                            raise paper.OrdenRechazada(motivo)
                        o = paper.comprar(cartera, apertura, limites.exposicion_max * cartera.patrimonio(apertura)) \
                            if lado == "compra" else paper.vender_todo(cartera, apertura)
                        ordenes.append({**o, "fecha": fecha, "estado": "ejecutada", "motivo": f"decisión del {pend['fecha']}"})
                    except paper.OrdenRechazada as e:
                        ordenes.append({"fecha": fecha, "lado": lado, "cantidad": 0.0, "precio": apertura,
                                        "estado": "rechazada", "motivo": str(e)})
            elif pend:
                reg.error("ciclo", f"decisión del {pend['fecha']} vencida en la vela {fecha}: no se ejecuta")
            accion = "comprar" if est > UMBRAL else "efectivo"
            motivo = f"regla Avance 3: estimado {est:.4%} {'>' if est > UMBRAL else '≤'} δ {UMBRAL:.2%}"
            if llm_modelo:
                pct = lambda x: round(100 * float(x), 3)   # en % y redondeado: menos tokens y cifras que el LLM sí lee
                datos = {"simbolo": simbolo, "fecha_vela": fecha, "cierre": round(cierre, 2), "rendimiento_estimado_pct": pct(est),
                         "variables_pct": {k: pct(fila[k].iloc[0]) for k in COLUMNAS},
                         "cartera": {"efectivo": round(cartera.efectivo, 2), "unidades_btc": cartera.unidades,
                                     "patrimonio": round(cartera.patrimonio(cierre), 2), "en_posicion": cartera.unidades > 0},
                         "limites": {"exposicion_max": limites.exposicion_max, "perdida_diaria_max": limites.perdida_diaria_max},
                         "senal": {"umbral_pct": pct(UMBRAL), "estimado_mayor_que_umbral": est > UMBRAL, "conviene_posicion": est > UMBRAL,
                                   "accion_sugerida": ("mantener" if est > UMBRAL else "vender") if cartera.unidades > 0 else ("comprar" if est > UMBRAL else "mantener")},
                         "acciones_permitidas": ["mantener", "vender"] if cartera.unidades > 0 else ["comprar", "mantener"]}
        falla = None
        if llm_modelo:
            try:
                p, ms = llm.proponer(datos, ollama, llm_modelo, llm_timeout)
                i = llm.info(ollama, llm_modelo)
                accion, motivo = p.accion, f"LLM {llm_modelo} · Ollama {i['ollama']} · {i['hardware']} · {ms:.0f} ms: {p.justificacion}"
            except llm.ErrorLLM as e:
                falla, motivo = e, f"respaldo · {motivo}"
        with reg.candado:
            if falla:
                reg.error("llm", falla)
            previo = reg.uno("SELECT patrimonio FROM patrimonio WHERE fecha=?", str((v.index[-1] - pd.Timedelta(days=1)).date()))
            freno = riesgo.freno_por_perdida(cartera.patrimonio(cierre) / previo[0] - 1 if previo else None, limites)
            reg.guardar(cartera, ordenes, fecha, (apertura, cierre), (est, accion, motivo), freno)
            return {"vela": fecha, "estado": reg.estado(), "freno": freno, "ordenes": ordenes, "rendimiento_estimado": est,
                    "accion_siguiente": accion, "motivo": motivo,
                    "patrimonio": cartera.patrimonio(cierre), "efectivo": cartera.efectivo, "unidades": cartera.unidades}

    @app.get("/estado", dependencies=[Depends(exigir_clave)])
    def estado():
        with reg.candado:
            d, p = reg.ultima_decision(), reg.uno("SELECT * FROM patrimonio ORDER BY fecha DESC LIMIT 1")
            c = reg.cartera()
            return {"estado": reg.estado(), "simbolo": simbolo, "efectivo": c.efectivo, "unidades": c.unidades,
                    "ultima_vela": dict(p) if p else None, "ultima_decision": dict(d) if d else None,
                    "ordenes": [dict(o) for o in reg.db.execute("SELECT * FROM ordenes ORDER BY id DESC LIMIT 20")],
                    "errores": [dict(e) for e in reg.db.execute("SELECT * FROM errores ORDER BY id DESC LIMIT 20")],
                    "limites": asdict(limites), "mercado": paper.MERCADO, "capital_inicial": paper.CAPITAL, "costo": paper.COSTO}

    @app.get("/historial", dependencies=[Depends(exigir_clave)])
    def historial():
        """Solo lectura para las gráficas: patrimonio y precio por vela, y las órdenes ejecutadas (marcas de compra/venta)."""
        with reg.candado:
            return {"velas": [dict(r) for r in reg.db.execute("SELECT fecha, precio, patrimonio FROM patrimonio ORDER BY fecha")],
                    "ordenes": [dict(r) for r in reg.db.execute(
                        "SELECT fecha, lado, precio FROM ordenes WHERE estado='ejecutada' ORDER BY id")],
                    "capital_inicial": paper.CAPITAL}

    def cambiar(valor):
        with reg.candado:
            reg.poner_estado(valor)
        return {"estado": valor}

    app.post("/iniciar", dependencies=[Depends(exigir_clave)])(lambda: cambiar("activo"))
    app.post("/pausar", dependencies=[Depends(exigir_clave)])(lambda: cambiar("pausado"))
    app.post("/detener", dependencies=[Depends(exigir_clave)])(lambda: cambiar("detenido"))

    @app.post("/liquidar", dependencies=[Depends(exigir_clave)])
    def liquidar():
        """Acción aparte de detener: vende toda la posición al último cierre registrado (Paper)."""
        if not en_curso.acquire(blocking=False):   # el ciclo guarda su cartera al final: liquidar en medio la pisaría
            raise HTTPException(409, "Hay un ciclo en curso: liquida cuando termine")
        try:
            with reg.candado:
                p = reg.uno("SELECT fecha, precio FROM patrimonio ORDER BY fecha DESC LIMIT 1")
                cartera = reg.cartera()
                if not p or cartera.unidades == 0:
                    raise HTTPException(409, "No hay posición que liquidar")
                o = paper.vender_todo(cartera, p["precio"])
                reg.guardar(cartera, [{**o, "fecha": p["fecha"], "estado": "ejecutada", "motivo": "liquidar (manual)"}])
                return {**o, "efectivo": cartera.efectivo}
        finally:
            en_curso.release()

    return app
