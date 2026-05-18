"""StampTextOnImage — toma una foto base (URL Envato o file path) y stampa
texto + branding + logo con Pillow. Texto SIEMPRE perfecto (no Gemini que
puede inventar palabras). Brand colors 100% respetados.

Use cases:
- Foto stock pediátrica + headline "5 síntomas que no debes ignorar" → post premium
- Imagen Gemini hero + texto editorial sobre fondo semi-transparente
- Cualquier base + brand bar inferior con doctor name
"""
from __future__ import annotations

import io
import json
import os
import uuid as _uuid
from pathlib import Path
from typing import Literal, Optional, List

import httpx
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from agency_swarm import BaseTool


OUTPUT_DIR = Path("/app/mnt/agentic_composed/generated_images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Fonts disponibles. Editorial premium prefiere serif/script para headlines,
# sans clean para body. Fallback a DejaVu si no instalados.
def _first_existing(*paths):
    for p in paths:
        if Path(p).exists():
            return p
    return paths[-1]

FONT_HEADLINE_SCRIPT = _first_existing(
    "/usr/share/fonts/truetype/caveat/Caveat-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
FONT_HEADLINE_SERIF = _first_existing(
    "/usr/share/fonts/truetype/playfair/PlayfairDisplay-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
)
FONT_BOLD = _first_existing(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
FONT_REG = _first_existing(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


class TextOverlay(BaseModel):
    text: str
    position: Literal["top_center", "center", "bottom_center", "bottom_left", "bottom_right", "top_left"] = "bottom_center"
    role: Literal["headline", "subhead", "body", "cta", "footer"] = "body"
    color_hex: Optional[str] = None  # Default usa brand colors según role


def _hex_to_rgb(hex_color: str, alpha: int = 255) -> tuple:
    h = (hex_color or "#000000").lstrip("#")
    if len(h) == 3: h = "".join(c*2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _fetch_image(url_or_path: str) -> Image.Image:
    """Carga imagen desde URL HTTP o file path local."""
    if url_or_path.startswith("http"):
        with httpx.Client(timeout=30.0) as cx:
            r = cx.get(url_or_path, follow_redirects=True)
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGBA")
    p = Path(url_or_path)
    if p.exists():
        return Image.open(p).convert("RGBA")
    raise FileNotFoundError(url_or_path)


def _fit_text(text: str, max_w: int, font_path: str, max_size: int, min_size: int = 16):
    """Encuentra font_size más grande que cabe en max_w (word-wrap)."""
    for size in range(max_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        # Word wrap manual
        words = text.split()
        lines = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            bbox = font.getbbox(test)
            if bbox[2] - bbox[0] <= max_w:
                cur = test
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        max_line_w = max(font.getbbox(ln)[2] - font.getbbox(ln)[0] for ln in lines) if lines else 0
        if max_line_w <= max_w:
            return font, lines, size
    return ImageFont.truetype(font_path, min_size), [text], min_size


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: str,
    role: str,
    canvas_w: int,
    canvas_h: int,
    color: tuple,
    bg_color: Optional[tuple] = None,
):
    """Stampa un bloque de texto en la posición indicada con auto-fit."""
    # Tamaño base por rol
    role_sizes = {
        "headline": (int(canvas_w * 0.13), int(canvas_w * 0.85)),  # más grande
        "subhead": (int(canvas_w * 0.055), int(canvas_w * 0.80)),
        "body": (int(canvas_w * 0.040), int(canvas_w * 0.80)),
        "cta": (int(canvas_w * 0.045), int(canvas_w * 0.50)),
        "footer": (int(canvas_w * 0.030), int(canvas_w * 0.90)),
    }
    max_size, max_w = role_sizes.get(role, role_sizes["body"])
    # Fonts editoriales por rol (matchea estilo target del Marketing AI ref)
    if role == "headline":
        font_path = FONT_HEADLINE_SCRIPT  # Caveat — cursive elegante
    elif role == "subhead":
        font_path = FONT_HEADLINE_SERIF  # Playfair — serif premium
    elif role == "cta":
        font_path = FONT_BOLD
    else:
        font_path = FONT_REG

    font, lines, size = _fit_text(text, max_w, font_path, max_size, min_size=16)
    line_h = int(size * 1.25)
    total_h = line_h * len(lines)

    # Compute position
    pad = int(canvas_w * 0.04)
    if position == "top_center":
        x_center, y_start = canvas_w // 2, pad * 2
    elif position == "center":
        x_center, y_start = canvas_w // 2, (canvas_h - total_h) // 2
    elif position == "bottom_center":
        x_center, y_start = canvas_w // 2, canvas_h - total_h - pad * 2
    elif position == "bottom_left":
        x_center, y_start = pad * 3, canvas_h - total_h - pad * 2
    elif position == "bottom_right":
        x_center, y_start = canvas_w - pad * 3, canvas_h - total_h - pad * 2
    else:  # top_left
        x_center, y_start = pad * 3, pad * 2

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        line_w = bbox[2] - bbox[0]
        if position.endswith("_left"):
            x = x_center
        elif position.endswith("_right"):
            x = x_center - line_w
        else:
            x = x_center - line_w // 2
        y = y_start + i * line_h

        # Optional bg box (for legibility on photos)
        if bg_color:
            pad_box = int(size * 0.3)
            draw.rounded_rectangle(
                [(x - pad_box, y - pad_box // 2),
                 (x + line_w + pad_box, y + line_h + pad_box // 2)],
                radius=int(size * 0.2),
                fill=bg_color,
            )
        draw.text((x, y), line, font=font, fill=color)


class StampTextOnImage(BaseTool):
    """Stampa texto + branding + logo encima de una imagen base (URL o path).
    Texto perfecto (Pillow, no AI). Brand colors respetados al 100%.

    Use this AFTER browsing the library + choosing a good base image, OR
    after the Image Agent generates a clean illustration. The base image
    should be EITHER pure visual without text OR have explicit empty space
    for overlays.

    Output: PNG file path en /app/mnt/agentic_composed/generated_images/."""

    base_image_url: str = Field(
        ...,
        description="URL HTTP o file path absoluto de la imagen base. Ej: foto Envato del library o file_path de Image Agent."
    )
    text_overlays: List[dict] = Field(
        ...,
        description=(
            "Lista de overlays. Cada uno: {text, position, role, color_hex?}. "
            "Roles: headline (gigante), subhead, body, cta (con bg box), footer. "
            "Positions: top_center, center, bottom_center, bottom_left, bottom_right, top_left."
        ),
    )
    brand_primary_hex: str = Field(default="#E91E8C")
    brand_secondary_hex: str = Field(default="#6A0066")
    logo_url: Optional[str] = Field(None, description="URL del logo del doctor — pegado esquina sup izq")
    output_size: Literal["1080x1080", "1080x1350", "1080x1920"] = Field(default="1080x1080")
    file_name_hint: str = Field(default="composed", description="Slug para nombrar el archivo output")

    def run(self) -> str:
        try:
            # 1. Load base
            base = _fetch_image(self.base_image_url)
            target_w, target_h = map(int, self.output_size.split("x"))
            # Cover-fit a output size
            iw, ih = base.size
            scale = max(target_w / iw, target_h / ih)
            new_w, new_h = int(iw * scale), int(ih * scale)
            base = base.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            base = base.crop((left, top, left + target_w, top + target_h))

            # 2. Brand colors
            primary = _hex_to_rgb(self.brand_primary_hex)
            secondary = _hex_to_rgb(self.brand_secondary_hex)
            white = (255, 255, 255, 255)
            text_dark = (31, 41, 55, 255)

            # 3. Draw overlays
            # El Creative Director decide colores con color_hex param si quiere.
            # Defaults usan brand colors para máximo respeto a identidad.
            draw = ImageDraw.Draw(base)
            for o in self.text_overlays:
                role = o.get("role", "body")
                if o.get("color_hex"):
                    color = _hex_to_rgb(o["color_hex"])
                elif role == "headline":
                    color = primary  # Rosa brand directo (script Caveat)
                elif role == "subhead":
                    color = text_dark
                elif role == "body":
                    color = text_dark
                elif role == "cta":
                    color = white  # blanco sobre pill rosa
                elif role == "footer":
                    color = text_dark
                else:
                    color = text_dark

                # Background box: solo CTA tiene pill. Resto sin caja
                # (estilo editorial limpio del Marketing AI target).
                bg = None
                if role == "cta":
                    bg = primary  # CTA pill rosa

                _draw_text_block(
                    draw,
                    text=o.get("text", ""),
                    position=o.get("position", "bottom_center"),
                    role=role,
                    canvas_w=target_w,
                    canvas_h=target_h,
                    color=color,
                    bg_color=bg,
                )

            # 4. Logo overlay esquina sup izq
            if self.logo_url:
                try:
                    logo = _fetch_image(self.logo_url)
                    # trim transparent
                    bbox = logo.getchannel("A").getbbox() if logo.mode == "RGBA" else None
                    if bbox:
                        logo = logo.crop(bbox)
                    logo_w = int(target_w * 0.18)
                    logo_h = int(target_h * 0.10)
                    iw2, ih2 = logo.size
                    scale = min(logo_w / iw2, logo_h / ih2)
                    logo = logo.resize((max(1, int(iw2 * scale)), max(1, int(ih2 * scale))), Image.LANCZOS)
                    pad_x = int(target_w * 0.04)
                    pad_y = int(target_h * 0.04)
                    # Fondo blanco semi para asegurar visibilidad sobre cualquier foto
                    bg_box = Image.new("RGBA", (logo.width + 20, logo.height + 20), (255, 255, 255, 230))
                    base.alpha_composite(bg_box, (pad_x - 10, pad_y - 10))
                    base.alpha_composite(logo, (pad_x, pad_y))
                except Exception as e:
                    pass  # logo failure no rompe el render

            # 5. Save
            out_name = f"{self.file_name_hint}_{_uuid.uuid4().hex[:8]}.png"
            out_path = OUTPUT_DIR / out_name
            base.convert("RGB").save(out_path, "PNG", compress_level=2)
            return json.dumps({
                "success": True,
                "file_path": str(out_path),
                "size": f"{target_w}x{target_h}",
                "overlays_drawn": len(self.text_overlays),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)[:300]})
