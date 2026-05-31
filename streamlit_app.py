
import streamlit as st
from datetime import datetime, timezone
try:
    from supabase import create_client
except Exception:
    create_client = None
import pandas as pd

# -------------------------
# SUPABASE USER TRACKING
# -------------------------

FREE_GENERATION_LIMIT = 999

def get_supabase_client():
    if create_client is None:
        return None
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)

supabase = get_supabase_client()

def log_event(email, event_type, **kwargs):
    """Insert an event using only the columns that exist in the current Supabase events table.

    Current expected columns:
    email, event_type, created_at, climate, sun_exposure, water_needs,
    design_style, export_type, notes.

    Do not add state, zone, density, or plants_generated_count unless those columns
    are also added to Supabase. Supabase will reject inserts when unknown columns
    are included.
    """
    if supabase is None or not email:
        return False, "Supabase is not connected or user email is missing."

    event = {
        "email": email,
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "climate": kwargs.get("climate"),
        "sun_exposure": kwargs.get("sun_exposure"),
        "water_needs": kwargs.get("water_needs"),
        "design_style": kwargs.get("design_style"),
        "export_type": kwargs.get("export_type"),
        "notes": kwargs.get("notes"),
    }

    # Remove empty optional fields so Supabase receives a clean payload.
    event = {k: v for k, v in event.items() if v is not None}

    try:
        supabase.table("events").insert(event).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def log_plant_request(email, requested_plant, **kwargs):
    requested_plant = (requested_plant or "").strip()
    if not requested_plant:
        return False, "Plant request is empty."

    ok, err = log_event(
        email,
        "plant_requested",
        notes=requested_plant,
        **kwargs
    )

    # Optional dedicated table. If you create a plant_requests table in Supabase,
    # this will also save requests there. If that table does not exist, the
    # events table above is still the primary tracking location.
    if supabase is not None and email:
        try:
            supabase.table("plant_requests").insert({
                "email": email,
                "requested_plant": requested_plant,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "climate": kwargs.get("climate"),
                "sun_exposure": kwargs.get("sun_exposure"),
                "water_needs": kwargs.get("water_needs"),
                "notes": requested_plant,
            }).execute()
        except Exception:
            pass

    return ok, err

def get_or_create_user(email):
    email = email.strip().lower()
    if supabase is None:
        return {"email": email, "paid_status": False, "total_generations": 0, "total_exports": 0}

    now = datetime.now(timezone.utc).isoformat()
    result = supabase.table("users").select("*").eq("email", email).execute()
    if result.data:
        user = result.data[0]
        supabase.table("users").update({"last_seen": now}).eq("email", email).execute()
        return user

    new_user = {
        "email": email,
        "first_seen": now,
        "last_seen": now,
        "paid_status": False,
        "total_generations": 0,
        "total_exports": 0,
    }
    created = supabase.table("users").insert(new_user).execute()
    return created.data[0] if created.data else new_user

def increment_generation_count(email):
    if supabase is None:
        return 0
    result = supabase.table("users").select("total_generations").eq("email", email).execute()
    current = 0
    if result.data:
        current = result.data[0].get("total_generations") or 0
    new_count = current + 1
    supabase.table("users").update({
        "total_generations": new_count,
        "last_seen": datetime.now(timezone.utc).isoformat()
    }).eq("email", email).execute()
    return new_count

def increment_export_count(email):
    if supabase is None:
        return
    result = supabase.table("users").select("total_exports").eq("email", email).execute()
    current = 0
    if result.data:
        current = result.data[0].get("total_exports") or 0
    supabase.table("users").update({"total_exports": current + 1}).eq("email", email).execute()

def beta_email_gate():
    if "user_email" not in st.session_state:
        st.session_state.user_email = None
    if st.session_state.user_email:
        return True

    st.title("Native Plant Layout Engine by The Landscape Library")
    st.markdown("### Enter your email to begin generating planting layouts.")
    email = st.text_input("Enter your email to continue")
    if st.button("Continue"):
        if "@" not in email or "." not in email:
            st.error("Please enter a valid email address.")
            st.stop()
        user = get_or_create_user(email)
        st.session_state.user_email = user["email"]
        st.session_state.user_data = user
        log_event(user["email"], "app_opened")
        st.rerun()
    st.stop()

beta_email_gate()


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
    page_title="Native Plant Layout Engine",
    layout="wide"
)

st.title("Native Plant Layout Engine")
st.caption("A California native planting layout generator for naturalistic and restorative landscape studies, plant palettes, plan views, elevation views, and schedules.")

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
    "Low": 120,
    "Moderate": 180,
    "Dense": 240,
    "Very Dense": 320
}

COMPOSITION_STYLES = [
    "Naturalistic Composition",
    "Clustered Massing",
    "Structured Rhythm",
]

