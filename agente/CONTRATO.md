# Contrato del agente (protocolo §14-§16) · qué entra y qué sale de cada pieza

Fuente: `../2026-11-10-cdeconomia-agente-primer-avance/enunciado/2133398/p.txt` (líneas 1887-2260). Escalón 1 = backend con modelo y pronóstico. Escalón 2 = Paper + riesgo + SQLite con la regla del Avance 3 (sin LLM).

## Contrato de variables (igual que el Avance 5, versión final B)
| Columna | Definición al cierre de la vela *t* (día UTC) |
|---|---|
| `r_lag0` … `r_lag19` | rendimiento simple `close_t-k / close_t-k-1 − 1`, k = 0…19 |
| `dist_sma20` | `close_t / mean(close_t-19..t) − 1` |
| `vol20` | desviación estándar muestral (ddof 1) de `r_lag0..19`, sin anualizar |
Salida del modelo: rendimiento simple estimado de *t*+1. Escaladores `StandardScaler` (X e y) ajustados solo con TR.
Se necesitan 21 cierres diarios consecutivos y cerrados. Modelo: el que el Avance 2 elija con VA (hoy regresión lineal, corrida de prueba en CPU).

## Piezas
| Pieza | Entra | Sale | Estado |
|---|---|---|---|
| `backend/modelo/exportar.py` | CSV de los Avances 1 y 5 | `modelo/v1/modelo.joblib` + `meta.json` (versión, columnas, hash de datos, pronóstico de control) | escalón 1 |
| `backend/app/mexc.py` | símbolo, intervalo `1d` | velas cerradas validadas (activo, frecuencia, orden, antigüedad) o `ErrorDatos` | escalón 1 |
| `backend/app/variables.py` | velas | una fila con las 22 columnas del contrato | escalón 1 |
| `backend/app/main.py` (FastAPI) | cabecera `X-API-Key` | `/salud` (sin clave), `/pronostico` (con clave) | escalón 1 |
| `backend/app/llm.py` (Ollama local, 127.0.0.1) | datos estructurados (pronóstico, variables en %, cartera, límites) | `{accion ∈ comprar/mantener/vender, simbolo, fecha_vela, justificacion ≤ 300}` validado con pydantic; si falla, regla del Avance 3 marcada «respaldo» | escalón 3 |
| `backend/app/riesgo.py` (determinista) | orden + estado + config | aprobada / rechazada con motivo; límites inmutables (`frozen`), leídos al arrancar; pérdida del día > máximo → detenido | escalón 2 |
| `backend/app/paper.py` + `mercado.json` | orden aprobada | efectivo, posición, patrimonio. 50,000 USDT, costo 0.0 %, sin corto ni apalancamiento; cantidad al paso de MEXC (0.000001 BTC, leído 5-nov-2026); apertura de t+1; deslizamiento 0 (supuesto) | escalón 2 |
| `backend/app/registro.py` (SQLite) | todo lo anterior | velas (única por fecha), decisiones, órdenes, patrimonio, errores, estado y cartera; una transacción por vela | escalón 2 |
| UI React + TS | API del backend | activo, fecha, pronóstico, indicadores, acción, motivo, riesgo, posición, patrimonio; iniciar/pausar/detener | pendiente |

## Ciclo (§15)
1 velas cerradas y validadas → 2 variables + pronóstico → 3 Ollama propone → 4 validar JSON → 5 riesgo → 6 Paper + registro (una vez por vela) → 7 UI y esperar la siguiente vela.

## Nueve errores a demostrar (§15) y dónde se atienden
| Error | Pieza | Escalón 1 |
|---|---|---|
| API de MEXC sin respuesta o con límite (429) | mexc.py: reintentos con espera creciente, luego 503 | sí |
| Dato atrasado | mexc.py: última vela cerrada más vieja que `MAX_ANTIGUEDAD_H` → 503 | sí |
| Ollama detenido | llm.py: error `llm` registrado → decide la regla («respaldo») | escalón 3 |
| JSON inválido | llm.py: pydantic (acción, campos extra, símbolo y fecha) → error `llm` y regla | escalón 3 |
| Clave incorrecta | main.py: 401 | sí |
| Saldo insuficiente | paper.py: orden rechazada y registrada | escalón 2 |
| Evento duplicado | registro.py: vela única → 409, sin orden | escalón 2 |
| Reinicio del backend | registro.py: cartera, estado y decisión pendiente salen de SQLite | escalón 2 |
| Botón de detención | `/detener` (bloquea, no liquida) y `/liquidar` aparte; UI pendiente | escalón 2 (backend) |

## Configuración (solo en el servidor; `.env.example` sin valores)
`AGENTE_API_KEY` (obligatoria; sin ella el backend no arranca), `MAX_ANTIGUEDAD_H` (36), `SIMBOLO` (BTCUSDT), `EXPOSICION_MAX` (1.0), `PERDIDA_DIARIA_MAX` (0.10), `AGENTE_DB` (datos/agente.db), `OLLAMA_URL` (http://127.0.0.1:11434), `LLM_MODELO` (qwen2.5:1.5b; vacío = sin LLM), `LLM_TIMEOUT_S` (60). Órdenes reales: no existe ninguna ruta que las envíe.
