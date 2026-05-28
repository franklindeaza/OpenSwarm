"""CleanAudio — ElevenLabs Voice Isolator.

Quita ruido ambiente, eco, música de fondo no deseada del audio crudo del
doctor (típicamente grabado con iPhone en consulta). Conserva voz humana.

Cuesta ~$0.05/min según pricing ElevenLabs — solo invocar si el audio
realmente lo necesita. Si la transcripción de TranscribeVideo tiene
average_confidence > 0.85 y no hay quejas de ruido, probablemente puedes
saltearte este paso.
"""
from __future__ import annotations
from typing import Optional
import json

from pydantic import Field
from agency_swarm import BaseTool

from ._internal_client import post_internal


class CleanAudio(BaseTool):
    """Limpia el audio del video con ElevenLabs Voice Isolator.

    Devuelve el path del audio limpio (mp3). Para usar el audio limpio en el
    render final, sustituye el audio source del Remotion composition.

    Cuesta crédito ElevenLabs ~$0.05/min. Solo invocar si el doctor grabó en
    ambiente ruidoso. Si el audio original ya es claro, no llames esta tool.
    """

    audio_path: str = Field(
        ...,
        description="Path absoluto al audio o video con audio (mp3/wav/m4a/mp4)",
    )
    output_path: Optional[str] = Field(
        None,
        description="Destino mp3. Si None, autogenerado junto al input",
    )

    def run(self) -> str:
        try:
            result = post_internal(
                "clean-audio",
                {"audio_path": self.audio_path, "output_path": self.output_path},
            )
        except Exception as e:
            return json.dumps({"error": f"clean_audio_failed: {e}"})
        # Backend puede degradar gracefully (audio_isolation scope missing)
        if result.get("skipped"):
            return json.dumps({
                "skipped": True,
                "reason": result.get("reason"),
                "message": result.get("message"),
                "audio_path": result.get("audio_path"),
                "note": "El audio original se usará sin limpiar. CONTINÚA el flow sin retry — NO vuelvas a llamar CleanAudio.",
            }, ensure_ascii=False)
        return json.dumps(result.get("data", {}), ensure_ascii=False)
