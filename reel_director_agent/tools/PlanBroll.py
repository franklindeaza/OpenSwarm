"""PlanBroll — propone insertos de B-roll médico contextual al transcript.

El agente lee el transcript, identifica entidades médicas mencionadas
(especialidad, condición, anatomía, escena clínica) y propone para cada
inserto:
  - timestamp en el reel (segundo)
  - duración (2-3s recomendado)
  - query semántico para BrowseAssets (Envato library médica curada)
  - mode: "picture-in-picture" (default) o "full-bleed" o "split"

Reglas duras:
- Max 4 B-rolls por 60s de reel (no saturar)
- Cada inserto 2-3s (no más, no menos)
- Nunca durante el hook (los primeros 5s del reel publicado)
- Espaciar mínimo 4s entre insertos consecutivos
- Espaciar mínimo 2s del final del reel
"""
from __future__ import annotations
from typing import Any, Literal
import json

from pydantic import Field
from agency_swarm import BaseTool


class PlanBroll(BaseTool):
    """Propone B-roll insertions contextuales al transcript.

    El agente analiza el transcript identificando entidades médicas (e.g.
    "vacunación" → "child smiling vaccine"; "control prenatal" → "ultrasound
    pregnant woman doctor"). Pasa la lista propuesta a esta tool para que
    valide la distribución temporal.
    """

    inserts: list[dict[str, Any]] = Field(
        ...,
        description=(
            "Lista de B-roll inserts. Cada item: "
            "{at: sec, duration: sec, query: str, mode: 'picture-in-picture'|'full-bleed'|'split'}"
        ),
    )
    reel_duration_sec: float = Field(
        ...,
        description="Duración FINAL del reel (después de cuts + hook reorder)",
    )
    hook_end_sec: float = Field(
        default=5.0,
        description="Segundo donde termina el hook — no insertar B-roll antes",
    )

    def run(self) -> str:
        if not self.inserts:
            return json.dumps({"broll": [], "warnings": ["no_inserts_proposed"]})

        ordered = sorted(self.inserts, key=lambda x: x.get("at", 0))
        validated = []
        warnings = []

        last_end = self.hook_end_sec
        for i, ins in enumerate(ordered):
            at = float(ins.get("at", 0))
            dur = float(ins.get("duration", 2.5))
            query = ins.get("query", "").strip()
            mode = ins.get("mode", "picture-in-picture")

            if at < self.hook_end_sec:
                warnings.append(f"insert_{i}_during_hook (at={at}, hook_end={self.hook_end_sec})")
                continue
            if at + dur > self.reel_duration_sec - 2.0:
                warnings.append(f"insert_{i}_too_close_to_end (at={at}, dur={dur})")
                continue
            if at - last_end < 4.0 and last_end > self.hook_end_sec:
                warnings.append(f"insert_{i}_too_close_to_previous (gap={at - last_end:.1f}s)")
                continue
            if dur < 2.0 or dur > 3.5:
                warnings.append(f"insert_{i}_duration_out_of_range ({dur}s — recomendado 2-3s)")
            if not query:
                warnings.append(f"insert_{i}_empty_query")
                continue

            validated.append({
                "at": round(at, 3),
                "duration": round(dur, 3),
                "query": query,
                "mode": mode,
            })
            last_end = at + dur

        # Cap a 4 por minuto
        max_inserts = max(1, int(self.reel_duration_sec / 60 * 4))
        if len(validated) > max_inserts:
            warnings.append(f"too_many_inserts (got {len(validated)}, max {max_inserts})")
            validated = validated[:max_inserts]

        return json.dumps({
            "broll": validated,
            "warnings": warnings,
            "count": len(validated),
        }, ensure_ascii=False)
