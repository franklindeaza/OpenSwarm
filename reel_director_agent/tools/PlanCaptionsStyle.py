"""PlanCaptionsStyle — decide estilo de subtítulos del reel.

Tres estilos disponibles cada uno con tono distinto:

- pill_karaoke: palabra-por-palabra con highlight pill rosa brand (Submagic-style).
  → Tono: informativo, accesible, juvenil, alta retención. Default.
- kinetic_slam: cada palabra "golpea" entrando desde arriba con bounce.
  → Tono: impacto, urgencia, llamadas de atención.
- clip_wipe: palabras revelan progresivamente con clip-path left-to-right.
  → Tono: editorial sobrio, doctores tradicionales.

Otros parámetros editoriales:
- uppercase: True (recomendado para mobile-first) vs False (más legible para textos largos)
- bottom_offset: distancia desde el fondo (220 default. Subir si lower-third está abajo)
- max_width_pct: 88 default. Bajar para captions más estrechos (texto menos abigarrado)
"""
from __future__ import annotations
from typing import Literal
import json

from pydantic import Field
from agency_swarm import BaseTool


class PlanCaptionsStyle(BaseTool):
    """Decide estilo de captions."""

    style: Literal["pill_karaoke", "kinetic_slam", "clip_wipe"] = Field(
        ...,
        description="Estilo según tono del reel.",
    )
    uppercase: bool = Field(
        default=True,
        description="True = TODO MAYÚSCULAS (mobile-first, más legible). False = sentence case.",
    )
    bottom_offset: int = Field(
        default=220,
        description="Distancia en px desde el fondo del frame.",
    )
    max_width_pct: int = Field(
        default=88,
        description="Ancho máximo del bloque de caption en % del frame.",
    )
    text_color: str = Field(
        default="#FFFFFF",
        description="Color del texto en hex. Default blanco.",
    )
    background: str = Field(
        default="rgba(0,0,0,0.78)",
        description="Background del bloque. rgba con alpha para semi-transparente.",
    )
    rationale: str = Field(
        ...,
        description="Justificación editorial.",
    )

    def run(self) -> str:
        return json.dumps({
            "captions": {
                "enabled": True,
                "style": self.style,
                "uppercase": self.uppercase,
                "bottom_offset": self.bottom_offset,
                "max_width_pct": self.max_width_pct,
                "text_color": self.text_color,
                "background": self.background,
            },
            "rationale": self.rationale,
        }, ensure_ascii=False)
