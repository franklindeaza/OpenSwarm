"""Tool: Fetch doctor's brand kit from MediConnect's Postgres.

Connects to the existing mediconnect-postgres container by reading config
from /opt/mediconnect/.env (DATABASE_URL). Returns normalized brand kit data.

For PoC: hardcoded fallback to Dr. Edward Rijo if DB unavailable.
"""
from __future__ import annotations
import os
import json
from typing import Optional

import asyncio
from pydantic import Field
from agency_swarm import BaseTool


# Fallback brand kit (Dr. Rijo) for testing without DB access
FALLBACK_BRAND_KIT = {
    "dr_edward_rijo": {
        "doctor_id": "dr_edward_rijo",
        "doctor_name": "Dr. Edward Rijo",
        "specialty": "Oftalmología Pediátrica",
        "tenant_schema": "tenant_dr_edward_rijo_bfcf89f5",
        "brand_colors": {
            "primary": "#E91E8C",
            "secondary": "#6A0066",
            "accent": "#FFFFFF",
            "text_dark": "#1F2937",
        },
        "logo_light_url": "https://api-mediconnect.deazasoluciones.com/uploads/markestudio/logos/71d689d6-1576-4aaf-add9-bd0170f78bfd.png",
        "logo_dark_url": "https://api-mediconnect.deazasoluciones.com/uploads/markestudio/logos/bb4a6d4c-c86a-469c-a96d-b126369f7936.png",
        "tone": "trustworthy",
        "voice": "Español dominicano natural, empático, profesional",
        "audience": "Padres dominicanos de niños 4-14 años, clase media-alta",
        "language": "es-DO",
    },
}


def _load_mediconnect_db_url() -> Optional[str]:
    """Read DATABASE_URL from /opt/mediconnect/.env if accessible."""
    try:
        with open("/opt/mediconnect/.env", "r") as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if "+asyncpg" in url:
                        url = url.replace("+asyncpg", "")
                    return url
    except (FileNotFoundError, PermissionError):
        return None
    return None


async def _fetch_from_db(doctor_id_or_email: str) -> Optional[dict]:
    """Fetch doctor + brand kit from MediConnect Postgres."""
    db_url = _load_mediconnect_db_url()
    if not db_url:
        return None
    try:
        import asyncpg  # type: ignore
    except ImportError:
        return None

    try:
        conn = await asyncpg.connect(db_url)
        try:
            doctor_row = await conn.fetchrow(
                """
                SELECT id, full_name, schema_name
                FROM public.doctors
                WHERE id::text = $1 OR email = $1 OR full_name ILIKE $2
                LIMIT 1
                """,
                doctor_id_or_email, f"%{doctor_id_or_email}%",
            )
            if not doctor_row:
                return None
            schema = doctor_row["schema_name"]
            await conn.execute(f'SET search_path TO "{schema}"')
            kit_row = await conn.fetchrow(
                """
                SELECT colors_json, colors_palette, logo_light_url, logo_dark_url,
                       brand_name
                FROM studio_brand_kits LIMIT 1
                """
            )
            primary = "#1E88E5"
            secondary = "#43A047"
            accent = "#FFFFFF"
            if kit_row:
                palette = kit_row.get("colors_palette")
                if isinstance(palette, dict) and isinstance(palette.get("palettes"), list):
                    active = int(palette.get("active", 0) or 0)
                    palettes = palette["palettes"]
                    if 0 <= active < len(palettes) and palettes[active]:
                        pal = [str(c) for c in palettes[active]]
                        if len(pal) >= 1 and pal[0].startswith("#"):
                            primary = pal[0]
                        if len(pal) >= 2 and pal[1].startswith("#"):
                            secondary = pal[1]
                        if len(pal) >= 3 and pal[2].startswith("#"):
                            accent = pal[2]
            return {
                "doctor_id": str(doctor_row["id"]),
                "doctor_name": doctor_row["full_name"],
                "tenant_schema": schema,
                "brand_colors": {
                    "primary": primary,
                    "secondary": secondary,
                    "accent": accent,
                    "text_dark": "#1F2937",
                },
                "logo_light_url": kit_row.get("logo_light_url") if kit_row else None,
                "logo_dark_url": kit_row.get("logo_dark_url") if kit_row else None,
                "tone": "trustworthy",
                "voice": "Español dominicano natural, empático, profesional",
                "audience": "Padres dominicanos clase media-alta",
                "language": "es-DO",
            }
        finally:
            await conn.close()
    except Exception:
        return None


class FetchDoctorBrandKit(BaseTool):
    """Fetch the doctor's brand kit (colors, logo, tone, audience) from
    MediConnect's database. Falls back to a curated brand kit for known
    doctors (Dr. Rijo) if DB is unavailable."""

    doctor_id: str = Field(
        ...,
        description="Doctor identifier — can be UUID, email, slug ('dr_edward_rijo'), or full name fragment.",
    )

    def run(self) -> str:
        # PRIORITY 1: Brand override file (set by mediconnect_server.py when
        # MarkEstudio API passes brand_override in request payload). This is
        # the most reliable source — DB access from this container is unreliable.
        override_path = Path("/tmp/_brand_override_current.json")
        if override_path.exists():
            try:
                override = json.loads(override_path.read_text())
                if override:
                    return json.dumps(override, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # PRIORITY 2: DB query (rarely works because container lacks DB access)
        try:
            db_kit = asyncio.run(_fetch_from_db(self.doctor_id))
        except RuntimeError:
            db_kit = None
        if db_kit:
            return json.dumps(db_kit, ensure_ascii=False, indent=2)

        # Fallback to curated kit
        slug = self.doctor_id.lower().replace(" ", "_").replace(".", "")
        for key, kit in FALLBACK_BRAND_KIT.items():
            if key in slug or slug in key:
                return json.dumps(kit, ensure_ascii=False, indent=2)

        # Last resort: generic
        return json.dumps({
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor_id,
            "specialty": "Medicina General",
            "brand_colors": {"primary": "#1E88E5", "secondary": "#43A047", "accent": "#FFFFFF"},
            "logo_light_url": None,
            "logo_dark_url": None,
            "tone": "trustworthy",
            "voice": "Español dominicano natural",
            "audience": "Pacientes dominicanos",
            "language": "es-DO",
            "_warning": "Brand kit not found, using generic defaults",
        }, ensure_ascii=False, indent=2)
