"""PlanBrandStripe — decide si poner una stripe vertical con color del brand.

La brand stripe es una franja de 6-12px que recorre verticalmente el reel,
marcando identidad visual. Decisión editorial:

- enabled: a veces no se quiere (interfiere con el video o se ve overkill)
- width_px: grosor (6-12)
- side: left o right
- opacity: 0.6-1.0
- color override: por defecto usa brand_kit.accent, pero el agente puede
  override para coherencia con el mood del reel
"""
from __future__ import annotations
from typing import Literal, Optional
import json

from pydantic import Field
from agency_swarm import BaseTool


class PlanBrandStripe(BaseTool):
    """Decide brand stripe vertical."""

    enabled: bool = Field(
        ...,
        description="Si False, no se muestra stripe (ej. para reels muy minimalistas).",
    )
    width_px: int = Field(
        default=8,
        description="Grosor en px. 6=sutil, 8=balanceado, 12=fuerte.",
    )
    side: Literal["left", "right"] = Field(
        default="left",
        description="Lado del reel donde aparece.",
    )
    opacity: float = Field(
        default=0.85,
        description="0..1. 0.6=sutil, 0.85=normal, 1.0=fuerte.",
    )
    color_override: Optional[str] = Field(
        default=None,
        description="Hex color override. None = usa brand_kit.accent del doctor.",
    )
    rationale: str = Field(
        ...,
        description="Justificación editorial.",
    )

    def run(self) -> str:
        return json.dumps({
            "brand_stripe": {
                "enabled": self.enabled,
                "width_px": self.width_px,
                "side": self.side,
                "opacity": self.opacity,
                "color": self.color_override,
            },
            "rationale": self.rationale,
        }, ensure_ascii=False)
