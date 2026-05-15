import streamlit as st

# -------------------------
# PASSWORD PROTECTION
# -------------------------

PASSWORD = st.secrets["APP_PASSWORD"]

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("YODRA")
    st.markdown("### Private Beta Access")

    password = st.text_input("Enter access password", type="password")

    if st.button("Enter"):
        if password == PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")

    return False


if not check_password():
    st.stop()

# -------------------------
# YOUR APP BELOW
# -------------------------

import random
import math
import os
import html
import base64
from io import BytesIO, StringIO

import matplotlib.pyplot as plt
from PIL import Image, ImageDraw
from shapely.geometry import Polygon, Point
from streamlit_drawable_canvas import st_canvas
try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except Exception:
    streamlit_image_coordinates = None

# -----------------------------
# Compatibility patch
# -----------------------------
# streamlit-drawable-canvas still calls an older Streamlit helper named
# st.image.image_to_url when using background_image. Newer Streamlit versions
# removed that helper, which causes an AttributeError on image upload.
# This patch restores the expected helper by converting the PIL background image
# into a browser-safe base64 data URL.
def _yodra_image_to_url(image, width=None, clamp=False, channels="RGB", output_format="PNG", image_id=None):
    """Compatibility helper for streamlit-drawable-canvas background images.

    Newer Streamlit versions removed st.image.image_to_url, but
    streamlit-drawable-canvas still calls it. This replacement returns a
    base64 PNG data URL that the canvas component can use as its background.
    """
    if image is None:
        return None

    if isinstance(image, str):
        return image

    if not isinstance(image, Image.Image):
        image = Image.fromarray(image)

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"

try:
    # This is the exact object streamlit-drawable-canvas references: st.image.image_to_url
    st.image.image_to_url = _yodra_image_to_url
except Exception:
    pass

try:
    # Also patch Streamlit's image module for environments that reference it directly.
    import streamlit.elements.image as st_image
    st_image.image_to_url = _yodra_image_to_url
except Exception:
    pass

st.set_page_config(
    page_title="AI-Powered Planting Design Engine",
    layout="wide"
)

st.title("AI-Powered Planting Design Engine")
st.caption("Draw a planting boundary or upload a scaled bed image, trace the bedline, generate a hierarchy-based planting plan, preview the matching elevation, and download the result.")

# -----------------------------
# Canvas + Scale settings
# -----------------------------

MAX_CANVAS_WIDTH = 900
MAX_CANVAS_HEIGHT = 600
DEFAULT_BED_LENGTH_FEET = 50
DEFAULT_BED_WIDTH_FEET = 50
MAX_BED_FEET = 50

GRID_SPACING_FEET = 5

DENSITY_OPTIONS = {
    "Low": 0.30,
    "Moderate": 0.45,
    "Dense": 0.68,
    "Very Dense": 0.90
}

SPACING_BY_DENSITY = {
    "Low": 1.30,
    "Moderate": 1.15,
    "Dense": 1.05,
    "Very Dense": 1.00
}

MAX_PLANTS_BY_DENSITY = {
    "Low": 180,
    "Moderate": 260,
    "Dense": 350,
    "Very Dense": 500
}

# Placeholder used only while the plant database is being defined.
# Runtime radii are recalculated after the active bed scale is known.
def feet_to_canvas_radius(width_ft):
    return width_ft / 2

# -----------------------------
# Plant database
# -----------------------------

