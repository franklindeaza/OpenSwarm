"""PlanEndCard — decide cierre del reel (3-5 últimos segundos).

El end card es lo que el doctor quiere que la audiencia recuerde + acción.
Decisión editorial completa del agente:

- duration_sec: cuánto dura (3s default, hasta 5s si CTA largo)
- background_style:
  - gradient_brand: degradado secondary→primary (impactante, profesional)
  - solid_primary: color primary plano (limpio minimalista)
  - solid_secondary: color secondary plano
  - blurred_video: deja el video del doctor desenfocado de fondo (íntimo)
- cta_text: el call-to-action (el agente lo escribe coherente con el tema)
- show_doctor_name: si poner nombre del doctor arriba del CTA (default True)
"""
from __future__ import annotations
from typing import Literal
import json

from pydantic import Field
from agency_swarm import BaseTool


class PlanEndCard(BaseTool):
    """Decide presentación del end card final."""

    enabled: bool = Field(
        ...,
        description="Si False, el reel no tiene end card (termina en el video).",
    )
    duration_sec: float = Field(
        default=3.0,
        description="Segundos antes del fin que se muestra el end card. 3-5 recomendado.",
    )
    background_style: Literal["gradient_brand", "solid_primary", "solid_secondary", "blurred_video"] = Field(
        default="gradient_brand",
        description=(
            "gradient_brand = degradado de colores del brand (clásico). "
            "solid_primary/secondary = un color plano. "
            "blurred_video = doctor desenfocado de fondo (íntimo, recomendado para reels personales)."
        ),
    )
    show_doctor_name: bool = Field(
        default=True,
        description="Si poner el nombre del doctor arriba del CTA.",
    )
    cta_text: str = Field(
        ...,
        description=(
            "Texto del CTA — el agente lo escribe coherente con el tema. "
            "Ejemplos: 'Agenda tu cita', 'Aprende más', 'Reserva tu consulta'."
        ),
    )
    rationale: str = Field(
        ...,
        description="Por qué este cierre dado el tono y el tema del reel.",
    )

    def run(self) -> str:
        return json.dumps({
            "end_card": {
                "enabled": self.enabled,
                "duration_sec": self.duration_sec,
                "background_style": self.background_style,
                "show_doctor_name": self.show_doctor_name,
                "cta_text": self.cta_text,
            },
            "rationale": self.rationale,
        }, ensure_ascii=False)
