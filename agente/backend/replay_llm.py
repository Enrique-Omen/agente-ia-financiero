"""Replay con Ollama REAL: N velas históricas (MEXC simulado con el CSV auditado) por el ciclo completo, registradas en
datos/replay-llm.db. Evidencia de inferencia local: modelo, versión, hardware y latencia por vela.
Uso: python replay_llm.py [N] [base.db]   (Ollama corriendo en 127.0.0.1:11434 con LLM_MODELO, por defecto qwen2.5:1.5b)"""
import json, os, sys
import pytest
from tests.test_ciclo import FECHAS, H, Agente   # clave de prueba del harness, no un secreto

n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", sys.argv[2] if len(sys.argv) > 2 else "replay-llm.db")
if os.path.exists(db):
    os.remove(db)
mp = pytest.MonkeyPatch()
mp.setenv("LLM_MODELO", os.environ.get("LLM_MODELO", "qwen2.5:1.5b"))
a = Agente(mp, db)
print(json.dumps(a.c.get("/salud").json()["llm"], ensure_ascii=False))
a.c.post("/iniciar", headers=H)
for f in FECHAS[:n]:
    r = a.vela(f).json()
    print(f, r.get("accion_siguiente"), "|", r.get("motivo"), "|", [o["lado"] + ":" + o["estado"] for o in r.get("ordenes", [])])
print("errores llm:", a.sql("SELECT COUNT(*) FROM errores WHERE etapa='llm'")[0][0], "· db:", db)
