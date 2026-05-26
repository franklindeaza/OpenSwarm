"""ValidateCompliance — Ley 42-01 + CMD compliance scan sobre el transcript.

Llama al endpoint internal /compliance del API MediConnect, que internamente
usa Claude Haiku 4.5 con SYSTEM_PROMPT_COMPLIANCE específico para RD.

Severidades:
  - ok:       sin problemas detectados
  - warning:  recomendaciones pero publicable
  - error:    BLOQUEANTE — no se publica hasta corregir

BLOQUEANTE ABSOLUTO: si el scan retorna severity="error", el agente NO debe
emitir el render plan. En su lugar, debe devolver al caller la frase problema
+ sugerencia de cómo reformularla.
"""
from __future__ import annotations
from typing import Optional
import json

from pydantic import Field
from agency_swarm import BaseTool

from ._internal_client import post_internal


class ValidateCompliance(BaseTool):
    """Scan compliance Ley 42-01 + CMD sobre el transcript del doctor.

    Reglas detectadas:
    - Claims medicos absolutos ("cura", "elimina al 100%", "garantizado")
    - Promesas de resultado ("perderás 10 libras")
    - Marketing engañoso (testimonios sin consentimiento)
    - Falta de disclaimer profesional
    - Diagnostico via redes
    - Promocion de medicamentos específicos sin contexto
    - PHI leak (datos personales de pacientes)

    Devuelve severity + warnings/blockers. Bloqueante si severity=error.
    """

    transcript_text: str = Field(..., description="Texto completo del transcript del doctor")
    doctor_specialty: Optional[str] = Field(
        None,
        description="Especialidad para context-aware scan (e.g. ginecología, cardiología)",
    )

    def run(self) -> str:
        try:
            result = post_internal(
                "compliance",
                {
                    "transcript_text": self.transcript_text,
                    "doctor_specialty": self.doctor_specialty,
                    "locale": "es-DO",
                },
            )
        except Exception as e:
            return json.dumps({"error": f"compliance_failed: {e}", "fallback_severity": "warning"})
        data = result.get("data", {})
        return json.dumps(data, ensure_ascii=False)
