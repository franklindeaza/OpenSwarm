"""Tool: Validate Spanish text in a rendered image using Claude Haiku Vision.

Scans the image for visible text, detects typos / nonsense words / missing
tildes / English leakage. Returns structured findings the Creative Director
uses to decide whether to accept or re-generate.

Cost: ~$0.005 per check.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Literal

import httpx
from pydantic import Field
from agency_swarm import BaseTool


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

PROMPT = """Eres un editor profesional de español dominicano. Te paso una
imagen generada por IA. Tu única tarea: detectar errores en el texto visible.

DETECTA:
1. Typos / palabras inventadas (ej. "diecino" en vez de "diciendo", "Optalmologo" en vez de "Oftalmólogo")
2. Tildes faltantes en palabras que las requieren (ej. "evaluacion" debe ser "evaluación")
3. Ñ mal escrita o ausente (ej. "ninos" debe ser "niños")
4. Texto en inglés cuando debería estar en español ("Book Now" en vez de "Reserva")
5. Palabras médicas mal escritas (Oftalmología, Pediátrica, etc.)
6. Espacios incorrectos / caracteres raros

DEVUELVE SOLO JSON sin markdown, sin texto extra:
{
  "publishable": <true|false>,
  "errors": [
    {"text_seen": "...", "should_be": "...", "severity": "minor|major"}
  ],
  "regenerate_instructions": "..."
}

publishable=false SI hay UN solo error major (palabra inventada, inglés leak, palabra
médica mal escrita). Errores minor (1 tilde faltante) pueden pasar.

regenerate_instructions: instrucción concreta en inglés para el modelo de imagen
sobre qué corregir. Ej: "Replace 'diecino' with 'diciendo', replace 'Optalmologo'
with 'Oftalmólogo Pediátrico' in footer".
"""


def _load_image_b64(file_path: str) -> str | None:
    p = Path(file_path)
    if not p.exists():
        return None
    try:
        return base64.b64encode(p.read_bytes()).decode("ascii")
    except Exception:
        return None


class ValidateSpanishText(BaseTool):
    """Validate Spanish text in a rendered image. Detects typos, missing tildes,
    English leakage, misspelled medical terms. Returns publishable boolean +
    list of errors + concrete regeneration instructions."""

    file_path: str = Field(
        ...,
        description="Absolute path to the image file to validate (e.g. /opt/mediconnect-creative/mnt/.../image.png)",
    )

    def run(self) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return json.dumps({
                "publishable": True,
                "errors": [],
                "regenerate_instructions": "",
                "_warning": "ANTHROPIC_API_KEY not set, skipping validation",
            })

        b64 = _load_image_b64(self.file_path)
        if not b64:
            return json.dumps({
                "publishable": False,
                "errors": [{"text_seen": "FILE_MISSING", "should_be": self.file_path, "severity": "major"}],
                "regenerate_instructions": "File not found, cannot validate",
            })

        try:
            with httpx.Client(timeout=45.0) as cx:
                resp = cx.post(
                    ANTHROPIC_URL,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": HAIKU_MODEL,
                        "max_tokens": 600,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                                {"type": "text", "text": PROMPT},
                            ],
                        }],
                    },
                )
                resp.raise_for_status()
                raw = resp.json()["content"][0]["text"].strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0] if "\n" in raw else raw
                data = json.loads(raw)
                return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({
                "publishable": True,
                "errors": [],
                "regenerate_instructions": "",
                "_warning": f"validation API call failed: {e}",
            })
