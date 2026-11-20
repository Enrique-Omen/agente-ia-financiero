"""Exporta el modelo final del Avance 5 (versión B, entrenado solo con TR) y sus escaladores a modelo/v1/.
Uso (desde agente/backend): python modelo/exportar.py
Mismo procedimiento que la celda 5 del cuaderno del Avance 5; comprueba que el pronóstico al cierre de la última vela
coincide con avance5/outputs/pronostico_futuro.json. Si el Avance 2 en T4 elige una red, este script se detiene."""
import hashlib, json, os, platform, sys
import joblib, numpy as np, pandas as pd, sklearn
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from app.variables import COLUMNAS, VENTANA, variables  # noqa: E402

AV5 = os.path.join(AQUI, "../../../avance5/")
VERSION = "v1"
SALIDA = os.path.join(AQUI, VERSION)

seleccion = json.load(open(AV5 + "outputs/seleccion_avance2.json"))
if not seleccion["elegido"].startswith("Regresión lineal"):
    raise SystemExit(f"El Avance 2 eligió {seleccion['elegido']}: falta exportar la red (este script solo cubre la lineal).")
resumen = json.load(open(AV5 + "outputs/resumen.json"))
assert resumen["final"].startswith("B"), "La versión final del Avance 5 ya no es B: revisa COLUMNAS"

precios = pd.read_csv(AV5 + "data/processed/btcusdt_1d_auditado.csv", parse_dates=["fecha"]).set_index("fecha").sort_index()
datos = pd.read_csv(AV5 + "data/processed/ventanas_btcusdt_1d.csv", parse_dates=["fecha_emision"])
sma = precios.close.rolling(VENTANA, min_periods=VENTANA).mean()
ind = pd.DataFrame({"dist_sma20": precios.close / sma - 1,
                    "vol20": precios.close.pct_change().rolling(VENTANA, min_periods=VENTANA).std(ddof=1)})
datos = datos.merge(ind, left_on="fecha_emision", right_index=True, how="left", validate="1:1")
TR = datos[(datos.conjunto == "TR") & datos[COLUMNAS].notna().all(axis=1)]

escX, escY = StandardScaler().fit(TR[COLUMNAS]), StandardScaler().fit(TR[["y"]])
lineal = LinearRegression().fit(escX.transform(TR[COLUMNAS]), escY.transform(TR[["y"]]).ravel())

# Control: el pronóstico del cuaderno (última vela del dataset) con las variables calculadas por app.variables
control = json.load(open(AV5 + "outputs/pronostico_futuro.json"))
fila = variables(precios.close)
assert str(fila.index[0].date()) == control["emitido_al_cierre_de"]
est = float(escY.inverse_transform(lineal.predict(escX.transform(fila[COLUMNAS])).reshape(-1, 1))[0, 0])
assert abs(est - control["rendimiento_estimado"]) < 1e-12, f"{est} ≠ {control['rendimiento_estimado']} del cuaderno"

os.makedirs(SALIDA, exist_ok=True)
joblib.dump({"escX": escX, "escY": escY, "modelo": lineal, "columnas": COLUMNAS}, os.path.join(SALIDA, "modelo.joblib"))
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
meta = {"version": VERSION, "modelo": seleccion["elegido"], "variables": resumen["final"], "columnas": COLUMNAS,
        "objetivo": "rendimiento simple del día siguiente (vela diaria UTC de BTCUSDT en MEXC)",
        "entrenado_con": f"TR: {len(TR)} ejemplos, {TR.fecha_emision.min().date()} a {TR.fecha_emision.max().date()}",
        "modo_avance2": seleccion["modo"], "RMSE_VA": resumen["RMSE_VA"][resumen["final"]], "RMSE_TE": resumen["RMSE_TE"],
        "control": {"vela": control["emitido_al_cierre_de"], "rendimiento_estimado": est},
        "sha256_datos": {f: sha(AV5 + "data/processed/" + f) for f in ["btcusdt_1d_auditado.csv", "ventanas_btcusdt_1d.csv"]},
        "versiones": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                      "scikit-learn": sklearn.__version__, "joblib": joblib.__version__}}
json.dump(meta, open(os.path.join(SALIDA, "meta.json"), "w"), ensure_ascii=False, indent=1)
print(f"{VERSION}: {len(TR)} ejemplos TR · control {control['emitido_al_cierre_de']} → {est:+.6%} (= cuaderno) · {SALIDA}")
