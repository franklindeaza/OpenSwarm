"""BrowseTemplates tool — lista templates PSD curados de la biblioteca."""
from __future__ import annotations
import json
import os
from typing import Literal, Optional

import httpx
from pydantic import Field
from agency_swarm import BaseTool


MARKESTUDIO_API = os.getenv("MARKESTUDIO_API_URL", "http://mediconnect-api:8100")


class BrowseTemplates(BaseTool):
    """Lista templates PSD curados (115 templates editoriales con structure).
    Útil cuando el topic se beneficia de un layout existente (lista de
    síntomas, comparativa antes/después, infografía con cifras)."""

    specialty: Optional[str] = Field(
        None,
        description="oftalmologia | cardiologia | pediatria | ginecologia | dermatologia | salud_mental | preventiva | general",
    )
    format: Optional[Literal["post", "story_9x16", "square", "portrait", "landscape"]] = None
    intent: Optional[str] = Field(
        None,
        description="awareness | prevencion | educativo | tip | fact | checkup | testimonial",
    )
    limit: int = Field(default=15, ge=1, le=30)

    def run(self) -> str:
        params = {"limit": self.limit}
        if self.specialty: params["specialty"] = self.specialty
        if self.format: params["format"] = self.format
        if self.intent: params["intent"] = self.intent
        try:
            with httpx.Client(timeout=15.0) as cx:
                r = cx.get(
                    f"{MARKESTUDIO_API}/api/v1/markestudio/agentic/library/templates",
                    params=params,
                )
                r.raise_for_status()
                data = r.json()
                items = [
                    {
                        "id": t["id"],
                        "title": t["display_title"],
                        "format": t["format"],
                        "size": f"{t['width_px']}x{t['height_px']}",
                        "specialty": t.get("specialty_tags"),
                        "thumbnail": t.get("thumbnail_url"),
                    }
                    for t in data.get("templates", [])
                ]
                return json.dumps(
                    {"count": data.get("count"), "templates": items},
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            return json.dumps({"error": str(e)[:300], "templates": []})
