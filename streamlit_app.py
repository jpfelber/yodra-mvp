import math
import random
from io import BytesIO, StringIO
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st
import matplotlib.pyplot as plt
from PIL import Image, ImageEnhance
from shapely.geometry import Point, Polygon
from streamlit_drawable_canvas import st_canvas

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(page_title="Native Plant Design Generator", layout="wide")

# ============================================================
# SETTINGS
# ============================================================

GOOGLE_MAPS_API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", "")

CANVAS_WIDTH = 900
CANVAS_HEIGHT = 620
DEFAULT_ZOOM = 20
DEFAULT_IMAGE_SCALE = 2
WHITE_FADE_OVERLAY = 0.50

DENSITY_OPTIONS = {
    "Low": 0.22,
    "Moderate": 0.35,
    "Dense": 0.48,
}

SPACING_FACTOR = {
    "Low": 1.45,
    "Moderate": 1.25,
    "Dense": 1.05,
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

USDA_LOCATION_OPTIONS = {
    "5a - Cold / Upper Midwest / Mountain towns": {"zones": [5], "regions": ["Midwest", "Mountain"]},
    "5b - Cold / Upper Midwest / Mountain towns": {"zones": [5], "regions": ["Midwest", "Mountain"]},
    "6a - Northeast / Midwest / Interior West": {"zones": [6], "regions": ["Northeast", "Midwest", "Mountain"]},
    "6b - Northeast / Mid-Atlantic / Interior West": {"zones": [6], "regions": ["Northeast", "Mid-Atlantic", "Mountain"]},
    "7a - Mid-Atlantic / Pacific Northwest / Transition South": {"zones": [7], "regions": ["Mid-Atlantic", "Pacific Northwest", "Southeast"]},
    "7b - Mid-Atlantic / Pacific Northwest / Upper South": {"zones": [7], "regions": ["Mid-Atlantic", "Pacific Northwest", "Southeast"]},
    "8a - Southeast / Texas / Pacific Northwest": {"zones": [8], "regions": ["Southeast", "Texas", "Pacific Northwest"]},
    "8b - Southeast / Texas / Pacific Northwest / Coastal CA": {"zones": [8], "regions": ["Southeast", "Texas", "Pacific Northwest", "California"]},
    "9a - Florida / Gulf Coast / California / Southwest": {"zones": [9], "regions": ["Florida", "Gulf Coast", "California", "Southwest"]},
    "9b - Florida / Gulf Coast / Coastal California / Southwest": {"zones": [9], "regions": ["Florida", "Gulf Coast", "California", "Southwest"]},
    "10a - South Florida / Coastal Southern California": {"zones": [10], "regions": ["Florida", "California"]},
    "10b - South Florida / Coastal Southern California": {"zones": [10], "regions": ["Florida", "California"]},
}

# ============================================================
# PLANT DATABASE
# Add/edit this list as your real YODRA plant database grows.
# symbol_color controls the colored 2D plan symbol.
# ============================================================

PLANTS = [
    # California
    {"name": "Carex pansa", "common": "Sand Dune Sedge", "code": "CP", "regions": ["California"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Matrix", "Groundcover"], "intents": ["Full Sun", "Part Shade", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 2, "height_ft": 1, "symbol_color": "#8BA76A", "weight": 5},
    {"name": "Festuca californica", "common": "California Fescue", "code": "FC", "regions": ["California"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Part Shade", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 2, "height_ft": 2, "symbol_color": "#7F9A82", "weight": 4},
    {"name": "Muhlenbergia rigens", "common": "Deergrass", "code": "MR", "regions": ["California", "Southwest"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 5, "height_ft": 4, "symbol_color": "#B8A46D", "weight": 4},
    {"name": "Arctostaphylos densiflora 'Howard McMinn'", "common": "Howard McMinn Manzanita", "code": "AHM", "regions": ["California"], "usda_min": 8, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Structure", "Shrub"], "intents": ["Privacy", "Full Sun", "Part Shade", "Low Water Requirements", "Foundation Planting"], "spread_ft": 8, "height_ft": 7, "symbol_color": "#6F7F6C", "weight": 3},
    {"name": "Heteromeles arbutifolia", "common": "Toyon", "code": "HA", "regions": ["California"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Structure", "Shrub"], "intents": ["Privacy", "Shade", "Full Sun", "Part Shade", "Low Water Requirements"], "spread_ft": 10, "height_ft": 15, "symbol_color": "#4F6F52", "weight": 2},
    {"name": "Salvia spathacea", "common": "Hummingbird Sage", "code": "SS", "regions": ["California"], "usda_min": 8, "usda_max": 10, "sun": ["Part Shade"], "water": ["Moderate"], "roles": ["Accent", "Perennial"], "intents": ["Part Shade", "Pollinator Planting", "Foundation Planting"], "spread_ft": 4, "height_ft": 2, "symbol_color": "#9B3E72", "weight": 3},
    {"name": "Eriogonum fasciculatum", "common": "California Buckwheat", "code": "EF", "regions": ["California", "Southwest"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Accent", "Shrub"], "intents": ["Full Sun", "Low Water Requirements", "Pollinator Planting", "Meadow / Naturalistic"], "spread_ft": 5, "height_ft": 4, "symbol_color": "#C7B47E", "weight": 3},
    {"name": "Quercus agrifolia", "common": "Coast Live Oak", "code": "QA", "regions": ["California"], "usda_min": 8, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Canopy", "Tree"], "intents": ["Shade", "Privacy", "Low Water Requirements"], "spread_ft": 30, "height_ft": 40, "symbol_color": "#3F5D3D", "weight": 1},

    # Florida / Gulf Coast / Southeast
    {"name": "Muhlenbergia capillaris", "common": "Muhly Grass", "code": "MC", "regions": ["Florida", "Gulf Coast", "Southeast"], "usda_min": 6, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low", "Moderate"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Low Water Requirements", "Meadow / Naturalistic", "Pollinator Planting"], "spread_ft": 3, "height_ft": 3, "symbol_color": "#C87CA0", "weight": 5},
    {"name": "Serenoa repens", "common": "Saw Palmetto", "code": "SR", "regions": ["Florida", "Gulf Coast", "Southeast"], "usda_min": 8, "usda_max": 11, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Structure", "Shrub"], "intents": ["Privacy", "Full Sun", "Part Shade", "Low Water Requirements", "Foundation Planting"], "spread_ft": 8, "height_ft": 6, "symbol_color": "#5C7A54", "weight": 3},
    {"name": "Ilex vomitoria", "common": "Yaupon Holly", "code": "IV", "regions": ["Florida", "Gulf Coast", "Southeast", "Texas"], "usda_min": 7, "usda_max": 10, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Structure", "Shrub"], "intents": ["Privacy", "Shade", "Full Sun", "Part Shade", "Foundation Planting"], "spread_ft": 8, "height_ft": 12, "symbol_color": "#315C45", "weight": 3},
    {"name": "Zamia integrifolia", "common": "Coontie", "code": "ZI", "regions": ["Florida", "Gulf Coast"], "usda_min": 8, "usda_max": 11, "sun": ["Full Sun", "Part Shade"], "water": ["Low"], "roles": ["Matrix", "Groundcover"], "intents": ["Full Sun", "Part Shade", "Low Water Requirements", "Foundation Planting"], "spread_ft": 3, "height_ft": 2, "symbol_color": "#4E7A50", "weight": 4},
    {"name": "Tripsacum dactyloides", "common": "Fakahatchee Grass", "code": "TD", "regions": ["Florida", "Gulf Coast", "Southeast"], "usda_min": 8, "usda_max": 11, "sun": ["Full Sun", "Part Shade"], "water": ["Moderate", "High"], "roles": ["Matrix", "Grass"], "intents": ["High Water Requirements", "Full Sun", "Part Shade", "Privacy"], "spread_ft": 5, "height_ft": 5, "symbol_color": "#789262", "weight": 4},
    {"name": "Conradina canescens", "common": "False Rosemary", "code": "CC", "regions": ["Florida", "Gulf Coast"], "usda_min": 8, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Accent", "Shrub"], "intents": ["Full Sun", "Low Water Requirements", "Pollinator Planting"], "spread_ft": 3, "height_ft": 3, "symbol_color": "#A7B8A0", "weight": 3},
    {"name": "Sabal minor", "common": "Dwarf Palmetto", "code": "SM", "regions": ["Florida", "Gulf Coast", "Southeast", "Texas"], "usda_min": 7, "usda_max": 10, "sun": ["Part Shade", "Full Sun"], "water": ["Moderate", "High"], "roles": ["Structure", "Shrub"], "intents": ["Part Shade", "High Water Requirements", "Privacy", "Foundation Planting"], "spread_ft": 5, "height_ft": 5, "symbol_color": "#426C4A", "weight": 3},

    # Texas / Southeast / Mid-Atlantic
    {"name": "Schizachyrium scoparium", "common": "Little Bluestem", "code": "SSK", "regions": ["Texas", "Southeast", "Mid-Atlantic", "Midwest"], "usda_min": 3, "usda_max": 9, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 2, "height_ft": 3, "symbol_color": "#B07D52", "weight": 5},
    {"name": "Bouteloua gracilis", "common": "Blue Grama", "code": "BG", "regions": ["Texas", "Southwest", "Mountain", "Midwest"], "usda_min": 3, "usda_max": 10, "sun": ["Full Sun"], "water": ["Low"], "roles": ["Matrix", "Grass"], "intents": ["Full Sun", "Low Water Requirements", "Meadow / Naturalistic"], "spread_ft": 2, "height_ft": 2, "symbol_color": "#BCA76A", "weight": 5},
    {"name": "Echinacea purpurea", "common": "Purple Coneflower", "code": "EP", "regions": ["Texas", "Southeast", "Mid-Atlantic", "Midwest"], "usda_min": 3, "usda_max": 9, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Accent", "Perennial"], "intents": ["Full Sun", "Part Shade", "Pollinator Planting", "Meadow / Naturalistic"], "spread_ft": 2, "height_ft": 3, "symbol_color": "#9C6DAD", "weight": 4},
    {"name": "Rudbeckia fulgida", "common": "Black-Eyed Susan", "code": "RF", "regions": ["Southeast", "Mid-Atlantic", "Midwest", "Texas"], "usda_min": 3, "usda_max": 9, "sun": ["Full Sun", "Part Shade"], "water": ["Low", "Moderate"], "roles": ["Accent", "Perennial"], "intents": ["Full Sun", "Part Shade", "Pollinator Planting", "Meadow / Naturalistic"], "spread_ft": 2, "height_ft": 3, "symbol_color": "#D1A231", "weight": 4},
    {"name": "Itea virginica", "common": "Virginia Sweetspire", "code": "IT", "regions": ["Southeast", "Mid-Atlantic"], "usda_min": 5, "usda_max": 9, "sun": ["Full Sun", "Part Shade"], "water": ["Moderate", "High"], "roles": ["Structure", "Shrub"], "intents": ["Part Shade", "High Water Requirements", "Foundation Planting", "Pollinator Planting"], "spread_ft": 5, "height_ft": 5, "symbol_color": "#6F8E55", "weight": 3},
    {"name": "Amelanchier canadensis", "common": "Serviceberry", "code": "ACN", "regions": ["Northeast", "Mid-Atlantic", "Southeast", "Midwest"], "usda_min": 4, "usda_max": 8, "sun": ["Full Sun", "Part Shade"], "water": ["Moderate"], "roles": ["Canopy", "Tree"], "intents": ["Shade", "Part Shade", "Foundation Planting", "Pollinator Planting"], "spread_ft": 15, "height_ft": 20, "symbol_color": "#55704E", "weight": 2},
    {"name": "Carpinus caroliniana", "common": "American Hornbeam", "code": "CAR", "regions": ["Northeast", "Mid-Atlantic", "Southeast", "Midwest"], "usda_min": 3, "usda_max": 9, "sun": ["Part Shade", "Full Sun"], "water": ["Moderate", "High"], "roles": ["Canopy", "Tree"], "intents": ["Shade", "Privacy", "Part Shade", "High Water Requirements"], "spread_ft": 20, "height_ft": 25, "symbol_color": "#405B3E", "weight": 1},
]

# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "lat": None,
    "lon": None,
    "address": "",
    "satellite_image": None,
    "faded_satellite_image": None,
    "zones": [],
    "placed_plants": [],
    "locked_plant_names": [],
    "plant_id_counter": 1,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ============================================================
# SATELLITE + GEOCODING
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
def fetch_google_satellite_image(lat, lon, zoom, width, height, api_key):
    url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{lat},{lon}",
        "zoom": zoom,
        "size": f"{width}x{height}",
        "scale": DEFAULT_IMAGE_SCALE,
        "maptype": "satellite",
        "format": "png",
        "key": api_key,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content)).convert("RGB")
    return image.resize((width, height))

@st.cache_data(show_spinner=False)
def fetch_openstreetmap_placeholder(address):
    # Fallback only. This does NOT provide satellite imagery.
    image = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), "#e8e5dc")
    return image

def fade_image_with_white(image, opacity=0.50):
    image = image.convert("RGB")
    white = Image.new("RGB", image.size, "white")
    return Image.blend(image, white, opacity)

# ============================================================
# GEOMETRY + GENERATION HELPERS
# ============================================================

def get_polygon_points_from_canvas(canvas_json):
    if not canvas_json or "objects" not in canvas_json:
        return None
    objects = canvas_json.get("objects", [])
    if not objects:
        return None
    obj = objects[-1]
    if obj.get("type") != "path" and "path" not in obj:
        return None
    points = []
    for command in obj.get("path", []):
        if len(command) >= 3 and command[0] in ["M", "L"]:
            points.append((float(command[1]), float(command[2])))
    return points if len(points) >= 3 else None

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

def plant_radius_px(plant):
    # Symbol radius is proportional but intentionally compressed for readability on satellite imagery.
    return max(7, min(44, plant["spread_ft"] * 3.0))

def next_plant_id():
    pid = st.session_state.plant_id_counter
    st.session_state.plant_id_counter += 1
    return pid

def zone_filters_from_intent(zone_intent):
    sun = None
    water = None
    role_boosts = []

    if zone_intent == "Full Sun":
        sun = "Full Sun"
    elif zone_intent == "Part Shade" or zone_intent == "Shade":
        sun = "Part Shade"
    elif zone_intent == "Low Water Requirements":
        water = "Low"
    elif zone_intent == "High Water Requirements":
        water = "High"
    elif zone_intent == "Privacy":
        role_boosts = ["Structure", "Shrub", "Canopy", "Tree"]
    elif zone_intent == "Foundation Planting":
        role_boosts = ["Structure", "Shrub", "Matrix", "Groundcover"]
    elif zone_intent == "Meadow / Naturalistic":
        role_boosts = ["Matrix", "Grass", "Accent", "Perennial"]
    elif zone_intent == "Pollinator Planting":
        role_boosts = ["Accent", "Perennial", "Shrub"]

    return sun, water, role_boosts

def plant_matches_zone(plant, zone_intent, usda_info):
    selected_zones = usda_info["zones"]
    selected_regions = usda_info["regions"]

    if not any(plant["usda_min"] <= z <= plant["usda_max"] for z in selected_zones):
        return False

    if not any(region in plant["regions"] for region in selected_regions):
        return False

    preferred_sun, preferred_water, _ = zone_filters_from_intent(zone_intent)

    if preferred_sun and preferred_sun not in plant["sun"]:
        return False

    if preferred_water == "High":
        if "High" not in plant["water"] and "Moderate" not in plant["water"]:
            return False
    elif preferred_water and preferred_water not in plant["water"]:
        return False

    # Soft intent matching: exact intent match gets handled by weighting, not hard exclusion.
    return True

def weighted_palette_for_zone(zone_intent, usda_info, locked_names):
    candidates = [p for p in PLANTS if plant_matches_zone(p, zone_intent, usda_info)]

    if not candidates:
        # Fallback: same USDA only, regardless of region.
        selected_zones = usda_info["zones"]
        candidates = [p for p in PLANTS if any(p["usda_min"] <= z <= p["usda_max"] for z in selected_zones)]

    weighted = []
    _, _, role_boosts = zone_filters_from_intent(zone_intent)

    for plant in candidates:
        weight = plant.get("weight", 1)
        if zone_intent in plant.get("intents", []):
            weight += 5
        if any(role in plant.get("roles", []) for role in role_boosts):
            weight += 4
        if plant["name"] in locked_names:
            weight += 20
        weighted.append((plant, max(1, weight)))

    return weighted

def choose_plant(weighted_plants):
    plants = [item[0] for item in weighted_plants]
    weights = [item[1] for item in weighted_plants]
    return random.choices(plants, weights=weights, k=1)[0]

def generate_plants_for_zone(zone, usda_info, density, locked_names, existing_locked_instances):
    poly = normalize_polygon(zone["points"])
    if poly is None:
        return []

    weighted_plants = weighted_palette_for_zone(zone["intent"], usda_info, locked_names)
    if not weighted_plants:
        return []

    minx, miny, maxx, maxy = poly.bounds
    target_area = poly.area * DENSITY_OPTIONS[density]
    spacing = SPACING_FACTOR[density]
    placed = [p for p in existing_locked_instances if p.get("zone_id") == zone["id"]]
    new_items = []
    covered_area = sum(math.pi * (p["radius"] ** 2) for p in placed)
    max_attempts = 12000
    attempts = 0

    while covered_area < target_area and attempts < max_attempts and len(placed) + len(new_items) < 500:
        attempts += 1
        plant = choose_plant(weighted_plants)
        radius = plant_radius_px(plant)

        if (maxx - minx) < radius * 2 or (maxy - miny) < radius * 2:
            continue

        x = random.uniform(minx + radius, maxx - radius)
        y = random.uniform(miny + radius, maxy - radius)

        if not point_buffer_fits(poly, x, y, radius):
            continue

        if overlaps_existing(x, y, radius, placed + new_items, spacing):
            continue

        item = {
            "id": next_plant_id(),
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "zone_intent": zone["intent"],
            "x": x,
            "y": y,
            "radius": radius,
            "plant": plant,
            "locked": plant["name"] in locked_names,
        }
        new_items.append(item)
        covered_area += math.pi * radius ** 2

    return placed + new_items

def run_generation(usda_label, density, locked_names, keep_locked_instances):
    usda_info = USDA_LOCATION_OPTIONS[usda_label]
    existing_locked_instances = []
    if keep_locked_instances:
        existing_locked_instances = [p for p in st.session_state.placed_plants if p.get("plant", {}).get("name") in locked_names]
        for item in existing_locked_instances:
            item["locked"] = True

    generated = []
    for zone in st.session_state.zones:
        generated.extend(generate_plants_for_zone(zone, usda_info, density, locked_names, existing_locked_instances))

    st.session_state.placed_plants = generated

# ============================================================
# EXPORT HELPERS
# ============================================================

def render_plan_image(base_image, zones, placed_plants):
    image = base_image.copy().convert("RGB")
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.imshow(image, extent=(0, CANVAS_WIDTH, CANVAS_HEIGHT, 0), zorder=0)

    for zone in zones:
        pts = zone["points"] + [zone["points"][0]]
        xs, ys = zip(*pts)
        ax.plot(xs, ys, linewidth=2.0, zorder=2)
        ax.text(zone["points"][0][0], zone["points"][0][1], f"{zone['name']} | {zone['intent']}", fontsize=8, zorder=4)

    for item in placed_plants:
        plant = item["plant"]
        circle = plt.Circle(
            (item["x"], item["y"]),
            item["radius"],
            facecolor=plant["symbol_color"],
            edgecolor="black",
            linewidth=1.8 if item.get("locked") else 1.0,
            alpha=0.78,
            zorder=3,
        )
        ax.add_patch(circle)
        ax.text(item["x"], item["y"], plant["code"], ha="center", va="center", fontsize=8, fontweight="bold", zorder=4)

    ax.set_xlim(0, CANVAS_WIDTH)
    ax.set_ylim(CANVAS_HEIGHT, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig

def fig_to_png_bytes(fig):
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=220, bbox_inches="tight")
    buffer.seek(0)
    return buffer

def plant_schedule_dataframe(placed_plants):
    rows = []
    counts = {}
    for item in placed_plants:
        name = item["plant"]["name"]
        counts[name] = counts.get(name, 0) + 1

    for name, count in sorted(counts.items()):
        plant = next(p for p in PLANTS if p["name"] == name)
        rows.append({
            "Code": plant["code"],
            "Qty": count,
            "Botanical Name": plant["name"],
            "Common Name": plant["common"],
            "Spread": f"{plant['spread_ft']} ft",
            "Height": f"{plant['height_ft']} ft",
            "Water": ", ".join(plant["water"]),
            "Sun": ", ".join(plant["sun"]),
        })
    return pd.DataFrame(rows)

def dataframe_to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown("### Native Plant Design Generator")
    st.caption("Address → satellite image → planting zones → generated native planting plan")

    st.divider()
    st.header("1. Site")
    address = st.text_input("Project address", value=st.session_state.address, placeholder="Example: 123 Main St, McLean, VA")
    zoom = st.slider("Satellite zoom", 18, 21, DEFAULT_ZOOM)

    if st.button("Load Satellite Image", use_container_width=True):
        if not address.strip():
            st.warning("Enter an address first.")
        elif not GOOGLE_MAPS_API_KEY:
            st.error("Add GOOGLE_MAPS_API_KEY to Streamlit secrets before loading satellite imagery.")
        else:
            with st.spinner("Loading satellite image..."):
                try:
                    lat, lon, formatted = geocode_address_google(address.strip(), GOOGLE_MAPS_API_KEY)
                    satellite = fetch_google_satellite_image(lat, lon, zoom, CANVAS_WIDTH, CANVAS_HEIGHT, GOOGLE_MAPS_API_KEY)
                    faded = fade_image_with_white(satellite, WHITE_FADE_OVERLAY)
                    st.session_state.lat = lat
                    st.session_state.lon = lon
                    st.session_state.address = formatted
                    st.session_state.satellite_image = satellite
                    st.session_state.faded_satellite_image = faded
                    st.session_state.zones = []
                    st.session_state.placed_plants = []
                    st.success("Satellite image loaded.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Satellite image could not be loaded: {exc}")

    st.divider()
    st.header("2. Region")
    usda_label = st.selectbox("USDA hardiness zone + location", list(USDA_LOCATION_OPTIONS.keys()), index=8)
    density = st.selectbox("Planting density", list(DENSITY_OPTIONS.keys()), index=1)

    st.divider()
    generate_clicked = st.button("Generate Plant Design", type="primary", use_container_width=True)
    regenerate_clicked = st.button("Regenerate Around Locked Plant Names", use_container_width=True)

# ============================================================
# MAIN UI
# ============================================================

st.title("Native Plant Design Generator")
st.markdown("Enter an address, load faded satellite imagery, draw multiple planting zones, and generate a colored native planting plan.")

if st.session_state.faded_satellite_image is None:
    st.info("Start by entering an address in the sidebar and loading satellite imagery. You need a Google Maps API key in Streamlit secrets named `GOOGLE_MAPS_API_KEY`.")
else:
    st.caption(f"Loaded site: {st.session_state.address}")

left, right = st.columns([2.2, 1])

with left:
    st.subheader("Create Planting Zones")

    if st.session_state.faded_satellite_image is None:
        st.image(Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), "#f2f2f2"), caption="Satellite image will appear here.")
    else:
        zone_name = st.text_input("Zone name", value=f"Zone {len(st.session_state.zones) + 1}")
        zone_intent = st.selectbox("Zone type / design intent", ZONE_INTENTS)

        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 0.18)",
            stroke_width=3,
            stroke_color="#000000",
            background_image=st.session_state.faded_satellite_image,
            height=CANVAS_HEIGHT,
            width=CANVAS_WIDTH,
            drawing_mode="polygon",
            key=f"zone_canvas_{len(st.session_state.zones)}_{st.session_state.address}_{zoom}",
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Add Planting Zone", use_container_width=True):
                points = get_polygon_points_from_canvas(canvas_result.json_data if canvas_result else None)
                if not points:
                    st.warning("Draw a closed polygon first.")
                else:
                    zone_id = f"zone_{len(st.session_state.zones) + 1}_{random.randint(1000, 9999)}"
                    st.session_state.zones.append({
                        "id": zone_id,
                        "name": zone_name.strip() or f"Zone {len(st.session_state.zones) + 1}",
                        "intent": zone_intent,
                        "points": points,
                    })
                    st.session_state.placed_plants = []
                    st.success("Zone added.")
                    st.rerun()
        with c2:
            if st.button("Clear All Zones", use_container_width=True):
                st.session_state.zones = []
                st.session_state.placed_plants = []
                st.session_state.locked_plant_names = []
                st.rerun()

        if st.session_state.zones:
            st.subheader("Saved Zones")
            for idx, zone in enumerate(st.session_state.zones, start=1):
                poly = normalize_polygon(zone["points"])
                approx_area_px = poly.area if poly else 0
                row_a, row_b = st.columns([4, 1])
                with row_a:
                    st.caption(f"{idx}. {zone['name']} — {zone['intent']} — approx. {approx_area_px:,.0f} px²")
                with row_b:
                    if st.button("Delete", key=f"delete_zone_{zone['id']}"):
                        st.session_state.zones = [z for z in st.session_state.zones if z["id"] != zone["id"]]
                        st.session_state.placed_plants = [p for p in st.session_state.placed_plants if p.get("zone_id") != zone["id"]]
                        st.rerun()

with right:
    st.subheader("Locked Plant Names")
    generated_names = sorted({p["plant"]["name"] for p in st.session_state.placed_plants})

    if generated_names:
        st.session_state.locked_plant_names = st.multiselect(
            "Lock broad plant names before regenerating",
            generated_names,
            default=[name for name in st.session_state.locked_plant_names if name in generated_names],
            help="This preserves and prioritizes these plant names when regenerating. It does not manually place individual plants.",
        )
    else:
        st.caption("After generation, plant names will appear here for broad locking.")

    st.subheader("Matching Plant Pool")
    usda_info_preview = USDA_LOCATION_OPTIONS[usda_label]
    preview_candidates = []
    for intent in ZONE_INTENTS:
        preview_candidates.extend([p["name"] for p, _ in weighted_palette_for_zone(intent, usda_info_preview, [])])
    preview_names = sorted(set(preview_candidates))
    st.caption(f"{len(preview_names)} plants available for selected region/USDA filter.")
    with st.expander("View available plants"):
        for name in preview_names:
            plant = next(p for p in PLANTS if p["name"] == name)
            st.markdown(f"**{plant['name']}**")
            st.caption(f"{plant['common']} | {plant['code']} | {plant['spread_ft']} ft spread | {', '.join(plant['sun'])} | {', '.join(plant['water'])}")

# ============================================================
# GENERATION ACTIONS
# ============================================================

if generate_clicked:
    if not st.session_state.zones:
        st.warning("Create at least one planting zone before generating.")
    elif st.session_state.faded_satellite_image is None:
        st.warning("Load satellite imagery before generating.")
    else:
        run_generation(usda_label, density, locked_names=[], keep_locked_instances=False)
        st.success("Plant design generated.")
        st.rerun()

if regenerate_clicked:
    if not st.session_state.zones:
        st.warning("Create at least one planting zone before regenerating.")
    elif not st.session_state.locked_plant_names:
        st.warning("Select at least one plant name to lock before regenerating.")
    else:
        run_generation(usda_label, density, st.session_state.locked_plant_names, keep_locked_instances=True)
        st.success("Regenerated around locked plant names.")
        st.rerun()

# ============================================================
# OUTPUTS
# ============================================================

if st.session_state.faded_satellite_image is not None and (st.session_state.zones or st.session_state.placed_plants):
    st.divider()
    st.subheader("Generated Planting Plan")
    plan_fig = render_plan_image(
        st.session_state.faded_satellite_image,
        st.session_state.zones,
        st.session_state.placed_plants,
    )
    st.pyplot(plan_fig)

if st.session_state.placed_plants:
    st.subheader("Plant Schedule")
    schedule_df = plant_schedule_dataframe(st.session_state.placed_plants)
    st.dataframe(schedule_df, use_container_width=True)

    png_bytes = fig_to_png_bytes(plan_fig)
    csv_bytes = dataframe_to_csv_bytes(schedule_df)

    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "Download Planting Plan PNG",
            data=png_bytes,
            file_name="native-plant-design-satellite-plan.png",
            mime="image/png",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "Download Plant Schedule CSV",
            data=csv_bytes,
            file_name="native-plant-schedule.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.caption(f"Generated plants: {len(st.session_state.placed_plants)}")
    st.caption(f"Locked plant names: {len(st.session_state.locked_plant_names)}")
