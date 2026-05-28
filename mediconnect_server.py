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


def _normalize_render_plan(plan: dict) -> dict:
    """Normaliza el plan emitido al schema que DoctorVideoReelV2 espera.

    El LLM a veces sintetiza el JSON él mismo en vez de llamar BuildRenderPlan
    y termina usando keys nombre-de-tool (hook_style, captions_spec) en lugar
    de keys de schema (hook, captions). Aquí mapeamos y aseguramos que
    plan["remotion"]["props"]["directorPlan"] esté presente listo para Remotion.

    Idempotente: si ya está en el formato correcto no hace nada.
    """
    if not isinstance(plan, dict):
        return plan

    # Si el wrapper es {ok, plan: {...}} extraer el inner
    inner = plan
    wrapper_keys = set(plan.keys())
    if wrapper_keys <= {"ok", "reel_id", "plan", "blocked_by_compliance", "compliance", "message"} and isinstance(plan.get("plan"), dict):
        inner = plan["plan"]

    dp = inner.get("director_plan") or {}

    # Map keys nombre-de-tool / sintetizadas por LLM → keys del schema template
    key_mapping = {
        "hook_style":        "hook",
        "captions_spec":     "captions",
        "captions_style":    "captions",
        "logo_spec":         "logo",
        "lower_third_spec":  "lower_third",
        "end_card_spec":     "end_card",
        "brand_stripe_spec": "brand_stripe",
        "music_mix":         "music",
        "music_spec":        "music",
    }
    normalized_dp = {}
    for k, v in dp.items():
        target = key_mapping.get(k, k)
        normalized_dp[target] = v
    inner["director_plan"] = normalized_dp

    # Asegurar que plan["remotion"]["props"]["directorPlan"] esté presente
    remotion = inner.setdefault("remotion", {})
    props = remotion.setdefault("props", {})
    if "directorPlan" not in props:
        props["directorPlan"] = normalized_dp

    # Si broll quedó al toplevel del plan pero director_plan["broll"] está vacío,
    # copiarlo al director plan (algunos LLMs lo separan)
    if not normalized_dp.get("broll") and inner.get("broll"):
        normalized_dp["broll"] = inner["broll"]
        props["directorPlan"]["broll"] = inner["broll"]

    return plan


class ReelPlanRequest(BaseModel):
    """Request para reel-plan: el orquestador genera JSON plan v1 listo para Remotion."""
    doctor_id: str = Field(..., description="Doctor UUID/email/slug")
    video_path: str = Field(..., description="Path absoluto al video crudo dentro del container API")
    topic: str = Field(..., min_length=3, max_length=400)
    target_duration_sec: float = Field(default=45.0, ge=15, le=90)
    audience_hint: Optional[str] = None
    tone_hint: Optional[str] = None
    brand_override: Optional[dict] = None
    voice_clone_id: Optional[str] = None
    apply_audio_cleanup: bool = Field(
        default=True,
        description="Si True, el agente puede llamar a CleanAudio (cuesta créditos ElevenLabs)",
    )


def _build_callid_name_map(items) -> dict[str, str]:
    """Construye {call_id → tool_name} desde los ToolCallItem en new_items.

    ToolCallItem.raw_item es ResponseFunctionToolCall con .name y .call_id.
    ToolCallOutputItem.raw_item es dict con call_id + output (sin .name).
    Esta función es el join entre ambos.
    """
    callid_to_name: dict[str, str] = {}
    for item in items:
        if type(item).__name__ != "ToolCallItem":
            continue
        raw = getattr(item, "raw_item", None)
        if raw is None:
            continue
        name = getattr(raw, "name", None)
        call_id = getattr(raw, "call_id", None)
        if name and call_id:
            callid_to_name[call_id] = name
    return callid_to_name


def _extract_buildrenderplan_output(result) -> Optional[dict]:
    """Recorre new_items hacia atrás y devuelve el output PARSED de la última
    tool call BuildRenderPlan ejecutada. None si no se ejecutó.

    Matchea ToolCallOutputItem.raw_item["call_id"] contra ToolCallItem.raw_item.call_id
    para identificar qué tool produjo qué output.
    """
    import json as _json
    new_items = getattr(result, "new_items", []) or []
    callid_to_name = _build_callid_name_map(new_items)

    for item in reversed(new_items):
        if type(item).__name__ != "ToolCallOutputItem":
            continue
        raw = getattr(item, "raw_item", None)
        if not isinstance(raw, dict):
            continue
        call_id = raw.get("call_id")
        tool_name = callid_to_name.get(call_id)
        if tool_name != "BuildRenderPlan":
            continue
        output_str = item.output if hasattr(item, "output") else raw.get("output")
        if not output_str:
            continue
        try:
            parsed = _json.loads(output_str)
        except Exception:
            continue
        if isinstance(parsed, dict) and (parsed.get("plan") or parsed.get("ok") is not None):
            return parsed
    return None


