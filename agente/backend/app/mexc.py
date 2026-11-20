"""Velas diarias públicas de MEXC (sin clave), solo lectura. Aquí no existe ninguna ruta de órdenes."""
import http.client, json, time, urllib.request
import numpy as np, pandas as pd

FUENTE = "https://api.mexc.com/api/v3/klines"
SIMBOLOS = {"BTCUSDT"}
DIA_MS = 86_400_000


class ErrorDatos(Exception):
    """Datos no válidos o fuente caída: el ciclo no decide con esto."""


def pedir_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def velas(simbolo, max_antiguedad_h=36, limite=30, reintentos=3, espera=0.5, ahora_ms=None):
    """Velas 1d cerradas y validadas (DataFrame indexado por fecha UTC). Reintenta con espera creciente."""
    if simbolo not in SIMBOLOS:
        raise ErrorDatos(f"Símbolo no permitido: {simbolo}")
    url = f"{FUENTE}?symbol={simbolo}&interval=1d&limit={limite}"
    for intento in range(reintentos):
        try:
            crudo = pedir_json(url)
            break
        except (OSError, http.client.HTTPException, ValueError) as e:   # URLError, HTTPError (429, 5xx), cortes, timeout
            causa = getattr(e, "code", None) or e
            if intento == reintentos - 1:
                raise ErrorDatos(f"MEXC sin respuesta tras {reintentos} intentos ({causa})") from e
            time.sleep(espera * 2 ** intento)
    ahora_ms = ahora_ms if ahora_ms is not None else int(time.time() * 1000)
    try:
        df = pd.DataFrame([f[:7] for f in crudo], columns=["open_time", "open", "high", "low", "close", "volume", "close_time"])
        df = df.astype({"open_time": "int64", "close_time": "int64", "open": float, "high": float, "low": float, "close": float, "volume": float})
    except (TypeError, ValueError) as e:
        raise ErrorDatos(f"Respuesta de MEXC con formato inesperado: {e}") from e
    df = df[df.close_time <= ahora_ms]                       # la vela del día en curso no es definitiva
    if len(df) == 0:
        raise ErrorDatos("MEXC no devolvió velas cerradas")
    if not (df.open_time.diff().dropna() == DIA_MS).all():
        raise ErrorDatos("Velas fuera de orden, repetidas o con huecos")
    if (df.open_time % DIA_MS != 0).any() or ((df.close_time - df.open_time) != DIA_MS).any():
        raise ErrorDatos("Frecuencia distinta de 1 día UTC")
    precios = df[["open", "high", "low", "close", "volume"]]
    fuera = (df[["open", "close"]].max(axis=1) > df.high) | (df[["open", "close"]].min(axis=1) < df.low)
    if not np.isfinite(precios).all().all() or (df.low <= 0).any() or fuera.any() or (df.volume < 0).any():
        raise ErrorDatos("Valores no válidos en las velas")
    antiguedad_h = (ahora_ms - df.close_time.iloc[-1]) / 3_600_000
    if antiguedad_h > max_antiguedad_h:
        raise ErrorDatos(f"Dato atrasado: la última vela cerró hace {antiguedad_h:.1f} h (máximo {max_antiguedad_h} h)")
    df.index = pd.to_datetime(df.open_time, unit="ms").rename("fecha")
    return df[["open", "high", "low", "close", "volume"]]
