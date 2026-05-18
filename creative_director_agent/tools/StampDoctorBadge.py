"""StampDoctorBadge — renderiza la INSIGNIA del doctor (foto circular + bloque
nombre dark + bloque especialidad accent) como overlay PNG transparente para
componer encima de cualquier post/story/reel.

Reemplaza el footer de texto plano "Dr. X · Especialidad" por un componente
visual con marca real (foto del doctor + 2 bloques de color brand kit), tipo
insignia profesional que el CEO usa siempre para Dr. Edward Rijo.

Inputs:
- doctor_name, specialty, avatar_url, brand_dark_hex, brand_accent_hex
  (todos opcionales — defaults leídos de /tmp/_brand_override_current.json)
- canvas_size (1080x1080 / 1080x1920 / etc) — solo para dimensionar overlay
- position: bottom-left, bottom-right, top-left, center-bottom
- size: small (~28% width), medium (~45%), large (~65%)
- variant: light_bg (insignia con bloques saturados, default) | dark_bg (claros)

Output: PNG con TRANSPARENCIA al canvas_size pedido, listo para alpha_composite
encima del render base. El Creative Director lo pide después de tener el base
final y antes de exportar.

Layout (escalonado, matchea referencia CEO):

  [foto]   [================================]
  circular [ Dr. Edward Rijo                ] ← bloque DARK (brand secondary)
  con halo [================================]
              [================================]
              [ Ginecólogo-Obstetra,           ] ← bloque ACCENT (brand primary)
              [ Fertilidad y Reproducción      ]
              [================================]
"""
from __future__ import annotations

import io
import json
import uuid as _uuid
from pathlib import Path
from typing import Literal, Optional, Tuple

import httpx
from PIL import Image, ImageDraw, ImageFont
from pydantic import Field
from agency_swarm import BaseTool


OUTPUT_DIR = Path("/app/mnt/agentic_composed/badges")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BRAND_OVERRIDE_PATH = Path("/tmp/_brand_override_current.json")


def _first_existing(*paths: str) -> str:
    for p in paths:
        if Path(p).exists():
            return p
    return paths[-1]


