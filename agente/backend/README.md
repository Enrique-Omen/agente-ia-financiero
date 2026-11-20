# Backend del agente (escalón 3: modelo + pronóstico + Ollama local + Paper, riesgo y SQLite)

FastAPI que lee velas diarias **públicas** de MEXC (sin clave de trading), calcula las mismas variables del entrenamiento
(`app/variables.py`, contrato en `../CONTRATO.md`) y devuelve el pronóstico del modelo final del Avance 5. No existe ninguna ruta de órdenes.

## Instalar y correr
```bash
pip install -r requirements.txt
python modelo/exportar.py            # regenera modelo/v1/ y comprueba que coincide con el cuaderno del Avance 5
python -m pytest -q                  # 51 pruebas, sin red y con Ollama simulado (-m replay: solo el replay de 20 velas)
python replay_llm.py 5               # 5 velas con Ollama REAL → datos/replay-llm.db
# En el servidor: copiar entorno.ejemplo como .env, poner una clave larga y cargarla en el entorno
uvicorn app.main:crear_app --factory --port 8765
curl localhost:8765/salud
curl -H "X-API-Key: <tu clave>" localhost:8765/pronostico
curl -XPOST -H "X-API-Key: <tu clave>" localhost:8765/iniciar     # arranca en pausa
curl -XPOST -H "X-API-Key: <tu clave>" localhost:8765/ciclo       # una vez al día, después de las 00:00 UTC
```
Documentación de la API: `http://localhost:8765/docs`.

## Qué responde
| Ruta | Clave | Respuesta |
|---|---|---|
| `/salud` | no | estado, versión del modelo y del LLM (modelo, versión de Ollama, URL local, hardware) |
| `/pronostico` | `X-API-Key` | vela usada (última cerrada), cierre, rendimiento estimado, las 22 variables, versión, latencia |
| — | ausente o incorrecta | 401 |
| — | MEXC caída o con límite (3 intentos, espera 0.5 s y 1 s), dato atrasado (> `MAX_ANTIGUEDAD_H`), velas con huecos, desorden o valores imposibles | 503 con el motivo; no se decide |

La vela del día en curso se descarta (MEXC la manda aunque no haya cerrado). Prueba del 5-nov-2026: `/pronostico` con MEXC en vivo
dio −0.21133 % para la vela del 4-nov, igual al cuaderno del Avance 5 (diferencia 4.6e-17).

## Ciclo Paper
`POST /ciclo` toma la última vela cerrada *t*: ejecuta a su **apertura** la decisión del cierre de *t*−1, valora al **cierre** de *t*
y decide para *t*+1. Todo queda en SQLite en una sola transacción.

**Decisión (escalón 3).** Ollama local (`LLM_MODELO`, por defecto `qwen2.5:1.5b`, en 127.0.0.1) recibe datos estructurados
(símbolo, fecha, cierre, pronóstico y variables en %, cartera, límites) y propone `{accion, simbolo, fecha_vela, justificacion}`
con salida JSON forzada por esquema; `app/llm.py` la valida con pydantic (acción ∈ comprar/mantener/vender, campos extra
prohibidos, símbolo y fecha iguales a los pedidos). Ollama caído, sin respuesta en `LLM_TIMEOUT_S`, propuesta inválida o con una acción imposible para la cartera → error
registrado (`errores.etapa = llm`) y decide la regla del Avance 3 (comprar si el estimado > 0.05 %; si no, efectivo), con
motivo «respaldo · …». `LLM_MODELO=` vacío → solo la regla (para la comparación sin/con LLM del §16). El LLM no ve claves
ni cambia límites; solo puede elegir entre las acciones posibles (sin posición: comprar o mantener; con posición: mantener o vender), forzadas por el esquema y revisadas otra vez; riesgo.py y el Paper se aplican igual. La consulta corre fuera del candado de la base: `/detener` y `/estado` responden mientras piensa, y `/liquidar` responde 409 hasta que el ciclo termine. Ollama no tiene autenticación: escucha solo en la caja y el
único camino es este backend, con `X-API-Key`.

