"""Registro en SQLite: velas procesadas (una por fecha), decisiones, órdenes, patrimonio, errores y el estado del agente.
El estado completo (cartera, estado, decisión pendiente) se recupera de aquí al reiniciar."""
import sqlite3, threading
from datetime import datetime, timezone

from app.paper import CAPITAL, Cartera

ESQUEMA = """
CREATE TABLE IF NOT EXISTS velas (fecha TEXT PRIMARY KEY, apertura REAL, cierre REAL, procesada TEXT);
CREATE TABLE IF NOT EXISTS decisiones (fecha TEXT PRIMARY KEY REFERENCES velas, rendimiento_estimado REAL, accion TEXT, motivo TEXT);
CREATE TABLE IF NOT EXISTS ordenes (id INTEGER PRIMARY KEY, fecha TEXT, lado TEXT, cantidad REAL, precio REAL, estado TEXT, motivo TEXT);
CREATE TABLE IF NOT EXISTS patrimonio (fecha TEXT PRIMARY KEY REFERENCES velas, efectivo REAL, unidades REAL, precio REAL, patrimonio REAL);
CREATE TABLE IF NOT EXISTS errores (id INTEGER PRIMARY KEY, momento TEXT, etapa TEXT, detalle TEXT);
CREATE TABLE IF NOT EXISTS control (clave TEXT PRIMARY KEY, valor TEXT);
INSERT OR IGNORE INTO control VALUES ('estado', 'pausado');
INSERT OR IGNORE INTO control VALUES ('efectivo', '{capital!r}');
INSERT OR IGNORE INTO control VALUES ('unidades', '0.0');
"""


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Registro:
    def __init__(self, ruta):
        self.db = sqlite3.connect(ruta, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(ESQUEMA.format(capital=CAPITAL))
        self.candado = threading.RLock()   # una escritura o lectura a la vez sobre la conexión compartida

    def uno(self, sql, *args):
        return self.db.execute(sql, args).fetchone()

    def estado(self):
        return self.uno("SELECT valor FROM control WHERE clave='estado'")["valor"]

    def poner_estado(self, valor):
        self.db.execute("UPDATE control SET valor=? WHERE clave='estado'", (valor,))

    def error(self, etapa, detalle):
        self.db.execute("INSERT INTO errores (momento, etapa, detalle) VALUES (?,?,?)", (ahora(), etapa, str(detalle)))

    def ya_procesada(self, fecha):
        return self.uno("SELECT 1 FROM velas WHERE fecha=?", fecha) is not None

    def cartera(self):
        v = dict(self.db.execute("SELECT clave, valor FROM control").fetchall())
        return Cartera(float(v["efectivo"]), float(v["unidades"]))

    def ultima_decision(self):
        return self.uno("SELECT * FROM decisiones ORDER BY fecha DESC LIMIT 1")

    def guardar(self, cartera, ordenes, fecha=None, vela=None, decision=None, freno=None):
        """Órdenes, cartera y (si hay vela) vela, patrimonio y decisión en una sola transacción: o queda todo o nada.
        ordenes: dicts con fecha, lado, cantidad, precio, estado, motivo. vela: (apertura, cierre). decision: (estimado, accion, motivo).
        freno: motivo para detener el agente al cerrar la vela (límite de pérdida), en la misma transacción."""
        with self.db:
            self.db.execute("BEGIN")
            for o in ordenes:
                self.db.execute("INSERT INTO ordenes (fecha, lado, cantidad, precio, estado, motivo) VALUES "
                                "(:fecha, :lado, :cantidad, :precio, :estado, :motivo)", o)
            self.db.executemany("UPDATE control SET valor=? WHERE clave=?",
                                [(repr(cartera.efectivo), "efectivo"), (repr(cartera.unidades), "unidades")])
            if vela:
                apertura, cierre = vela
                self.db.execute("INSERT INTO velas VALUES (?,?,?,?)", (fecha, apertura, cierre, ahora()))
                self.db.execute("INSERT INTO patrimonio VALUES (?,?,?,?,?)",
                                (fecha, cartera.efectivo, cartera.unidades, cierre, cartera.patrimonio(cierre)))
                self.db.execute("INSERT INTO decisiones VALUES (?,?,?,?)", (fecha, *decision))
            if freno:
                self.poner_estado("detenido")
                self.error("riesgo", freno)
