# Evidencia de T4 · Avance 2 (y repetición de 3 y 5) · 26-nov-2026

Sesión de Colab de la cuenta de Enrique (`colab whoami`: 193088-0@iberoleon.edu.mx), creada con `colab new -s econ-t4 --gpu T4` y cerrada con `colab stop -s econ-t4` (`colab sessions`: «No active sessions found»).

## GPU vista
`nvidia-smi` dentro de la VM (celda 1 de `avance2_t4_output.ipynb`; también `resultados/outputs/nvidia_smi.txt`):
`Tesla T4 · 15360 MiB · Driver 580.82.07 · CUDA 13.0`. PyTorch `2.14.1+cu130`, Python 3.13.16: `cuda disponible: True | device: cuda | GPU: Tesla T4`.
Operación de prueba en GPU: `PyTorch ve: Tesla T4 | operación de prueba en cuda:0: suma=32553.3 en 0.005 s`.
Las 10 corridas de `experimentos.csv` dicen `dispositivo=cuda:0`, `gpu=Tesla T4`.
Las 9 comprobaciones finales salen «OK», incluida «entrenamiento en T4».

## Tiempos
- Entrenamiento total de las 10 corridas (suma de `segundos`): **18.1 s en T4** frente a 32.1 s en CPU (prueba `avance2/prueba_cpu_150`, caja de 6 núcleos). Las LSTM ganan (2.0 s vs 4.1-7.6 s); las MLP son iguales (~1.5 s): son redes muy chicas, la GPU no cambia mucho.
- Celda más larga: el entrenamiento, 18.4-25.5 s. Cuaderno completo con `colab exec`: 53 s de pared. Cada celda imprime `[tiempo celda] N s`. En la 2.ª corrida de Avance 2 (la guardada) esas líneas salen duplicadas porque el gancho se registró dos veces en el mismo kernel; los valores son los mismos.
- Avance 3: ~2 s de cómputo por todo el cuaderno; Avance 5: ~1.7 s. No usan GPU (sklearn); se corrieron en la misma VM T4 y su celda 1 muestra `Tesla T4, 15360 MiB`.

## Métricas: T4 vs CPU (RMSE de VA, media de 3 semillas)
| Modelo | CPU 150 épocas (`prueba_cpu_150`) | T4 (esta corrida) |
|---|---|---|
| Cero | 0.024342 | 0.024342 |
| Regresión lineal | 0.024258 | 0.024258 |
| MLP (16) | 0.024280 | 0.024280 |
| LSTM | 0.024295 (16 neuronas en T4) / 0.024292 (32 en CPU) | 0.024295 (16 neuronas) |
Elegido: **Regresión lineal** en ambas. Mismas épocas de parada y mejores épocas en las 10 corridas; la mejor LSTM cambia de 32 a 16 neuronas por una diferencia de 3e-6. El resultado sigue: ninguna red supera a la lineal en VA; MLP y LSTM mejoran a cero 0.26 % y 0.19 %. `seleccion.json` ahora dice `modo: t4`.
- Avance 3 con la selección de T4: regla δ=0.05 %, +32.54 % neto en VA, 101 operaciones, no supera comprar y mantener (+72.91 %): idéntico a la prueba en CPU.
- Avance 5 con la selección de T4: B (rezagos+indicadores) RMSE VA 0.024228 vs A 0.024258; pronóstico del 5-nov: -0.21 %; `modo_avance2: t4`. Cambios solo en el decimal 15 (versiones de numpy/pandas/sklearn de Colab).

## Unidades de Colab
`colab usage`: antes 198.20, después 198.10 → **0.10 unidades** gastadas (sesión T4 de pocos minutos de cómputo, incluidas las dos corridas del Avance 2 y las de 3 y 5).

## Archivos
- `avance2/entrega_t4/`: `avance2_t4.ipynb` (entrada), `avance2_t4_output.ipynb` y `.html` (ejecutados), `resultados/` (outputs, figures).
- `avance3/entrega_t4/` y `avance5/entrega_t4/`: lo mismo.

## Qué cambié respecto al cuaderno original (copia, original intacto)
Celda nueva al inicio (nvidia-smi, device, tiempos por celda); `EN_COLAB = False` en el Avance 2 para no montar Drive (checkpoints en /content, sin copia a Drive; la §10 imprime «Fuera de Colab»); insumos subidos con `colab upload` (en 3 y 5 con `seleccion_avance2.json` y `experimentos_avance2.csv` de esta corrida T4). Lógica sin tocar.

## Límites
Los checkpoints no se descargaron (no hay copia a Drive); las salidas y figuras sí. La evidencia vale como sesión de su cuenta, pero la sube Enrique a Moodle. El incidente de la 1.ª corrida del Avance 2 (hook de tiempos sin inicializar, imprimía un traceback en la celda 1) se corrigió y se repitió completa; la guardada es la 2.ª.
