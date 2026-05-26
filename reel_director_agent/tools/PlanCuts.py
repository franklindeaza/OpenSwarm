"""PlanCuts — calcula plan de cortes sin tocar el video.

Toma el `words` array de TranscribeVideo y produce un keep_segments plan
removiendo:
  - Silencios > min_silence_gap_sec entre palabras consecutivas
  - Muletillas español ("eh", "este", "um", "mmm", etc.) si probability < 0.85
  - Stutters de baja confianza (opcional)

NO modifica el video — solo devuelve el plan. apply-cuts (en BuildRenderPlan
o en el worker downstream) ejecuta el ffmpeg.
"""
from __future__ import annotations
from typing import Any
import json

from pydantic import Field
from agency_swarm import BaseTool

from ._internal_client import post_internal


class PlanCuts(BaseTool):
    """Calcula plan de cuts (silencios + muletillas) del transcript.

    Usar DESPUÉS de TranscribeVideo. Pasa los `words` directamente del
    transcript. Conservador en speech — nunca corta mid-word.
    """

    words: list[dict[str, Any]] = Field(
        ...,
        description="Words array de TranscribeVideo (con probability)",
    )
    duration: float = Field(..., description="Duración total del video en segundos")
    min_silence_gap: float = Field(
        default=0.6,
        description="Cortar silencios mayores a este valor (segundos)",
    )
    cut_fillers: bool = Field(default=True, description="Cortar muletillas low-confidence")
    cut_silences: bool = Field(default=True, description="Cortar silencios largos")

    def run(self) -> str:
        try:
            result = post_internal(
                "plan-cuts",
                {
                    "words": self.words,
                    "duration": self.duration,
                    "min_silence_gap": self.min_silence_gap,
                    "cut_fillers": self.cut_fillers,
                    "cut_silences": self.cut_silences,
                },
            )
        except Exception as e:
            return json.dumps({"error": f"plan_cuts_failed: {e}"})
        return json.dumps(result.get("data", {}), ensure_ascii=False)
