import math
import random
from io import BytesIO, StringIO

import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Point, Polygon

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except Exception:
    streamlit_image_coordinates = None

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(page_title="Native Plant Generator", layout="wide")

# ============================================================
# SETTINGS
# ============================================================

GOOGLE_MAPS_API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", "")

CANVAS_WIDTH = 980
CANVAS_HEIGHT = 640
GOOGLE_STATIC_ZOOM = 20  # intentionally fixed: no user-facing zoom control
GOOGLE_IMAGE_SCALE = 2
WHITE_FADE_OVERLAY = 0.50

DENSITY_OPTIONS = {
    "Low": 0.22,
    "Moderate": 0.34,
    "Dense": 0.48,
}

SPACING_FACTOR = {
    "Low": 1.45,
    "Moderate": 1.25,
    "Dense": 1.05,
}

STATE_TO_REGIONS = {
    "California": ["California", "Southwest"],
    "Florida": ["Florida", "Gulf Coast", "Southeast"],
    "Texas": ["Texas", "Gulf Coast", "Southeast", "Southwest"],
    "Virginia": ["Mid-Atlantic", "Southeast"],
    "Maryland": ["Mid-Atlantic"],
    "New York": ["Northeast", "Mid-Atlantic"],
    "North Carolina": ["Southeast", "Mid-Atlantic"],
    "South Carolina": ["Southeast"],
    "Georgia": ["Southeast"],
    "Pennsylvania": ["Northeast", "Mid-Atlantic"],
    "Illinois": ["Midwest"],
    "Wisconsin": ["Midwest"],
    "Colorado": ["Mountain", "Southwest"],
    "Oregon": ["Pacific Northwest"],
    "Washington": ["Pacific Northwest"],
}

ZONE_INTENTS = [
    "Privacy",
    "Shade",
    "High Water Requirements",
    "Low Water Requirements",
    "Full Sun",
    "Part Shade",
    "Foundation Planting",
    "Pollinator Planting",
    "Meadow / Naturalistic",
    "Entry Planting",
]

