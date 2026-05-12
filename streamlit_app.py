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
# IMPORTS
# -------------------------

import random
import math
import os
from io import BytesIO

import matplotlib.pyplot as plt
from shapely.geometry import Polygon, Point
from streamlit_drawable_canvas import st_canvas

# -------------------------
# PAGE SETTINGS
# -------------------------

st.set_page_config(
    page_title="AI-Powered Planting Design Engine",
    layout="wide"
)

st.title("AI-Powered Planting Design Engine")

st.caption(
    "Draw a planting boundary, generate a hierarchy-based plan, preview the matching elevation, and download the result."
)

# -----------------------------
# CANVAS + SCALE SETTINGS
# -----------------------------

CANVAS_WIDTH = 900
CANVAS_HEIGHT = 600
MAX_SITE_FEET = 50

FEET_PER_CANVAS_UNIT = MAX_SITE_FEET / CANVAS_WIDTH

GRID_SPACING_FEET = 5
GRID_SPACING_UNITS = GRID_SPACING_FEET / FEET_PER_CANVAS_UNIT

# -----------------------------
# DENSITY SETTINGS
# -----------------------------

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
# PLANT DATABASE
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
        "style": ["Naturalistic"],
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
        "climate": ["Coastal"],
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
        "climate": ["Coastal"],
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
]

# -----------------------------
# HIERARCHY SETTINGS
# -----------------------------

HIERARCHY_ORDER = [
    "Anchor",
    "Mid Layer",
    "Accent Layer",
    "Groundcover"
]

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
# HELPER FUNCTIONS
# -----------------------------

def circle_inside(poly, x, y, r):
    return poly.contains(Point(x, y).buffer(r))


def circles_overlap(x, y, r, placed, spacing_factor, plant=None):

    for p in placed:

        existing_plant = p["plant"]

        existing_allows_underplanting = existing_plant.get(
            "allows_underplanting",
            False
        )

        current_allows_underplanting = (
            plant is not None
            and plant.get("allows_underplanting", False)
        )

        if existing_allows_underplanting and not current_allows_underplanting:
            continue

        if current_allows_underplanting and not existing_allows_underplanting:
            continue

        distance = math.dist(
            (x, y),
            (p["x"], p["y"])
        )

        min_distance = (
            r + p["radius"]
        ) * spacing_factor

        if distance < min_distance:
            return True

    return False


def weighted_choice(plants):

    if not plants:
        return None

    weights = [
        p.get("weight", 1)
        for p in plants
    ]

    return random.choices(
        plants,
        weights=weights,
        k=1
    )[0]


def pack_layer(
    poly,
    plants,
    target_area,
    spacing_factor,
    existing_placed,
    max_plants_total
):

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

        if circles_overlap(
            x,
            y,
            r,
            all_existing,
            spacing_factor,
            plant
        ):
            continue

        placed_layer.append({
            "x": x,
            "y": y,
            "radius": r,
            "plant": plant
        })

        placed_area += math.pi * (r ** 2)

    return placed_layer, placed_area


def pack_by_hierarchy(
    poly,
    plant_pool,
    target_coverage,
    spacing_factor,
    max_plants_total
):

    boundary_area = poly.area

    if boundary_area <= 0:
        return [], 0

    total_target_area = boundary_area * target_coverage

    all_placed = []
    total_placed_area = 0

    for hierarchy in HIERARCHY_ORDER:

        layer_plants = [
            p for p in plant_pool
            if p["hierarchy"] == hierarchy
        ]

        if not layer_plants:
            continue

        layer_target_area = (
            total_target_area
            * HIERARCHY_COVERAGE_SPLIT[hierarchy]
        )

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

    return (
        all_placed,
        total_placed_area / boundary_area
    )

# -----------------------------
# COMPATIBILITY FILTERING
# -----------------------------

def sun_is_compatible(selected_sun, plant_sun_options):

    sun_compatibility = {

        "Full Sun": [
            "Full Sun",
            "Full Sun-Part Shade"
        ],

        "Full Sun-Part Shade": [
            "Full Sun",
            "Full Sun-Part Shade",
            "Part Shade-Full Shade"
        ],

        "Part Shade-Full Shade": [
            "Full Sun-Part Shade",
            "Part Shade-Full Shade"
        ],
    }

    compatible_values = sun_compatibility.get(
        selected_sun,
        [selected_sun]
    )

    return any(
        sun_value in compatible_values
        for sun_value in plant_sun_options
    )


def water_is_compatible(selected_water, plant_water_options):

    water_compatibility = {

        "Low": [
            "Low",
            "Moderate-Low",
            "Low-Moderate"
        ],

        "Moderate-Low": [
            "Low",
            "Moderate-Low",
            "Low-Moderate",
            "Moderate"
        ],

        "Low-Moderate": [
            "Low",
            "Moderate-Low",
            "Low-Moderate",
            "Moderate"
        ],

        "Moderate": [
            "Moderate",
            "Low-Moderate",
            "Moderate-Low"
        ],
    }

    compatible_values = water_compatibility.get(
        selected_water,
        [selected_water]
    )

    return any(
        water_value in compatible_values
        for water_value in plant_water_options
    )


def filter_plants(
    state,
    climate,
    sun,
    water,
    style
):

    return [

        plant for plant in PLANTS

        if state in plant["state"]

        and climate in plant["climate"]

        and style in plant["style"]

        and sun_is_compatible(
            sun,
            plant["sun"]
        )

        and water_is_compatible(
            water,
            plant["water"]
        )
    ]