FONT_NAME = _first_existing(
    "/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
FONT_SPECIALTY = _first_existing(
    "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _hex_to_rgb(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    h = (hex_color or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _darken(rgb: Tuple[int, int, int, int], factor: float = 0.45) -> Tuple[int, int, int, int]:
    """Para derivar un 'dark' del primary cuando no hay secondary explícito."""
    return (int(rgb[0] * factor), int(rgb[1] * factor), int(rgb[2] * factor), rgb[3])


def _lighten(rgb: Tuple[int, int, int, int], factor: float = 0.55) -> Tuple[int, int, int, int]:
    """Halo claro derivado del primary."""
    return (
        min(255, int(rgb[0] + (255 - rgb[0]) * factor)),
        min(255, int(rgb[1] + (255 - rgb[1]) * factor)),
        min(255, int(rgb[2] + (255 - rgb[2]) * factor)),
        rgb[3],
    )


def _fetch_image(url_or_path: str) -> Image.Image:
    if url_or_path.startswith("http"):
        with httpx.Client(timeout=20.0) as cx:
            r = cx.get(url_or_path, follow_redirects=True)
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGBA")
    p = Path(url_or_path)
    if p.exists():
        return Image.open(p).convert("RGBA")
    raise FileNotFoundError(url_or_path)


def _circular_with_halo(
    avatar: Image.Image,
    diameter: int,
    halo_color: Tuple[int, int, int, int],
    halo_thickness: int = 0,
) -> Image.Image:
    """Recorta avatar a círculo + agrega anillo halo del color brand."""
    halo_thickness = halo_thickness or max(8, diameter // 28)
    full = diameter + halo_thickness * 2

    # Halo background (filled circle)
    out = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    halo_draw = ImageDraw.Draw(out)
    halo_draw.ellipse([(0, 0), (full - 1, full - 1)], fill=halo_color)

    # Crop avatar to square center + scale
    iw, ih = avatar.size
    side = min(iw, ih)
    left = (iw - side) // 2
    top = (ih - side) // 2
    sq = avatar.crop((left, top, left + side, top + side)).resize(
        (diameter, diameter), Image.LANCZOS
    )

    # Circular mask for avatar
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse([(0, 0), (diameter - 1, diameter - 1)], fill=255)
    sq.putalpha(mask)

    out.alpha_composite(sq, (halo_thickness, halo_thickness))
    return out


def _fit_font_for_text(text: str, max_w: int, max_h: int, font_path: str,
                       start_size: int, min_size: int = 14):
    """Encuentra font_size que cabe en (max_w, max_h) sin truncar."""
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        words = text.split()
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            bbox = font.getbbox(test)
            if bbox[2] - bbox[0] <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        line_h = int(size * 1.2)
        total_h = line_h * len(lines)
        max_line_w = max((font.getbbox(ln)[2] - font.getbbox(ln)[0]) for ln in lines) if lines else 0
        if max_line_w <= max_w and total_h <= max_h:
            return font, lines, size
    return ImageFont.truetype(font_path, min_size), [text], min_size


def _draw_block_with_text(
    canvas: Image.Image,
    text: str,
    box_xy: Tuple[int, int, int, int],
    bg_color: Tuple[int, int, int, int],
    text_color: Tuple[int, int, int, int],
    font_path: str,
    pad_x: int,
    pad_y: int,
) -> None:
    """Dibuja un rectángulo (sin esquinas redondeadas, matchea referencia CEO)
    con texto centrado vertical, alineado izquierda."""
    x1, y1, x2, y2 = box_xy
    draw = ImageDraw.Draw(canvas)
    draw.rectangle(box_xy, fill=bg_color)
    max_text_w = (x2 - x1) - pad_x * 2
    max_text_h = (y2 - y1) - pad_y * 2
    start_size = int((y2 - y1) * 0.7)
    font, lines, size = _fit_font_for_text(
        text, max_text_w, max_text_h, font_path, start_size, min_size=14
    )
    line_h = int(size * 1.2)
    total_h = line_h * len(lines)
    ty = y1 + (y2 - y1 - total_h) // 2
    for i, ln in enumerate(lines):
        draw.text((x1 + pad_x, ty + i * line_h), ln, font=font, fill=text_color)


class StampDoctorBadge(BaseTool):
    """Stampa la INSIGNIA del doctor (foto circular con halo + nombre dark +
    especialidad accent) como overlay PNG transparente.

    Usa esta tool SIEMPRE que el brief pida footer del doctor, presentación
    del médico, o cierre de marca. Reemplaza el texto plano
    "Dr. X · Especialidad" con un componente visual real con la cara y los
    colores del doctor — patrón validado por CEO Dr. Edward Rijo.

    El layout escalonado (foto + 2 bloques de color brand desfasados)
    matchea la referencia que el CEO usa siempre. Cada doctor lleva SU foto
    automáticamente (leída del brand_kit via /tmp/_brand_override_current.json
    o pasada explícita en avatar_url).

    Output: PNG transparente a canvas_size, listo para alpha_composite
    encima del render base.
    """

    canvas_size: Literal["1080x1080", "1080x1350", "1080x1920", "1920x1080"] = Field(
        default="1080x1080",
        description="Tamaño del overlay PNG. Debe matchear el formato del post base.",
    )
    position: Literal[
        "bottom_left", "bottom_right", "bottom_center", "top_left", "top_right", "center_bottom"
    ] = Field(
        default="bottom_left",
        description="Dónde anclar la insignia en el canvas. bottom_left matchea la referencia Rijo.",
    )
    size: Literal["small", "medium", "large"] = Field(
        default="medium",
        description="small=~30% width (footer discreto), medium=~50% (default, presentación), large=~70% (hero card)",
    )
    variant: Literal["light_bg", "dark_bg"] = Field(
        default="light_bg",
        description="light_bg: insignia con bloques saturados (texto blanco) sobre fondo claro. dark_bg: bloques claros sobre fondo oscuro.",
    )

    # Overrides opcionales — si se omiten, lee de /tmp/_brand_override_current.json
    doctor_name: Optional[str] = Field(default=None, description="Nombre completo. Si null, lee del brand_override.")
    specialty: Optional[str] = Field(default=None, description="Especialidad completa. Si null, lee del brand_override.")
    avatar_url: Optional[str] = Field(default=None, description="URL foto doctor. Si null, lee del brand_override.")
    brand_primary_hex: Optional[str] = Field(default=None, description="Color brand primary (bloque accent). Si null, lee del brand_override.")
    brand_secondary_hex: Optional[str] = Field(default=None, description="Color brand dark (bloque nombre). Si null, deriva del primary.")

    file_name_hint: str = Field(default="badge", description="Slug para nombrar el archivo output")

    def _load_override(self) -> dict:
        if BRAND_OVERRIDE_PATH.exists():
            try:
                return json.loads(BRAND_OVERRIDE_PATH.read_text())
            except Exception:
                return {}
        return {}

    def run(self) -> str:
        try:
            override = self._load_override()
            colors = override.get("brand_colors", {}) or {}

            doctor_name = self.doctor_name or override.get("doctor_name") or "Dr. MediConnect"
            specialty = self.specialty or override.get("specialty") or "Médico Especialista"
            avatar_url = self.avatar_url or override.get("avatar_url") or override.get("profile_photo_url")
            primary_hex = self.brand_primary_hex or colors.get("primary") or "#E91E8C"
            secondary_hex = self.brand_secondary_hex or colors.get("secondary")

            primary_rgb = _hex_to_rgb(primary_hex)
            if secondary_hex and secondary_hex != primary_hex:
                dark_rgb = _hex_to_rgb(secondary_hex)
            else:
                # Sin secondary explícito → derivar dark del primary
                dark_rgb = _darken(primary_rgb, factor=0.40)
            halo_rgb = _lighten(primary_rgb, factor=0.55)

            white = (255, 255, 255, 255)

            # Canvas dimensions
            cw, ch = map(int, self.canvas_size.split("x"))
            canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

            # Badge total width según size
            size_pct = {"small": 0.34, "medium": 0.55, "large": 0.74}[self.size]
            badge_w = int(cw * size_pct)
            avatar_d = int(badge_w * 0.30)
            halo_thickness = max(8, avatar_d // 25)
            badge_h = int(avatar_d + halo_thickness * 2)

            # Avatar circular con halo
            if avatar_url:
                try:
                    avatar = _fetch_image(avatar_url)
                    badge_avatar = _circular_with_halo(avatar, avatar_d, halo_rgb, halo_thickness)
                except Exception:
                    badge_avatar = None
            else:
                badge_avatar = None

            # Si no hay avatar, dibujar placeholder circular con inicial
            if badge_avatar is None:
                full = avatar_d + halo_thickness * 2
                badge_avatar = Image.new("RGBA", (full, full), (0, 0, 0, 0))
                d = ImageDraw.Draw(badge_avatar)
                d.ellipse([(0, 0), (full - 1, full - 1)], fill=halo_rgb)
                d.ellipse(
                    [(halo_thickness, halo_thickness),
                     (full - halo_thickness - 1, full - halo_thickness - 1)],
                    fill=dark_rgb,
                )
                try:
                    initial_font = ImageFont.truetype(FONT_NAME, int(avatar_d * 0.5))
                    initial = (doctor_name or "?").strip().lstrip("Dr.").strip()[:1].upper() or "?"
                    bbox = initial_font.getbbox(initial)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    d.text(
                        ((full - tw) // 2 - bbox[0], (full - th) // 2 - bbox[1]),
                        initial, font=initial_font, fill=white,
                    )
                except Exception:
                    pass

            # Bloques de texto — calc anchos a partir del badge_w restante
            gap = int(avatar_d * 0.08)
            text_block_w = badge_w - avatar_d - halo_thickness * 2 - gap
            name_block_h = int(avatar_d * 0.55)
            spec_block_h = int(avatar_d * 0.70)
            block_stagger_x = int(text_block_w * 0.08)  # bloque accent desplazado a la derecha

            # Total height puede crecer si bloques superan altura del avatar
            total_h = max(badge_h, name_block_h + spec_block_h + int(avatar_d * 0.08))

            # Compose badge en su propio buffer
            badge_buf_w = badge_w + block_stagger_x
            badge_buf = Image.new("RGBA", (badge_buf_w, total_h), (0, 0, 0, 0))

            # Avatar a la izquierda, centro vertical
            avatar_y = (total_h - (avatar_d + halo_thickness * 2)) // 2
            badge_buf.alpha_composite(badge_avatar, (0, avatar_y))

            # Bloques de texto a la derecha del avatar
            text_x1 = avatar_d + halo_thickness * 2 + gap

            # Variant light_bg: bloques saturados, texto blanco
            # Variant dark_bg: bloques claros (white + brand light), texto dark
            if self.variant == "light_bg":
                name_bg = dark_rgb
                spec_bg = primary_rgb
                name_text = white
                spec_text = white
            else:
                name_bg = white
                spec_bg = _lighten(primary_rgb, factor=0.20)
                name_text = dark_rgb
                spec_text = white

            # Bloque nombre arriba (alineado al top del avatar para empezar simétrico)
            name_y1 = avatar_y + int(halo_thickness * 0.5)
            name_y2 = name_y1 + name_block_h
            _draw_block_with_text(
                canvas=badge_buf,
                text=doctor_name,
                box_xy=(text_x1, name_y1, text_x1 + text_block_w, name_y2),
                bg_color=name_bg,
                text_color=name_text,
                font_path=FONT_NAME,
                pad_x=int(text_block_w * 0.05),
                pad_y=int(name_block_h * 0.12),
            )

            # Bloque especialidad debajo, desplazado a la derecha (escalonado)
            spec_y1 = name_y2 + int(avatar_d * 0.04)
            spec_y2 = spec_y1 + spec_block_h
            spec_x1 = text_x1 + block_stagger_x
            spec_x2 = spec_x1 + text_block_w
            _draw_block_with_text(
                canvas=badge_buf,
                text=specialty,
                box_xy=(spec_x1, spec_y1, spec_x2, spec_y2),
                bg_color=spec_bg,
                text_color=spec_text,
                font_path=FONT_SPECIALTY,
                pad_x=int(text_block_w * 0.05),
                pad_y=int(spec_block_h * 0.10),
            )

            # Anchor del badge en el canvas
            margin = int(min(cw, ch) * 0.04)
            bw, bh = badge_buf.size
            if self.position == "bottom_left":
                anchor = (margin, ch - bh - margin)
            elif self.position == "bottom_right":
                anchor = (cw - bw - margin, ch - bh - margin)
            elif self.position == "bottom_center":
                anchor = ((cw - bw) // 2, ch - bh - margin)
            elif self.position == "top_left":
                anchor = (margin, margin)
            elif self.position == "top_right":
                anchor = (cw - bw - margin, margin)
            else:  # center_bottom
                anchor = ((cw - bw) // 2, int(ch * 0.65))

            canvas.alpha_composite(badge_buf, anchor)

            # Save
            out_name = f"{self.file_name_hint}_{_uuid.uuid4().hex[:8]}.png"
            out_path = OUTPUT_DIR / out_name
            canvas.save(out_path, "PNG", compress_level=2)

            return json.dumps({
                "success": True,
                "file_path": str(out_path),
                "canvas_size": self.canvas_size,
                "position": self.position,
                "size": self.size,
                "variant": self.variant,
                "doctor_name": doctor_name,
                "specialty": specialty,
                "has_avatar": avatar_url is not None,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)[:300]})