# symbol_color controls colored 2D plan symbols.
PLANTS = [
    # California
    {"name": "Carex pansa", "common": "Sand Dune Sedge", "code": "CP", "regions": ["California"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Matrix", "Groundcover"], "intents": ["Full Sun", "Part Shade", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 2, "symbol_color": "#8BA76A", "weight": 5},
    {"name": "Festuca californica", "common": "California Fescue", "code": "FC", "regions": ["California"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Part Shade", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 2, "symbol_color": "#7F9A82", "weight": 4},
    {"name": "Muhlenbergia rigens", "common": "Deergrass", "code": "MR", "regions": ["California", "Southwest"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 5, "symbol_color": "#B8A46D", "weight": 4},
    {"name": "Arctostaphylos densiflora 'Howard McMinn'", "common": "Howard McMinn Manzanita", "code": "AHM", "regions": ["California"], "usda_min": 8, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Structure", "Shrub"], "intents": ["Privacy", "Full Sun", "Part Shade", "Low Water Requirements", "Foundation Planting"], "spread_ft": 8, "symbol_color": "#6F7F6C", "weight": 3},
    {"name": "Heteromeles arbutifolia", "common": "Toyon", "code": "HA", "regions": ["California"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Structure", "Shrub"], "intents": ["Privacy", "Shade", "Full Sun", "Part Shade", "Low Water Requirements"], "spread_ft": 10, "symbol_color": "#4F6F52", "weight": 2},
    {"name": "Salvia spathacea", "common": "Hummingbird Sage", "code": "SS", "regions": ["California"], "usda_min": 8, "usda_max": 10, "sun": ["Part Shade"], "water": ["Moderate"], "roles": ["Accent", "Perennial"], "intents": ["Part Shade", "Pollinator Planting", "Foundation Planting"], "spread_ft": 4, "symbol_color": "#9B3E72", "weight": 3},
    {"name": "Eriogonum fasciculatum", "common": "California Buckwheat", "code": "EF", "regions": ["California", "Southwest"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Accent", "Shrub"], "intents": ["Full Sun", "Low Water Requirements", "Pollinator Planting", "Meadow / Naturalistic"], "spread_ft": 5, "symbol_color": "#C7B47E", "weight": 3},
    {"name": "Quercus agrifolia", "common": "Coast Live Oak", "code": "QA", "regions": ["California"], "usda_min": 8, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Canopy", "Tree"], "intents": ["Shade", "Privacy", "Low Water Requirements"], "spread_ft": 30, "symbol_color": "#3F5D3D", "weight": 1},

    # Florida / Gulf Coast / Southeast
    {"name": "Muhlenbergia capillaris", "common": "Muhly Grass", "code": "MC", "regions": ["Florida", "Gulf Coast", "Southeast"], "usda_min": 6, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low", "Moderate"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Low Water Requirements", "Meadow / Naturalistic", "Pollinator Planting"], "spread_ft": 3, "symbol_color": "#C87CA0", "weight": 5},
    {"name": "Serenoa repens", "common": "Saw Palmetto", "code": "SR", "regions": ["Florida", "Gulf Coast", "Southeast"], "usda_min": 8, "usda_max": 11, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Structure", "Shrub"], "intents": ["Privacy", "Full Sun", "Part Shade", "Low Water Requirements", "Foundation Planting"], "spread_ft": 8, "symbol_color": "#5C7A54", "weight": 3},
    {"name": "Ilex vomitoria", "common": "Yaupon Holly", "code": "IV", "regions": ["Florida", "Gulf Coast", "Southeast", "Texas"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Structure", "Shrub"], "intents": ["Privacy", "Shade", "Full Sun", "Part Shade", "Foundation Planting"], "spread_ft": 8, "symbol_color": "#315C45", "weight": 3},
    {"name": "Zamia integrifolia", "common": "Coontie", "code": "ZI", "regions": ["Florida", "Gulf Coast"], "usda_min": 8, "usda_max": 11, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Matrix", "Groundcover"], "intents": ["Full Sun", "Part Shade", "Low Water Requirements", "Foundation Planting"], "spread_ft": 3, "symbol_color": "#4E7A50", "weight": 4},
    {"name": "Tripsacum dactyloides", "common": "Fakahatchee Grass", "code": "TD", "regions": ["Florida", "Gulf Coast", "Southeast"], "usda_min": 8, "usda_max": 11, "sun": ["Full Sun", "Part Shade"], "water": ["Moderate", "High"], "roles": ["Matrix", "Grass"], "intents": ["High Water Requirements", "Full Sun", "Part Shade", "Privacy"], "spread_ft": 5, "symbol_color": "#789262", "weight": 4},
    {"name": "Conradina canescens", "common": "False Rosemary", "code": "CC", "regions": ["Florida", "Gulf Coast"], "usda_min": 8, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Accent", "Shrub"], "intents": ["Full Sun", "Low Water Requirements", "Pollinator Planting"], "spread_ft": 3, "symbol_color": "#A7B8A0", "weight": 3},
    {"name": "Sabal minor", "common": "Dwarf Palmetto", "code": "SM", "regions": ["Florida", "Gulf Coast", "Southeast", "Texas"], "usda_min": 7, "usda_max": 10, "sun": ["Part Shade", "Full Sun"], "water": ["Moderate", "High"], "roles": ["Structure", "Shrub"], "intents": ["Part Shade", "High Water Requirements", "Privacy", "Foundation Planting"], "spread_ft": 5, "symbol_color": "#426C4A", "weight": 3},

    # Texas / Southeast / Mid-Atlantic / Midwest
    {"name": "Schizachyrium scoparium", "common": "Little Bluestem", "code": "SSK", "regions": ["Texas", "Southeast", "Mid-Atlantic", "Midwest"], "usda_min": 3, "usda_max": 9, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 2, "symbol_color": "#B07D52", "weight": 5},
    {"name": "Bouteloua gracilis", "common": "Blue Grama", "code": "BG", "regions": ["Texas", "Southwest", "Mountain", "Midwest"], "usda_min": 3, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 2, "symbol_color": "#BCA76A", "weight": 5},
    {"name": "Echinacea purpurea", "common": "Purple Coneflower", "code": "EP", "regions": ["Texas", "Southeast", "Mid-Atlantic", "Midwest"], "usda_min": 3, "usda_max": 9, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Accent", "Perennial"], "intents": ["Full Sun", "Part Shade", "Pollinator Planting", "Meadow / Naturalistic"], "spread_ft": 2, "symbol_color": "#9C6DAD", "weight": 4},
    {"name": "Rudbeckia fulgida", "common": "Black-Eyed Susan", "code": "RF", "regions": ["Southeast", "Mid-Atlantic", "Midwest", "Texas"], "usda_min": 3, "usda_max": 9, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Accent", "Perennial"], "intents": ["Full Sun", "Part Shade", "Pollinator Planting", "Meadow / Naturalistic"], "spread_ft": 2, "symbol_color": "#D1A231", "weight": 4},
    {"name": "Itea virginica", "common": "Virginia Sweetspire", "code": "IT", "regions": ["Southeast", "Mid-Atlantic"], "usda_min": 5, "usda_max": 9, "sun": ["Full Sun", "Part Shade"], "water": ["Moderate", "High"], "roles": ["Structure", "Shrub"], "intents": ["Part Shade", "High Water Requirements", "Foundation Planting", "Pollinator Planting"], "spread_ft": 5, "symbol_color": "#6F8E55", "weight": 3},
    {"name": "Amelanchier canadensis", "common": "Serviceberry", "code": "ACN", "regions": ["Northeast", "Mid-Atlantic", "Southeast", "Midwest"], "usda_min": 4, "usda_max": 8, "sun": ["Full Sun", "Part Shade"], "water": ["Moderate"], "roles": ["Canopy", "Tree"], "intents": ["Shade", "Part Shade", "Foundation Planting", "Pollinator Planting"], "spread_ft": 15, "symbol_color": "#55704E", "weight": 2},
    {"name": "Carpinus caroliniana", "common": "American Hornbeam", "code": "CAR", "regions": ["Northeast", "Mid-Atlantic", "Southeast", "Midwest"], "usda_min": 3, "usda_max": 9, "sun": ["Part Shade", "Full Sun"], "water": ["Moderate", "High"], "roles": ["Canopy", "Tree"], "intents": ["Shade", "Privacy", "Part Shade", "High Water Requirements"], "spread_ft": 20, "symbol_color": "#405B3E", "weight": 1},
]

# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"] { background: #ffffff; }
    [data-testid="stSidebar"] { background: #f3f5f7; border-right: 1px solid #e5e7eb; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #0b0b0b; }
    .block-container { padding-top: 1.25rem; padding-bottom: 2rem; max-width: 1550px; }
    .app-title { font-size: 26px; font-weight: 900; letter-spacing: .03em; line-height: 1; margin-bottom: 4px; }
    .app-byline { font-size: 12px; font-weight: 700; margin-bottom: 22px; }
    .step-title { font-size: 18px; font-weight: 800; margin-top: 26px; margin-bottom: 12px; }
    .hint { font-size: 12px; color: #6b7280; line-height: 1.35; }
    .zone-chip { display:inline-block; padding: 6px 9px; margin: 0 5px 6px 0; background:#fff; border:1px solid #d1d5db; border-radius:999px; font-size:12px; font-weight:700; }
    .metric-card { background:#f7f7f4; border:1px solid #e5e7eb; border-radius:10px; padding:12px 14px; }
    div.stButton > button, div.stDownloadButton > button { border-radius: 8px; font-weight: 800; }
    div[data-testid="stSidebar"] div.stButton > button[kind="primary"] { background:#000 !important; border-color:#000 !important; color:#fff !important; }
    table { font-size: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "address": "",
    "formatted_address": "",
    "lat": None,
    "lon": None,
    "feet_per_pixel": None,
    "satellite_image": None,
    "faded_satellite_image": None,
    "zones": [],
    "current_trace_points": [],
    "last_trace_click": None,
    "placed_plants": [],
    "plant_id_counter": 1,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ============================================================
# GOOGLE MAPS
# ============================================================

@st.cache_data(show_spinner=False)
def geocode_address_google(address, api_key):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "OK" or not data.get("results"):
        raise ValueError(f"Geocoding failed: {data.get('status', 'UNKNOWN')}")
    loc = data["results"][0]["geometry"]["location"]
    formatted = data["results"][0].get("formatted_address", address)
    return float(loc["lat"]), float(loc["lng"]), formatted

@st.cache_data(show_spinner=False)
def fetch_google_satellite_image(lat, lon, api_key):
    url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{lat},{lon}",
        "zoom": GOOGLE_STATIC_ZOOM,
        "size": f"{CANVAS_WIDTH}x{CANVAS_HEIGHT}",
        "scale": GOOGLE_IMAGE_SCALE,
        "maptype": "satellite",
        "format": "png",
        "key": api_key,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content)).convert("RGB")
    return image.resize((CANVAS_WIDTH, CANVAS_HEIGHT))

def fade_image_with_white(image, opacity=0.50):
    white = Image.new("RGB", image.size, "white")
    return Image.blend(image.convert("RGB"), white, opacity)

# ============================================================
# GEOMETRY + PLANTING GENERATION
# ============================================================

def normalize_polygon(points):
    if not points or len(points) < 3:
        return None
    poly = Polygon(points)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area <= 0:
        return None
    return poly

def point_buffer_fits(poly, x, y, radius):
    return poly.contains(Point(x, y).buffer(radius))

def overlaps_existing(x, y, radius, placed, spacing_factor):
    for item in placed:
        distance = math.dist((x, y), (item["x"], item["y"]))
        if distance < (radius + item["radius"]) * spacing_factor:
            return True
    return False

def next_plant_id():
    pid = st.session_state.plant_id_counter
    st.session_state.plant_id_counter += 1
    return pid

def calculate_feet_per_pixel(latitude, zoom):
    """Approximate ground resolution for Google Web Mercator tiles.

    Because this app resizes Google Static Maps scale=2 imagery back to the
    requested logical image size, this returns feet per displayed app pixel.
    """
    meters_per_pixel = 156543.03392 * math.cos(math.radians(latitude)) / (2 ** zoom)
    return meters_per_pixel * 3.28084

def plant_radius_px(plant, feet_per_pixel=None):
    """Convert botanical spread in feet to a true map-scaled circle radius in pixels."""
    feet_per_pixel = feet_per_pixel or st.session_state.get("feet_per_pixel") or 1.0
    spread_ft = float(plant.get("spread_ft", 3))
    radius_px = (spread_ft / 2.0) / max(feet_per_pixel, 0.0001)
    # Keep very small symbols minimally clickable/visible while preserving scale closely.
    return max(2.5, radius_px)

def polygon_area_sqft(poly):
    feet_per_pixel = st.session_state.get("feet_per_pixel") or 1.0
    return poly.area * (feet_per_pixel ** 2)

def get_scaled_font(size):
    size = int(max(5, min(22, size)))
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()

def centered_text(draw, xy, text, font, fill):
    x, y = xy
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except Exception:
        tw, th = draw.textsize(text, font=font)
    draw.text((x - tw / 2, y - th / 2), text, font=font, fill=fill)

def filter_plants(state_name, usda_zone, zone_intent):
    regions = STATE_TO_REGIONS.get(state_name, [state_name])
    candidates = []
    for plant in PLANTS:
        region_match = any(region in plant["regions"] for region in regions)
        zone_match = plant["usda_min"] <= usda_zone <= plant["usda_max"]
        intent_match = zone_intent in plant["intents"]
        flexible_match = (
            zone_intent in ["Entry Planting", "Foundation Planting"]
            and any(i in plant["intents"] for i in ["Foundation Planting", "Pollinator Planting", "Full Sun", "Part Shade"])
        )
        if region_match and zone_match and (intent_match or flexible_match):
            candidates.append(plant)

    if len(candidates) < 5:
        for plant in PLANTS:
            region_match = any(region in plant["regions"] for region in regions)
            zone_match = plant["usda_min"] <= usda_zone <= plant["usda_max"]
            if region_match and zone_match and plant not in candidates:
                candidates.append(plant)

    if len(candidates) < 5:
        for plant in PLANTS:
            zone_match = plant["usda_min"] <= usda_zone <= plant["usda_max"]
            if zone_match and plant not in candidates:
                candidates.append(plant)

    return candidates[:12]

def weighted_choice(plants):
    weights = [max(1, int(p.get("weight", 1))) for p in plants]
    return random.choices(plants, weights=weights, k=1)[0]

def generate_for_zone(zone, plant_pool, density_name):
    poly = normalize_polygon(zone["points"])
    if poly is None or not plant_pool:
        return []

    target_coverage = DENSITY_OPTIONS[density_name]
    spacing_factor = SPACING_FACTOR[density_name]
    target_area = poly.area * target_coverage
    placed = []
    placed_area = 0
    minx, miny, maxx, maxy = poly.bounds
    attempts = 0
    max_attempts = 12000

    while placed_area < target_area and attempts < max_attempts and len(placed) < 450:
        attempts += 1
        plant = weighted_choice(plant_pool)
        radius = plant_radius_px(plant, st.session_state.get("feet_per_pixel"))
        if (maxx - minx) < radius * 2 or (maxy - miny) < radius * 2:
            break

        x = random.uniform(minx + radius, maxx - radius)
        y = random.uniform(miny + radius, maxy - radius)

        if not point_buffer_fits(poly, x, y, radius):
            continue
        if overlaps_existing(x, y, radius, placed, spacing_factor):
            continue

        placed.append({
            "id": next_plant_id(),
            "x": x,
            "y": y,
            "radius": radius,
            "plant": plant,
            "zone": zone["name"],
            "intent": zone["intent"],
        })
        placed_area += math.pi * radius * radius

    return placed

def generate_all_zones(state_name, usda_zone, density_name):
    all_placed = []
    for zone in st.session_state.zones:
        pool = filter_plants(state_name, usda_zone, zone["intent"])
        zone_placed = generate_for_zone(zone, pool, density_name)
        all_placed.extend(zone_placed)
    st.session_state.placed_plants = all_placed

# ============================================================
# RENDERING
# ============================================================

def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def draw_zone(draw, points, label, outline=(0, 0, 0), fill=(255, 255, 255, 45), width=3):
    if len(points) >= 3:
        draw.polygon(points, fill=fill)
        draw.line(points + [points[0]], fill=outline, width=width)
        x, y = points[0]
        draw.rectangle((x, y - 18, x + max(90, len(label) * 7), y), fill=(255, 255, 255, 210))
        draw.text((x + 4, y - 15), label, fill=(0, 0, 0))
    elif len(points) >= 2:
        draw.line(points, fill=(0, 0, 0), width=3)
    for x, y in points:
        r = 5
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(255, 255, 255), outline=(0, 0, 0), width=2)

def render_working_image():
    if st.session_state.faded_satellite_image is None:
        base = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), "#f4f1ea")
    else:
        base = st.session_state.faded_satellite_image.copy().convert("RGBA")

    overlay = Image.new("RGBA", base.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    for idx, zone in enumerate(st.session_state.zones, start=1):
        label = f"{idx}. {zone['name']}"
        draw_zone(draw, zone["points"], label, outline=(0, 0, 0), fill=(255, 255, 255, 55), width=3)

    if st.session_state.current_trace_points:
        draw_zone(draw, st.session_state.current_trace_points, "Current zone", outline=(0, 0, 0), fill=(255, 255, 255, 35), width=3)

    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

def render_plan_image(include_table=True):
    base = render_working_image().convert("RGBA")
    draw = ImageDraw.Draw(base)

    for item in st.session_state.placed_plants:
        plant = item["plant"]
        color = hex_to_rgb(plant["symbol_color"])
        x, y, r = item["x"], item["y"], item["radius"]
        draw.ellipse((x-r, y-r, x+r, y+r), fill=color + (165,), outline=(0, 0, 0, 230), width=1 if r < 6 else 2)
        code = plant["code"]
        # Text scales with symbol diameter. No white label background.
        font_size = max(5, min(16, r * 0.78))
        font = get_scaled_font(font_size)
        text_fill = (0, 0, 0, 235) if r >= 5 else (0, 0, 0, 0)
        if r >= 4.5:
            centered_text(draw, (x, y), code, font, text_fill)

    if not include_table:
        return base.convert("RGB")

    table_width = 440
    table = Image.new("RGBA", (table_width, CANVAS_HEIGHT), (255, 255, 255, 255))
    tdraw = ImageDraw.Draw(table)
    tdraw.text((18, 18), "Plant Schedule", fill=(0, 0, 0))
    tdraw.line((18, 40, table_width - 18, 40), fill=(0, 0, 0), width=2)

    df = plant_schedule_dataframe()
    y = 60
    headers = ["Code", "Qty", "Botanical Name", "Common Name"]
    x_positions = [18, 70, 118, 292]
    for x, h in zip(x_positions, headers):
        tdraw.text((x, y), h, fill=(80, 80, 80))
    y += 22
    tdraw.line((18, y - 6, table_width - 18, y - 6), fill=(220, 220, 220), width=1)

    for _, row in df.iterrows():
        if y > CANVAS_HEIGHT - 28:
            break
        color = hex_to_rgb(row["Color"])
        tdraw.ellipse((18, y + 3, 30, y + 15), fill=color + (220,), outline=(0, 0, 0))
        tdraw.text((34, y), str(row["Code"]), fill=(0, 0, 0))
        tdraw.text((70, y), str(row["Qty"]), fill=(0, 0, 0))
        tdraw.text((118, y), str(row["Botanical Name"])[:24], fill=(0, 0, 0))
        tdraw.text((292, y), str(row["Common Name"])[:18], fill=(0, 0, 0))
        y += 24
        tdraw.line((18, y - 6, table_width - 18, y - 6), fill=(235, 235, 235), width=1)

    combined = Image.new("RGB", (CANVAS_WIDTH + table_width, CANVAS_HEIGHT), "white")
    combined.paste(base.convert("RGB"), (0, 0))
    combined.paste(table.convert("RGB"), (CANVAS_WIDTH, 0))
    return combined

def image_to_png_bytes(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# ============================================================
# EXPORTS
# ============================================================

def plant_schedule_dataframe():
    counts = {}
    for item in st.session_state.placed_plants:
        plant = item["plant"]
        key = plant["name"]
        if key not in counts:
            counts[key] = {"plant": plant, "qty": 0}
        counts[key]["qty"] += 1

    rows = []
    for data in sorted(counts.values(), key=lambda d: d["plant"]["code"]):
        plant = data["plant"]
        rows.append({
            "Code": plant["code"],
            "Qty": data["qty"],
            "Botanical Name": plant["name"],
            "Common Name": plant["common"],
            "Color": plant["symbol_color"],
        })
    return pd.DataFrame(rows)

def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")

def hex_to_rgb_tuple(hex_color):
    """Return (r, g, b) from a hex color."""
    value = (hex_color or "#777777").strip().lstrip("#")
    if len(value) != 6:
        return (119, 119, 119)
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (119, 119, 119)

def nearest_aci_color(hex_color):
    """
    Approximate a hex color to a basic AutoCAD Color Index.
    This keeps the DXF simple and AutoCAD-friendly.
    """
    r, g, b = hex_to_rgb_tuple(hex_color)
    palette = {
        1: (255, 0, 0),       # red
        2: (255, 255, 0),     # yellow
        3: (0, 255, 0),       # green
        4: (0, 255, 255),     # cyan
        5: (0, 0, 255),       # blue
        6: (255, 0, 255),     # magenta
        7: (255, 255, 255),   # white/black depending on background
        8: (128, 128, 128),   # gray
        30: (255, 128, 0),
        40: (255, 191, 0),
        70: (0, 128, 0),
        90: (0, 128, 128),
        140: (0, 0, 128),
        200: (128, 0, 128),
    }
    def dist(c):
        return (r - c[0]) ** 2 + (g - c[1]) ** 2 + (b - c[2]) ** 2
    return min(palette.keys(), key=lambda idx: dist(palette[idx]))

def clean_dxf_layer_name(value, fallback="LAYER"):
    text = str(value or fallback).upper()
    for ch in '<>/\\":;?*|=,`':
        text = text.replace(ch, "_")
    text = text.replace(" ", "_")
    text = "".join(ch for ch in text if ch.isalnum() or ch in "_-$")
    return (text or fallback)[:31]

def dxf_pair(code, value):
    return f"{code}\n{value}\n"

def dxf_text_entity(layer, x, y, height, text, color=7):
    """Simple R12-compatible TEXT entity."""
    safe = str(text).replace("\n", " ").replace("\r", " ")
    out = []
    out.append(dxf_pair(0, "TEXT"))
    out.append(dxf_pair(8, layer))
    out.append(dxf_pair(62, color))
    out.append(dxf_pair(10, f"{x:.4f}"))
    out.append(dxf_pair(20, f"{y:.4f}"))
    out.append(dxf_pair(30, "0.0"))
    out.append(dxf_pair(40, f"{height:.4f}"))
    out.append(dxf_pair(1, safe))
    out.append(dxf_pair(7, "STANDARD"))
    return "".join(out)

def plan_to_dxf_bytes():
    """
    Export a geometry-only DXF.

    Important:
    - The satellite image is intentionally NOT exported.
    - This avoids broken IMAGE / IMAGEDEF references in AutoCAD.
    - The DXF contains only zone linework, plant circles, plant code text, and a legend.
    - Units are approximate feet, using the Google Static Maps feet-per-pixel calculation.
    """
    feet_per_pixel = float(st.session_state.get("feet_per_pixel") or 1.0)

    # R12-style DXF is intentionally used for maximum AutoCAD compatibility.
    dxf = StringIO()
    dxf.write(dxf_pair(0, "SECTION"))
    dxf.write(dxf_pair(2, "HEADER"))
    dxf.write(dxf_pair(9, "$ACADVER"))
    dxf.write(dxf_pair(1, "AC1009"))
    dxf.write(dxf_pair(9, "$INSUNITS"))
    dxf.write(dxf_pair(70, 2))  # feet
    dxf.write(dxf_pair(0, "ENDSEC"))

    dxf.write(dxf_pair(0, "SECTION"))
    dxf.write(dxf_pair(2, "TABLES"))

    # Layer table.
    layer_names = {"ZONES": 7, "PLANTS": 3, "PLANT_CODES": 7, "LEGEND": 7}
    for item in st.session_state.get("placed_plants", []):
        plant = item.get("plant", {})
        layer_names[clean_dxf_layer_name("PLANT_" + plant.get("code", "XX"), "PLANTS")] = nearest_aci_color(plant.get("symbol_color", "#777777"))
    for zone in st.session_state.get("zones", []):
        layer_names[clean_dxf_layer_name("ZONE_" + zone.get("name", "ZONE"), "ZONES")] = 7

    dxf.write(dxf_pair(0, "TABLE"))
    dxf.write(dxf_pair(2, "LAYER"))
    dxf.write(dxf_pair(70, len(layer_names)))
    for lname, color in layer_names.items():
        dxf.write(dxf_pair(0, "LAYER"))
        dxf.write(dxf_pair(2, lname))
        dxf.write(dxf_pair(70, 0))
        dxf.write(dxf_pair(62, color))
        dxf.write(dxf_pair(6, "CONTINUOUS"))
    dxf.write(dxf_pair(0, "ENDTAB"))
    dxf.write(dxf_pair(0, "ENDSEC"))

    dxf.write(dxf_pair(0, "SECTION"))
    dxf.write(dxf_pair(2, "ENTITIES"))

    # Zones as closed linework in approximate real-world feet.
    for zone in st.session_state.get("zones", []):
        pts = zone.get("points", [])
        if len(pts) < 3:
            continue
        layer = clean_dxf_layer_name("ZONE_" + zone.get("name", "ZONE"), "ZONES")
        closed_pts = pts + [pts[0]]
        for i in range(len(closed_pts) - 1):
            x1, y1 = closed_pts[i]
            x2, y2 = closed_pts[i + 1]
            dxf.write(dxf_pair(0, "LINE"))
            dxf.write(dxf_pair(8, layer))
            dxf.write(dxf_pair(62, 7))
            dxf.write(dxf_pair(10, f"{x1 * feet_per_pixel:.4f}"))
            dxf.write(dxf_pair(20, f"{-y1 * feet_per_pixel:.4f}"))
            dxf.write(dxf_pair(30, "0.0"))
            dxf.write(dxf_pair(11, f"{x2 * feet_per_pixel:.4f}"))
            dxf.write(dxf_pair(21, f"{-y2 * feet_per_pixel:.4f}"))
            dxf.write(dxf_pair(31, "0.0"))

        # Zone label.
        zx, zy = pts[0]
        dxf.write(dxf_text_entity(
            layer="ZONES",
            x=zx * feet_per_pixel,
            y=-zy * feet_per_pixel,
            height=2.0,
            text=f"{zone.get('name', 'Zone')} - {zone.get('intent', '')}",
            color=7,
        ))

    # Plants as colored circles and code text.
    for item in st.session_state.get("placed_plants", []):
        plant = item.get("plant", {})
        code = plant.get("code", "XX")
        layer = clean_dxf_layer_name("PLANT_" + code, "PLANTS")
        color = nearest_aci_color(plant.get("symbol_color", "#777777"))
        x = float(item.get("x", 0)) * feet_per_pixel
        y = -float(item.get("y", 0)) * feet_per_pixel
        r = max(0.1, float(item.get("radius", 1)) * feet_per_pixel)

        dxf.write(dxf_pair(0, "CIRCLE"))
        dxf.write(dxf_pair(8, layer))
        dxf.write(dxf_pair(62, color))
        dxf.write(dxf_pair(10, f"{x:.4f}"))
        dxf.write(dxf_pair(20, f"{y:.4f}"))
        dxf.write(dxf_pair(30, "0.0"))
        dxf.write(dxf_pair(40, f"{r:.4f}"))

        # Code text scales to symbol diameter and has no background.
        text_height = max(0.25, min(1.25, r * 0.45))
        dxf.write(dxf_text_entity(
            layer="PLANT_CODES",
            x=x - (len(code) * text_height * 0.22),
            y=y - (text_height * 0.35),
            height=text_height,
            text=code,
            color=7,
        ))

    # Legend / schedule, placed to the right of the map extents.
    schedule_df = plant_schedule_dataframe() if st.session_state.get("placed_plants") else pd.DataFrame()
    legend_x = CANVAS_WIDTH * feet_per_pixel + 20
    legend_y = 0
    dxf.write(dxf_text_entity("LEGEND", legend_x, legend_y, 2.5, "PLANT SCHEDULE", 7))
    legend_y -= 5
    if not schedule_df.empty:
        for _, row in schedule_df.iterrows():
            line = f"{row['Code']}  QTY {row['Qty']}  {row['Botanical Name']}  ({row['Common Name']})"
            dxf.write(dxf_text_entity("LEGEND", legend_x, legend_y, 1.5, line[:120], 7))
            legend_y -= 3.2

    dxf.write(dxf_pair(0, "ENDSEC"))
    dxf.write(dxf_pair(0, "EOF"))
    return BytesIO(dxf.getvalue().encode("ascii", errors="ignore"))

# ============================================================
# SIDEBAR UI
# ============================================================

with st.sidebar:
    st.markdown('<div class="app-title">NATIVE PLANT GENERATOR</div>', unsafe_allow_html=True)
    st.markdown('<div class="app-byline">by The Landscape Library</div>', unsafe_allow_html=True)
    st.divider()

    st.markdown('<div class="step-title">1. Site</div>', unsafe_allow_html=True)
    address = st.text_input("Project address", placeholder="Example: 123 Main St, McLean, VA", value=st.session_state.address)
    load_satellite = st.button("Load Satellite Image", use_container_width=True)

    if load_satellite:
        if not GOOGLE_MAPS_API_KEY:
            st.error("Missing GOOGLE_MAPS_API_KEY in Streamlit Secrets.")
        elif not address.strip():
            st.warning("Enter a project address first.")
        else:
            try:
                with st.spinner("Loading satellite image..."):
                    lat, lon, formatted = geocode_address_google(address.strip(), GOOGLE_MAPS_API_KEY)
                    raw_img = fetch_google_satellite_image(lat, lon, GOOGLE_MAPS_API_KEY)
                    faded_img = fade_image_with_white(raw_img, WHITE_FADE_OVERLAY)
                    st.session_state.address = address.strip()
                    st.session_state.formatted_address = formatted
                    st.session_state.lat = lat
                    st.session_state.lon = lon
                    st.session_state.feet_per_pixel = calculate_feet_per_pixel(lat, GOOGLE_STATIC_ZOOM)
                    st.session_state.satellite_image = raw_img
                    st.session_state.faded_satellite_image = faded_img
                    st.session_state.zones = []
                    st.session_state.current_trace_points = []
                    st.session_state.last_trace_click = None
                    st.session_state.placed_plants = []
                    st.success("Satellite image loaded.")
                    st.rerun()
            except Exception as e:
                st.error(f"Satellite image could not be loaded: {e}")

    st.divider()
    st.markdown('<div class="step-title">2. Planting Zones</div>', unsafe_allow_html=True)
    zone_name = st.text_input("Zone name", value=f"Zone {len(st.session_state.zones) + 1}")
    zone_intent = st.selectbox("Zone design intent", ZONE_INTENTS, index=0)

    c1, c2 = st.columns(2)
    with c1:
        add_zone = st.button("Add Zone", use_container_width=True)
    with c2:
        clear_points = st.button("Clear Points", use_container_width=True)

    if clear_points:
        st.session_state.current_trace_points = []
        st.session_state.last_trace_click = None
        st.rerun()

    if add_zone:
        points = st.session_state.current_trace_points
        if len(points) < 3:
            st.warning("Click at least 3 points on the satellite image first.")
        else:
            cleaned_name = zone_name.strip() or f"Zone {len(st.session_state.zones) + 1}"
            st.session_state.zones.append({
                "name": cleaned_name,
                "intent": zone_intent,
                "points": [(float(x), float(y)) for x, y in points],
            })
            st.session_state.current_trace_points = []
            st.session_state.last_trace_click = None
            st.session_state.placed_plants = []
            st.rerun()

    if st.session_state.zones:
        st.markdown("<div class='hint'>Saved zones:</div>", unsafe_allow_html=True)
        for idx, z in enumerate(st.session_state.zones, start=1):
            st.markdown(f"<span class='zone-chip'>{idx}. {z['name']} · {z['intent']}</span>", unsafe_allow_html=True)
        if st.button("Delete Last Zone", use_container_width=True):
            st.session_state.zones = st.session_state.zones[:-1]
            st.session_state.placed_plants = []
            st.rerun()
        if st.button("Clear All Zones", use_container_width=True):
            st.session_state.zones = []
            st.session_state.current_trace_points = []
            st.session_state.placed_plants = []
            st.rerun()

    st.divider()
    st.markdown('<div class="step-title">3. Parameters</div>', unsafe_allow_html=True)
    state_name = st.selectbox("State", list(STATE_TO_REGIONS.keys()), index=list(STATE_TO_REGIONS.keys()).index("California"))
    usda_zone = st.selectbox("USDA hardiness zone", list(range(3, 12)), index=6)
    density_name = st.selectbox("Planting density", list(DENSITY_OPTIONS.keys()), index=1)

    generate = st.button("Generate Plant Design", type="primary", use_container_width=True)

    if generate:
        if not st.session_state.zones:
            st.warning("Create at least one planting zone first.")
        else:
            generate_all_zones(state_name, int(usda_zone), density_name)
            if st.session_state.placed_plants:
                st.success("Plant design generated.")
                st.rerun()
            else:
                st.warning("No plants could be generated. Try a larger zone or different state / USDA zone.")

# ============================================================
# MAIN UI
# ============================================================

main_col, schedule_col = st.columns([4.4, 1.35], gap="large")

with main_col:
    if st.session_state.faded_satellite_image is None:
        st.markdown("### Enter a location to begin")
        st.info("Load a satellite image, then click points around the planting area. Add each zone before drawing the next one.")
    else:
        st.caption(st.session_state.formatted_address or st.session_state.address)
        if st.session_state.get("feet_per_pixel"):
            st.caption(f"Approx. map scale: 1 pixel = {st.session_state.feet_per_pixel:.2f} ft | plant symbols use botanical spread in feet")
        working = render_working_image()

        if streamlit_image_coordinates is None:
            st.error("Missing package: streamlit-image-coordinates. Add it to requirements.txt and redeploy.")
            st.image(working, use_container_width=False)
        else:
            clicked = streamlit_image_coordinates(
                working,
                key=f"satellite_click_{st.session_state.address}_{len(st.session_state.zones)}_{len(st.session_state.current_trace_points)}",
                width=CANVAS_WIDTH,
            )
            if clicked and "x" in clicked and "y" in clicked:
                new_point = (int(clicked["x"]), int(clicked["y"]))
                if st.session_state.last_trace_click != new_point:
                    if not st.session_state.current_trace_points or math.dist(st.session_state.current_trace_points[-1], new_point) > 4:
                        st.session_state.current_trace_points.append(new_point)
                    st.session_state.last_trace_click = new_point
                    st.rerun()

        tool_a, tool_b, tool_c = st.columns([1, 1, 3])
        with tool_a:
            if st.button("Undo Point", use_container_width=True):
                st.session_state.current_trace_points = st.session_state.current_trace_points[:-1]
                st.session_state.last_trace_click = None
                st.rerun()
        with tool_b:
            st.metric("Current Points", len(st.session_state.current_trace_points))
        with tool_c:
            st.markdown("<div class='hint'>Click around a planting bed. Add Zone. Then draw the next zone while previous boundaries remain visible.</div>", unsafe_allow_html=True)

        if st.session_state.placed_plants:
            st.markdown("### Generated Plan View")
            final_plan = render_plan_image(include_table=False)
            st.image(final_plan, use_container_width=False)

with schedule_col:
    st.markdown("### Plan Schedule")
    if st.session_state.placed_plants:
        df = plant_schedule_dataframe()
        st.dataframe(df.drop(columns=["Color"]), hide_index=True, use_container_width=True)
        st.caption(f"Plant instances: {len(st.session_state.placed_plants)}")
        st.caption(f"Zones designed: {len(st.session_state.zones)}")

        png_img = render_plan_image(include_table=True)
        st.download_button(
            "Download Plan PNG",
            data=image_to_png_bytes(png_img),
            file_name="native-planting-plan.png",
            mime="image/png",
            use_container_width=True,
        )
        st.download_button(
            "Download Plant Schedule CSV",
            data=csv_bytes(df.drop(columns=["Color"])),
            file_name="native-plant-schedule.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            "Download Plan DXF",
            data=plan_to_dxf_bytes(),
            file_name="native-planting-plan.dxf",
            mime="application/dxf",
            use_container_width=True,
        )
    else:
        st.info("After generation, the plant schedule and downloads will appear here.")
        if st.session_state.zones:
            zone_rows = []
            for idx, z in enumerate(st.session_state.zones, start=1):
                poly = normalize_polygon(z["points"])
                zone_rows.append({
                    "Zone": idx,
                    "Name": z["name"],
                    "Intent": z["intent"],
                    "Approx. Area": round(polygon_area_sqft(poly)) if poly else 0,
                })
            st.dataframe(pd.DataFrame(zone_rows), hide_index=True, use_container_width=True)
