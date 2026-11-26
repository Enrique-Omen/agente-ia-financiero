# RUBRICA-CHECK · agente final (§16) y práctica · 26-nov-2026

Leyenda: **OK** = cumplido y probado en la caja (evidencia: archivo · comando · salida) · **solo Enrique** = depende de su sesión, con el paso exacto · **FALTA** = nada hecho.
Pruebas (comando en `backend/`): `python -m pytest -q` → `54 passed`. Frontend (en `frontend/`): `npm run build` → `✓ built`.

## A. Rúbrica del proyecto final (100 puntos, §16)
| Criterio (pts) | Subcriterio | Estado | Evidencia |
|---|---|---|---|
| Integración y modelo (15) | Modelo y escalador versionados (5) | OK | `backend/modelo/v1/modelo.joblib` + `meta.json` (versión, columnas, hash); `test_pronostico_igual_al_cuaderno` |
| | Ollama realmente local (5) | OK | `GET /salud` → `{"llm":{"modelo":"qwen3:1.7b","ollama":"0.40.14","url":"http://127.0.0.1:11434","hardware":"CPU x86_64 × 6"}}`; `test_salud_reporta_llm_local`; latencia en `datos/comparacion.csv` |
| | UI React y TypeScript funcional (5) | OK (sin captura de pantalla) | `frontend/src/App.tsx`; `npm run build` verde; con `vite preview` y la clave en el entorno, `curl localhost:4173/api/estado` y `/api/pronostico` devuelven JSON; la clave no aparece en `dist/assets/*.js` (0 coincidencias) |
| API privada y secretos (10) | Autenticación y rechazo (5) | OK | `test_clave_ausente_o_incorrecta_401`, `test_rutas_nuevas_piden_clave`; en vivo: `curl localhost:8765/estado` sin clave → `401` |
| | Secretos solo en servidor (5) | OK | `backend/entorno.ejemplo` y `frontend/entorno.ejemplo` sin valores; la clave del frontend sin prefijo `VITE_` (`frontend/vite.config.ts`); `test_sin_clave_en_servidor_no_arranca`. Nota: el archivo se llama `entorno.ejemplo`, no `.env.example`; para el nombre literal del protocolo: `git mv backend/entorno.ejemplo backend/.env.example` (y el del frontend) — solo Enrique o quien tenga permiso, la caja bloquea crear archivos con ese nombre |
| Datos MEXC y Paper (15) | Datos válidos y fechados (5) | OK | `app/mexc.py` valida activo, frecuencia, orden, antigüedad; `test_dato_atrasado_se_rechaza`, `test_huecos_o_desorden_se_rechazan`; en vivo vela 2026-11-25 (`datos/vivo-programador.db`) |
| | Simulador con saldo, costos y precisión (5) | OK | `app/paper.py`; `test_saldo_insuficiente_*`, `test_cantidad_redondeada_al_paso_del_exchange` |
| | Bloqueo de operaciones reales (5) | OK | `test_no_hay_ruta_de_ordenes` |
| Ciclo del agente (15) | Observación, herramientas y propuesta estructurada (5) | OK | `app/llm.py` (esquema pydantic, JSON forzado); `test_propuesta_valida_manda_y_riesgo_ejecuta` |
| | Validación de acciones (5) | OK | `test_propuesta_rechazada_cae_a_la_regla` (10 casos) |
| | Ciclo programado con evidencia (5) | OK | `backend/programador.py` (00:05 UTC, una vez al día); `test_programador.py`; `datos/programador.log`: `2026-11-26T19:54:49+00:00 POST /ciclo -> 200` con MEXC y Ollama reales (vela 2026-11-25, decisión `mantener` por el LLM, 57 s); un segundo `/ciclo` → `409` |
| Riesgo y control humano (10) | Límites deterministas (5) | OK | `app/riesgo.py`; `test_limite_de_perdida_detiene_*`, `test_limites_inmutables_y_validados` |
| | Iniciar, pausar y detener efectivos (5) | OK | `test_pausa_no_procesa_y_detener_bloquea_ordenes_sin_liquidar`; botones en la UI |
| Errores y persistencia (15) | Nueve escenarios con respuesta correcta (5) | OK | tabla de los nueve errores en `INFORME.md`, cada uno con su prueba |
| | Recuperación sin duplicados (5) | OK | `test_reinicio_recupera_estado_sin_duplicar`, `test_vela_duplicada_no_repite_orden` |
| | Bitácora trazable (5) | OK | tabla `errores` y `decisiones` en SQLite (`app/registro.py`); visibles en la UI y en `GET /estado` |
| Evaluación (10) | Comparación sin LLM / con LLM / pasiva (5) | OK | `datos/comparacion.csv` (20 velas, 50,000 USDT, costo 0 %) |
| | Métricas y límites interpretados (5) | OK | `INFORME.md` («¿Aporta valor el LLM?»: no en estas 20 velas) y README «Escalón 4b» |
| Entrega reproducible (10) | README y configuración sin secretos (5) | OK | `backend/README.md`, `entorno.ejemplo` |
| | Demostración y evidencia completa (5) | Parcial → **solo Enrique** el cierre | 20 ciclos con LLM real (replay marcado como tal, `datos/comparar-qwen3-1.7b.db`), ciclo en vivo con MEXC (`datos/vivo-programador.db`), nueve errores con pruebas. Para completar: en su máquina, `npm run dev` y tomar 1 captura de la UI con datos (la caja no tiene navegador de prueba del frontend verificado) |

