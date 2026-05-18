"""BrowseAssets tool — busca fotos/videos curados de Envato library."""
from __future__ import annotations
import json
import os
from typing import Literal, Optional

import httpx
from pydantic import Field
from agency_swarm import BaseTool


MARKESTUDIO_API = os.getenv("MARKESTUDIO_API_URL", "http://mediconnect-api:8100")


class BrowseAssets(BaseTool):
    """Lista fotos/videos curados de Envato library (326 assets médicos
    catalogados). Búsqueda semántica por keyword.

    Ejemplos de keywords útiles:
    - 'doctor consulta pediatrica niño'
    - 'mujer dolor abdominal pelvico'
    - 'examen visual ojo niño'
    - 'embarazo prenatal ultrasonido'
    - 'estetoscopio escritorio medico'

    Devuelve hasta 20 assets con file_url + tags + dimensions. Cada asset
    es una FOTO REAL profesional — preferir esto sobre Gemini synthesis
    (que genera caras AI con dedos extra, ojos asimétricos)."""

    keyword: Optional[str] = Field(
        None,
        description="Palabras clave separadas por espacios (mezclar ES + EN para mejor match)",
    )
    category: Literal["photo", "video", "music"] = "photo"
    limit: int = Field(default=10, ge=1, le=20)

    def run(self) -> str:
        params = {"category": self.category, "limit": self.limit}
        if self.keyword:
            params["keyword"] = self.keyword
        try:
            with httpx.Client(timeout=15.0) as cx:
                r = cx.get(
                    f"{MARKESTUDIO_API}/api/v1/markestudio/agentic/library/assets",
                    params=params,
                )
                r.raise_for_status()
                data = r.json()
                items = [
                    {
                        "id": a["id"],
                        "title": a["title"],
                        "tags": (a.get("tags") or [])[:8],
                        "size": f"{a.get('width')}x{a.get('height')}" if a.get("width") else None,
                        "file_url": a["file_url"],
                    }
                    for a in data.get("assets", [])
                ]
                return json.dumps(
                    {"count": data.get("count"), "assets": items},
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            return json.dumps({"error": str(e)[:300], "assets": []})