def _list_tools_called(result) -> list[str]:
    """Lista nombres de tools efectivamente ejecutadas (= con response) en orden."""
    new_items = getattr(result, "new_items", []) or []
    callid_to_name = _build_callid_name_map(new_items)
    names: list[str] = []
    for item in new_items:
        if type(item).__name__ != "ToolCallOutputItem":
            continue
        raw = getattr(item, "raw_item", None)
        if not isinstance(raw, dict):
            continue
        call_id = raw.get("call_id")
        name = callid_to_name.get(call_id)
        if name:
            names.append(name)
    return names


# Build retry prompts cada vez más estrictos. attempt=0 es el original; 1 y 2 son retries.
def _build_reel_prompt(req: "ReelPlanRequest", brand: dict, attempt: int = 0) -> str:
    import json as _json
    base = (
        f"Toma este video crudo del doctor y produce el RENDER PLAN v1 JSON.\n\n"
        f"INPUT:\n"
        f"  video_path: {req.video_path}\n"
        f"  doctor_id: {req.doctor_id}\n"
        f"  topic: {req.topic}\n"
        f"  audience: {req.audience_hint or 'general'}\n"
        f"  tone: {req.tone_hint or 'cercano, informativo'}\n"
        f"  target_duration_sec: {req.target_duration_sec}\n"
        f"  voice_clone_id: {req.voice_clone_id or 'none'}\n"
        f"  apply_audio_cleanup: {req.apply_audio_cleanup}\n\n"
        f"BRAND_KIT:\n{_json.dumps(brand, ensure_ascii=False)}\n\n"
        f"Secuencia (autoridad para variar el contenido, NO la última tool):\n"
        f"  1. TranscribeVideo\n"
        f"  2. (opcional) CleanAudio\n"
        f"  3. PlanCuts\n"
        f"  4. DetectHook\n"
        f"  5. PlanBroll (decide queries, position, size, transitions)\n"
        f"  6. SelectMood\n"
        f"  7. ValidateCompliance (BLOQUEANTE si error)\n"
        f"  8. PlanHookStyle (cinematic_zoom/punch_in/static/none)\n"
        f"  9. PlanLogo (position, height, background, animation)\n"
        f" 10. PlanLowerThird (enabled, appear_at, position, background_style)\n"
        f" 11. PlanEndCard (duration, background_style, cta_text)\n"
        f" 12. PlanBrandStripe (enabled, width, side, opacity)\n"
        f" 13. PlanCaptionsStyle (style, uppercase, bottom_offset, colors)\n"
        f" 14. BuildRenderPlan(passing outputs of 8-13 as hook_style/logo_spec/etc params)\n\n"
    )
    if attempt == 0:
        return base + (
            "DEBES llamar BuildRenderPlan como última tool. "
            "El sistema lee su output, NO tu mensaje final.\n"
        )
    elif attempt == 1:
        return base + (
            "VIOLATION DETECTED en intento previo: NO llamaste a BuildRenderPlan. "
            "El sistema rechazó la respuesta porque el plan AUTORITATIVO sólo proviene "
            "del tool call BuildRenderPlan, NO de tu prosa final.\n\n"
            "AHORA EJECUTA: TranscribeVideo → DetectHook → PlanBroll → SelectMood → "
            "ValidateCompliance → PlanHookStyle → PlanLogo → PlanLowerThird → "
            "PlanEndCard → PlanBrandStripe → PlanCaptionsStyle → BuildRenderPlan.\n"
            "La tool BuildRenderPlan ES TU SALIDA. NO escribas el JSON en prosa.\n"
        )
    else:  # attempt 2+ — último intento
        return base + (
            "🚨 ÚLTIMO INTENTO 🚨\n"
            "Los 2 intentos previos fallaron porque no invocaste BuildRenderPlan.\n"
            "Esta es la última oportunidad. Tu respuesta DEBE ser literalmente:\n"
            "  1) Una secuencia de tool_calls que termina con BuildRenderPlan\n"
            "  2) Ningún JSON inline en tu mensaje final\n"
            "Si fallas otra vez, el endpoint devolverá 422 y el doctor no recibirá su reel.\n"
        )


