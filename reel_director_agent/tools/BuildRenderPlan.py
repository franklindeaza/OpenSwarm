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
        description="Estilo captions: pill_karaoke|kinetic_slam|clip_wipe|highlight",
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
            "captions": {
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
                    "cta": "Agenda tu cita",
                    "brandColors": {
                        "primary": self.brand_kit.get("primary", "#4F4F4F"),
                        "secondary": self.brand_kit.get("secondary", "#2A2A2A"),
                        "accent": self.brand_kit.get("accent", "#9CA3AF"),
                        "text_dark": self.brand_kit.get("text_dark", "#1F1F1F"),
                    },
                    "fonts": self.brand_kit.get("fonts", {"heading": "DejaVu Sans", "body": "DejaVu Sans"}),
                    "logoLightUrl": self.brand_kit.get("logo_light_url", ""),
                    "captionWords": self.transcript.get("words", []),
                    "captionStyle": self.captions_style,
                    "hookStart": self.hook.get("start", 0),
                    "hookEnd": self.hook.get("end", 0),
                    "musicMood": self.music.get("mood"),
                    "musicBpmTarget": self.music.get("bpm_target"),
                    "musicDuckDb": self.music.get("duck_db", -14),
                    "brollPlan": self.broll,
                },
            },
        }

        return json.dumps({
            "ok": True,
            "reel_id": reel_id,
            "plan": plan,
        }, ensure_ascii=False)
