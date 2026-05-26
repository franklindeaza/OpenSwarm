"""DetectHook — encuentra los 3-5 segundos más virales/impactantes del transcript.

Usa el modelo del agente (Sonnet 4.6 / Haiku / GPT-5.2) vía un thought call
estructurado. NO necesita endpoint externo — el agente razona directo sobre
el transcript.

Sin embargo, lo exponemos como tool para que el agente lo invoque
deterministicamente cuando el plan lo requiera, en lugar de razonar libre y
olvidarse.

El "hook" se reordena al inicio del reel: si la frase clave está en segundo
12-17 del original, en el reel publicado aparecerá en segundo 0-5.

Heurística que el agente aplica:
- Statement claim (e.g. "5 cosas que nadie te dice sobre...")
- Question hook (e.g. "¿Sabías que...?")
- Number / stat (e.g. "El 70% de los pacientes...")
- Emotional peak (cambio de tono, énfasis)
- Avoid silencios o muletillas como hook
"""
from __future__ import annotations
from typing import Any
import json

from pydantic import Field
from agency_swarm import BaseTool


class DetectHook(BaseTool):
    """Identifica los 3-5 segundos más impactantes del transcript que serán
    el opening del reel.

    El agente debe razonar sobre el transcript usando estas reglas:
    - Preferir afirmaciones con números o stats
    - Preferir preguntas que generan curiosidad
    - Preferir el momento de mayor énfasis emocional/tonal
    - EVITAR silencios o muletillas como hook
    - Buscar entre segundos 5 y duration-5 (no usar los extremos)

    Esta tool consolida el razonamiento del agente: el agente decide la
    ventana [start, end] y le pasa a esta tool para validarla y devolverla
    estructurada.
    """

    transcript_text: str = Field(..., description="Texto completo del transcript")
    proposed_start_sec: float = Field(
        ...,
        description="Segundo donde inicia el hook (decisión del agente)",
    )
    proposed_end_sec: float = Field(
        ...,
        description="Segundo donde termina el hook",
    )
    rationale: str = Field(
        ...,
        description="Por qué este segmento es el mejor hook (1-2 frases)",
    )
    total_duration: float = Field(..., description="Duración total del video original")

    def run(self) -> str:
        # Validaciones simples
        duration = self.proposed_end_sec - self.proposed_start_sec
        warnings = []
        if duration < 2.5:
            warnings.append(f"hook_too_short ({duration:.1f}s, recomendado 3-5s)")
        if duration > 6.0:
            warnings.append(f"hook_too_long ({duration:.1f}s, recomendado 3-5s)")
        if self.proposed_start_sec < 1.0:
            warnings.append("hook_at_very_beginning (puede capturar silencio inicial)")
        if self.proposed_end_sec > self.total_duration - 1.0:
            warnings.append("hook_at_very_end (puede capturar silencio final)")

        return json.dumps({
            "hook": {
                "start": round(self.proposed_start_sec, 3),
                "end": round(self.proposed_end_sec, 3),
                "duration": round(duration, 3),
                "rationale": self.rationale,
            },
            "warnings": warnings,
            "valid": len(warnings) == 0,
        }, ensure_ascii=False)