@custom_app.post("/api/v1/agentic/reel-plan")
async def reel_plan(req: ReelPlanRequest):
    """Orquestador del Reel Director: doctor sube video crudo → emite plan JSON.

    Política estricta CEO 27-may "el orquestador es el diseñador": el plan
    AUTORITATIVO solo se acepta del output bruto de BuildRenderPlan. Si el LLM
    se salta esa tool, el endpoint reintenta hasta MAX_ATTEMPTS con prompt
    progresivamente más estricto, luego devuelve 422.
    """
    import json as _json

    MAX_ATTEMPTS = 3
    t0 = time.time()
    attempts_log: list[dict] = []
    last_text = ""

    try:
        from agency_swarm import Agency
        from reel_director_agent import create_reel_director

        agency = Agency(create_reel_director(), name="ReelDirector")

        brand = req.brand_override or {
            "primary": "#4F4F4F",
            "secondary": "#2A2A2A",
            "accent": "#9CA3AF",
            "text_dark": "#1F1F1F",
            "fonts": {"heading": "DejaVu Sans", "body": "DejaVu Sans"},
            "logo_light_url": "",
        }

        plan = None
        tool_source = None

        for attempt in range(MAX_ATTEMPTS):
            prompt = _build_reel_prompt(req, brand, attempt=attempt)
            result = agency.get_response_sync(prompt)
            last_text = result.final_output if hasattr(result, "final_output") else str(result)

            tools_called = _list_tools_called(result)
            extracted = _extract_buildrenderplan_output(result)
            if extracted is not None:
                plan = extracted
                tool_source = "BuildRenderPlan.output"
                attempts_log.append({
                    "attempt": attempt,
                    "source": tool_source,
                    "ok": True,
                    "tools_called": tools_called,
                })
                break

            attempts_log.append({
                "attempt": attempt,
                "source": "llm_text_only",
                "ok": False,
                "reason": "BuildRenderPlan tool call not found in new_items",
                "tools_called": tools_called,
            })
            logger.warning(f"reel-plan attempt {attempt} skipped BuildRenderPlan. Tools called: {tools_called}")

        # Si tras MAX_ATTEMPTS sigue sin BuildRenderPlan → 422 (no aceptamos plan sintetizado)
        if plan is None:
            return {
                "success": False,
                "error": "llm_skipped_buildrenderplan",
                "message": (
                    f"El agente Reel Director NO invocó BuildRenderPlan en {MAX_ATTEMPTS} intentos. "
                    "El sistema rechaza planes sintetizados por el LLM porque no garantizan "
                    "el schema esperado por el template. Revisar instructions.md o el modelo."
                ),
                "attempts": attempts_log,
                "elapsed_seconds": round(time.time() - t0, 1),
                "last_llm_text": last_text[:1500],
            }

        # Normalizar plan (defensa adicional aunque venga de BuildRenderPlan)
        plan = _normalize_render_plan(plan)

        return {
            "success": True,
            "elapsed_seconds": round(time.time() - t0, 1),
            "plan": plan,
            "plan_source": tool_source,
            "attempts": attempts_log,
        }
    except Exception as e:
        logger.exception("reel_plan failed")
        err_str = str(e)
        err_str_lower = err_str.lower()
        # Detectar errores comunes y devolver mensaje accionable al frontend
        if "credit balance" in err_str_lower or "credits" in err_str_lower and "insufficient" in err_str_lower:
            user_msg = (
                "Anthropic credits agotados. Recarga en https://console.anthropic.com/settings/billing "
                "y reintenta."
            )
            error_code = "anthropic_credits_exhausted"
        elif "rate_limit" in err_str_lower or "429" in err_str_lower:
            user_msg = "Rate limit Anthropic. Espera 1-2 minutos y reintenta."
            error_code = "anthropic_rate_limit"
        elif "api_key" in err_str_lower or "401" in err_str_lower or "authentication" in err_str_lower:
            user_msg = "API key Anthropic inválida o expirada. Verificar config."
            error_code = "anthropic_auth_failed"
        elif "timeout" in err_str_lower or "timed out" in err_str_lower:
            user_msg = "Timeout llamando al LLM. Reintenta — si persiste, problema de red al provider."
            error_code = "llm_timeout"
        else:
            user_msg = "Error inesperado al generar el plan. Revisar logs del Creative Engine."
            error_code = "unknown"
        return {
            "success": False,
            "error": error_code,
            "message": user_msg,
            "debug": err_str[:500],
            "elapsed_seconds": round(time.time() - t0, 1),
            "attempts": attempts_log,
        }


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
