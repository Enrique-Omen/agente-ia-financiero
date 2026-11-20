"""Paper trading (simulado): 50,000 USDT, costo 0.0 %, solo contado (sin corto ni apalancamiento). No existe envío al exchange.
Ejecución: la decisión tomada al cierre de la vela t se ejecuta al precio de apertura de t+1.
Supuesto de deslizamiento: 0 (se llena completo a la apertura). En el mercado real el precio de llenado sería distinto."""
import json, os
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

CAPITAL = 50_000.0
COSTO = 0.0
MERCADO = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mercado.json")))


class OrdenRechazada(Exception):
    """La orden no se ejecuta; el motivo se registra."""


@dataclass
class Cartera:
    efectivo: float = CAPITAL
    unidades: float = 0.0

    def patrimonio(self, precio):
        return self.efectivo + self.unidades * precio


def comprar(cartera, precio, monto, mercado=MERCADO):
    """Compra BTC por hasta `monto` USDT a `precio`. La cantidad se redondea hacia abajo al paso del exchange."""
    if monto > cartera.efectivo + 1e-9:
        raise OrdenRechazada(f"Saldo insuficiente: pide {monto:.2f} USDT y hay {cartera.efectivo:.2f}")
    monto = min(monto, mercado["monto_maximo_usdt"])
    cantidad = float((Decimal(repr(monto)) / Decimal(repr(precio * (1 + COSTO)))).quantize(Decimal(mercado["paso_cantidad"]), ROUND_DOWN))
    if cantidad <= 0 or cantidad * precio < mercado["monto_minimo_usdt"]:
        raise OrdenRechazada(f"Saldo insuficiente para el mínimo: {monto:.2f} USDT está bajo el mínimo de {mercado['monto_minimo_usdt']} USDT")
    cartera.efectivo -= cantidad * precio * (1 + COSTO)
    cartera.unidades += cantidad
    return {"lado": "compra", "cantidad": cantidad, "precio": precio}


def vender_todo(cartera, precio):
    if cartera.unidades <= 0:
        raise OrdenRechazada("No hay posición que vender")
    cantidad = cartera.unidades
    cartera.efectivo += cantidad * precio * (1 - COSTO)
    cartera.unidades = 0.0
    return {"lado": "venta", "cantidad": cantidad, "precio": precio}
