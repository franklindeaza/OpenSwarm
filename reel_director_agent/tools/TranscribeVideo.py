"""TranscribeVideo — Whisper word-level con probability per word.

Llama al endpoint internal /transcribe del API MediConnect. faster-whisper modelo
small español. Devuelve dict {language, duration, text, words[], segments[]}.

Cada word incluye {start, end, word, probability 0-1}. La probability es CRÍTICA
para que PlanCuts decida si cortar muletillas (solo si prob < 0.85).
"""
from __future__ import annotations
from typing import Optional
import json

from pydantic import Field
from agency_swarm import BaseTool

from ._internal_client import post_internal


class TranscribeVideo(BaseTool):
    """Transcribe el video del doctor con Whisper word-level + confidence.

    Usar PRIMERO antes de cualquier otro tool. La salida (transcript completo
    con timing por palabra) es el insumo de PlanCuts, DetectHook, PlanBroll,
    ValidateCompliance y SelectMood.

    Si el audio del doctor es muy ruidoso, considera llamar CleanAudio ANTES de
    TranscribeVideo para mejorar la calidad de la transcripción.
    """

    video_path: str = Field(
        ...,
        description="Path absoluto del video dentro del container API (e.g. /app/uploads/markestudio/raw/abc.mp4)",
    )
    language: str = Field(default="es", description="ISO language code")
    beam_size: int = Field(default=5, ge=1, le=10)

    def run(self) -> str:
        try:
            result = post_internal(
                "transcribe",
                {
                    "video_path": self.video_path,
                    "language": self.language,
                    "beam_size": self.beam_size,
                },
            )
        except Exception as e:
            return json.dumps({"error": f"transcribe_failed: {e}"})
        data = result.get("data", {})
        # Devolvemos un resumen + la data completa. El agente lee el JSON.
        return json.dumps({
            "summary": {
                "language": data.get("language"),
                "duration": data.get("duration"),
                "word_count": len(data.get("words", [])),
                "segment_count": len(data.get("segments", [])),
                "text_preview": (data.get("text") or "")[:300],
            },
            "data": data,
        }, ensure_ascii=False)
