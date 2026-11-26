# Informe breve · Agente de IA financiero (Paper) · 26-nov-2026

Sistema: React + TypeScript (Vite) → FastAPI con API key → modelo de regresión lineal del Avance 5 (`backend/modelo/v1`, escalador incluido) → Ollama local (qwen3:1.7b, 127.0.0.1, CPU) → riesgo determinista → Paper (50,000 USDT, costo 0 %, sin corto ni apalancamiento) → SQLite. No existe ninguna ruta de órdenes reales.

## Qué se midió (todo de corridas reales, comandos en `backend/README.md`)
| Medida | Resultado | Fuente |
|---|---|---|
| Pruebas automáticas | 54 passed (8.3 s), sin red y con Ollama simulado | `python -m pytest -q` en `backend/` |
| Ciclos válidos con LLM real | 20 (replay histórico 16-oct a 4-nov-2026): 4 comprar, 12 mantener, 4 vender, 0 respaldos, 0 rechazadas | `backend/datos/comparar-qwen3-1.7b.db` |
| Ciclo con MEXC en vivo | vela 2026-11-25 procesada por `POST /ciclo` (regla, sin LLM): estimado −0.0641 % ≤ δ → efectivo; el segundo `/ciclo` dio 409 «ya procesada» sin orden | corrida del 26-nov-2026 con el frontend como intermediario |
| Ciclo programado | `programador.py --una-vez` llamó a `/ciclo` y anotó el código HTTP en `datos/programador.log` (409 por vela repetida) | `backend/programador.py` |
| Latencia del LLM | media 15.6 s, máxima 38.9 s por decisión (CPU × 6, sin GPU) | `backend/datos/comparacion.csv` |

## Comparación §16 (mismas 20 velas, 50,000 USDT, costo 0 %)
| Estrategia | Rend. neto | Drawdown | Win Rate | Operaciones | Rechazadas | Respaldos | Latencia media |
|---|---|---|---|---|---|---|---|
| Sin LLM (regla Avance 3) | −0.47 % | 1.29 % | 25 % | 4 | 0 | — | — |
| Con LLM qwen3:1.7b | −0.47 % | 1.29 % | 25 % | 4 | 0 | 0 | 15.6 s |
| Comprar y mantener | −1.352 % | 8.653 % | 0 % | 1 | 0 | — | — |

**¿Aporta valor el LLM?** No, en estas 20 velas. Sin la señal en los datos acertaba 35 % (intento 1, rend. −1.369 %, drawdown 8.09 %); con `accion_sugerida` copia la regla y da el mismo resultado, más 15 s de latencia por decisión. Lo único que añade es la justificación en texto. Límites: 20 velas y un periodo a la baja (el pasivo pierde 1.35 %); no es evidencia de rentabilidad ni de que otro modelo no aporte. El modelo qwen2.5:1.5b (5-nov) quedó descartado: hoy produce texto sin sentido en este Ollama.

## Los nueve errores (§15): respuesta correcta, evento registrado, sin orden indebida
| Error | Prueba automática | Resultado |
|---|---|---|
| API de MEXC caída o con límite (429) | `test_backend.py::test_mexc_caida_o_con_limite_error_controlado` | 3 intentos con espera creciente, luego 503 con motivo y error `datos` registrado |
| Dato atrasado | `test_backend.py::test_dato_atrasado_se_rechaza` | 503, no se decide |
| Ollama detenido | `test_llm.py::test_propuesta_rechazada_cae_a_la_regla` (casos «Ollama no respondió», tiempo límite, corte) y corrida real `datos/replay-llm-ollama-detenido.db` | error `llm` y decide la regla («respaldo») |
| JSON inválido | mismo test (JSON roto, acción fuera de catálogo, campo extra, símbolo o fecha distintos, vender sin posición) | error `llm` y regla |
| Clave incorrecta | `test_backend.py::test_clave_ausente_o_incorrecta_401` | 401 |
| Saldo insuficiente | `test_ciclo.py::test_saldo_insuficiente_en_el_ciclo` | orden rechazada y registrada |
| Evento duplicado | `test_ciclo.py::test_vela_duplicada_no_repite_orden` | 409 sin orden (también en vivo, arriba) |
| Reinicio del backend | `test_ciclo.py::test_reinicio_recupera_estado_sin_duplicar` | cartera, estado y decisión salen de SQLite |
| Botón de detención | `test_ciclo.py::test_pausa_no_procesa_y_detener_bloquea_ordenes_sin_liquidar` | bloquea órdenes sin liquidar; `/liquidar` es aparte |

## Pendiente (no lo puede hacer la caja)
Evidencia de entrenamiento en T4 (Colab, sesión de Enrique) y captura de rendimiento de MEXC; subida a Moodle. Ver `RUBRICA-CHECK.md`.