# These values are intentionally modest. They improve the visual read of the plan
# without turning the MVP into a complicated drift/community engine.
COMPOSITION_SETTINGS = {
    "Naturalistic Composition": {
        "structure_cluster_count": 3,
        "accent_cluster_count": 4,
        "cluster_tightness": 0.13,
        "matrix_cluster_bias": 0.18,
    },
    "Clustered Massing": {
        "structure_cluster_count": 3,
        "accent_cluster_count": 3,
        "cluster_tightness": 0.09,
        "matrix_cluster_bias": 0.35,
    },
    "Structured Rhythm": {
        "structure_cluster_count": 4,
        "accent_cluster_count": 4,
        "cluster_tightness": 0.07,
        "matrix_cluster_bias": 0.08,
    },
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



# -----------------------------
# MVP composition metadata from Google Sheet
# -----------------------------
# These columns let YODRA compose before it packs circles:
# Design Tier: 1 focal/canopy, 2 structure, 3 accent, 4 matrix.
# Dominance %: relative visual/area dominance inside a compatible palette.
# Community Group: plants that should read as the same ecological/design community.
# Companion Plants: plant codes that should be favored nearby.
COMPOSITION_DATABASE = {
    "CP": {"group_min": 8, "group_max": 20, "spacing_min_ft": 1.5, "spacing_max_ft": 2.5, "placement_pattern": "Drift", "edge_preference": "Any", "design_tier": 4, "dominance_percent": 70, "community_group": "Coastal Meadow", "companion_plants": ["FC", "ID", "EL"]},
    "EL": {"group_min": 3, "group_max": 7, "spacing_min_ft": 2, "spacing_max_ft": 4, "placement_pattern": "Accent Pocket", "edge_preference": "Interior", "design_tier": 3, "dominance_percent": 15, "community_group": "Coastal Meadow", "companion_plants": ["CP", "FC", "ID"]},
    "FC": {"group_min": 5, "group_max": 12, "spacing_min_ft": 2, "spacing_max_ft": 3, "placement_pattern": "Drift", "edge_preference": "Any", "design_tier": 4, "dominance_percent": 50, "community_group": "Coastal Meadow", "companion_plants": ["CP", "EL", "ID"]},
    "SS": {"group_min": 3, "group_max": 5, "spacing_min_ft": 3, "spacing_max_ft": 5, "placement_pattern": "Accent Pocket", "edge_preference": "Interior", "design_tier": 3, "dominance_percent": 10, "community_group": "Coastal Woodland Edge", "companion_plants": ["ID", "AHM", "CP"]},
    "ID": {"group_min": 5, "group_max": 9, "spacing_min_ft": 2, "spacing_max_ft": 3, "placement_pattern": "Drift", "edge_preference": "Any", "design_tier": 3, "dominance_percent": 15, "community_group": "Coastal Meadow", "companion_plants": ["CP", "FC", "EL"]},
    "AM": {"group_min": 1, "group_max": 1, "spacing_min_ft": 18, "spacing_max_ft": 25, "placement_pattern": "Specimen", "edge_preference": "Back", "design_tier": 1, "dominance_percent": 5, "community_group": "Coastal Woodland", "companion_plants": ["AHM", "SS"]},
    "AHM": {"group_min": 1, "group_max": 3, "spacing_min_ft": 8, "spacing_max_ft": 12, "placement_pattern": "Anchor Mass", "edge_preference": "Edge", "design_tier": 2, "dominance_percent": 15, "community_group": "Coastal Woodland", "companion_plants": ["AM", "SS", "ID"]},

    "MR": {"group_min": 5, "group_max": 12, "spacing_min_ft": 4, "spacing_max_ft": 6, "placement_pattern": "Drift", "edge_preference": "Any", "design_tier": 4, "dominance_percent": 60, "community_group": "Inland Grassland", "companion_plants": ["SP", "EF", "EC"]},
    "SP": {"group_min": 10, "group_max": 25, "spacing_min_ft": 1.5, "spacing_max_ft": 2.5, "placement_pattern": "Drift", "edge_preference": "Any", "design_tier": 4, "dominance_percent": 70, "community_group": "Inland Grassland", "companion_plants": ["MR", "EF", "EC"]},
    "JP": {"group_min": 5, "group_max": 10, "spacing_min_ft": 2, "spacing_max_ft": 4, "placement_pattern": "Drift", "edge_preference": "Any", "design_tier": 4, "dominance_percent": 35, "community_group": "Inland Riparian", "companion_plants": ["MR", "EF"]},
    "EF": {"group_min": 3, "group_max": 5, "spacing_min_ft": 4, "spacing_max_ft": 6, "placement_pattern": "Accent Pocket", "edge_preference": "Interior", "design_tier": 3, "dominance_percent": 20, "community_group": "Inland Grassland", "companion_plants": ["SP", "MR", "EC"]},
    "EC": {"group_min": 5, "group_max": 10, "spacing_min_ft": 2, "spacing_max_ft": 3, "placement_pattern": "Accent Pocket", "edge_preference": "Interior", "design_tier": 3, "dominance_percent": 10, "community_group": "Inland Grassland", "companion_plants": ["EF", "SP"]},
    "AC": {"group_min": 4, "group_max": 8, "spacing_min_ft": 4, "spacing_max_ft": 6, "placement_pattern": "Drift", "edge_preference": "Any", "design_tier": 2, "dominance_percent": 25, "community_group": "Dry Chaparral", "companion_plants": ["EF", "EC"]},
    "QC": {"group_min": 1, "group_max": 1, "spacing_min_ft": 25, "spacing_max_ft": 35, "placement_pattern": "Specimen", "edge_preference": "Back", "design_tier": 1, "dominance_percent": 5, "community_group": "Oak Woodland", "companion_plants": ["AC", "EF"]},

    "CT": {"group_min": 8, "group_max": 20, "spacing_min_ft": 1.5, "spacing_max_ft": 2.5, "placement_pattern": "Drift", "edge_preference": "Any", "design_tier": 4, "dominance_percent": 70, "community_group": "Oak Woodland Floor", "companion_plants": ["PM", "HM"]},
    "PM": {"group_min": 5, "group_max": 12, "spacing_min_ft": 3, "spacing_max_ft": 5, "placement_pattern": "Drift", "edge_preference": "Interior", "design_tier": 4, "dominance_percent": 50, "community_group": "Oak Woodland Floor", "companion_plants": ["CT", "HM", "WF"]},
    "HM": {"group_min": 5, "group_max": 9, "spacing_min_ft": 2, "spacing_max_ft": 3, "placement_pattern": "Accent Pocket", "edge_preference": "Interior", "design_tier": 3, "dominance_percent": 15, "community_group": "Woodland Edge", "companion_plants": ["PM", "CT"]},
    "RS": {"group_min": 3, "group_max": 5, "spacing_min_ft": 5, "spacing_max_ft": 7, "placement_pattern": "Accent Pocket", "edge_preference": "Interior", "design_tier": 3, "dominance_percent": 15, "community_group": "Woodland Edge", "companion_plants": ["PM", "HM"]},
    "WF": {"group_min": 3, "group_max": 7, "spacing_min_ft": 4, "spacing_max_ft": 6, "placement_pattern": "Drift", "edge_preference": "Interior", "design_tier": 4, "dominance_percent": 40, "community_group": "Riparian Woodland", "companion_plants": ["PM", "CT"]},
    "ACI": {"group_min": 1, "group_max": 1, "spacing_min_ft": 12, "spacing_max_ft": 20, "placement_pattern": "Specimen", "edge_preference": "Back", "design_tier": 1, "dominance_percent": 5, "community_group": "Woodland Canopy", "companion_plants": ["PM", "HM"]},
    "HA": {"group_min": 1, "group_max": 3, "spacing_min_ft": 10, "spacing_max_ft": 15, "placement_pattern": "Anchor Mass", "edge_preference": "Edge", "design_tier": 2, "dominance_percent": 20, "community_group": "Woodland Edge", "companion_plants": ["ACI", "RS"]},
}


def apply_composition_database(plants):
    enriched = []
    for plant in plants:
        p = plant.copy()
        meta = COMPOSITION_DATABASE.get(p.get("code"), {})
        p.update(meta)
        p.setdefault("group_min", 1)
        p.setdefault("group_max", 3)
        p.setdefault("spacing_min_ft", p.get("spread_ft", 2))
        p.setdefault("spacing_max_ft", max(p.get("spread_ft", 2), p.get("spacing_min_ft", 2)))
        p.setdefault("placement_pattern", "Drift")
        p.setdefault("edge_preference", "Any")
        p.setdefault("design_tier", {"Canopy": 1, "Structure": 2, "Accent": 3, "Matrix": 4}.get(p.get("role"), 4))
        p.setdefault("dominance_percent", max(5, int(p.get("weight", 1)) * 10))
        p.setdefault("community_group", ", ".join(p.get("climate", [])))
        p.setdefault("companion_plants", [])
        enriched.append(p)
    return enriched

PLANTS = apply_composition_database(PLANTS)


ROLE_ORDER = sorted({plant["role"] for plant in PLANTS})

DEFAULT_ROLE_COVERAGE_PERCENTAGES = {
    "Canopy": 12,
    "Structure": 22,
    "Matrix": 44,
    "Accent": 22,
}

def default_role_percentage(role):
    return DEFAULT_ROLE_COVERAGE_PERCENTAGES.get(role, 20)

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

    # Dominance % is the main MVP composition weight.
    # Design Tier then slightly reinforces hierarchy without overpowering dominance.
    tier_multiplier = {1: 0.7, 2: 1.0, 3: 0.85, 4: 1.25}
    weights = []
    for p in plants:
        dominance = float(p.get("dominance_percent", p.get("weight", 1) * 10) or 1)
        tier = int(p.get("design_tier", 4) or 4)
        weights.append(max(0.1, dominance * tier_multiplier.get(tier, 1.0)))
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


def pack_by_role(poly, plant_pool, target_coverage, spacing_factor, max_plants_total, role_split=None):
    boundary_area = poly.area

    if boundary_area <= 0:
        return [], 0

    total_target_area = boundary_area * target_coverage
    all_placed = []
    total_placed_area = 0

    active_roles = [role for role in ROLE_ORDER if any(p["role"] == role for p in plant_pool)]

    if not active_roles:
        return [], 0

    if role_split is None:
        total_default = sum(default_role_percentage(role) for role in active_roles) or 1
        role_split = {
            role: default_role_percentage(role) / total_default
            for role in active_roles
        }

    for role in active_roles:
        role_plants = [p for p in plant_pool if p["role"] == role]

        if not role_plants:
            continue

        layer_target_area = total_target_area * role_split.get(role, 0)

        placed_layer, placed_area = pack_layer(
            poly=poly,
            plants=role_plants,
            target_area=layer_target_area,
            spacing_factor=spacing_factor,
            existing_placed=all_placed,
            max_plants_total=max_plants_total
        )

        all_placed.extend(placed_layer)
        total_placed_area += placed_area

    return all_placed, total_placed_area / boundary_area


def random_point_inside(poly, radius=0, max_attempts=1200):
    """Return a random point whose plant circle fits inside the polygon."""
    minx, miny, maxx, maxy = poly.bounds
    for _ in range(max_attempts):
        x = random.uniform(minx + radius, maxx - radius)
        y = random.uniform(miny + radius, maxy - radius)
        if circle_inside(poly, x, y, radius):
            return x, y
    return None

def point_with_preference(poly, radius=0, preference="Any", max_attempts=1600):
    """Return a valid point honoring broad design intent from the Google Sheet."""
    preference = (preference or "Any").strip().lower()
    minx, miny, maxx, maxy = poly.bounds
    height = max(1, maxy - miny)
    width = max(1, maxx - minx)
    diag = max(1, math.dist((minx, miny), (maxx, maxy)))
    centroid = poly.centroid

    for _ in range(max_attempts):
        x = random.uniform(minx + radius, maxx - radius)
        y = random.uniform(miny + radius, maxy - radius)
        if not circle_inside(poly, x, y, radius):
            continue

        point = Point(x, y)
        dist_to_edge = point.distance(poly.boundary)

        if preference == "back" and y > miny + height * 0.42:
            continue
        if preference == "edge" and dist_to_edge > diag * 0.16:
            continue
        if preference == "interior" and dist_to_edge < diag * 0.10:
            continue

        return x, y

    return random_point_inside(poly, radius)


def get_species_target_area(target_area, plants):
    """Split a layer target by dominance percent instead of treating species equally."""
    total = sum(max(1, float(p.get("dominance_percent", 10) or 10)) for p in plants) or 1
    return {p["code"]: target_area * (max(1, float(p.get("dominance_percent", 10) or 10)) / total) for p in plants}


def grouped_species_order(plants):
    """Order plants by design tier, then dominance. Lower tier number places earlier."""
    return sorted(plants, key=lambda p: (int(p.get("design_tier", 4) or 4), -float(p.get("dominance_percent", 10) or 10)))


def make_composition_centers(poly, count, edge_preference=False):
    """Create loose visual anchor points for clusters/masses."""
    centers = []
    centroid = poly.centroid
    minx, miny, maxx, maxy = poly.bounds
    diag = max(1, math.dist((minx, miny), (maxx, maxy)))

    attempts = 0
    while len(centers) < count and attempts < 2500:
        attempts += 1
        pt = random_point_inside(poly, 0)
        if pt is None:
            break

        x, y = pt
        if edge_preference:
            # Avoid all anchors falling dead-center; structure plants often read better
            # when they hold edges, corners, or back-of-bed positions.
            d_centroid = math.dist((x, y), (centroid.x, centroid.y))
            if d_centroid < diag * 0.18 and random.random() < 0.75:
                continue

        min_center_spacing = diag * (0.18 if count <= 3 else 0.13)
        if all(math.dist((x, y), c) >= min_center_spacing for c in centers):
            centers.append((x, y))

    if not centers:
        fallback = random_point_inside(poly, 0)
        if fallback is not None:
            centers.append(fallback)

    return centers


def point_near_center(poly, center, radius, spread):
    """Find a point near a cluster center, falling back to any valid point."""
    cx, cy = center
    minx, miny, maxx, maxy = poly.bounds
    spread = max(spread, radius * 2.5, 8)

    for _ in range(800):
        x = random.gauss(cx, spread)
        y = random.gauss(cy, spread)
        if x < minx + radius or x > maxx - radius or y < miny + radius or y > maxy - radius:
            continue
        if circle_inside(poly, x, y, radius):
            return x, y

    return random_point_inside(poly, radius)


def relaxed_overlap(x, y, r, placed, spacing_factor, plant=None):
    """A stricter overlap test for visible design composition.

    Canopy plants may still allow underplanting, but structure shrubs no longer create
    a free overlap pass. This prevents the MVP from producing visually messy circles.
    """
    for p in placed:
        existing_plant = p["plant"]
        existing_role = existing_plant.get("role", "")
        current_role = plant.get("role", "") if plant else ""

        existing_allows_underplanting = existing_plant.get("allows_underplanting", False) and existing_role == "Canopy"
        current_allows_underplanting = plant is not None and plant.get("allows_underplanting", False) and current_role == "Canopy"

        if existing_allows_underplanting and current_role in ["Matrix", "Accent"]:
            continue
        if current_allows_underplanting and existing_role in ["Matrix", "Accent"]:
            continue

        distance = math.dist((x, y), (p["x"], p["y"]))
        min_distance = (r + p["radius"]) * spacing_factor
        if distance < min_distance:
            return True

    return False


def place_from_candidates(poly, plants, target_area, spacing_factor, existing_placed, max_plants_total, centers=None, cluster_spread=40, matrix_bias=0.0):
    """Place a role/layer using Google Sheet composition metadata.

    This is the key MVP upgrade:
    - Species targets are split by Dominance %, not random equality.
    - Design Tier determines order.
    - Group Min/Max creates masses, drifts, and pockets.
    - Edge Preference steers back/edge/interior plants.
    - Companion Plants are encouraged by reusing nearby centers when possible.
    """
    if not plants:
        return [], 0

    placed_layer = []
    placed_area = 0
    max_attempts = 8000
    attempts = 0
    species_targets = get_species_target_area(target_area, plants)
    code_to_recent_centers = {}

    minx, miny, maxx, maxy = poly.bounds
    diag = max(1, math.dist((minx, miny), (maxx, maxy)))

    for plant in grouped_species_order(plants):
        if len(existing_placed) + len(placed_layer) >= max_plants_total:
            break

        species_target = species_targets.get(plant["code"], target_area / max(1, len(plants)))
        species_area = 0
        r = plant["radius"]
        pattern = plant.get("placement_pattern", "Drift")
        edge_pref = plant.get("edge_preference", "Any")
        group_min = int(plant.get("group_min", 1) or 1)
        group_max = max(group_min, int(plant.get("group_max", group_min) or group_min))

        if pattern in ["Specimen"] or int(plant.get("design_tier", 4)) == 1:
            group_min = group_max = 1
        elif pattern in ["Anchor Mass"]:
            group_max = min(group_max, 3)

        # Convert sheet spacing values into a local spacing adjustment.
        desired_spacing_ft = (float(plant.get("spacing_min_ft", plant.get("spread_ft", 2))) + float(plant.get("spacing_max_ft", plant.get("spread_ft", 2)))) / 2
        spread_ft = max(0.5, float(plant.get("spread_ft", desired_spacing_ft) or desired_spacing_ft))
        local_spacing_factor = max(0.92, min(1.45, spacing_factor * desired_spacing_ft / spread_ft))

        # Dominant matrix species should read as fields, not single circles.
        if int(plant.get("design_tier", 4)) == 4:
            local_cluster_spread = max(cluster_spread, diag * 0.16)
        elif pattern == "Accent Pocket":
            local_cluster_spread = max(r * 3.5, diag * 0.075)
        elif pattern == "Anchor Mass":
            local_cluster_spread = max(r * 2.2, diag * 0.09)
        else:
            local_cluster_spread = max(r * 3.0, cluster_spread)

        while species_area < species_target and attempts < max_attempts and len(existing_placed) + len(placed_layer) < max_plants_total:
            attempts += 1

            companion_centers = []
            for code in plant.get("companion_plants", []):
                companion_centers.extend(code_to_recent_centers.get(code, []))

            if companion_centers and random.random() < 0.55:
                center = random.choice(companion_centers)
            elif centers and random.random() < max(0.20, min(0.85, 1.0 - matrix_bias)):
                center = random.choice(centers)
            else:
                center = point_with_preference(poly, r, edge_pref)

            if center is None:
                continue

            group_count = random.randint(group_min, group_max)
            if species_area + math.pi * (r ** 2) * group_count > species_target * 1.35:
                group_count = max(1, int((species_target - species_area) / max(math.pi * (r ** 2), 1)))

            group_placed = 0
            for _ in range(max(1, group_count)):
                if len(existing_placed) + len(placed_layer) >= max_plants_total:
                    break

                if pattern == "Specimen":
                    pt = center
                else:
                    pt = point_near_center(poly, center, r, local_cluster_spread)

                if pt is None:
                    continue

                x, y = pt
                all_existing = existing_placed + placed_layer
                if relaxed_overlap(x, y, r, all_existing, local_spacing_factor, plant):
                    continue

                placed_layer.append({"x": x, "y": y, "radius": r, "plant": plant})
                species_area += math.pi * (r ** 2)
                placed_area += math.pi * (r ** 2)
                group_placed += 1
                code_to_recent_centers.setdefault(plant["code"], []).append((x, y))

            # If nothing in the group could place, try another center.
            if group_placed == 0:
                continue

    return placed_layer, placed_area

def composition_role_order(active_roles):
    # Professional planting hierarchy: focal/anchor first, structure second,
    # matrix field third, accents last so they land as moments, not noise.
    preferred = ["Canopy", "Structure", "Matrix", "Accent"]
    ordered = [role for role in preferred if role in active_roles]
    ordered.extend([role for role in active_roles if role not in ordered])
    return ordered


def pack_composed_layout(poly, plant_pool, target_coverage, spacing_factor, max_plants_total, composition_style="Naturalistic Composition"):
    """Composition-first packing.

    This keeps the MVP simple but makes the visual result more intentional:
    1. Canopy/large anchors first.
    2. Structure plants in readable masses.
    3. Matrix plants fill the field.
    4. Accent plants occur near structure/anchor moments.
    """
    boundary_area = poly.area
    if boundary_area <= 0:
        return [], 0, []

    settings = COMPOSITION_SETTINGS.get(composition_style, COMPOSITION_SETTINGS["Naturalistic Composition"])
    total_target_area = boundary_area * target_coverage
    all_placed = []
    total_placed_area = 0

    active_roles = [role for role in ROLE_ORDER if any(p["role"] == role for p in plant_pool)]
    if not active_roles:
        return [], 0, []

    minx, miny, maxx, maxy = poly.bounds
    diag = max(1, math.dist((minx, miny), (maxx, maxy)))
    cluster_spread = diag * settings["cluster_tightness"]

    structure_centers = make_composition_centers(
        poly,
        settings["structure_cluster_count"],
        edge_preference=True,
    )
    accent_centers = list(structure_centers)

    role_debug = []

    for role in composition_role_order(active_roles):
        role_plants = [p for p in plant_pool if p["role"] == role]
        if not role_plants:
            continue

        # Database-driven role allocation. Role percentages/sliders were removed
        # because they fought the hierarchy already stored in the sheet.
        role_plants_dominance = sum(max(1, float(p.get("dominance_percent", 10) or 10)) for p in role_plants)
        total_palette_dominance = sum(max(1, float(p.get("dominance_percent", 10) or 10)) for p in plant_pool) or 1
        layer_target_area = total_target_area * (role_plants_dominance / total_palette_dominance)

        # Protect the main design hierarchy: Tier 1 and Tier 2 should not consume the whole bed,
        # even if their circles are large. Matrix should remain the dominant visual field.
        if role == "Canopy":
            layer_target_area = min(layer_target_area, total_target_area * 0.12)
        elif role == "Structure":
            layer_target_area = min(layer_target_area, total_target_area * 0.22)
        elif role == "Accent":
            layer_target_area = min(layer_target_area, total_target_area * 0.20)
        elif role == "Matrix":
            layer_target_area = max(layer_target_area, total_target_area * 0.46)

        if layer_target_area <= 0:
            continue

        if role == "Canopy":
            centers = make_composition_centers(poly, max(1, min(2, len(role_plants))), edge_preference=True)
            layer, area = place_from_candidates(
                poly, role_plants, layer_target_area, max(spacing_factor, 1.2),
                all_placed, max_plants_total, centers=centers, cluster_spread=diag * 0.18
            )
            accent_centers.extend([(p["x"], p["y"]) for p in layer])

        elif role == "Structure":
            layer, area = place_from_candidates(
                poly, role_plants, layer_target_area, max(spacing_factor, 1.12),
                all_placed, max_plants_total, centers=structure_centers, cluster_spread=cluster_spread
            )
            accent_centers.extend([(p["x"], p["y"]) for p in layer])

        elif role == "Matrix":
            # Matrix should read as a continuous field, with only a modest clustering bias.
            layer, area = place_from_candidates(
                poly, role_plants, layer_target_area, spacing_factor,
                all_placed, max_plants_total, centers=structure_centers,
                cluster_spread=diag * 0.22, matrix_bias=settings["matrix_cluster_bias"]
            )

        elif role == "Accent":
            if not accent_centers:
                accent_centers = make_composition_centers(poly, settings["accent_cluster_count"], edge_preference=False)
            layer, area = place_from_candidates(
                poly, role_plants, layer_target_area, max(spacing_factor, 1.05),
                all_placed, max_plants_total, centers=accent_centers,
                cluster_spread=diag * 0.11
            )

        else:
            layer, area = place_from_candidates(
                poly, role_plants, layer_target_area, spacing_factor,
                all_placed, max_plants_total
            )

        all_placed.extend(layer)
        total_placed_area += area
        role_debug.append({"Role": role, "Count": len(layer), "Coverage Sq Ft Equivalent": round(canvas_area_to_sqft(area, feet_per_canvas_unit), 1) if 'feet_per_canvas_unit' in globals() else round(area, 1)})

    return all_placed, total_placed_area / boundary_area, role_debug


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


def hardiness_is_compatible(selected_zones, usda_min, usda_max):
    if not selected_zones:
        return True
    return any(usda_min <= zone <= usda_max for zone in selected_zones)


def filter_plants(plant_database, state, climate, selected_usda_zones, sun, water):
    return [
        plant for plant in plant_database
        if state in plant["state"]
        and climate in plant["climate"]
        and hardiness_is_compatible(selected_usda_zones, plant["usda_min"], plant["usda_max"])
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


def normalize_polygon(points):
    if points is None or len(points) < 3:
        return None
    poly = Polygon(points)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area <= 0:
        return None
    return poly


def polygon_points_from_geometry(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [(float(x), float(y)) for x, y in list(geom.exterior.coords)[:-1]]
    if geom.geom_type == "MultiPolygon":
        largest = max(list(geom.geoms), key=lambda g: g.area)
        return [(float(x), float(y)) for x, y in list(largest.exterior.coords)[:-1]]
    return []


def valid_role_zones_for_boundary(role_zones, main_poly):
    valid = {}
    for role, points in (role_zones or {}).items():
        zone_poly = normalize_polygon(points)
        if zone_poly is None:
            continue
        clipped = zone_poly.intersection(main_poly)
        if clipped.is_empty or clipped.area <= 0:
            continue
        valid[role] = clipped
    return valid


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


def plan_to_svg(points, placed_instances, canvas_width, canvas_height, feet_per_canvas_unit, role_zones=None):
    """Create a clean vector SVG of the plan geometry.

    This avoids relying on Matplotlib's SVG output and gives you true circle/vector objects.
    """
    path_points = " ".join([f"{x:.2f},{y:.2f}" for x, y in points])
    svg = StringIO()
    svg.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}">\n')
    svg.write('<rect width="100%" height="100%" fill="white"/>\n')
    svg.write(f'<polygon points="{path_points}" fill="none" stroke="black" stroke-width="2"/>\n')

    for role, zone_points in (role_zones or {}).items():
        if not zone_points or len(zone_points) < 3:
            continue
        zone_path = " ".join([f"{x:.2f},{y:.2f}" for x, y in zone_points])
        first_x, first_y = zone_points[0]
        svg.write(f'<polygon points="{zone_path}" fill="none" stroke="black" stroke-width="1" stroke-dasharray="4 4" opacity="0.45"/>\n')
        svg.write(f'<text x="{first_x:.2f}" y="{first_y:.2f}" font-family="Arial" font-size="10" opacity="0.65">{escape_svg_text(role)} zone</text>\n')

    for item in placed_instances:
        plant = item["plant"]
        dash = ' stroke-dasharray="6 4"' if plant.get("allows_underplanting", False) else ""
        weight = "bold" if plant.get("allows_underplanting", False) else "normal"
        svg.write(f'<circle cx="{item["x"]:.2f}" cy="{item["y"]:.2f}" r="{item["radius"]:.2f}" fill="none" stroke="black" stroke-width="1.2"{dash}/>\n')
        svg.write(f'<text x="{item["x"]:.2f}" y="{item["y"]:.2f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="8" font-weight="{weight}">{escape_svg_text(plant["code"])}</text>\n')

    svg.write(f'<text x="12" y="{canvas_height - 14}" font-family="Arial" font-size="10">Scale: 1 px = {feet_per_canvas_unit:.3f} ft</text>\n')
    svg.write('</svg>')
    return BytesIO(svg.getvalue().encode("utf-8"))


def plan_to_dxf(points, placed_instances, feet_per_canvas_unit, role_zones=None):
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
    climate = st.selectbox("California Plant Community", ["Coastal", "Inland", "Dry", "Woodland"])

    st.markdown("**USDA Hardiness**")
    st.caption("Select one or more USDA zones. Plants are included when the selected zone falls between USDA Min and USDA Max in the plant database.")
    usda_zone_options = list(range(5, 11))
    default_usda_zones = [9]
    selected_usda_zones = []
    zone_cols = st.columns(3)
    for idx, zone in enumerate(usda_zone_options):
        with zone_cols[idx % 3]:
            checked = st.checkbox(f"Zone {zone}", value=zone in default_usda_zones, key=f"usda_zone_{zone}")
            if checked:
                selected_usda_zones.append(zone)

    sun = st.selectbox(
        "Sun Exposure",
        ["Full Sun", "Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"]
    )

    water = st.selectbox(
        "Water Needs",
        ["Low", "Moderate-Low", "Low-Moderate", "Moderate"]
    )

    st.header("Density")

    density = st.selectbox(
        "Coverage Density",
        ["Low", "Moderate", "Dense", "Very Dense"]
    )

    st.header("Composition")
    composition_style = st.selectbox(
        "Layout Character",
        COMPOSITION_STYLES,
        index=0,
        help="Improves the visual read of the plan without adding complex drift/community controls."
    )

    target_coverage = DENSITY_OPTIONS[density]
    spacing_factor = SPACING_BY_DENSITY[density]
    max_plants_total = MAX_PLANTS_BY_DENSITY[density]

    st.header("Scale")
    st.caption(f"Bed limit: {MAX_BED_FEET} ft max length or width")
    st.caption(f"Active bed: {bed_length_ft:.0f} ft x {bed_width_ft:.0f} ft")

# -----------------------------
# Active plant database + image prep
# -----------------------------

runtime_plants = make_runtime_plant_pool(PLANTS, feet_per_canvas_unit)
selected_plants = filter_plants(runtime_plants, state, climate, selected_usda_zones, sun, water)
# Manual include / exclude controls
all_matching_names = [p["name"] for p in selected_plants]
with st.sidebar:
    st.header("Plant Controls")
    include_names = st.multiselect("Force include plants", [p["name"] for p in runtime_plants])
    exclude_names = st.multiselect("Exclude plants", all_matching_names)

    st.caption("Composition is now controlled by the plant database: Design Tier, Dominance %, Placement Pattern, Group Min/Max, Edge Preference, Community Group, and Companion Plants.")
forced = [p for p in runtime_plants if p["name"] in include_names]
selected_plants = [p for p in selected_plants if p["name"] not in exclude_names]
for p in forced:
    if p["name"] not in [sp["name"] for sp in selected_plants]:
        selected_plants.append(p)

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
        st.caption("TIP: Left click to add boundary points. Right click to end nearest the origin point and complete the boundary.")
        st.caption('Drawing canvas: 50\'-0" horizontal × 50\'-0" vertical.')

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
        st.caption("Click around the planting bedline in order. Use more points for curves. The final segment closes automatically between the last point and first point.")

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
    st.subheader("Request a Plant")
    requested_plant = st.text_input("Plant you want added")
    if st.button("Submit Plant Request"):
        if requested_plant.strip():
            ok, error_message = log_plant_request(
                st.session_state.get("user_email"),
                requested_plant.strip(),
                state=state,
                zone=", ".join([f"USDA {z}" for z in selected_usda_zones]),
                climate=climate,
                sun_exposure=sun,
                water_needs=water,
                design_style="Native Plant Layout Engine",
            )
            if ok:
                st.success("Plant request submitted.")
            else:
                st.error(f"Plant request was not saved: {error_message}")
        else:
            st.warning("Enter a plant name before submitting.")

    st.subheader("3. Selected Plant Palette")

    if len(selected_plants) == 0:
        st.warning("No plants match these parameters yet. Try adjusting USDA hardiness, sun exposure, or water needs.")
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
    if supabase is not None and st.session_state.get("user_email"):
        user_check = supabase.table("users").select("*").eq("email", st.session_state.user_email).execute()
        current_user = user_check.data[0] if user_check.data else {}
        if not current_user.get("paid_status", False) and (current_user.get("total_generations") or 0) >= FREE_GENERATION_LIMIT:
            st.warning("You have reached the free generation limit.")
            log_event(st.session_state.user_email, "paywall_shown")
            st.stop()
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
                poly = normalize_polygon(points)

                if poly is None:
                    st.warning("The boundary is invalid. Try tracing a clearer closed shape.")

                else:
                    placed_instances, actual_coverage, role_debug = pack_composed_layout(
                        poly=poly,
                        plant_pool=selected_plants,
                        target_coverage=target_coverage,
                        spacing_factor=spacing_factor,
                        max_plants_total=max_plants_total,
                        composition_style=composition_style
                    )

                    if len(placed_instances) == 0:
                        st.warning("No plants could fit inside the boundary. Try a larger area, lower density, or different plant parameters.")

                    else:
                        new_generation_count = increment_generation_count(st.session_state.get("user_email"))
                        log_event(
                            st.session_state.get("user_email"),
                            "generation_run",
                            state=state,
                            zone=", ".join([f"USDA {z}" for z in selected_usda_zones]),
                            climate=climate,
                            sun_exposure=sun,
                            water_needs=water,
                            design_style=composition_style,
                            notes=f"density={density}; plants_generated={len(placed_instances)}"
                        )

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
                        st.caption(f"Composition style: {composition_style}")

                        if role_debug:
                            with st.expander("Composition Summary"):
                                st.dataframe(pd.DataFrame(role_debug), width="stretch")

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

                        counts = {}
                        for item in placed_instances:
                            plant = item["plant"]
                            counts[plant["name"]] = counts.get(plant["name"], 0) + 1

                        st.subheader("Plant Schedule")

                        schedule = []
                        for plant_name, count in counts.items():
                            plant = next(p for p in runtime_plants if p["name"] == plant_name)

                            schedule.append({
                                "Code": plant["code"],
                                "Count": count,
                                "Botanical Name": plant["name"],
                                "Common Name": plant["common_name"],
                                "Form": plant["form"],
                                "Role": plant["role"],
                                "Texture": plant["texture"],
                                "Color Tone": plant["color_tone"],
                                "Visual Weight": plant["visual_weight"],
                                "Spread Ft": plant["spread_ft"],
                                "Height Ft": plant["height_ft"],
                                "State": state,
                                "Climate": ", ".join(plant["climate"]),
                                "USDA Min": plant["usda_min"],
                                "USDA Max": plant["usda_max"],
                                "Sun": ", ".join(plant["sun"]),
                                "Water": ", ".join(plant["water"]),
                                "Seasonality": plant["seasonality"],
                                "Allows Underplanting": plant.get("allows_underplanting", False),
                                "Design Tier": plant.get("design_tier"),
                                "Dominance %": plant.get("dominance_percent"),
                                "Community Group": plant.get("community_group"),
                                "Companion Plants": ", ".join(plant.get("companion_plants", [])),
                                "Placement Pattern": plant.get("placement_pattern"),
                                "Edge Preference": plant.get("edge_preference"),
                                "Group Min": plant.get("group_min"),
                                "Group Max": plant.get("group_max"),
                                "Spacing Min Ft": plant.get("spacing_min_ft"),
                                "Spacing Max Ft": plant.get("spacing_max_ft")
                            })

                        schedule_df = pd.DataFrame(schedule)
                        st.dataframe(schedule_df, width="stretch")

                        csv_buffer = schedule_df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            label="Download Plant Schedule CSV / Excel",
                            data=csv_buffer,
                            file_name="yodra-plant-schedule.csv",
                            mime="text/csv",
                            on_click=lambda: increment_export_count(st.session_state.get("user_email"))
                        )
                        log_event(st.session_state.get("user_email"), "schedule_export_ready", export_type="csv")

    except Exception as e:
        st.error("The app crashed while generating the layout.")
        st.exception(e)
