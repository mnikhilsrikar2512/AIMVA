"""Whole-image style presets for the image editor ("/skeleton", "/portrait", ...).

Each style is a restyle instruction for the instruct model (FLUX Kontext by default). They all say what to keep
(the same people, layout and pose), because without that the model invents a new picture instead of restyling this one.
Add a style by adding a row here: the editor's menu and slash commands read this list from the API.
"""
from typing import Optional

KEEP = "Keep the same composition, subjects, faces, poses, framing and text placement."

# (id, name, group, what the user gets, instruction)
_ROWS = [
    # Popular
    ("portrait", "Portrait", "Popular", "Studio portrait: soft light, blurred background",
     "Turn this into a professional studio portrait photo: soft flattering key light, gentle rim light, shallow depth of field "
     "with a smoothly blurred background. Keep every person's identity, face, hair and clothing exactly the same."),
    ("cinematic", "Cinematic", "Popular", "Movie still: dramatic light, film colour grade",
     "Restyle this as a cinematic movie still: dramatic lighting, teal and orange colour grade, subtle film grain, "
     "anamorphic depth. " + KEEP),
    ("anime", "Anime", "Popular", "Japanese anime look, clean lines, bright colours",
     "Redraw this image in a high-quality Japanese anime style with clean line art, cel shading and vibrant colours. " + KEEP),
    ("3d", "3D cartoon", "Popular", "Rounded, colourful 3D animated-film look",
     "Turn this into a polished 3D animated film render: soft rounded shapes, expressive features, colourful global "
     "illumination. " + KEEP),
    ("watercolor", "Watercolour", "Popular", "Soft hand-painted watercolour",
     "Repaint this as a delicate watercolour painting on textured paper, with soft bleeding edges and light washes of colour. " + KEEP),
    # Art
    ("oil", "Oil painting", "Art", "Classic oil on canvas, visible brush strokes",
     "Repaint this as a classical oil painting on canvas with rich colour and visible brush strokes. " + KEEP),
    ("sketch", "Pencil sketch", "Art", "Black and white pencil drawing",
     "Turn this into a detailed graphite pencil sketch on white paper, with hatching and shading, no colour. " + KEEP),
    ("comic", "Comic book", "Art", "Bold ink outlines, halftone dots",
     "Redraw this as a comic book panel with bold ink outlines, flat colours and halftone dot shading. " + KEEP),
    ("popart", "Pop art", "Art", "Bright, bold 1960s pop art",
     "Restyle this as bold 1960s pop art: flat saturated colours, thick outlines, Ben-Day dots. " + KEEP),
    ("pixel", "Pixel art", "Art", "Retro 16-bit video game pixels",
     "Turn this into retro 16-bit pixel art with a limited colour palette and crisp visible pixels. " + KEEP),
    ("lowpoly", "Low poly", "Art", "Geometric faceted 3D shapes",
     "Restyle this as low-poly 3D art made of flat-shaded triangular facets. " + KEEP),
    ("claymation", "Claymation", "Art", "Handmade plasticine figures",
     "Turn this into a stop-motion claymation scene: everything made of plasticine with fingerprints and soft studio light. " + KEEP),
    # Photo
    ("bw", "Black & white", "Photo", "Timeless monochrome photo",
     "Make this a high-contrast black and white fine-art photograph with rich tones. Change nothing else."),
    ("vintage", "Vintage film", "Photo", "Faded 1970s film photo",
     "Make this look like a faded 1970s film photograph: warm colour shift, soft grain, slight vignette. " + KEEP),
    ("product", "Product shot", "Photo", "Clean commercial studio lighting",
     "Restyle this as a clean commercial product photograph: bright even studio lighting, crisp reflections, "
     "uncluttered background. Keep the product exactly the same shape, colour, label and text."),
    ("golden", "Golden hour", "Photo", "Warm sunset light",
     "Relight this scene at golden hour with warm, low sunlight and long soft shadows. " + KEEP),
    ("night", "Night", "Photo", "Night time with city or moon light",
     "Change this scene to night time with realistic moonlight and glowing artificial lights. " + KEEP),
    # Fun
    ("skeleton", "Skeleton", "Fun", "People and animals become skeletons",
     "Turn every person and animal into an anatomically accurate skeleton, keeping the same pose, clothing, accessories, "
     "setting, lighting and composition. Everything else stays the same."),
    ("zombie", "Zombie", "Fun", "Spooky zombie makeover",
     "Give every person a realistic, film-quality zombie makeover: pale greenish skin, sunken eyes, torn clothes. " + KEEP),
    ("cyberpunk", "Cyberpunk", "Fun", "Neon lights, futuristic city mood",
     "Restyle this in a cyberpunk aesthetic: neon pink and cyan lighting, futuristic tech details, rainy reflective "
     "surfaces. " + KEEP),
    ("bricks", "Toy bricks", "Fun", "Built from plastic toy bricks",
     "Rebuild this whole scene out of plastic toy building bricks and minifigure-style figures. " + KEEP),
    ("sticker", "Sticker", "Fun", "Die-cut sticker with white border",
     "Turn the main subject into a glossy die-cut sticker with a thick white border on a plain background."),
    # Seasonal
    ("winter", "Winter", "Seasonal", "Snow and cold winter light",
     "Make it winter: fresh snow on surfaces, cold soft daylight, visible breath in the air. " + KEEP),
    ("festive", "Festive", "Seasonal", "Holiday lights and decorations",
     "Add a festive holiday mood: warm string lights, tasteful decorations and soft bokeh. " + KEEP),
]

STYLES = [{"id": i, "name": n, "group": g, "hint": h, "prompt": p} for i, n, g, h, p in _ROWS]
_BY_ID = {s["id"]: s for s in STYLES}


def get(style_id: str) -> Optional[dict]:
    return _BY_ID.get((style_id or "").strip().lstrip("/").lower())


def public() -> list:
    """What the editor shows. The prompt is included so the user can see and tweak exactly what will be asked."""
    return [dict(s) for s in STYLES]


def instruction(style_id: str, extra: str = "") -> str:
    """The instruction sent to the model: the style's own, plus anything the user typed."""
    s = get(style_id)
    extra = (extra or "").strip()
    if not s:
        return extra
    return f"{s['prompt']} Also: {extra}" if extra else s["prompt"]
