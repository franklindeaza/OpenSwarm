"""BuildRenderPlan — consolida outputs de las tools en JSON v1 final.

Es la última tool que el agente invoca. Toma todos los outputs intermedios
(transcript, cuts, hook, broll, music, compliance) y los consolida en un
JSON plan v1 que el Remotion renderer consume.

NO ejecuta el render — solo arma el JSON. El render lo hace un worker
downstream que toma el plan de la cola.
"""
from __future__ import annotations
from typing import Any, Optional
import json
import uuid as _uuid

from pydantic import Field
from agency_swarm import BaseTool


class BuildRenderPlan(BaseTool):
    """Consolida todos los outputs en un Render Plan v1 final.

    El plan resultante alimenta:
    - Worker apply-cuts (corta el video usando keep_segments)
    - Cliente Suno (genera o pide del cache música según mood + duration)
    - Cliente Envato/Kie AI (resuelve B-roll queries → URLs)
    - Remotion render (composition DoctorVideoReelV2 + props consolidados)

    BLOQUEA emisión si compliance.severity == "error".
    """

    reel_id: Optional[str] = Field(
        None,
        description="UUID del reel; si None se autogenera",
    )
    input_video_path: str = Field(..., description="Path del video crudo original")
    cleaned_audio_path: Optional[str] = Field(
        None,
        description="Path del audio limpio (CleanAudio output); None si no se aplicó",
    )
    transcript: dict[str, Any] = Field(..., description="Output completo de TranscribeVideo.data")
    cuts: dict[str, Any] = Field(..., description="Output de PlanCuts")
    hook: dict[str, Any] = Field(..., description="Output de DetectHook (validated)")
    broll: list[dict[str, Any]] = Field(default_factory=list, description="Output de PlanBroll.broll")
    music: dict[str, Any] = Field(..., description="Output de SelectMood.music")
    compliance: dict[str, Any] = Field(..., description="Output de ValidateCompliance")
    brand_kit: dict[str, Any] = Field(..., description="Brand kit del doctor (colors, fonts, logo)")
    doctor: dict[str, Any] = Field(..., description="Doctor info {name, specialty, voice_id?}")
    target_duration_sec: float = Field(
        default=45.0,
        ge=15,
        le=90,
        description="Duración objetivo del reel final",
    )
    captions_style: str = Field(
        default="pill_karaoke",
        description="Estilo captions: pill_karaoke|kinetic_slam|clip_wipe|highlight (legacy — preferir hook_style/captions_spec via director_plan_overrides)",
    )

    # ───── DirectorPlan editorial (autoridad del agente) ─────
    # Cada uno proviene del .run() de la tool correspondiente, parsed.
    # Si None, fallback al comportamiento legacy del template.
    hook_style: Optional[dict[str, Any]] = Field(
        default=None,
        description="Output de PlanHookStyle.hook_style — cinematic_zoom/punch_in/static/none + duración + zoom params",
    )
    logo_spec: Optional[dict[str, Any]] = Field(
        default=None,
        description="Output de PlanLogo.logo — position, height, background, animation",
    )
    lower_third_spec: Optional[dict[str, Any]] = Field(
        default=None,
        description="Output de PlanLowerThird.lower_third — enabled, appear_at, duration, position, background_style",
    )
    end_card_spec: Optional[dict[str, Any]] = Field(
        default=None,
        description="Output de PlanEndCard.end_card — duration, background_style, cta_text, show_doctor_name",
    )
    brand_stripe_spec: Optional[dict[str, Any]] = Field(
        default=None,
        description="Output de PlanBrandStripe.brand_stripe — enabled, width, side, opacity, color",
    )
    captions_spec: Optional[dict[str, Any]] = Field(
        default=None,
        description="Output de PlanCaptionsStyle.captions — style, uppercase, bottom_offset, colors (override captions_style legacy)",
    )

    def run(self) -> str:
        # BLOQUEAR si compliance error
        severity = (self.compliance or {}).get("severity", "warning")
        if severity == "error":
            return json.dumps({
                "ok": False,
                "blocked_by_compliance": True,
                "compliance": self.compliance,
                "message": "Render plan NOT emitted. Doctor must rephrase the violating statements.",
            }, ensure_ascii=False)

        reel_id = self.reel_id or _uuid.uuid4().hex[:12]

        # Calcular duración final del reel
        keep_segments = self.cuts.get("keep_segments", [])
        kept_duration = sum(s["end"] - s["start"] for s in keep_segments) if keep_segments else 0

        final_duration = min(self.target_duration_sec, kept_duration) if kept_duration > 0 else self.target_duration_sec

        # Construir DirectorPlan editorial — autoridad total del agente
        director_plan = {
            "hook": self.hook_style or {
                # Fallback: derivar del hook segment con tratamiento safe cinematic_zoom
                "type": "cinematic_zoom",
                "duration_sec": float(self.hook.get("end", 0)) - float(self.hook.get("start", 0)),
                "zoom_from": 1.12,
                "zoom_to": 1.0,
            },
            "brand_stripe": self.brand_stripe_spec or {
                "enabled": True, "width_px": 8, "side": "left", "opacity": 0.85,
            },
            "broll": self.broll,  # ya viene con position/size/border/opacity desde PlanBroll
            "logo": self.logo_spec or {
                "enabled": bool(self.brand_kit.get("logo_light_url")),
                "position": {"top": 50, "right": 50},
                "height_px": 80,
                "background": "rgba(255,255,255,0.88)",
                "padding_px": 14,
                "border_radius": 16,
                "appear_animation": "bounce_in",
            },
            "lower_third": self.lower_third_spec or {
                "enabled": True,
                "appear_at_sec": 1.0,
                "visible_duration_sec": 4.0,
                "position": {"left": 60, "bottom": 340},
                "background_style": "gradient",
                "border_radius": 12,
            },
            "captions": self.captions_spec or {
                "enabled": True,
                "style": self.captions_style,
                "bottom_offset": 220,
                "uppercase": True,
                "background": "rgba(0,0,0,0.78)",
                "text_color": "#FFFFFF",
                "max_width_pct": 88,
            },
            "end_card": self.end_card_spec or {
                "enabled": True,
                "duration_sec": 3.0,
                "background_style": "gradient_brand",
                "show_doctor_name": True,
                "cta_text": "Agenda tu cita",
            },
            "music": {
                "volume": (self.music or {}).get("volume", 0.18),
                "duck_db": (self.music or {}).get("duck_db", -14),
            },
        }

        plan = {
            "version": "v1",
            "reel_id": reel_id,
            "input_video": self.input_video_path,
            "cleaned_audio": self.cleaned_audio_path,
            "transcript": {
                "language": self.transcript.get("language"),
                "duration": self.transcript.get("duration"),
                "text": self.transcript.get("text"),
                "word_count": len(self.transcript.get("words", [])),
                "words": self.transcript.get("words", []),
            },
            "cuts": self.cuts,
            "hook": self.hook,
            "broll": self.broll,
            "music": self.music,
            "compliance": self.compliance,
            "director_plan": director_plan,  # ← editorial completo (orquestador es el diseñador)
            "captions": {  # ← bloque legacy (orchestrator/template aún lo lee como fallback)
                "style": self.captions_style,
                "font": (self.brand_kit.get("fonts") or {}).get("body", "DejaVu Sans"),
                "heading_font": (self.brand_kit.get("fonts") or {}).get("heading", "DejaVu Sans"),
                "highlight_color": self.brand_kit.get("primary", "#FF5A8E"),
                "text_color": "#FFFFFF",
                "background": "rgba(0,0,0,0.78)",
            },
            "remotion": {
                "composition_id": "DoctorVideoReelV2",
                "duration_seconds": round(final_duration, 1),
                "props": {
                    "doctorName": self.doctor.get("name", "Dr."),
                    "specialty": self.doctor.get("specialty", ""),
                    "title": "",
                    "cta": director_plan["end_card"].get("cta_text", "Agenda tu cita"),
                    "brandColors": {
                        "primary": self.brand_kit.get("primary", "#4F4F4F"),
                        "secondary": self.brand_kit.get("secondary", "#2A2A2A"),
                        "accent": self.brand_kit.get("accent", "#9CA3AF"),
                        "text_dark": self.brand_kit.get("text_dark", "#1F1F1F"),
                    },
                    "fonts": self.brand_kit.get("fonts", {"heading": "DejaVu Sans", "body": "DejaVu Sans"}),
                    "logoLightUrl": self.brand_kit.get("logo_light_url", ""),
                    "captionWords": self.transcript.get("words", []),
                    # ↓ DirectorPlan completo — el template lo lee y todo el resto se ignora si viene
                    "directorPlan": director_plan,
                    # ↓ Legacy props (template fallback si directorPlan ausente)
                    "captionStyle": director_plan["captions"]["style"],
                    "hookStart": self.hook.get("start", 0),
                    "hookEnd": self.hook.get("end", 0),
                    "musicMood": self.music.get("mood"),
                    "musicDuckDb": director_plan["music"].get("duck_db"),
                    "brollPlan": self.broll,
                },
            },
        }

        return json.dumps({
            "ok": True,
            "reel_id": reel_id,
            "plan": plan,
        }, ensure_ascii=False)
