"""PlanHookStyle — el agente decide el tratamiento visual del hook segment.

El hook ya fue identificado por DetectHook (qué decir). Esta tool decide
CÓMO mostrarlo visualmente:

- cinematic_zoom: zoom suave 1.12 → 1.0 sobre la duración del hook
  → ideal para insights/punchlines tranquilizadores (rinde profesional)
- punch_in: zoom rápido 1.0 → 1.18 → 1.0 (snap inicial 15% del tiempo)
  → ideal para shocks/cifras impactantes ("3 de cada 10 niños...")
- static: sin zoom (el video se ve como grabado)
  → ideal cuando el hook ya tiene fuerza por sí mismo o el doctor se mueve mucho
- none: sin tratamiento de hook (el reel arranca normal)

Decisión editorial del agente — debe ser coherente con el tono pedido
y con la energía del segmento que DetectHook identificó.
"""
from __future__ import annotations
from typing import Literal
import json

from pydantic import Field
from agency_swarm import BaseTool


class PlanHookStyle(BaseTool):
    """Decide tratamiento visual del hook segment."""

    type: Literal["cinematic_zoom", "punch_in", "static", "none"] = Field(
        ...,
        description=(
            "cinematic_zoom = zoom suave profesional. "
            "punch_in = snap rápido para impacto. "
            "static = sin zoom. "
            "none = sin tratamiento de hook."
        ),
    )
    duration_sec: float = Field(
        ...,
        description="Duración del hook segment (mismo que DetectHook.hook.duration)",
    )
    zoom_from: float = Field(
        default=1.12,
        description="Scale inicial — solo para cinematic_zoom",
    )
    zoom_to: float = Field(
        default=1.0,
        description="Scale final — solo para cinematic_zoom",
    )
    rationale: str = Field(
        ...,
        description="Justificación editorial breve de por qué este tratamiento (1-2 frases)",
    )

    def run(self) -> str:
        return json.dumps({
            "hook_style": {
                "type": self.type,
                "duration_sec": round(self.duration_sec, 2),
                "zoom_from": self.zoom_from if self.type == "cinematic_zoom" else None,
                "zoom_to": self.zoom_to if self.type == "cinematic_zoom" else None,
            },
            "rationale": self.rationale,
        }, ensure_ascii=False)