PLANTS = [
    {
        "name": "Carex pansa",
        "common_name": "Sand Dune Sedge",
        "code": "CP",
        "state": ["California"],
        "climate": ["Coastal"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Full Sun-Part Shade"],
        "water": ["Moderate-Low"],
        "spread_ft": 2,
        "height_ft": 1,
        "radius": feet_to_canvas_radius(2),
        "form": "Grass",
        "role": "Matrix",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Fine",
        "color_tone": "Green",
        "visual_weight": 1,
        "seasonality": "Evergreen",
        "image": "plant_images/carex-pansa.webp",
        "elevation_height": 28,
        "hierarchy": "Groundcover",
        "weight": 5,
        "allows_underplanting": False
    },
    {
        "name": "Eriogonum latifolium",
        "common_name": "Coast Buckwheat",
        "code": "EL",
        "state": ["California"],
        "climate": ["Coastal"],
        "usda_min": 8,
        "usda_max": 10,
        "sun": ["Full Sun"],
        "water": ["Low"],
        "spread_ft": 2,
        "height_ft": 2,
        "radius": feet_to_canvas_radius(2),
        "form": "Perennial",
        "role": "Accent",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Medium",
        "color_tone": "Silver-Green",
        "visual_weight": 2,
        "seasonality": "Evergreen",
        "image": "plant_images/eriogonum-latifolium.webp",
        "elevation_height": 34,
        "hierarchy": "Accent Layer",
        "weight": 3,
        "allows_underplanting": False
    },
    {
        "name": "Festuca californica",
        "common_name": "California Fescue",
        "code": "FC",
        "state": ["California"],
        "climate": ["Coastal"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Full Sun-Part Shade"],
        "water": ["Low-Moderate"],
        "spread_ft": 2,
        "height_ft": 2,
        "radius": feet_to_canvas_radius(2),
        "form": "Grass",
        "role": "Matrix",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Fine",
        "color_tone": "Blue-Green",
        "visual_weight": 1,
        "seasonality": "Evergreen",
        "image": "plant_images/festuca-californica.webp",
        "elevation_height": 34,
        "hierarchy": "Groundcover",
        "weight": 4,
        "allows_underplanting": False
    },
    {
        "name": "Salvia spathacea",
        "common_name": "Hummingbird Sage",
        "code": "SS",
        "state": ["California"],
        "climate": ["Coastal"],
        "usda_min": 8,
        "usda_max": 10,
        "sun": ["Part Shade-Full Shade"],
        "water": ["Moderate"],
        "spread_ft": 4,
        "height_ft": 2,
        "radius": feet_to_canvas_radius(4),
        "form": "Perennial",
        "role": "Accent",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Bold",
        "color_tone": "Dark Green",
        "visual_weight": 2,
        "seasonality": "Evergreen",
        "image": "plant_images/salvia-spathacea.webp",
        "elevation_height": 42,
        "hierarchy": "Mid Layer",
        "weight": 3,
        "allows_underplanting": False
    },
    {
        "name": "Iris douglasiana",
        "common_name": "Douglas Iris",
        "code": "ID",
        "state": ["California"],
        "climate": ["Coastal"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Full Sun-Part Shade"],
        "water": ["Moderate"],
        "spread_ft": 2,
        "height_ft": 2,
        "radius": feet_to_canvas_radius(2),
        "form": "Perennial",
        "role": "Accent",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Medium",
        "color_tone": "Green",
        "visual_weight": 2,
        "seasonality": "Evergreen",
        "image": "plant_images/iris-douglasiana.webp",
        "elevation_height": 42,
        "hierarchy": "Accent Layer",
        "weight": 3,
        "allows_underplanting": False
    },
    {
        "name": "Arbutus menziesii",
        "common_name": "Pacific Madrone",
        "code": "AM",
        "state": ["California"],
        "climate": ["Coastal", "Woodland"],
        "usda_min": 7,
        "usda_max": 9,
        "sun": ["Full Sun-Part Shade"],
        "water": ["Low"],
        "spread_ft": 20,
        "height_ft": 40,
        "radius": feet_to_canvas_radius(20),
        "form": "Tree",
        "role": "Canopy",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Bold",
        "color_tone": "Dark Green",
        "visual_weight": 3,
        "seasonality": "Evergreen",
        "image": "plant_images/arbutus-menziesii.webp",
        "elevation_height": 135,
        "hierarchy": "Anchor",
        "weight": 1,
        "allows_underplanting": True
    },
    {
        "name": "Arctostaphylos densiflora 'Howard McMinn'",
        "common_name": "Howard McMinn Manzanita",
        "code": "AHM",
        "state": ["California"],
        "climate": ["Coastal", "Inland"],
        "usda_min": 8,
        "usda_max": 10,
        "sun": ["Full Sun-Part Shade"],
        "water": ["Low"],
        "spread_ft": 8,
        "height_ft": 7,
        "radius": feet_to_canvas_radius(8),
        "form": "Shrub",
        "role": "Structure",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Medium",
        "color_tone": "Grey-Green",
        "visual_weight": 3,
        "seasonality": "Evergreen",
        "image": "plant_images/arctostaphylos-howard-mcminn.webp",
        "elevation_height": 105,
        "hierarchy": "Anchor",
        "weight": 2,
        "allows_underplanting": True
    },
    {
        "name": "Muhlenbergia rigens",
        "common_name": "Deergrass",
        "code": "MR",
        "state": ["California"],
        "climate": ["Inland"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Full Sun"],
        "water": ["Low"],
        "spread_ft": 5,
        "height_ft": 4,
        "radius": feet_to_canvas_radius(5),
        "form": "Grass",
        "role": "Matrix",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Fine",
        "color_tone": "Green",
        "visual_weight": 2,
        "seasonality": "Evergreen",
        "image": "plant_images/muhlenbergia-rigens.webp",
        "elevation_height": 58,
        "hierarchy": "Mid Layer",
        "weight": 4,
        "allows_underplanting": False
    },
    {
        "name": "Stipa pulchra",
        "common_name": "Purple Needlegrass",
        "code": "SP",
        "state": ["California"],
        "climate": ["Inland"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Full Sun"],
        "water": ["Low"],
        "spread_ft": 2,
        "height_ft": 2,
        "radius": feet_to_canvas_radius(2),
        "form": "Grass",
        "role": "Matrix",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Fine",
        "color_tone": "Golden Green",
        "visual_weight": 1,
        "seasonality": "Evergreen",
        "image": "plant_images/stipa-pulchra.webp",
        "elevation_height": 34,
        "hierarchy": "Groundcover",
        "weight": 5,
        "allows_underplanting": False
    },
    {
        "name": "Juncus patens",
        "common_name": "Common Rush",
        "code": "JP",
        "state": ["California"],
        "climate": ["Inland", "Coastal"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Full Sun-Part Shade"],
        "water": ["Low-Moderate"],
        "spread_ft": 3,
        "height_ft": 3,
        "radius": feet_to_canvas_radius(3),
        "form": "Grass",
        "role": "Matrix",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Fine",
        "color_tone": "Blue-Green",
        "visual_weight": 2,
        "seasonality": "Evergreen",
        "image": "plant_images/juncus-patens.webp",
        "elevation_height": 46,
        "hierarchy": "Groundcover",
        "weight": 4,
        "allows_underplanting": False
    },
    {
        "name": "Eriogonum fasciculatum",
        "common_name": "California Buckwheat",
        "code": "EF",
        "state": ["California"],
        "climate": ["Inland", "Dry"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Full Sun"],
        "water": ["Low"],
        "spread_ft": 5,
        "height_ft": 4,
        "radius": feet_to_canvas_radius(5),
        "form": "Shrub",
        "role": "Accent",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Medium",
        "color_tone": "Grey-Green",
        "visual_weight": 2,
        "seasonality": "Evergreen",
        "image": "plant_images/eriogonum-fasciculatum.webp",
        "elevation_height": 58,
        "hierarchy": "Mid Layer",
        "weight": 3,
        "allows_underplanting": False
    },
    {
        "name": "Epilobium canum",
        "common_name": "California Fuchsia",
        "code": "EC",
        "state": ["California"],
        "climate": ["Inland", "Dry"],
        "usda_min": 8,
        "usda_max": 10,
        "sun": ["Full Sun"],
        "water": ["Low"],
        "spread_ft": 3,
        "height_ft": 2,
        "radius": feet_to_canvas_radius(3),
        "form": "Perennial",
        "role": "Accent",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Medium",
        "color_tone": "Green",
        "visual_weight": 2,
        "seasonality": "Semi-evergreen",
        "image": "plant_images/epilobium-canum.webp",
        "elevation_height": 42,
        "hierarchy": "Accent Layer",
        "weight": 3,
        "allows_underplanting": False
    },
    {
        "name": "Artemisia californica",
        "common_name": "California Sagebrush",
        "code": "AC",
        "state": ["California"],
        "climate": ["Inland", "Dry"],
        "usda_min": 8,
        "usda_max": 10,
        "sun": ["Full Sun"],
        "water": ["Low"],
        "spread_ft": 5,
        "height_ft": 4,
        "radius": feet_to_canvas_radius(5),
        "form": "Shrub",
        "role": "Matrix",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Fine",
        "color_tone": "Silver-Grey",
        "visual_weight": 2,
        "seasonality": "Evergreen",
        "image": "plant_images/artemisia-californica.webp",
        "elevation_height": 58,
        "hierarchy": "Mid Layer",
        "weight": 4,
        "allows_underplanting": False
    },
    {
        "name": "Quercus chrysolepis",
        "common_name": "Canyon Live Oak",
        "code": "QC",
        "state": ["California"],
        "climate": ["Inland", "Woodland"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Full Sun-Part Shade"],
        "water": ["Low"],
        "spread_ft": 30,
        "height_ft": 40,
        "radius": feet_to_canvas_radius(30),
        "form": "Tree",
        "role": "Canopy",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Bold",
        "color_tone": "Dark Green",
        "visual_weight": 3,
        "seasonality": "Evergreen",
        "image": "plant_images/quercus-chrysolepis.webp",
        "elevation_height": 135,
        "hierarchy": "Anchor",
        "weight": 1,
        "allows_underplanting": True
    },
    {
        "name": "Carex tumulicola",
        "common_name": "Foothill Sedge",
        "code": "CT",
        "state": ["California"],
        "climate": ["Woodland"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Part Shade-Full Sun"],
        "water": ["Moderate-Low"],
        "spread_ft": 2,
        "height_ft": 2,
        "radius": feet_to_canvas_radius(2),
        "form": "Grass",
        "role": "Matrix",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Fine",
        "color_tone": "Green",
        "visual_weight": 1,
        "seasonality": "Evergreen",
        "image": "plant_images/carex-tumulicola.webp",
        "elevation_height": 34,
        "hierarchy": "Groundcover",
        "weight": 5,
        "allows_underplanting": False
    },
    {
        "name": "Polystichum munitum",
        "common_name": "Western Sword Fern",
        "code": "PM",
        "state": ["California"],
        "climate": ["Woodland"],
        "usda_min": 5,
        "usda_max": 9,
        "sun": ["Part Shade-Full Shade"],
        "water": ["Moderate"],
        "spread_ft": 4,
        "height_ft": 4,
        "radius": feet_to_canvas_radius(4),
        "form": "Fern",
        "role": "Matrix",
        "style": ["Naturalistic"],
        "texture": "Bold",
        "color_tone": "Dark Green",
        "visual_weight": 2,
        "seasonality": "Evergreen",
        "image": "plant_images/polystichum-munitum.webp",
        "elevation_height": 58,
        "hierarchy": "Mid Layer",
        "weight": 4,
        "allows_underplanting": False
    },
    {
        "name": "Heuchera maxima",
        "common_name": "Island Alum Root",
        "code": "HM",
        "state": ["California"],
        "climate": ["Woodland"],
        "usda_min": 8,
        "usda_max": 10,
        "sun": ["Part Shade"],
        "water": ["Moderate-Low"],
        "spread_ft": 3,
        "height_ft": 2,
        "radius": feet_to_canvas_radius(3),
        "form": "Perennial",
        "role": "Accent",
        "style": ["Naturalistic"],
        "texture": "Medium",
        "color_tone": "Green",
        "visual_weight": 2,
        "seasonality": "Evergreen",
        "image": "plant_images/heuchera-maxima.webp",
        "elevation_height": 42,
        "hierarchy": "Accent Layer",
        "weight": 3,
        "allows_underplanting": False
    },
    {
        "name": "Ribes sanguineum",
        "common_name": "Red-Flowering Currant",
        "code": "RS",
        "state": ["California"],
        "climate": ["Woodland"],
        "usda_min": 6,
        "usda_max": 9,
        "sun": ["Full Sun-Part Shade"],
        "water": ["Moderate-Low"],
        "spread_ft": 6,
        "height_ft": 8,
        "radius": feet_to_canvas_radius(6),
        "form": "Shrub",
        "role": "Accent",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Medium",
        "color_tone": "Green",
        "visual_weight": 2,
        "seasonality": "Deciduous",
        "image": "plant_images/ribes-sanguineum.webp",
        "elevation_height": 110,
        "hierarchy": "Mid Layer",
        "weight": 3,
        "allows_underplanting": False
    },
    {
        "name": "Woodwardia fimbriata",
        "common_name": "Giant Chain Fern",
        "code": "WF",
        "state": ["California"],
        "climate": ["Woodland"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Part Shade-Full Shade"],
        "water": ["Moderate"],
        "spread_ft": 6,
        "height_ft": 5,
        "radius": feet_to_canvas_radius(6),
        "form": "Fern",
        "role": "Matrix",
        "style": ["Naturalistic"],
        "texture": "Bold",
        "color_tone": "Dark Green",
        "visual_weight": 3,
        "seasonality": "Evergreen",
        "image": "plant_images/woodwardia-fimbriata.webp",
        "elevation_height": 70,
        "hierarchy": "Mid Layer",
        "weight": 4,
        "allows_underplanting": False
    },
    {
        "name": "Acer circinatum",
        "common_name": "Vine Maple",
        "code": "ACI",
        "state": ["California"],
        "climate": ["Woodland"],
        "usda_min": 6,
        "usda_max": 9,
        "sun": ["Part Shade"],
        "water": ["Moderate"],
        "spread_ft": 15,
        "height_ft": 20,
        "radius": feet_to_canvas_radius(15),
        "form": "Tree",
        "role": "Canopy",
        "style": ["Naturalistic"],
        "texture": "Medium",
        "color_tone": "Green",
        "visual_weight": 3,
        "seasonality": "Deciduous",
        "image": "plant_images/acer-circinatum.webp",
        "elevation_height": 125,
        "hierarchy": "Anchor",
        "weight": 1,
        "allows_underplanting": True
    },
    {
        "name": "Heteromeles arbutifolia",
        "common_name": "Toyon",
        "code": "HA",
        "state": ["California"],
        "climate": ["Woodland", "Inland"],
        "usda_min": 7,
        "usda_max": 10,
        "sun": ["Full Sun-Part Shade"],
        "water": ["Low"],
        "spread_ft": 10,
        "height_ft": 15,
        "radius": feet_to_canvas_radius(10),
        "form": "Shrub",
        "role": "Structure",
        "style": ["Naturalistic", "Contemporary"],
        "texture": "Medium",
        "color_tone": "Dark Green",
        "visual_weight": 3,
        "seasonality": "Evergreen",
        "image": "plant_images/heteromeles-arbutifolia.webp",
        "elevation_height": 118,
        "hierarchy": "Anchor",
        "weight": 2,
        "allows_underplanting": True
    },
]


HIERARCHY_ORDER = ["Anchor", "Mid Layer", "Accent Layer", "Groundcover"]

HIERARCHY_COVERAGE_SPLIT = {
    "Anchor": 0.24,
    "Mid Layer": 0.30,
    "Accent Layer": 0.20,
    "Groundcover": 0.26
}

HEIGHT_VARIATION_BY_HIERARCHY = {
    "Anchor": 0.06,
    "Mid Layer": 0.10,
    "Accent Layer": 0.15,
    "Groundcover": 0.08
}

# -----------------------------
# Helper functions
# -----------------------------

def clamp_dimension(value, fallback):
    try:
        value = float(value)
    except Exception:
        return fallback
    return max(1, min(value, MAX_BED_FEET))


def get_canvas_setup(length_ft, width_ft):
    """Return canvas dimensions and true feet-per-canvas-unit scale.

    length_ft is horizontal. width_ft is vertical/depth.
    The canvas preserves the real bed aspect ratio and fits inside the max pixel bounds.
    """
    length_ft = clamp_dimension(length_ft, DEFAULT_BED_LENGTH_FEET)
    width_ft = clamp_dimension(width_ft, DEFAULT_BED_WIDTH_FEET)

    pixels_per_foot = min(MAX_CANVAS_WIDTH / length_ft, MAX_CANVAS_HEIGHT / width_ft)
    canvas_width = max(250, int(round(length_ft * pixels_per_foot)))
    canvas_height = max(250, int(round(width_ft * pixels_per_foot)))
    feet_per_canvas_unit = 1 / pixels_per_foot
    grid_spacing_units = GRID_SPACING_FEET / feet_per_canvas_unit

    return canvas_width, canvas_height, feet_per_canvas_unit, grid_spacing_units


def make_runtime_plant_pool(plants, feet_per_canvas_unit):
    runtime_plants = []
    for plant in plants:
        p = plant.copy()
        p["radius"] = (p["spread_ft"] / 2) / feet_per_canvas_unit
        runtime_plants.append(p)
    return runtime_plants


def circle_inside(poly, x, y, r):
    return poly.contains(Point(x, y).buffer(r))


def circles_overlap(x, y, r, placed, spacing_factor, plant=None):
    for p in placed:
        existing_plant = p["plant"]

        existing_allows_underplanting = existing_plant.get("allows_underplanting", False)
        current_allows_underplanting = plant is not None and plant.get("allows_underplanting", False)

        if existing_allows_underplanting and not current_allows_underplanting:
            continue

        if current_allows_underplanting and not existing_allows_underplanting:
            continue

        distance = math.dist((x, y), (p["x"], p["y"]))
        min_distance = (r + p["radius"]) * spacing_factor

        if distance < min_distance:
            return True

    return False


def weighted_choice(plants):
    if not plants:
        return None

    weights = [p.get("weight", 1) for p in plants]
    return random.choices(plants, weights=weights, k=1)[0]


def pack_layer(poly, plants, target_area, spacing_factor, existing_placed, max_plants_total):
    if not plants:
        return [], 0

    minx, miny, maxx, maxy = poly.bounds
    placed_layer = []
    placed_area = 0
    attempts = 0
    max_attempts = 16000

    while (
        placed_area < target_area
        and attempts < max_attempts
        and len(existing_placed) + len(placed_layer) < max_plants_total
    ):
        attempts += 1

        plant = weighted_choice(plants)
        if plant is None:
            break

        r = plant["radius"]

        if maxx - minx < r * 2 or maxy - miny < r * 2:
            break

        x = random.uniform(minx + r, maxx - r)
        y = random.uniform(miny + r, maxy - r)

        if not circle_inside(poly, x, y, r):
            continue

        all_existing = existing_placed + placed_layer

        if circles_overlap(x, y, r, all_existing, spacing_factor, plant):
            continue

        placed_layer.append({"x": x, "y": y, "radius": r, "plant": plant})
        placed_area += math.pi * (r ** 2)

    return placed_layer, placed_area


def pack_by_hierarchy(poly, plant_pool, target_coverage, spacing_factor, max_plants_total):
    boundary_area = poly.area

    if boundary_area <= 0:
        return [], 0

    total_target_area = boundary_area * target_coverage
    all_placed = []
    total_placed_area = 0

    for hierarchy in HIERARCHY_ORDER:
        layer_plants = [p for p in plant_pool if p["hierarchy"] == hierarchy]

        if not layer_plants:
            continue

        layer_target_area = total_target_area * HIERARCHY_COVERAGE_SPLIT[hierarchy]

        placed_layer, placed_area = pack_layer(
            poly=poly,
            plants=layer_plants,
            target_area=layer_target_area,
            spacing_factor=spacing_factor,
            existing_placed=all_placed,
            max_plants_total=max_plants_total
        )

        all_placed.extend(placed_layer)
        total_placed_area += placed_area

    return all_placed, total_placed_area / boundary_area


def sun_is_compatible(selected_sun, plant_sun_options):
    sun_compatibility = {
        "Full Sun": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun"],
        "Full Sun-Part Shade": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade", "Part Shade-Full Shade"],
        "Part Shade": ["Part Shade", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade-Full Shade"],
        "Part Shade-Full Shade": ["Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"],
    }

    compatible_values = sun_compatibility.get(selected_sun, [selected_sun])
    return any(sun_value in compatible_values for sun_value in plant_sun_options)


def water_is_compatible(selected_water, plant_water_options):
    water_compatibility = {
        "Low": ["Low", "Moderate-Low", "Low-Moderate"],
        "Moderate-Low": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],
        "Low-Moderate": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],
        "Moderate": ["Moderate", "Low-Moderate", "Moderate-Low"],
    }

    compatible_values = water_compatibility.get(selected_water, [selected_water])
    return any(water_value in compatible_values for water_value in plant_water_options)


def filter_plants(plant_database, state, climate, sun, water, style):
    return [
        plant for plant in plant_database
        if state in plant["state"]
        and climate in plant["climate"]
        and style in plant["style"]
        and sun_is_compatible(sun, plant["sun"])
        and water_is_compatible(water, plant["water"])
    ]


def get_polygon_from_canvas(canvas_json):
    if canvas_json is None:
        return None

    objects = canvas_json.get("objects", [])
    if len(objects) == 0:
        return None

    obj = objects[0]
    if "path" not in obj:
        return None

    points = []
    for p in obj["path"]:
        if len(p) >= 3:
            points.append((p[1], p[2]))

    if len(points) < 3:
        return None

    return points


def rectangle_points(canvas_width, canvas_height):
    return [(0, 0), (canvas_width, 0), (canvas_width, canvas_height), (0, canvas_height)]


def fig_to_png_bytes(fig):
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=200, bbox_inches="tight", transparent=False)
    buffer.seek(0)
    return buffer


def fig_to_jpeg_bytes(fig):
    buffer = BytesIO()
    fig.savefig(buffer, format="jpg", dpi=200, bbox_inches="tight", facecolor="white", transparent=False)
    buffer.seek(0)
    return buffer


def fig_to_svg_bytes(fig):
    buffer = BytesIO()
    fig.savefig(buffer, format="svg", bbox_inches="tight")
    buffer.seek(0)
    return buffer


def canvas_area_to_sqft(area_canvas_units, feet_per_canvas_unit):
    return area_canvas_units * (feet_per_canvas_unit ** 2)


def canvas_length_to_feet(length_canvas_units, feet_per_canvas_unit):
    return length_canvas_units * feet_per_canvas_unit


def draw_grid(ax, canvas_width, canvas_height, grid_spacing_units):
    x = 0
    while x <= canvas_width:
        ax.axvline(x, linewidth=0.4, alpha=0.25)
        x += grid_spacing_units

    y = 0
    while y <= canvas_height:
        ax.axhline(y, linewidth=0.4, alpha=0.25)
        y += grid_spacing_units


def get_image_aspect_ratio(image_path):
    try:
        img = plt.imread(image_path)
        height_px, width_px = img.shape[:2]
        if height_px == 0:
            return 1
        return width_px / height_px
    except Exception:
        return 1


def varied_height(plant):
    tolerance = HEIGHT_VARIATION_BY_HIERARCHY.get(plant["hierarchy"], 0.08)
    variation = random.uniform(1 - tolerance, 1 + tolerance)
    return plant["elevation_height"] * variation


def prepare_uploaded_image(uploaded_file, canvas_width, canvas_height):
    if uploaded_file is None:
        return None, None

    image = Image.open(uploaded_file).convert("RGB")
    image = image.resize((canvas_width, canvas_height))
    image_array = plt.imread(BytesIO(image_to_png_bytes(image).getvalue()))
    return image, image_array


def render_trace_overlay(image, points, canvas_width, canvas_height):
    """Return a PIL image with the uploaded background plus the clicked/traced bedline points.

    This avoids relying on streamlit-drawable-canvas background_image, which can render
    blank on Streamlit Cloud. Users click around the bedline directly on the image.
    """
    if image is None:
        return None

    overlay = image.copy().convert("RGB")
    overlay = overlay.resize((canvas_width, canvas_height))
    draw = ImageDraw.Draw(overlay)

    if len(points) >= 2:
        draw.line(points, fill=(255, 255, 255), width=3)

    if len(points) >= 3:
        # Light preview of the closing segment so users understand the final polygon.
        draw.line([points[-1], points[0]], fill=(255, 255, 255), width=2)

    for idx, (x, y) in enumerate(points):
        r = 5
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 80, 80), outline=(255, 255, 255), width=2)
        draw.text((x + 7, y - 7), str(idx + 1), fill=(255, 255, 255))

    return overlay


def image_to_png_bytes(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def escape_svg_text(value):
    return html.escape(str(value), quote=True)


def plan_to_svg(points, placed_instances, canvas_width, canvas_height, feet_per_canvas_unit):
    """Create a clean vector SVG of the plan geometry.

    This avoids relying on Matplotlib's SVG output and gives you true circle/vector objects.
    """
    path_points = " ".join([f"{x:.2f},{y:.2f}" for x, y in points])
    svg = StringIO()
    svg.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}">\n')
    svg.write('<rect width="100%" height="100%" fill="white"/>\n')
    svg.write(f'<polygon points="{path_points}" fill="none" stroke="black" stroke-width="2"/>\n')

    for item in placed_instances:
        plant = item["plant"]
        dash = ' stroke-dasharray="6 4"' if plant.get("allows_underplanting", False) else ""
        weight = "bold" if plant.get("allows_underplanting", False) else "normal"
        svg.write(f'<circle cx="{item["x"]:.2f}" cy="{item["y"]:.2f}" r="{item["radius"]:.2f}" fill="none" stroke="black" stroke-width="1.2"{dash}/>\n')
        svg.write(f'<text x="{item["x"]:.2f}" y="{item["y"]:.2f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="8" font-weight="{weight}">{escape_svg_text(plant["code"])}</text>\n')

    svg.write(f'<text x="12" y="{canvas_height - 14}" font-family="Arial" font-size="10">Scale: 1 px = {feet_per_canvas_unit:.3f} ft</text>\n')
    svg.write('</svg>')
    return BytesIO(svg.getvalue().encode("utf-8"))


def plan_to_dxf(points, placed_instances, feet_per_canvas_unit):
    """Export a simple ASCII DXF in real feet.

    AutoCAD, Rhino, Vectorworks, and many CAD tools can open DXF. This is the practical
    Streamlit-friendly alternative to DWG.
    """
    dxf = StringIO()
    dxf.write("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n2\n0\nENDSEC\n")
    dxf.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n")
    dxf.write("0\nSECTION\n2\nENTITIES\n")

    closed_points = points + [points[0]]
    for i in range(len(closed_points) - 1):
        x1, y1 = closed_points[i]
        x2, y2 = closed_points[i + 1]
        dxf.write("0\nLINE\n8\nBOUNDARY\n")
        dxf.write(f"10\n{x1 * feet_per_canvas_unit:.4f}\n20\n{y1 * feet_per_canvas_unit:.4f}\n30\n0\n")
        dxf.write(f"11\n{x2 * feet_per_canvas_unit:.4f}\n21\n{y2 * feet_per_canvas_unit:.4f}\n31\n0\n")

    for item in placed_instances:
        plant = item["plant"]
        dxf.write("0\nCIRCLE\n8\nPLANTS\n")
        dxf.write(f"10\n{item['x'] * feet_per_canvas_unit:.4f}\n20\n{item['y'] * feet_per_canvas_unit:.4f}\n30\n0\n")
        dxf.write(f"40\n{item['radius'] * feet_per_canvas_unit:.4f}\n")
        dxf.write("0\nTEXT\n8\nPLANT_CODES\n")
        dxf.write(f"10\n{item['x'] * feet_per_canvas_unit:.4f}\n20\n{item['y'] * feet_per_canvas_unit:.4f}\n30\n0\n")
        dxf.write("40\n0.35\n")
        dxf.write(f"1\n{plant['code']}\n")

    dxf.write("0\nENDSEC\n0\nEOF\n")
    return BytesIO(dxf.getvalue().encode("utf-8"))

# -----------------------------
# Sidebar
# -----------------------------

with st.sidebar:
    st.markdown("### by The Landscape Library")

    st.header("Input Method")
    input_method = st.radio(
        "Choose how to define the planting bed",
        ["Draw Boundary", "Upload JPEG Image"],
        index=0
    )

    st.info("Max 50' bed")

    if input_method == "Upload JPEG Image":
        st.caption("Upload a JPEG image as a scaled reference, then click points around the actual bedline.")
        uploaded_bed_image = st.file_uploader(
            "Upload bed image",
            type=["jpg", "jpeg"]
        )

        bed_length_ft = st.number_input(
            "Image length / horizontal dimension (ft)",
            min_value=1.0,
            max_value=float(MAX_BED_FEET),
            value=30.0,
            step=1.0
        )

        bed_width_ft = st.number_input(
            "Image width / vertical dimension (ft)",
            min_value=1.0,
            max_value=float(MAX_BED_FEET),
            value=15.0,
            step=1.0
        )
    else:
        uploaded_bed_image = None
        bed_length_ft = DEFAULT_BED_LENGTH_FEET
        bed_width_ft = DEFAULT_BED_WIDTH_FEET

    canvas_width, canvas_height, feet_per_canvas_unit, grid_spacing_units = get_canvas_setup(
        bed_length_ft,
        bed_width_ft
    )

    st.header("Site Parameters")

    state = st.selectbox("State", ["California"])
    climate = st.selectbox("Climate", ["Coastal", "Inland", "Dry", "Woodland"])

    sun = st.selectbox(
        "Sun Exposure",
        ["Full Sun", "Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"]
    )

    water = st.selectbox(
        "Water Needs",
        ["Low", "Moderate-Low", "Low-Moderate", "Moderate"]
    )

    st.header("Design Style")

    style = st.selectbox(
        "Style",
        ["Naturalistic", "Contemporary", "Formal"]
    )

    st.header("Density")

    density = st.selectbox(
        "Coverage Density",
        ["Low", "Moderate", "Dense", "Very Dense"]
    )

    target_coverage = DENSITY_OPTIONS[density]
    spacing_factor = SPACING_BY_DENSITY[density]
    max_plants_total = MAX_PLANTS_BY_DENSITY[density]

    st.header("Scale")
    st.caption(f"Bed limit: {MAX_BED_FEET} ft max length or width")
    st.caption(f"Active bed: {bed_length_ft:.0f} ft x {bed_width_ft:.0f} ft")
    st.caption(f"Grid: 1 square = {GRID_SPACING_FEET} ft")

# -----------------------------
# Active plant database + image prep
# -----------------------------

runtime_plants = make_runtime_plant_pool(PLANTS, feet_per_canvas_unit)
selected_plants = filter_plants(runtime_plants, state, climate, sun, water, style)
background_image = None
background_array = None

if input_method == "Upload JPEG Image" and uploaded_bed_image is not None:
    background_image, background_array = prepare_uploaded_image(uploaded_bed_image, canvas_width, canvas_height)

# -----------------------------
# Main UI
# -----------------------------

left, right = st.columns([2, 1])

with left:
    if input_method == "Draw Boundary":
        st.subheader("1. Draw Planting Boundary")
        st.caption(f"Draw within the {MAX_BED_FEET} ft max bed area. Each grid square represents {GRID_SPACING_FEET} ft.")

        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 0, 0)",
            stroke_width=3,
            stroke_color="#111111",
            background_color="#f7f7f2",
            height=canvas_height,
            width=canvas_width,
            drawing_mode="polygon",
            key="draw_boundary_canvas",
        )
    else:
        st.subheader("1. Upload Scaled Bed Image + Trace Bedline")
        st.caption("Upload the JPEG as a scaled reference, then click points around the actual planting bed boundary inside the image. Plants will only generate inside the traced polygon, not across the full image rectangle.")

        if uploaded_bed_image is None:
            st.warning("Upload a JPEG image first, then click points around the actual bedline.")
            canvas_result = None
        else:
            canvas_result = None

            if streamlit_image_coordinates is None:
                st.error("Missing package: streamlit-image-coordinates. Add streamlit-image-coordinates to requirements.txt, then redeploy.")
            else:
                trace_key = f"trace_points_{uploaded_bed_image.name}_{canvas_width}_{canvas_height}"
                last_click_key = f"last_click_{uploaded_bed_image.name}_{canvas_width}_{canvas_height}"

                if trace_key not in st.session_state:
                    st.session_state[trace_key] = []
                if last_click_key not in st.session_state:
                    st.session_state[last_click_key] = None

                st.caption("Click points around the bedline in order. Use more points for curves. The final segment closes automatically between the last and first point.")

                overlay_image = render_trace_overlay(
                    background_image,
                    st.session_state[trace_key],
                    canvas_width,
                    canvas_height
                )

                clicked = streamlit_image_coordinates(
                    overlay_image,
                    key=f"click_trace_{uploaded_bed_image.name}_{canvas_width}_{canvas_height}",
                    width=canvas_width
                )

                if clicked is not None and "x" in clicked and "y" in clicked:
                    new_point = (int(clicked["x"]), int(clicked["y"]))

                    if st.session_state[last_click_key] != new_point:
                        existing_points = st.session_state[trace_key]

                        # Prevent accidental double-click duplicates.
                        if len(existing_points) == 0 or math.dist(existing_points[-1], new_point) > 4:
                            existing_points.append(new_point)
                            st.session_state[trace_key] = existing_points

                        st.session_state[last_click_key] = new_point
                        st.rerun()

                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("Undo Last Point") and len(st.session_state[trace_key]) > 0:
                        st.session_state[trace_key] = st.session_state[trace_key][:-1]
                        st.session_state[last_click_key] = None
                        st.rerun()
                with b2:
                    if st.button("Clear Trace"):
                        st.session_state[trace_key] = []
                        st.session_state[last_click_key] = None
                        st.rerun()
                with b3:
                    st.metric("Trace Points", len(st.session_state[trace_key]))

                if len(st.session_state[trace_key]) < 3:
                    st.info("Add at least 3 points before generating the planting layout.")

with right:
    st.subheader("2. Selected Plant Palette")

    if len(selected_plants) == 0:
        st.warning("No plants match these parameters yet. Try adjusting sun exposure, water needs, or style.")
    else:
        for plant in selected_plants:
            canopy_note = " | allows underplanting" if plant.get("allows_underplanting", False) else ""
            st.write(f"**{plant['name']}**")
            st.caption(
                f"{plant['code']} | {plant['common_name']} | {plant['form']} | {plant['role']} | spread: {plant['spread_ft']} ft{canopy_note}"
            )

# -----------------------------
# Boundary metrics
# -----------------------------

points_preview = None

if input_method == "Draw Boundary" and canvas_result is not None:
    points_preview = get_polygon_from_canvas(canvas_result.json_data)
elif input_method == "Upload JPEG Image" and uploaded_bed_image is not None:
    trace_key = f"trace_points_{uploaded_bed_image.name}_{canvas_width}_{canvas_height}"
    points_preview = st.session_state.get(trace_key, [])
    if len(points_preview) < 3:
        points_preview = None

if points_preview is not None:
    preview_poly = Polygon(points_preview)

    if not preview_poly.is_valid:
        preview_poly = preview_poly.buffer(0)

    if preview_poly.area > 0:
        area_sqft = canvas_area_to_sqft(preview_poly.area, feet_per_canvas_unit)
        perimeter_ft = canvas_length_to_feet(preview_poly.length, feet_per_canvas_unit)
        minx_preview, miny_preview, maxx_preview, maxy_preview = preview_poly.bounds

        width_ft = canvas_length_to_feet(maxx_preview - minx_preview, feet_per_canvas_unit)
        depth_ft = canvas_length_to_feet(maxy_preview - miny_preview, feet_per_canvas_unit)

        st.subheader("Boundary Metrics")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Approx. Area", f"{area_sqft:,.0f} sq ft")
        c2.metric("Approx. Perimeter", f"{perimeter_ft:,.0f} ft")
        c3.metric("Approx. Length", f"{width_ft:,.0f} ft")
        c4.metric("Approx. Width", f"{depth_ft:,.0f} ft")

generate = st.button("Generate Planting Layout", type="primary")

# -----------------------------
# Generate
# -----------------------------

if generate:
    try:
        with st.spinner("Generating planting plan and elevation view..."):
            if input_method == "Draw Boundary" and canvas_result is not None:
                points = get_polygon_from_canvas(canvas_result.json_data)
            elif input_method == "Upload JPEG Image" and uploaded_bed_image is not None:
                trace_key = f"trace_points_{uploaded_bed_image.name}_{canvas_width}_{canvas_height}"
                points = st.session_state.get(trace_key, [])
                if len(points) < 3:
                    points = None
            else:
                points = None

            if points is None:
                if input_method == "Draw Boundary":
                    st.warning("Draw a closed polygon boundary first.")
                else:
                    st.warning("Upload a JPEG image and trace a closed polygon boundary first.")

            elif bed_length_ft > MAX_BED_FEET or bed_width_ft > MAX_BED_FEET:
                st.warning(f"The bed is too large. Keep the image dimensions at or below {MAX_BED_FEET} ft.")

            elif len(selected_plants) == 0:
                st.warning("No plants are available for the selected site parameters.")

            else:
                poly = Polygon(points)

                if not poly.is_valid:
                    poly = poly.buffer(0)

                if poly.area <= 0:
                    st.warning("The boundary is invalid. Try tracing a clearer closed shape.")

                else:
                    placed_instances, actual_coverage = pack_by_hierarchy(
                        poly=poly,
                        plant_pool=selected_plants,
                        target_coverage=target_coverage,
                        spacing_factor=spacing_factor,
                        max_plants_total=max_plants_total
                    )

                    if len(placed_instances) == 0:
                        st.warning("No plants could fit inside the boundary. Try a larger area, lower density, or different plant parameters.")

                    else:
                        st.subheader("Plan View")

                        fig, ax = plt.subplots(figsize=(10, 10))

                        if background_array is not None:
                            ax.imshow(background_array, extent=(0, canvas_width, canvas_height, 0), alpha=0.35, zorder=0)

                        xs, ys = zip(*(points + [points[0]]))
                        ax.plot(xs, ys, linewidth=2, zorder=3)

                        draw_grid(ax, canvas_width, canvas_height, grid_spacing_units)

                        for item in placed_instances:
                            plant = item["plant"]

                            if plant.get("allows_underplanting", False):
                                continue

                            circle = plt.Circle(
                                (item["x"], item["y"]),
                                item["radius"],
                                fill=False,
                                linewidth=1.2,
                                zorder=4
                            )
                            ax.add_patch(circle)

                            ax.text(
                                item["x"],
                                item["y"],
                                plant["code"],
                                ha="center",
                                va="center",
                                fontsize=8,
                                zorder=5
                            )

                        for item in placed_instances:
                            plant = item["plant"]

                            if not plant.get("allows_underplanting", False):
                                continue

                            circle = plt.Circle(
                                (item["x"], item["y"]),
                                item["radius"],
                                fill=False,
                                linewidth=1.5,
                                linestyle="--",
                                alpha=0.75,
                                zorder=4
                            )
                            ax.add_patch(circle)

                            ax.text(
                                item["x"],
                                item["y"],
                                plant["code"],
                                ha="center",
                                va="center",
                                fontsize=8,
                                fontweight="bold",
                                zorder=5
                            )

                        ax.set_xlim(0, canvas_width)
                        ax.set_ylim(canvas_height, 0)
                        ax.set_aspect("equal")
                        ax.axis("off")

                        st.pyplot(fig)

                        plan_png = fig_to_png_bytes(fig)
                        plan_svg = plan_to_svg(points, placed_instances, canvas_width, canvas_height, feet_per_canvas_unit)
                        plan_dxf = plan_to_dxf(points, placed_instances, feet_per_canvas_unit)

                        d1, d2, d3 = st.columns(3)
                        with d1:
                            st.download_button(
                                label="Download Plan PNG",
                                data=plan_png,
                                file_name="yodra-planting-plan.png",
                                mime="image/png"
                            )
                        with d2:
                            st.download_button(
                                label="Download Plan SVG",
                                data=plan_svg,
                                file_name="yodra-planting-plan.svg",
                                mime="image/svg+xml"
                            )
                        with d3:
                            st.download_button(
                                label="Download Plan DXF",
                                data=plan_dxf,
                                file_name="yodra-planting-plan.dxf",
                                mime="application/dxf"
                            )

                        st.caption(f"Target coverage: {round(target_coverage * 100)}%")
                        st.caption(f"Actual generated coverage: {round(actual_coverage * 100)}%")
                        st.caption(f"Active bed scale: {bed_length_ft:.0f} ft x {bed_width_ft:.0f} ft")
                        st.caption(f"Maximum plant instances capped at {max_plants_total} for app performance.")

                        st.subheader("Elevation View")
                        st.caption("Elevation uses the same plant instances generated in plan view, with subtle height variation.")

                        elev_fig, elev_ax = plt.subplots(figsize=(12, 4))

                        placed_sorted = sorted(placed_instances, key=lambda item: item["x"])

                        for item in placed_sorted:
                            plant = item["plant"]
                            image_path = plant["image"]

                            height = varied_height(plant)
                            aspect_ratio = get_image_aspect_ratio(image_path)
                            width = height * aspect_ratio

                            if os.path.exists(image_path):
                                img = plt.imread(image_path)

                                elev_ax.imshow(
                                    img,
                                    extent=(
                                        item["x"] - width / 2,
                                        item["x"] + width / 2,
                                        0,
                                        height
                                    ),
                                    zorder=2
                                )
                            else:
                                elev_ax.text(
                                    item["x"],
                                    height / 2,
                                    plant["code"],
                                    ha="center",
                                    va="center",
                                    fontsize=8
                                )

                        elev_ax.axhline(0, linewidth=1)
                        elev_ax.set_xlim(0, canvas_width)
                        elev_ax.set_ylim(0, 140)
                        elev_ax.axis("off")

                        st.pyplot(elev_fig)

                        elevation_png = fig_to_png_bytes(elev_fig)
                        elevation_jpeg = fig_to_jpeg_bytes(elev_fig)

                        e1, e2 = st.columns(2)
                        with e1:
                            st.download_button(
                                label="Download Elevation PNG",
                                data=elevation_png,
                                file_name="yodra-planting-elevation.png",
                                mime="image/png"
                            )
                        with e2:
                            st.download_button(
                                label="Download Elevation JPEG",
                                data=elevation_jpeg,
                                file_name="yodra-planting-elevation.jpg",
                                mime="image/jpeg"
                            )

                        st.subheader("Plant Count")

                        counts = {}
                        for item in placed_instances:
                            plant = item["plant"]
                            counts[plant["name"]] = counts.get(plant["name"], 0) + 1

                        st.write(counts)

                        st.subheader("Plant Schedule")

                        schedule = []
                        for plant_name, count in counts.items():
                            plant = next(p for p in runtime_plants if p["name"] == plant_name)

                            schedule.append({
                                "Code": plant["code"],
                                "Botanical Name": plant["name"],
                                "Common Name": plant["common_name"],
                                "Form": plant["form"],
                                "Role": plant["role"],
                                "Style": ", ".join(plant["style"]),
                                "Texture": plant["texture"],
                                "Color Tone": plant["color_tone"],
                                "Visual Weight": plant["visual_weight"],
                                "Spread Ft": plant["spread_ft"],
                                "Height Ft": plant["height_ft"],
                                "Count": count,
                                "State": state,
                                "Climate": ", ".join(plant["climate"]),
                                "Sun": ", ".join(plant["sun"]),
                                "Water": ", ".join(plant["water"]),
                                "Seasonality": plant["seasonality"],
                                "Allows Underplanting": plant.get("allows_underplanting", False)
                            })

                        st.dataframe(schedule, width="stretch")

    except Exception as e:
        st.error("The app crashed while generating the layout.")
        st.exception(e)
