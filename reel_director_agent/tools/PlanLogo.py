"""PlanLogo — decide colocación, tamaño y estilo del logo del doctor.

Decisión editorial del agente. El logo existe (viene del brand kit), pero
DÓNDE/CÓMO mostrarlo es decisión visual:

- Esquinas (top_right, top_left, bottom_right, bottom_left) — clásico
- Sin background (logo flota) vs background pill blanco semi-transparente
- Tamaño según importancia / cuán grande es el logo nativo
- Aparición: bounce_in (juvenil/vibrante), fade (sobrio), none (estático)

Reglas:
- Para clínicas tradicionales tono "sobrio/profesional": background pill blanco + fade
- Para reels TikTok juvenil tono "cercano": bounce_in + sin background
- Para reels nocturnos/oscuros: background semi-transparente blanco mejora contraste
"""
from __future__ import annotations
from typing import Literal, Optional
import json

from pydantic import Field
from agency_swarm import BaseTool


class PlanLogo(BaseTool):
    """Decide presentación del logo en el reel."""

    enabled: bool = Field(
        ...,
        description="Si False, el reel NO muestra logo (el agente puede decidir omitirlo).",
    )
    position: Literal["top_right", "top_left", "bottom_right", "bottom_left"] = Field(
        default="top_right",
        description="Esquina donde aparece. Default top_right.",
    )
    margin_px: int = Field(
        default=50,
        description="Margen en px desde los bordes (default 50).",
    )
    height_px: int = Field(
        default=80,
        description="Altura del logo en px. 60-100 recomendado.",
    )
    background: Literal["white_pill", "dark_pill", "none"] = Field(
        default="white_pill",
        description=(
            "white_pill = rgba(255,255,255,0.88) — mejora contraste sobre cualquier video. "
            "dark_pill = rgba(0,0,0,0.6) — para logos blancos. "
            "none = logo flota sin fondo."
        ),
    )
    appear_animation: Literal["bounce_in", "fade", "none"] = Field(
        default="bounce_in",
        description="Animación de entrada del logo al inicio del reel.",
    )
    rationale: str = Field(
        ...,
        description="Por qué este placement y estilo según el tono del reel.",
    )

    def run(self) -> str:
        # Convertir position semántica a coordenadas
        pos_map = {
            "top_right":    {"top": self.margin_px, "right": self.margin_px},
            "top_left":     {"top": self.margin_px, "left": self.margin_px},
            "bottom_right": {"bottom": self.margin_px, "right": self.margin_px},
            "bottom_left":  {"bottom": self.margin_px, "left": self.margin_px},
        }
        bg_map = {
            "white_pill": "rgba(255,255,255,0.88)",
            "dark_pill":  "rgba(0,0,0,0.6)",
            "none":       "none",
        }
        return json.dumps({
            "logo": {
                "enabled": self.enabled,
                "position": pos_map[self.position],
                "height_px": self.height_px,
                "background": bg_map[self.background],
                "padding_px": 14 if self.background != "none" else 0,
                "border_radius": 16,
                "appear_animation": self.appear_animation,
            },
            "rationale": self.rationale,
        }, ensure_ascii=False)
