"""El programador dispara una vez al día a las 00:05 UTC y devuelve el código HTTP sin lanzar excepciones."""
import datetime as dt
import programador

U = dt.timezone.utc


def test_proxima_es_00_05_utc_de_hoy_o_de_mañana():
    assert programador.proxima(dt.datetime(2026, 11, 26, 0, 0, tzinfo=U)) == dt.datetime(2026, 11, 26, 0, 5, tzinfo=U)
    assert programador.proxima(dt.datetime(2026, 11, 26, 0, 5, tzinfo=U)) == dt.datetime(2026, 11, 27, 0, 5, tzinfo=U)
    assert programador.proxima(dt.datetime(2026, 11, 26, 23, 59, tzinfo=U)) == dt.datetime(2026, 11, 27, 0, 5, tzinfo=U)


def test_backend_caido_devuelve_0():
    assert programador.disparar("http://127.0.0.1:9", "x") == 0
