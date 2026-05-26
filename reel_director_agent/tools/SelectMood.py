"""SelectMood — escoge el mood musical y duración para el reel.

5 moods soportados, cada uno con BPM range y descripción de uso:

  - calm:        70-85 BPM. Temas: meditación, salud mental, ansiedad, sueño
  - warm:        85-105 BPM. Temas: familia, pediatría, cuidado, preventivo
  - uplifting:   100-130 BPM. Temas: motivación, logros, "antes/después", recovery
  - cinematic:   varies. Temas: emergencias, gravedad clínica, drama controlado
  - urgent:      120-140 BPM. Temas: alertas, prevención de riesgo, "no esperes"

El track real lo entrega Suno (tier premium) o catálogo CC0 local. Esta tool
solo decide MOOD + duración, el cliente Suno se llama después por separado
con cache por mood+duration.
"""
from __future__ import annotations
from typing import Literal
import json

from pydantic import Field
from agency_swarm import BaseTool


VALID_MOODS = ["calm", "warm", "uplifting", "cinematic", "urgent"]


class SelectMood(BaseTool):
    """Decide el mood musical y duración para el reel.

    El agente razona sobre tone + topic + audience del brief y propone el
    mood. Esta tool valida y devuelve el JSON estructurado.
    """

    mood: Literal["calm", "warm", "uplifting", "cinematic", "urgent"] = Field(
        ...,
        description="Mood elegido por el agente",
    )
    duration_sec: float = Field(
        ...,
        ge=10,
        le=120,
        description="Duración del track musical (debe coincidir con reel duration)",
    )
    duck_during_voice: bool = Field(
        default=True,
        description="Bajar volumen automáticamente cuando hay voz (ducking)",
    )
    rationale: str = Field(
        ...,
        description="Por qué este mood encaja con tone + topic + audience",
    )

    def run(self) -> str:
        bpm_ranges = {
            "calm": (70, 85),
            "warm": (85, 105),
            "uplifting": (100, 130),
            "cinematic": (60, 120),
            "urgent": (120, 140),
        }
        bpm_min, bpm_max = bpm_ranges[self.mood]
        bpm_target = (bpm_min + bpm_max) // 2

        return json.dumps({
            "music": {
                "mood": self.mood,
                "duration_sec": round(self.duration_sec, 1),
                "bpm_range": [bpm_min, bpm_max],
                "bpm_target": bpm_target,
                "duck_during_voice": self.duck_during_voice,
                "duck_db": -14 if self.duck_during_voice else 0,
                "rationale": self.rationale,
            }
        }, ensure_ascii=False)
