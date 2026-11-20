"""Contrato de variables: la misma definición del entrenamiento (Avance 5, versión B). Ver agente/CONTRATO.md."""
import pandas as pd

VENTANA = 20
COLUMNAS = [f"r_lag{i}" for i in range(VENTANA)] + ["dist_sma20", "vol20"]


def variables(cierres: pd.Series) -> pd.DataFrame:
    """cierres: Serie diaria indexada por fecha, ordenada, sin huecos. Devuelve 1 fila (índice = fecha de la última vela)."""
    c = cierres.iloc[-(VENTANA + 1):]
    if len(c) < VENTANA + 1:
        raise ValueError(f"Hacen falta {VENTANA + 1} cierres; hay {len(c)}")
    r = c.pct_change()
    fila = {**{f"r_lag{i}": r.iloc[-1 - i] for i in range(VENTANA)},
            "dist_sma20": c.iloc[-1] / c.iloc[-VENTANA:].mean() - 1,
            "vol20": r.iloc[-VENTANA:].std(ddof=1)}
    return pd.DataFrame([fila], index=[c.index[-1]])[COLUMNAS]
