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

    password = st.text_input(
        "Enter access password",
        type="password"
    )

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
from io import BytesIO

import matplotlib.pyplot as plt
from shapely.geometry import Polygon, Point
from streamlit_drawable_canvas import st_canvas

st.set_page_config(
    page_title="AI-Powered Planting Design Engine",
    layout="wide"
)

st.title("AI-Powered Planting Design Engine")
st.caption("Draw a planting boundary, generate a hierarchy-based plan, preview the matching elevation, and download the result.")

# -----------------------------
# Canvas + Scale settings
# -----------------------------

CANVAS_WIDTH = 900
CANVAS_HEIGHT = 600
MAX_SITE_FEET = 50

FEET_PER_CANVAS_UNIT = MAX_SITE_FEET / CANVAS_WIDTH

GRID_SPACING_FEET = 5
GRID_SPACING_UNITS = GRID_SPACING_FEET / FEET_PER_CANVAS_UNIT

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

def feet_to_canvas_radius(width_ft):
    return (width_ft / 2) / FEET_PER_CANVAS_UNIT

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

        placed_layer.append({
            "x": x,
            "y": y,
            "radius": r,
            "plant": plant
        })

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

def filter_plants(state, climate, sun, water, style):
    return [
        plant for plant in PLANTS
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

def fig_to_png_bytes(fig):
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=200, bbox_inches="tight", transparent=False)
    buffer.seek(0)
    return buffer

def canvas_area_to_sqft(area_canvas_units):
    return area_canvas_units * (FEET_PER_CANVAS_UNIT ** 2)

def canvas_length_to_feet(length_canvas_units):
    return length_canvas_units * FEET_PER_CANVAS_UNIT

def draw_grid(ax):
    x = 0
    while x <= CANVAS_WIDTH:
        ax.axvline(x, linewidth=0.4, alpha=0.25)
        x += GRID_SPACING_UNITS

    y = 0
    while y <= CANVAS_HEIGHT:
        ax.axhline(y, linewidth=0.4, alpha=0.25)
        y += GRID_SPACING_UNITS

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

# -----------------------------
# Sidebar
# -----------------------------

with st.sidebar:
    st.markdown("### by The Landscape Library")

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
    st.caption(f"Drawing area: {MAX_SITE_FEET} ft x {MAX_SITE_FEET} ft max")
    st.caption(f"Grid: 1 square = {GRID_SPACING_FEET} ft")

# -----------------------------
# Main UI
# -----------------------------

left, right = st.columns([2, 1])

with left:
    st.subheader("1. Draw Planting Boundary")
    st.caption(f"Draw within the {MAX_SITE_FEET} ft x {MAX_SITE_FEET} ft area. Each grid square represents {GRID_SPACING_FEET} ft.")

    canvas_result = st_canvas(
        fill_color="rgba(0, 0, 0, 0)",
        stroke_width=3,
        stroke_color="#111111",
        background_color="#f7f7f2",
        height=CANVAS_HEIGHT,
        width=CANVAS_WIDTH,
        drawing_mode="polygon",
        key="canvas",
    )

with right:
    st.subheader("2. Selected Plant Palette")

    selected_plants = filter_plants(state, climate, sun, water, style)

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

points_preview = get_polygon_from_canvas(canvas_result.json_data)

if points_preview is not None:
    preview_poly = Polygon(points_preview)

    if not preview_poly.is_valid:
        preview_poly = preview_poly.buffer(0)

    if preview_poly.area > 0:
        area_sqft = canvas_area_to_sqft(preview_poly.area)
        perimeter_ft = canvas_length_to_feet(preview_poly.length)
        minx_preview, miny_preview, maxx_preview, maxy_preview = preview_poly.bounds

        width_ft = canvas_length_to_feet(maxx_preview - minx_preview)
        depth_ft = canvas_length_to_feet(maxy_preview - miny_preview)

        st.subheader("Boundary Metrics")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Approx. Area", f"{area_sqft:,.0f} sq ft")
        c2.metric("Approx. Perimeter", f"{perimeter_ft:,.0f} ft")
        c3.metric("Approx. Width", f"{width_ft:,.0f} ft")
        c4.metric("Approx. Depth", f"{depth_ft:,.0f} ft")

generate = st.button("Generate Planting Layout", type="primary")

# -----------------------------
# Generate
# -----------------------------

if generate:
    try:
        with st.spinner("Generating planting plan and elevation view..."):
            points = get_polygon_from_canvas(canvas_result.json_data)

            if points is None:
                st.warning("Draw a closed polygon boundary first.")

            elif len(selected_plants) == 0:
                st.warning("No plants are available for the selected site parameters.")

            else:
                poly = Polygon(points)

                if not poly.is_valid:
                    poly = poly.buffer(0)

                if poly.area <= 0:
                    st.warning("The drawn boundary is invalid. Try drawing a clearer shape.")

                else:
                    placed_instances, actual_coverage = pack_by_hierarchy(
                        poly=poly,
                        plant_pool=selected_plants,
                        target_coverage=target_coverage,
                        spacing_factor=spacing_factor,
                        max_plants_total=max_plants_total
                    )

                    if len(placed_instances) == 0:
                        st.warning("No plants could fit inside the drawn boundary. Try drawing a larger area, lowering the density, or adjusting the plant parameters.")

                    else:
                        st.subheader("Plan View")

                        fig, ax = plt.subplots(figsize=(10, 10))

                        xs, ys = zip(*(points + [points[0]]))
                        ax.plot(xs, ys, linewidth=2)

                        draw_grid(ax)

                        for item in placed_instances:
                            plant = item["plant"]

                            if plant.get("allows_underplanting", False):
                                continue

                            circle = plt.Circle(
                                (item["x"], item["y"]),
                                item["radius"],
                                fill=False,
                                linewidth=1.2
                            )
                            ax.add_patch(circle)

                            ax.text(
                                item["x"],
                                item["y"],
                                plant["code"],
                                ha="center",
                                va="center",
                                fontsize=8
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
                                alpha=0.75
                            )
                            ax.add_patch(circle)

                            ax.text(
                                item["x"],
                                item["y"],
                                plant["code"],
                                ha="center",
                                va="center",
                                fontsize=8,
                                fontweight="bold"
                            )

                        ax.set_xlim(0, CANVAS_WIDTH)
                        ax.set_ylim(CANVAS_HEIGHT, 0)
                        ax.set_aspect("equal")
                        ax.axis("off")

                        st.pyplot(fig)

                        plan_png = fig_to_png_bytes(fig)

                        st.download_button(
                            label="Download Plan PNG",
                            data=plan_png,
                            file_name="yodra-planting-plan.png",
                            mime="image/png"
                        )

                        st.caption(f"Target coverage: {round(target_coverage * 100)}%")
                        st.caption(f"Actual generated coverage: {round(actual_coverage * 100)}%")
                        st.caption(f"Scale: full canvas = {MAX_SITE_FEET} ft x {MAX_SITE_FEET} ft")
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
                        elev_ax.set_xlim(0, CANVAS_WIDTH)
                        elev_ax.set_ylim(0, 140)
                        elev_ax.axis("off")

                        st.pyplot(elev_fig)

                        elevation_png = fig_to_png_bytes(elev_fig)

                        st.download_button(
                            label="Download Elevation PNG",
                            data=elevation_png,
                            file_name="yodra-planting-elevation.png",
                            mime="image/png"
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
                            plant = next(p for p in PLANTS if p["name"] == plant_name)

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


