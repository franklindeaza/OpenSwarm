"""PlanLowerThird — decide presentación del nameplate del doctor.

El lower-third clásico tipo noticiero: "Dr. Edward Rijo / Cardiología".
Aparece al inicio, sale después de 4-5s. Decisión editorial:

- background_style:
  - gradient = chevron fadeado a accent del brand (clásico noticiero)
  - solid = block sólido del color accent (moderno minimalista)
  - outline = transparente con borde accent (sobrio, deja ver el video)
  - none = sin background (texto puro sobre video — riesgo legibilidad)
- position vertical: bottom (clásico) vs alto medio (si los captions están abajo)
- appear_at y duration: cuándo aparecer (default 1s) y por cuánto (default 4s)
"""
from __future__ import annotations
from typing import Literal
import json

from pydantic import Field
from agency_swarm import BaseTool


class PlanLowerThird(BaseTool):
    """Decide presentación del lower-third doctor."""

    enabled: bool = Field(
        ...,
        description="Si False, no muestra lower-third (puede ser decisión editorial).",
    )
    appear_at_sec: float = Field(
        default=1.0,
        description="Cuándo aparece desde el inicio (default 1.0).",
    )
    visible_duration_sec: float = Field(
        default=4.0,
        description="Cuántos segundos visible antes de salir (default 4.0).",
    )
    background_style: Literal["gradient", "solid", "outline", "none"] = Field(
        default="gradient",
        description="Estilo del fondo del nameplate.",
    )
    vertical_position: Literal["bottom", "middle_bottom", "top"] = Field(
        default="bottom",
        description="bottom=clásico. middle_bottom=arriba de captions. top=evita conflicto con captions abajo.",
    )
    left_margin: int = Field(default=60, description="Margen desde borde izquierdo.")
    rationale: str = Field(
        ...,
        description="Justificación editorial.",
    )

    def run(self) -> str:
        bottom_map = {
            "bottom": 340,
            "middle_bottom": 480,
            "top": 1500,  # de arriba (top: ... convertido a bottom)
        }
        return json.dumps({
            "lower_third": {
                "enabled": self.enabled,
                "appear_at_sec": self.appear_at_sec,
                "visible_duration_sec": self.visible_duration_sec,
                "position": {
                    "left": self.left_margin,
                    "bottom": bottom_map[self.vertical_position],
                },
                "background_style": self.background_style,
                "border_radius": 12,
            },
            "rationale": self.rationale,
        }, ensure_ascii=False)
