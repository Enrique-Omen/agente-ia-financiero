"""Ciclo programado (§15): una vez al día, a las 00:05 UTC (la vela diaria de MEXC ya cerró), llama a POST /ciclo del backend.
Uso: python programador.py [--una-vez]   (la clave sale del entorno del servidor; BACKEND_URL por defecto http://127.0.0.1:8765)
Cada llamada queda en datos/programador.log con su hora UTC y el código HTTP; el backend es quien registra decisión, órdenes y errores.
No acelera la frecuencia: nunca llama dos veces en el mismo día UTC (y, si lo hiciera, el backend responde 409 por vela repetida)."""
import datetime as dt, os, sys, time, urllib.error, urllib.request

HORA = dt.time(0, 5)
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", "programador.log")


def proxima(ahora):
    """Próximo disparo (UTC) estrictamente posterior a `ahora`."""
    t = dt.datetime.combine(ahora.date(), HORA, tzinfo=dt.timezone.utc)
    return t if t > ahora else t + dt.timedelta(days=1)


def disparar(url, clave):
    req = urllib.request.Request(f"{url}/ciclo", b"", {"X-API-Key": clave}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status
    except urllib.error.HTTPError as e:   # 401, 409 (vela repetida o en pausa), 503 (datos): el backend ya lo registró
        return e.code
    except OSError:
        return 0                           # backend caído: se anota y se intenta en el siguiente día


def main():
    url, clave = os.environ.get("BACKEND_URL", "http://127.0.0.1:8765"), os.environ["AGENTE_API_KEY"]
    while True:
        if "--una-vez" not in sys.argv:
            time.sleep(max(0, (proxima(dt.datetime.now(dt.timezone.utc)) - dt.datetime.now(dt.timezone.utc)).total_seconds()))
        codigo = disparar(url, clave)
        with open(LOG, "a") as f:
            f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} POST /ciclo -> {codigo}\n")
        if "--una-vez" in sys.argv:
            return codigo


if __name__ == "__main__":
    main()