| Ruta | Qué hace |
|---|---|
| `POST /iniciar`, `/pausar` | activo / en pausa (en pausa `/ciclo` responde 409 y no procesa). Arranca en pausa |
| `POST /detener` | bloquea toda orden (quedan registradas como rechazadas); no liquida. También se activa solo si un día pierde más que `PERDIDA_DIARIA_MAX` |
| `POST /liquidar` | acción aparte: vende toda la posición al último cierre registrado |
| `GET /estado` | estado, cartera, última vela y decisión, últimas 20 órdenes y errores, límites, datos de mercado |

Supuestos: 50,000 USDT, costo 0.0 %, sin corto ni apalancamiento, deslizamiento 0, cantidad redondeada hacia abajo a 0.000001 BTC
(`app/mercado.json`, leído de `/api/v3/exchangeInfo` el 5-nov-2026). Vela repetida → 409 sin orden. Reinicio → el estado sale de SQLite.

Replay del 5-nov-2026 (`pytest -m replay`): 20 velas, 16-oct a 4-nov-2026, por el ciclo completo. 8 órdenes (4 compras, 4 ventas);
patrimonio igual a la regla del Avance 3 con 50,000 y 0 % (diferencia máxima 0.0007 USDT, por redondear la cantidad).

Ollama real del 5-nov-2026 (qwen2.5:1.5b, Ollama 0.40.14, CPU aarch64 × 2 sin GPU):
- `python replay_llm.py 5` → `datos/replay-llm.db` y `.txt`: 5 velas (16 a 20-oct), 0 errores, 4 órdenes ejecutadas, 13-45 s por propuesta.
- Con Ollama detenido (`systemctl stop ollama`) → `datos/replay-llm-ollama-detenido.db` y `.txt`: 2 velas decididas por la regla («respaldo»), 2 errores `llm`.
- En vivo (MEXC real, vela del 4-nov) → `datos/vivo-llm.db` y `.txt`: propuesta en 35 s.
Observación: el modelo de 1.5b justifica con cifras correctas pero decide al revés a veces (p. ej. «comprar» con estimado −0.211 %).
Falta medir uno mayor y la comparación sin LLM / con LLM / comprar y mantener del §16.

## Comparación del §16 (escalón 4, 5-nov-2026)
`python comparar.py qwen2.5:1.5b qwen2.5:3b` (≈ 25 min en la caja) → `datos/comparacion.csv`, `datos/comparacion.txt` y una base por
estrategia (`datos/comparar-*.db`). Mismas 20 velas (16-oct a 4-nov-2026), 50,000 USDT, costo 0 %, todo por el ciclo completo.

| Estrategia | Rend. neto | Drawdown máx. | Win Rate | Operaciones | Rechazadas | Respaldos LLM | Coherencia con el pronóstico | Latencia media / máx. |
|---|---|---|---|---|---|---|---|---|
| Sin LLM (regla Avance 3) | −0.47 % | 1.29 % | 25 % | 4 | 0 | — | 100 % | — |
| Con LLM qwen2.5:1.5b | −1.32 % | 5.94 % | 40 % | 10 | 0 | 0 | 50 % | 15.0 s / 19.4 s |
| Con LLM qwen2.5:3b | −3.98 % | 8.08 % | 0 % | 1 | 0 | 2 (tiempo límite 60 s) | 30 % | 30.5 s / 44.2 s |
| Comprar y mantener | −1.35 % | 8.65 % | 0 % | 1 | 0 | — | — | — |

Coherencia = la posición que pide la acción (comprar, o mantener con posición) coincide con la que pide el pronóstico (estimado > δ 0.05 %).
Operaciones = viajes compra → venta; el abierto al final se valora al último cierre.

**Hallazgo.** Ninguno de los dos modelos usa el pronóstico: el 1.5b alterna comprar y vender cada día sin importar el signo, y el 3b compra
el primer día y luego solo mantiene. **Modelo elegido: qwen2.5:1.5b** (el doble de rápido, 0 tiempos agotados, más coherente); el 7b no se
probó: con 2 CPU sin GPU la latencia crece con el tamaño (15 s → 30 s de 1.5b a 3b) y pasaría del límite de 60 s (estimado, no medido).
Antes de la UI hay que subir la coherencia (siguiente escalón).