Observación honesta: 20 ciclos «válidos» son un replay histórico (16-oct a 4-nov-2026) más 1 ciclo en vivo; el protocolo permite replay si se identifica como tal (así está). Más ciclos en vivo requieren esperar días reales: no se aceleran.

## B. Condición previa (§14): rúbrica de la práctica (100 puntos)
Fuente: protocolo §11. Estado según `PLAN.md` y los cuadernos de `../avances/`; solo lo de arriba (agente) lo volví a ejecutar hoy.
| Criterio (pts) | Estado |
|---|---|
| Datos, capítulos 7 y 11 (10) | OK en `avances/avance1_cap7.ipynb` (sin re-ejecutar hoy) |
| TR/VA/TE (15) | OK en `avance3.ipynb` |
| Referencias y modelos (12) | OK en cuaderno del Avance 2, corrida en CPU; MLP y LSTM «funcionales» se validan con la corrida real en Colab |
| **Uso efectivo de T4 (10)** | **solo Enrique**: abrir `avance2` en Colab con GPU T4, Entorno de ejecución → Cambiar tipo → T4, ejecutar todo, guardar el cuaderno con salidas (`nvidia-smi`, tiempos) y subirlo. Sin esa evidencia el apartado vale 0/10 |
| Validación y estudio técnico (12) | OK en `avance3.ipynb` y `avance5`; repetir tras T4 |
| Estimaciones y predicciones (12) | OK en `avance5` (pronóstico fechado); repetir tras T4 |
| Manejo de errores (15) | OK para el agente (sección A); «GPU y entrenamiento» (3) depende de la corrida en T4 → solo Enrique |
| Agente y simulación (9) | OK en `avance4` y `backend/` |
| Reproducibilidad (5) | OK (`README.md`, `requirements.txt`, pruebas) |

## C. Solo Enrique (pasos exactos)
1. **T4**: Colab → `avance2` → GPU T4 → ejecutar todo → guardar con salidas; repetir `avance3` y `avance5` con ese resultado.
2. **Captura MEXC (+20 %)**: captura de rendimiento de su cuenta, o confirmar con el profe que basta el Paper del agente (tarea 2133402).
3. **Subir** el repo y la tarea 2133401 a Moodle con su clic (la caja no sube nada ni hace `push`).
4. Opcional: `git mv backend/entorno.ejemplo backend/.env.example` y lo mismo en `frontend/`.
