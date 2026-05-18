"""MediConnect Creative Engine — FastAPI microservice on port 8081.

Wraps OpenSwarm agency + adds MediConnect-native REST endpoints that the
main MarkEstudio API can consume.

Endpoints exposed:
  - GET  /health                              — health check
  - POST /api/v1/agentic/generate-post        — full E2E (BrandDirector → CreativeDirector → ImageAgent)
  - POST /api/v1/agentic/brief-only           — solo BrandDirector (debug/preview)
  - POST /api/v1/agentic/visual-only          — solo ImageAgent con prompt directo
  - GET  /api/v1/agentic/file/{filename}      — serve generated images
  + todos los endpoints nativos /open-swarm/* del Agency Swarm wrapper

Run: .venv/bin/python mediconnect_server.py
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mediconnect-creative")

from swarm import create_agency
from agency_swarm.integrations.fastapi import run_fastapi


# ─── Pydantic request/response models ────────────────────────────────────

class GeneratePostRequest(BaseModel):
    doctor_id: str = Field(..., description="Doctor UUID, email, or slug (e.g. 'dr_edward_rijo').")
    topic: str = Field(..., min_length=3, max_length=400)
    format: Literal["post_1x1", "story_9x16", "reel_9x16", "carousel_4x5"] = "post_1x1"
    tone_hint: Optional[str] = None
    audience_hint: Optional[str] = None
    # Brand kit inline desde el MarkEstudio API (que tiene acceso a la DB).
    # Si presente, se inyecta al prompt para que el BrandDirector lo use
    # directamente sin necesitar query a DB del tenant.
    brand_override: Optional[dict] = None


class GeneratePostResponse(BaseModel):
    success: bool
    file_path: Optional[str] = None
    file_url: Optional[str] = None
    elapsed_seconds: float
    final_text: Optional[str] = None
    error: Optional[str] = None


class BriefOnlyRequest(BaseModel):
    doctor_id: str
    topic: str
    format: Literal["post_1x1", "story_9x16", "reel_9x16", "carousel_4x5"] = "post_1x1"


class VisualOnlyRequest(BaseModel):
    prompt: str = Field(..., min_length=10)
    aspect_ratio: Literal["1:1", "9:16", "16:9", "4:5"] = "1:1"
    product_name: str = "default"
    file_name: str = "generated"
    model: Literal["gemini-2.5-flash-image", "gemini-3-pro-image-preview"] = "gemini-3-pro-image-preview"


# ─── App + custom endpoints ──────────────────────────────────────────────

custom_app = FastAPI(
    title="MediConnect Creative Engine",
    version="1.0",
    description="Agentic creative engine for medical social media. Powered by OpenSwarm + Agency Swarm + Gemini 3 Pro Image.",
)

custom_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@custom_app.get("/health")
def health():
    """Health check sync (NO async) para que responda incluso si el event loop
    está saturado por un job agentic en curso. FastAPI ejecuta funciones sync
    en un thread pool aparte — no compite con el loop bloqueado por LLMs.
    """
    return {"status": "ok", "service": "mediconnect-creative", "version": "1.0"}


@custom_app.post("/api/v1/agentic/generate-post", response_model=GeneratePostResponse)
async def generate_post(req: GeneratePostRequest):
    """Full agentic flow: Orchestrator → BrandDirector → CreativeDirector → ImageAgent.

    Single endpoint for MarkEstudio to call. Returns generated image path + final text.
    """
    t0 = time.time()
    try:
        agency = create_agency()
        prompt = (
            f"doctor_id: {req.doctor_id}\n"
            f"topic: {req.topic}\n"
            f"format: {req.format}\n"
        )
        if req.tone_hint:
            prompt += f"tone_hint: {req.tone_hint}\n"
        if req.audience_hint:
            prompt += f"audience_hint: {req.audience_hint}\n"

        # Brand override: escribimos a archivo + inyectamos en prompt.
        # Doble path porque a veces el agente ignora el prompt — al menos la
        # tool FetchDoctorBrandKit lo leerá del archivo seguro.
        if req.brand_override:
            import json as _j
            override_path = Path("/tmp/_brand_override_current.json")
            try:
                override_path.write_text(_j.dumps(req.brand_override))
            except Exception as e:
                logger.warning("brand override write fail: %s", e)
            prompt += (
                "\n🚨 BRAND OVERRIDE OBLIGATORIO 🚨\n"
                "Usá ESTOS valores EXACTOS en el brief — no inventes, no cambies:\n"
                f"  doctor_name: {req.brand_override.get('doctor_name')}\n"
                f"  specialty: {req.brand_override.get('specialty')}\n"
                f"  primary_hex: {req.brand_override.get('primary_hex')}\n"
                f"  secondary_hex: {req.brand_override.get('secondary_hex')}\n"
                f"  logo_url: {req.brand_override.get('logo_light_url')}\n"
                f"  avatar_url: {req.brand_override.get('avatar_url')}\n"
                "El footer del post DEBE decir el nombre del doctor exacto.\n"
                "El brand color primario DEBE dominar el diseño.\n"
                "Si avatar_url está disponible, USAR StampDoctorBadge tool para\n"
                "la presentación del doctor (foto + nombre + especialidad) en\n"
                "vez de footer de texto plano.\n"
            )

        prompt += (
            "\nFlow: coordina con Brand Director para crear el brief creativo, "
            "después con Creative Director para que ejecute el diseño "
            "(él decide la mejor estrategia con sus tools disponibles o "
            "delegando al Image Agent según contexto), y finalmente devuélveme "
            "el path absoluto del PNG generado + caption Instagram + hashtags "
            'en JSON: {"file_path": "/app/mnt/...", "caption": "...", "hashtags": [...]}'
        )

        result = agency.get_response_sync(prompt)
        final_text = result.final_output if hasattr(result, "final_output") else str(result)
        elapsed = round(time.time() - t0, 1)

        # Extract file_path from final_text (best-effort scan).
        # Matches /app/mnt/... or /opt/mediconnect-creative/mnt/... or /mnt/...
        import re as _re
        file_path = None
        path_pattern = _re.compile(r'(/[\w./\-]*?/mnt/[\w./\-_ñáéíóúÁÉÍÓÚüÜ]+\.(?:png|jpg|jpeg|webp))')
        for match in path_pattern.finditer(final_text):
            candidate = match.group(1).strip()
            if Path(candidate).exists():
                file_path = candidate
                break
        # Fallback: si no encontró pero hay paths, usar el último (probable best)
        if not file_path:
            all_matches = path_pattern.findall(final_text)
            if all_matches:
                file_path = all_matches[-1].strip()

        file_url = None
        if file_path and Path(file_path).exists():
            # Convert local path to URL servable via /api/v1/agentic/file
            # Funciona en local (/opt/mediconnect-creative/mnt) y container (/app/mnt).
            mnt_candidates = ["/app/mnt", "/opt/mediconnect-creative/mnt"]
            for mnt_base in mnt_candidates:
                try:
                    rel = Path(file_path).relative_to(mnt_base)
                    file_url = f"/api/v1/agentic/file/{rel.as_posix()}"
                    break
                except ValueError:
                    continue

        return GeneratePostResponse(
            success=True,
            file_path=file_path,
            file_url=file_url,
            elapsed_seconds=elapsed,
            final_text=final_text[:3000],
        )

    except Exception as e:
        logger.exception("generate_post failed")
        return GeneratePostResponse(
            success=False,
            elapsed_seconds=round(time.time() - t0, 1),
            error=str(e)[:500],
        )


@custom_app.post("/api/v1/agentic/brief-only")
async def brief_only(req: BriefOnlyRequest):
    """Solo BrandDirector — útil para preview rápido sin generar imagen."""
    t0 = time.time()
    try:
        from brand_director_agent import create_brand_director
        from agency_swarm import Agency

        agency = Agency(create_brand_director(), name="BriefOnly")
        prompt = (
            f"doctor_id: {req.doctor_id}\n"
            f"topic: {req.topic}\n"
            f"format: {req.format}\n"
        )
        result = agency.get_response_sync(prompt)
        text = result.final_output if hasattr(result, "final_output") else str(result)
        return {
            "success": True,
            "elapsed_seconds": round(time.time() - t0, 1),
            "brief": text[:3000],
        }
    except Exception as e:
        logger.exception("brief_only failed")
        return {"success": False, "error": str(e)[:500]}


@custom_app.post("/api/v1/agentic/visual-only")
async def visual_only(req: VisualOnlyRequest):
    """Solo Image Agent con prompt directo — útil para iteración visual."""
    t0 = time.time()
    try:
        from image_generation_agent import create_image_generation_agent
        from agency_swarm import Agency

        agency = Agency(create_image_generation_agent(), name="VisualOnly")
        prompt = (
            f"{req.prompt}\n\n"
            f"Use product_name={req.product_name}, file_name={req.file_name}, "
            f"model={req.model}, aspect_ratio={req.aspect_ratio}. "
            f"Generate ONE image. Return file_path."
        )
        result = agency.get_response_sync(prompt)
        text = result.final_output if hasattr(result, "final_output") else str(result)

        # Extract file_path
        file_path = None
        for line in text.split("\n"):
            line_stripped = line.strip().strip("`").strip()
            if "/mnt/" in line_stripped and line_stripped.endswith(".png"):
                for part in line_stripped.split():
                    if "/mnt/" in part and part.endswith(".png"):
                        file_path = part.strip("`").strip()
                        break
                if file_path:
                    break

        return {
            "success": True,
            "elapsed_seconds": round(time.time() - t0, 1),
            "file_path": file_path,
            "final_text": text[:1500],
        }
    except Exception as e:
        logger.exception("visual_only failed")
        return {"success": False, "error": str(e)[:500]}


@custom_app.get("/api/v1/agentic/file/{path:path}")
async def serve_file(path: str):
    """Serve generated images. Tries both /app/mnt (container) and
    /opt/mediconnect-creative/mnt (host) depending on runtime."""
    for mnt_base in [Path("/app/mnt"), Path("/opt/mediconnect-creative/mnt")]:
        if not mnt_base.exists():
            continue
        file_path = mnt_base / path
        try:
            file_path.resolve().relative_to(mnt_base.resolve())
        except ValueError:
            continue
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")


# ─── Mount + run ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # Run the OpenSwarm wrapped FastAPI on port 8080 in a subprocess? Or just
    # run our custom FastAPI standalone? For MVP, run custom standalone — the
    # Agency Swarm wrapped server is optional for advanced UI.
    uvicorn.run(
        custom_app,
        host="0.0.0.0",
        port=8081,
        log_level="info",
    )
