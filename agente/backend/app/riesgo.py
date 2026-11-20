"""Riesgo determinista. Los límites se leen una vez al arrancar y son inmutables: nada del ciclo (ni el LLM) los cambia.
«detenido» bloquea toda orden y no liquida; liquidar es una acción aparte."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Limites:
    exposicion_max: float = 1.0        # fracción del patrimonio que se invierte al comprar (no rebalancea después)
    perdida_diaria_max: float = 0.10   # si un día (contra el cierre del día anterior) pierde más que esto, el agente se detiene
    max_antiguedad_h: float = 36.0     # la vela más reciente no puede ser más vieja

    @classmethod
    def del_entorno(cls):
        lim = cls(float(os.environ.get("EXPOSICION_MAX", "1.0")), float(os.environ.get("PERDIDA_DIARIA_MAX", "0.10")),
                  float(os.environ.get("MAX_ANTIGUEDAD_H", "36")))
        if not (0 < lim.exposicion_max <= 1 and 0 < lim.perdida_diaria_max < 1 and lim.max_antiguedad_h > 0):
            raise RuntimeError(f"Límites de riesgo fuera de rango: {lim}")
        return lim


def revisar(estado):
    """Motivo del rechazo de cualquier orden, o None si pasa."""
    return "Agente detenido: no se envía ninguna orden" if estado == "detenido" else None


def freno_por_perdida(perdida_dia, limites):
    """Si el día cerró con una pérdida mayor al máximo, el agente se detiene (no liquida); lo reinicia una persona con /iniciar."""
    if perdida_dia is not None and perdida_dia < -limites.perdida_diaria_max:
        return f"Pérdida del día {perdida_dia:.2%} supera el máximo de {limites.perdida_diaria_max:.2%}: agente detenido"
    return None
