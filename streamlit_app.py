import streamlit as st
from datetime import datetime, timezone
try:
    from supabase import create_client
except Exception:
    create_client = None

import random
import math
import os
import html
import base64
from io import BytesIO, StringIO
from copy import deepcopy

import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw
from shapely.geometry import Polygon, Point
try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except Exception:
    streamlit_image_coordinates = None

# Optional PDF support. Add PyMuPDF to requirements.txt for PDF uploads.
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

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
    event = {k: v for k, v in event.items() if v is not None}
    try:
        supabase.table("events").insert(event).execute()
        return True, None
    except Exception as e:
        return False, str(e)

def log_region_request(email, requested_region, requested_city, **kwargs):
    requested_region = (requested_region or "").strip()
    requested_city = (requested_city or "").strip()
    if not requested_region:
        return False, "Region request is empty."
    if not requested_city:
        return False, "City is empty."
    notes = f"Requested Region: {requested_region} | City: {requested_city}"
    ok, err = log_event(email, "region_requested", notes=notes, **kwargs)
    if supabase is not None and email:
        try:
            supabase.table("region_requests").insert({
                "email": email,
                "requested_region": requested_region,
                "requested_city": requested_city,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "design_style": kwargs.get("design_style"),
                "notes": notes,
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
    new_user = {"email": email, "first_seen": now, "last_seen": now, "paid_status": False, "total_generations": 0, "total_exports": 0}
    created = supabase.table("users").insert(new_user).execute()
    return created.data[0] if created.data else new_user

def increment_generation_count(email):
    if supabase is None or not email:
        return 0
    result = supabase.table("users").select("total_generations").eq("email", email).execute()
    current = result.data[0].get("total_generations") if result.data else 0
    current = current or 0
    new_count = current + 1
    supabase.table("users").update({"total_generations": new_count, "last_seen": datetime.now(timezone.utc).isoformat()}).eq("email", email).execute()
    return new_count

def increment_export_count(email):
    if supabase is None or not email:
        return
    result = supabase.table("users").select("total_exports").eq("email", email).execute()
    current = result.data[0].get("total_exports") if result.data else 0
    current = current or 0
    supabase.table("users").update({"total_exports": current + 1}).eq("email", email).execute()

# -------------------------
# PAGE + EMAIL GATE
# -------------------------

st.set_page_config(page_title="YODRA Site Concepts", layout="wide")

st.markdown("""
<style>
button[kind="primary"], div.stButton > button:first-child {
    font-weight:700 !important;
}
.yodra-tip {background:#fff9db;border:1px solid #fff3bf;color:#5f4b00;padding:10px 12px;border-radius:6px;font-size:14px;line-height:1.35;margin:10px 0 14px 0;}
.yodra-card {border:1px solid #e5e7eb;border-radius:10px;padding:12px;background:#ffffff;margin-bottom:10px;}
.yodra-muted {color:#6b7280;font-size:13px;}
.yodra-section-title {font-size:20px;font-weight:700;line-height:1.25;margin:0 0 8px 0;}
.yodra-plant-name {font-size:14px;font-weight:700;margin:0 0 2px 0;}
</style>
""", unsafe_allow_html=True)

def beta_email_gate():
    if "user_email" not in st.session_state:
        st.session_state.user_email = None
    if st.session_state.user_email:
        return True
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <h1 style="margin:0;line-height:1.1;">Generate Planting Concepts in Minutes</h1>
        <span style="background:#f3f4f6;border:1px solid #e5e7eb;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;">Beta</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("Visualize spacing, explore plant combinations, and build preliminary plant palettes.")
    st.caption("California Plant Database Available • Texas and Florida Coming Soon")
    email = st.text_input("Enter your email to continue")
    if st.button("Start Designing"):
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

TUTORIAL_URL = "https://youtu.be/mOuwuhSc2Gs"

# -----------------------------
# SETTINGS
# -----------------------------

MAX_CANVAS_WIDTH = 980
MAX_CANVAS_HEIGHT = 640
DEFAULT_SITE_LENGTH_FEET = 80
DEFAULT_SITE_WIDTH_FEET = 50
MAX_SITE_FEET = 300
GRID_SPACING_FEET = 10

DENSITY_OPTIONS = {"Low": 0.25, "Moderate": 0.38, "Dense": 0.55, "Very Dense": 0.72}
SPACING_BY_DENSITY = {"Low": 1.45, "Moderate": 1.25, "Dense": 1.12, "Very Dense": 1.05}
MAX_PLANTS_BY_DENSITY = {"Low": 220, "Moderate": 350, "Dense": 500, "Very Dense": 700}

# -----------------------------
# PLANT DATABASE
# -----------------------------

def feet_to_canvas_radius(width_ft):
    return width_ft / 2

PLANTS = [
    {"name":"Carex pansa","common_name":"Sand Dune Sedge","code":"CP","state":["California"],"climate":["Coastal"],"usda_min":7,"usda_max":10,"sun":["Full Sun-Part Shade"],"water":["Moderate-Low"],"spread_ft":2,"height_ft":1,"radius":feet_to_canvas_radius(2),"form":"Grass","role":"Matrix","texture":"Fine","color_tone":"Green","visual_weight":1,"seasonality":"Evergreen","image":"plant_images/carex-pansa.webp","elevation_height":28,"hierarchy":"Groundcover","weight":5,"allows_underplanting":False},
    {"name":"Eriogonum latifolium","common_name":"Coast Buckwheat","code":"EL","state":["California"],"climate":["Coastal"],"usda_min":8,"usda_max":10,"sun":["Full Sun"],"water":["Low"],"spread_ft":2,"height_ft":2,"radius":feet_to_canvas_radius(2),"form":"Perennial","role":"Accent","texture":"Medium","color_tone":"Silver-Green","visual_weight":2,"seasonality":"Evergreen","image":"plant_images/eriogonum-latifolium.webp","elevation_height":34,"hierarchy":"Accent Layer","weight":3,"allows_underplanting":False},
    {"name":"Festuca californica","common_name":"California Fescue","code":"FC","state":["California"],"climate":["Coastal"],"usda_min":7,"usda_max":10,"sun":["Full Sun-Part Shade"],"water":["Low-Moderate"],"spread_ft":2,"height_ft":2,"radius":feet_to_canvas_radius(2),"form":"Grass","role":"Matrix","texture":"Fine","color_tone":"Blue-Green","visual_weight":1,"seasonality":"Evergreen","image":"plant_images/festuca-californica.webp","elevation_height":34,"hierarchy":"Groundcover","weight":4,"allows_underplanting":False},
    {"name":"Salvia spathacea","common_name":"Hummingbird Sage","code":"SS","state":["California"],"climate":["Coastal"],"usda_min":8,"usda_max":10,"sun":["Part Shade-Full Shade"],"water":["Moderate"],"spread_ft":4,"height_ft":2,"radius":feet_to_canvas_radius(4),"form":"Perennial","role":"Accent","texture":"Bold","color_tone":"Dark Green","visual_weight":2,"seasonality":"Evergreen","image":"plant_images/salvia-spathacea.webp","elevation_height":42,"hierarchy":"Mid Layer","weight":3,"allows_underplanting":False},
    {"name":"Iris douglasiana","common_name":"Douglas Iris","code":"ID","state":["California"],"climate":["Coastal"],"usda_min":7,"usda_max":10,"sun":["Full Sun-Part Shade"],"water":["Moderate"],"spread_ft":2,"height_ft":2,"radius":feet_to_canvas_radius(2),"form":"Perennial","role":"Accent","texture":"Medium","color_tone":"Green","visual_weight":2,"seasonality":"Evergreen","image":"plant_images/iris-douglasiana.webp","elevation_height":42,"hierarchy":"Accent Layer","weight":3,"allows_underplanting":False},
    {"name":"Arbutus menziesii","common_name":"Pacific Madrone","code":"AM","state":["California"],"climate":["Coastal","Woodland"],"usda_min":7,"usda_max":9,"sun":["Full Sun-Part Shade"],"water":["Low"],"spread_ft":20,"height_ft":40,"radius":feet_to_canvas_radius(20),"form":"Tree","role":"Canopy","texture":"Bold","color_tone":"Dark Green","visual_weight":3,"seasonality":"Evergreen","image":"plant_images/arbutus-menziesii.webp","elevation_height":135,"hierarchy":"Anchor","weight":1,"allows_underplanting":True},
    {"name":"Arctostaphylos densiflora 'Howard McMinn'","common_name":"Howard McMinn Manzanita","code":"AHM","state":["California"],"climate":["Coastal","Inland"],"usda_min":8,"usda_max":10,"sun":["Full Sun-Part Shade"],"water":["Low"],"spread_ft":8,"height_ft":7,"radius":feet_to_canvas_radius(8),"form":"Shrub","role":"Structure","texture":"Medium","color_tone":"Grey-Green","visual_weight":3,"seasonality":"Evergreen","image":"plant_images/arctostaphylos-howard-mcminn.webp","elevation_height":105,"hierarchy":"Anchor","weight":2,"allows_underplanting":True},
    {"name":"Muhlenbergia rigens","common_name":"Deergrass","code":"MR","state":["California"],"climate":["Inland"],"usda_min":7,"usda_max":10,"sun":["Full Sun"],"water":["Low"],"spread_ft":5,"height_ft":4,"radius":feet_to_canvas_radius(5),"form":"Grass","role":"Matrix","texture":"Fine","color_tone":"Green","visual_weight":2,"seasonality":"Evergreen","image":"plant_images/muhlenbergia-rigens.webp","elevation_height":58,"hierarchy":"Mid Layer","weight":4,"allows_underplanting":False},
    {"name":"Stipa pulchra","common_name":"Purple Needlegrass","code":"SP","state":["California"],"climate":["Inland"],"usda_min":7,"usda_max":10,"sun":["Full Sun"],"water":["Low"],"spread_ft":2,"height_ft":2,"radius":feet_to_canvas_radius(2),"form":"Grass","role":"Matrix","texture":"Fine","color_tone":"Golden Green","visual_weight":1,"seasonality":"Evergreen","image":"plant_images/stipa-pulchra.webp","elevation_height":34,"hierarchy":"Groundcover","weight":5,"allows_underplanting":False},
    {"name":"Juncus patens","common_name":"Common Rush","code":"JP","state":["California"],"climate":["Inland","Coastal"],"usda_min":7,"usda_max":10,"sun":["Full Sun-Part Shade"],"water":["Low-Moderate"],"spread_ft":3,"height_ft":3,"radius":feet_to_canvas_radius(3),"form":"Grass","role":"Matrix","texture":"Fine","color_tone":"Blue-Green","visual_weight":2,"seasonality":"Evergreen","image":"plant_images/juncus-patens.webp","elevation_height":46,"hierarchy":"Groundcover","weight":4,"allows_underplanting":False},
    {"name":"Eriogonum fasciculatum","common_name":"California Buckwheat","code":"EF","state":["California"],"climate":["Inland","Dry"],"usda_min":7,"usda_max":10,"sun":["Full Sun"],"water":["Low"],"spread_ft":5,"height_ft":4,"radius":feet_to_canvas_radius(5),"form":"Shrub","role":"Accent","texture":"Medium","color_tone":"Grey-Green","visual_weight":2,"seasonality":"Evergreen","image":"plant_images/eriogonum-fasciculatum.webp","elevation_height":58,"hierarchy":"Mid Layer","weight":3,"allows_underplanting":False},
    {"name":"Epilobium canum","common_name":"California Fuchsia","code":"EC","state":["California"],"climate":["Inland","Dry"],"usda_min":8,"usda_max":10,"sun":["Full Sun"],"water":["Low"],"spread_ft":3,"height_ft":2,"radius":feet_to_canvas_radius(3),"form":"Perennial","role":"Accent","texture":"Medium","color_tone":"Green","visual_weight":2,"seasonality":"Semi-evergreen","image":"plant_images/epilobium-canum.webp","elevation_height":42,"hierarchy":"Accent Layer","weight":3,"allows_underplanting":False},
    {"name":"Artemisia californica","common_name":"California Sagebrush","code":"AC","state":["California"],"climate":["Inland","Dry"],"usda_min":8,"usda_max":10,"sun":["Full Sun"],"water":["Low"],"spread_ft":5,"height_ft":4,"radius":feet_to_canvas_radius(5),"form":"Shrub","role":"Matrix","texture":"Fine","color_tone":"Silver-Grey","visual_weight":2,"seasonality":"Evergreen","image":"plant_images/artemisia-californica.webp","elevation_height":58,"hierarchy":"Mid Layer","weight":4,"allows_underplanting":False},
    {"name":"Quercus chrysolepis","common_name":"Canyon Live Oak","code":"QC","state":["California"],"climate":["Inland","Woodland"],"usda_min":7,"usda_max":10,"sun":["Full Sun-Part Shade"],"water":["Low"],"spread_ft":30,"height_ft":40,"radius":feet_to_canvas_radius(30),"form":"Tree","role":"Canopy","texture":"Bold","color_tone":"Dark Green","visual_weight":3,"seasonality":"Evergreen","image":"plant_images/quercus-chrysolepis.webp","elevation_height":135,"hierarchy":"Anchor","weight":1,"allows_underplanting":True},
    {"name":"Carex tumulicola","common_name":"Foothill Sedge","code":"CT","state":["California"],"climate":["Woodland"],"usda_min":7,"usda_max":10,"sun":["Part Shade-Full Sun"],"water":["Moderate-Low"],"spread_ft":2,"height_ft":2,"radius":feet_to_canvas_radius(2),"form":"Grass","role":"Matrix","texture":"Fine","color_tone":"Green","visual_weight":1,"seasonality":"Evergreen","image":"plant_images/carex-tumulicola.webp","elevation_height":34,"hierarchy":"Groundcover","weight":5,"allows_underplanting":False},
    {"name":"Polystichum munitum","common_name":"Western Sword Fern","code":"PM","state":["California"],"climate":["Woodland"],"usda_min":5,"usda_max":9,"sun":["Part Shade-Full Shade"],"water":["Moderate"],"spread_ft":4,"height_ft":4,"radius":feet_to_canvas_radius(4),"form":"Fern","role":"Matrix","texture":"Bold","color_tone":"Dark Green","visual_weight":2,"seasonality":"Evergreen","image":"plant_images/polystichum-munitum.webp","elevation_height":58,"hierarchy":"Mid Layer","weight":4,"allows_underplanting":False},
    {"name":"Heuchera maxima","common_name":"Island Alum Root","code":"HM","state":["California"],"climate":["Woodland"],"usda_min":8,"usda_max":10,"sun":["Part Shade"],"water":["Moderate-Low"],"spread_ft":3,"height_ft":2,"radius":feet_to_canvas_radius(3),"form":"Perennial","role":"Accent","texture":"Medium","color_tone":"Green","visual_weight":2,"seasonality":"Evergreen","image":"plant_images/heuchera-maxima.webp","elevation_height":42,"hierarchy":"Accent Layer","weight":3,"allows_underplanting":False},
    {"name":"Ribes sanguineum","common_name":"Red-Flowering Currant","code":"RS","state":["California"],"climate":["Woodland"],"usda_min":6,"usda_max":9,"sun":["Full Sun-Part Shade"],"water":["Moderate-Low"],"spread_ft":6,"height_ft":8,"radius":feet_to_canvas_radius(6),"form":"Shrub","role":"Accent","texture":"Medium","color_tone":"Green","visual_weight":2,"seasonality":"Deciduous","image":"plant_images/ribes-sanguineum.webp","elevation_height":110,"hierarchy":"Mid Layer","weight":3,"allows_underplanting":False},
    {"name":"Woodwardia fimbriata","common_name":"Giant Chain Fern","code":"WF","state":["California"],"climate":["Woodland"],"usda_min":7,"usda_max":10,"sun":["Part Shade-Full Shade"],"water":["Moderate"],"spread_ft":6,"height_ft":5,"radius":feet_to_canvas_radius(6),"form":"Fern","role":"Matrix","texture":"Bold","color_tone":"Dark Green","visual_weight":3,"seasonality":"Evergreen","image":"plant_images/woodwardia-fimbriata.webp","elevation_height":70,"hierarchy":"Mid Layer","weight":4,"allows_underplanting":False},
    {"name":"Acer circinatum","common_name":"Vine Maple","code":"ACI","state":["California"],"climate":["Woodland"],"usda_min":6,"usda_max":9,"sun":["Part Shade"],"water":["Moderate"],"spread_ft":15,"height_ft":20,"radius":feet_to_canvas_radius(15),"form":"Tree","role":"Canopy","texture":"Medium","color_tone":"Green","visual_weight":3,"seasonality":"Deciduous","image":"plant_images/acer-circinatum.webp","elevation_height":125,"hierarchy":"Anchor","weight":1,"allows_underplanting":True},
    {"name":"Heteromeles arbutifolia","common_name":"Toyon","code":"HA","state":["California"],"climate":["Woodland","Inland"],"usda_min":7,"usda_max":10,"sun":["Full Sun-Part Shade"],"water":["Low"],"spread_ft":10,"height_ft":15,"radius":feet_to_canvas_radius(10),"form":"Shrub","role":"Structure","texture":"Medium","color_tone":"Dark Green","visual_weight":3,"seasonality":"Evergreen","image":"plant_images/heteromeles-arbutifolia.webp","elevation_height":118,"hierarchy":"Anchor","weight":2,"allows_underplanting":True},
]

STYLE_FIT_BY_CODE = {
    "CP":["Wild / Naturalized","Contemporary","Meadow"],"EL":["Wild / Naturalized","Meadow","Perennial Garden","Dry Garden"],"FC":["Wild / Naturalized","Contemporary","Meadow"],"SS":["Wild / Naturalized","Perennial Garden","Woodland Garden"],"ID":["Wild / Naturalized","Meadow","Perennial Garden","Woodland Garden"],"AM":["Wild / Naturalized","Woodland Garden","Contemporary"],"AHM":["Contemporary","Wild / Naturalized","Dry Garden"],"MR":["Wild / Naturalized","Contemporary","Meadow"],"SP":["Wild / Naturalized","Meadow"],"JP":["Wild / Naturalized","Meadow","Contemporary"],"EF":["Wild / Naturalized","Meadow","Perennial Garden","Dry Garden"],"EC":["Wild / Naturalized","Meadow","Perennial Garden","Dry Garden"],"AC":["Wild / Naturalized","Dry Garden","Meadow","Contemporary"],"QC":["Wild / Naturalized","Woodland Garden"],"CT":["Wild / Naturalized","Woodland Garden","Contemporary"],"PM":["Woodland Garden","Wild / Naturalized"],"HM":["Woodland Garden","Wild / Naturalized","Perennial Garden","Contemporary"],"RS":["Woodland Garden","Wild / Naturalized"],"WF":["Woodland Garden","Wild / Naturalized"],"ACI":["Woodland Garden","Wild / Naturalized","Contemporary"],"HA":["Woodland Garden","Contemporary","Wild / Naturalized","Dry Garden"]
}

STYLE_LOGIC = {
    "Wild / Naturalized": {"species_limit":9,"spacing_multiplier":1.00,"description":"Mixed ecological planting with canopy, structure, grasses, perennials, and accents.","form_priority":[],"role_boost":{"Matrix":1.15,"Accent":1.05,"Structure":1.0,"Canopy":0.8}},
    "Contemporary": {"species_limit":5,"spacing_multiplier":1.22,"description":"Fewer species, repeated masses, cleaner spacing, and more negative space.","form_priority":["Grass","Shrub","Tree","Fern","Perennial"],"role_boost":{"Structure":1.35,"Matrix":1.25,"Canopy":1.0,"Accent":0.75}},
    "Meadow": {"species_limit":6,"spacing_multiplier":0.96,"description":"Grass-dominant field condition with limited seasonal accents.","form_priority":["Grass","Perennial","Shrub"],"role_boost":{"Matrix":1.75,"Accent":1.0,"Structure":0.35,"Canopy":0.0}},
    "Perennial Garden": {"species_limit":7,"spacing_multiplier":1.02,"description":"Flowering and textural perennial emphasis with restrained matrix plants.","form_priority":["Perennial","Grass"],"role_boost":{"Accent":1.65,"Matrix":1.0,"Structure":0.0,"Canopy":0.0}},
    "Woodland Garden": {"species_limit":7,"spacing_multiplier":1.10,"description":"Shade-tolerant canopy, shrubs, ferns, sedges, and understory pockets.","form_priority":["Tree","Shrub","Fern","Grass","Perennial"],"role_boost":{"Canopy":1.25,"Structure":1.15,"Matrix":1.25,"Accent":1.0}},
    "Dry Garden": {"species_limit":6,"spacing_multiplier":1.14,"description":"Low-water grasses, shrubs, silver textures, and open spacing.","form_priority":["Shrub","Grass","Perennial"],"role_boost":{"Structure":1.25,"Matrix":1.15,"Accent":1.0,"Canopy":0.25}},
}
DESIGN_STYLE_OPTIONS = list(STYLE_LOGIC.keys())
CONCEPT_STYLES = ["Contemporary", "Meadow", "Perennial Garden"]

ZONE_INTENTS = [
    "Foundation Planting",
    "Entry Garden",
    "Pool Planting",
    "Privacy Screen",
    "Property Buffer",
    "Pollinator Garden",
    "Meadow / Ground Plane",
    "Woodland Understory",
    "Existing Tree Root Zone / Keep-Out",
    "No Plant Zone / Keep-Out",
]

INTENT_LOGIC = {
    "Foundation Planting": {"forms":["Shrub","Grass","Perennial","Fern"],"max_height":8,"density_boost":0.95,"role_boost":{"Structure":1.2,"Matrix":1.2,"Accent":1.0,"Canopy":0.0}},
    "Entry Garden": {"forms":["Shrub","Grass","Perennial","Fern","Tree"],"max_height":15,"density_boost":1.0,"role_boost":{"Structure":1.15,"Matrix":1.0,"Accent":1.25,"Canopy":0.35}},
    "Pool Planting": {"forms":["Shrub","Grass","Perennial"],"max_height":10,"density_boost":0.9,"role_boost":{"Structure":1.25,"Matrix":1.15,"Accent":0.85,"Canopy":0.0}},
    "Privacy Screen": {"forms":["Shrub","Tree"],"max_height":40,"density_boost":0.85,"role_boost":{"Structure":1.75,"Canopy":0.75,"Matrix":0.25,"Accent":0.25}},
    "Property Buffer": {"forms":["Shrub","Tree","Grass"],"max_height":40,"density_boost":0.9,"role_boost":{"Structure":1.4,"Canopy":0.8,"Matrix":1.0,"Accent":0.4}},
    "Pollinator Garden": {"forms":["Perennial","Grass","Shrub"],"max_height":6,"density_boost":1.1,"role_boost":{"Accent":1.6,"Matrix":1.0,"Structure":0.5,"Canopy":0.0}},
    "Meadow / Ground Plane": {"forms":["Grass","Perennial"],"max_height":5,"density_boost":1.15,"role_boost":{"Matrix":1.8,"Accent":0.9,"Structure":0.0,"Canopy":0.0}},
    "Woodland Understory": {"forms":["Fern","Grass","Perennial","Shrub"],"max_height":8,"density_boost":1.05,"role_boost":{"Matrix":1.4,"Accent":1.0,"Structure":0.8,"Canopy":0.0}},
}

ROLE_ORDER = ["Canopy", "Structure", "Matrix", "Accent"]
HEIGHT_VARIATION_BY_HIERARCHY = {"Anchor":0.06,"Mid Layer":0.10,"Accent Layer":0.15,"Groundcover":0.08}

# -----------------------------
# SESSION STATE
# -----------------------------

def init_state():
    defaults = {
        "zones": [],
        "active_zone_points": [],
        "last_click": None,
        "concepts": None,
        "active_concept_index": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = deepcopy(v)

init_state()

# -----------------------------
# HELPERS
# -----------------------------

def clamp_dimension(value, fallback):
    try:
        value = float(value)
    except Exception:
        return fallback
    return max(1, min(value, MAX_SITE_FEET))

def get_canvas_setup(length_ft, width_ft):
    length_ft = clamp_dimension(length_ft, DEFAULT_SITE_LENGTH_FEET)
    width_ft = clamp_dimension(width_ft, DEFAULT_SITE_WIDTH_FEET)
    pixels_per_foot = min(MAX_CANVAS_WIDTH / length_ft, MAX_CANVAS_HEIGHT / width_ft)
    canvas_width = max(320, int(round(length_ft * pixels_per_foot)))
    canvas_height = max(280, int(round(width_ft * pixels_per_foot)))
    feet_per_canvas_unit = 1 / pixels_per_foot
    grid_spacing_units = GRID_SPACING_FEET / feet_per_canvas_unit
    return canvas_width, canvas_height, feet_per_canvas_unit, grid_spacing_units

def make_runtime_plant_pool(plants, feet_per_canvas_unit):
    out = []
    for plant in plants:
        p = plant.copy()
        p["radius"] = (p["spread_ft"] / 2) / feet_per_canvas_unit
        p["style_fit"] = STYLE_FIT_BY_CODE.get(p.get("code"), ["Wild / Naturalized"])
        out.append(p)
    return out

def uploaded_file_to_image(uploaded_file, page_number=1):
    if uploaded_file is None:
        return None
    suffix = uploaded_file.name.lower().split(".")[-1]
    data = uploaded_file.getvalue()
    if suffix == "pdf":
        if fitz is None:
            st.error("PDF support requires PyMuPDF. Add `PyMuPDF` to requirements.txt, then redeploy.")
            return None
        doc = fitz.open(stream=data, filetype="pdf")
        page_index = max(0, min(page_number - 1, len(doc) - 1))
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        return Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
    return Image.open(BytesIO(data)).convert("RGB")

def resize_image_to_canvas(image, canvas_width, canvas_height):
    if image is None:
        return None
    return image.resize((canvas_width, canvas_height)).convert("RGB")

def image_to_png_bytes(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

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

def normalize_polygon(points):
    if not points or len(points) < 3:
        return None
    poly = Polygon(points)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area <= 0:
        return None
    return poly

def circle_inside(poly, x, y, r):
    return poly.contains(Point(x, y).buffer(r))

def canvas_area_to_sqft(area_canvas_units, feet_per_canvas_unit):
    return area_canvas_units * (feet_per_canvas_unit ** 2)

def canvas_length_to_feet(length_canvas_units, feet_per_canvas_unit):
    return length_canvas_units * feet_per_canvas_unit

def sun_is_compatible(selected_sun, plant_sun_options):
    compatible = {
        "Full Sun": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun"],
        "Full Sun-Part Shade": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade", "Part Shade-Full Shade"],
        "Part Shade": ["Part Shade", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade-Full Shade"],
        "Part Shade-Full Shade": ["Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"],
    }
    return any(v in compatible.get(selected_sun, [selected_sun]) for v in plant_sun_options)

def water_is_compatible(selected_water, plant_water_options):
    compatible = {
        "Low": ["Low", "Moderate-Low", "Low-Moderate"],
        "Moderate-Low": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],
        "Low-Moderate": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],
        "Moderate": ["Moderate", "Low-Moderate", "Moderate-Low"],
    }
    return any(v in compatible.get(selected_water, [selected_water]) for v in plant_water_options)

def hardiness_is_compatible(selected_zones, usda_min, usda_max):
    if not selected_zones:
        return True
    return any(usda_min <= z <= usda_max for z in selected_zones)

def filter_plants(plant_database, state, selected_usda_zones, sun, water):
    return [p for p in plant_database if state in p["state"] and hardiness_is_compatible(selected_usda_zones, p["usda_min"], p["usda_max"]) and sun_is_compatible(sun, p["sun"]) and water_is_compatible(water, p["water"])]

def filter_plants_by_style(plant_database, design_style):
    filtered = [p for p in plant_database if design_style in p.get("style_fit", [])]
    if design_style == "Perennial Garden":
        filtered = [p for p in filtered if p.get("form") == "Perennial"]
    if design_style == "Meadow":
        filtered = [p for p in filtered if p.get("form") in ["Grass", "Perennial", "Shrub"]]
    if design_style == "Dry Garden":
        filtered = [p for p in filtered if any(w in ["Low", "Low-Moderate", "Moderate-Low"] for w in p.get("water", []))]
    return filtered

def filter_plants_by_intent(plant_database, zone_intent):
    if zone_intent in ["Existing Tree Root Zone / Keep-Out", "No Plant Zone / Keep-Out"]:
        return []
    logic = INTENT_LOGIC.get(zone_intent)
    if not logic:
        return plant_database
    forms = logic.get("forms", [])
    max_height = logic.get("max_height")
    filtered = [p for p in plant_database if (not forms or p.get("form") in forms)]
    if max_height is not None:
        filtered = [p for p in filtered if p.get("height_ft", 0) <= max_height]
    return filtered or plant_database

def style_priority_score(plant, design_style, zone_intent=None):
    settings = STYLE_LOGIC.get(design_style, STYLE_LOGIC["Wild / Naturalized"])
    intent = INTENT_LOGIC.get(zone_intent, {})
    role_boost = settings.get("role_boost", {}).get(plant.get("role"), 1.0) * intent.get("role_boost", {}).get(plant.get("role"), 1.0)
    form_priority = settings.get("form_priority", [])
    form_score = 0
    if form_priority and plant.get("form") in form_priority:
        form_score = len(form_priority) - form_priority.index(plant.get("form"))
    visual_score = float(plant.get("visual_weight", 1))
    weight_score = float(plant.get("weight", 1))
    return (visual_score * 1.5 + weight_score * 0.8 + form_score * 1.6) * role_boost

def limit_palette_by_style(plant_database, design_style, zone_intent=None):
    if not plant_database:
        return []
    species_limit = STYLE_LOGIC.get(design_style, STYLE_LOGIC["Wild / Naturalized"]).get("species_limit", 8)
    sorted_plants = sorted(plant_database, key=lambda p: -style_priority_score(p, design_style, zone_intent))
    selected = sorted_plants[:species_limit]
    if design_style == "Meadow":
        grasses = [p for p in sorted_plants if p.get("form") == "Grass"]
        min_grasses = min(len(grasses), max(2, int(round(species_limit * 0.6))))
        selected = grasses[:min_grasses]
        for p in sorted_plants:
            if p not in selected and len(selected) < species_limit:
                selected.append(p)
    return selected

def weighted_choice(plants, design_style=None, zone_intent=None):
    if not plants:
        return None
    weights = [max(0.1, style_priority_score(p, design_style or "Wild / Naturalized", zone_intent)) for p in plants]
    return random.choices(plants, weights=weights, k=1)[0]

def plant_conflict(x, y, r, plant, placed, spacing_factor, feet_per_canvas_unit, root_buffer_ft):
    for p in placed:
        existing = p["plant"]
        dist = math.dist((x, y), (p["x"], p["y"]))
        min_dist = (r + p["radius"]) * spacing_factor

        # Root-zone correction: tree/shrub anchors create a larger keep-clear buffer.
        current_is_small = plant.get("form") not in ["Tree", "Shrub"]
        existing_is_small = existing.get("form") not in ["Tree", "Shrub"]
        current_anchor = plant.get("form") in ["Tree", "Shrub"] or plant.get("allows_underplanting", False)
        existing_anchor = existing.get("form") in ["Tree", "Shrub"] or existing.get("allows_underplanting", False)

        root_buffer_units = root_buffer_ft / feet_per_canvas_unit
        if existing_anchor and current_is_small:
            min_dist = max(min_dist, p["radius"] + r + root_buffer_units)
        if current_anchor and existing_is_small:
            min_dist = max(min_dist, r + p["radius"] + root_buffer_units)

        if dist < min_dist:
            return True
    return False

def point_in_any_keepout(x, y, r, keepout_polys):
    circle = Point(x, y).buffer(r)
    return any(circle.intersects(kp) for kp in keepout_polys if kp is not None and not kp.is_empty)

def pack_zone(zone, zone_poly, plant_pool, target_coverage, spacing_factor, max_plants_total, existing_locked, keepout_polys, design_style, feet_per_canvas_unit, root_buffer_ft):
    if zone["intent"] in ["Existing Tree Root Zone / Keep-Out", "No Plant Zone / Keep-Out"]:
        return [], 0
    plants = filter_plants_by_style(plant_pool, design_style)
    plants = filter_plants_by_intent(plants, zone["intent"])
    plants = limit_palette_by_style(plants, design_style, zone["intent"])
    if not plants:
        return [], 0

    minx, miny, maxx, maxy = zone_poly.bounds
    zone_target = zone_poly.area * target_coverage * INTENT_LOGIC.get(zone["intent"], {}).get("density_boost", 1.0)
    placed = []
    placed_area = 0
    attempts = 0
    max_attempts = 18000
    all_existing = list(existing_locked)

    while placed_area < zone_target and attempts < max_attempts and len(placed) < max_plants_total:
        attempts += 1
        plant = weighted_choice(plants, design_style, zone["intent"])
        if plant is None:
            break
        r = plant["radius"]
        if maxx - minx < r * 2 or maxy - miny < r * 2:
            continue
        x = random.uniform(minx + r, maxx - r)
        y = random.uniform(miny + r, maxy - r)
        if not circle_inside(zone_poly, x, y, r):
            continue
        if point_in_any_keepout(x, y, r, keepout_polys):
            continue
        if plant_conflict(x, y, r, plant, all_existing + placed, spacing_factor, feet_per_canvas_unit, root_buffer_ft):
            continue
        item = {
            "id": f"{zone['id']}-{len(placed)+1:03d}",
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "zone_intent": zone["intent"],
            "x": x,
            "y": y,
            "radius": r,
            "plant": plant,
            "locked": False,
            "deleted": False,
        }
        placed.append(item)
        placed_area += math.pi * (r ** 2)
    return placed, placed_area / zone_poly.area if zone_poly.area > 0 else 0

def generate_concept(zones, plant_pool, style, target_coverage, spacing_factor, max_plants_total, feet_per_canvas_unit, root_buffer_ft, locked_items=None):
    locked_items = locked_items or []
    keepout_polys = []
    plant_zones = []
    for z in zones:
        poly = normalize_polygon(z["points"])
        if poly is None:
            continue
        if z["intent"] in ["Existing Tree Root Zone / Keep-Out", "No Plant Zone / Keep-Out"]:
            keepout_polys.append(poly)
        else:
            plant_zones.append((z, poly))

    placed = [deepcopy(p) for p in locked_items if not p.get("deleted", False)]
    coverage_by_zone = {}
    max_per_zone = max(12, int(max_plants_total / max(1, len(plant_zones))))
    for zone, poly in plant_zones:
        zone_locked = [p for p in placed if p.get("zone_id") == zone["id"]]
        new_items, coverage = pack_zone(zone, poly, plant_pool, target_coverage, spacing_factor, max_per_zone, placed, keepout_polys, style, feet_per_canvas_unit, root_buffer_ft)
        placed.extend(new_items)
        coverage_by_zone[zone["name"]] = coverage

    return {
        "style": style,
        "items": placed,
        "coverage_by_zone": coverage_by_zone,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

def render_site_overlay(image, zones, active_points, canvas_width, canvas_height):
    if image is None:
        base = Image.new("RGB", (canvas_width, canvas_height), "#f7f7f2")
    else:
        base = image.copy().convert("RGB").resize((canvas_width, canvas_height))
    draw = ImageDraw.Draw(base)

    colors = {
        "Foundation Planting": (46, 125, 50),
        "Entry Garden": (25, 118, 210),
        "Pool Planting": (0, 121, 107),
        "Privacy Screen": (85, 139, 47),
        "Property Buffer": (124, 179, 66),
        "Pollinator Garden": (171, 71, 188),
        "Meadow / Ground Plane": (251, 140, 0),
        "Woodland Understory": (93, 64, 55),
        "Existing Tree Root Zone / Keep-Out": (198, 40, 40),
        "No Plant Zone / Keep-Out": (198, 40, 40),
    }
    for idx, z in enumerate(zones):
        pts = z.get("points", [])
        if len(pts) >= 2:
            c = colors.get(z.get("intent"), (0, 0, 0))
            closed = pts + [pts[0]] if len(pts) >= 3 else pts
            draw.line(closed, fill=c, width=4)
            for x, y in pts:
                draw.ellipse((x-4, y-4, x+4, y+4), fill=c, outline=(255,255,255), width=1)
            label = f"{z.get('name','Zone')} • {z.get('intent','')}"
            draw.text((pts[0][0] + 8, pts[0][1] + 8), label, fill=c)

    if len(active_points) >= 2:
        draw.line(active_points, fill=(255,255,255), width=3)
        if len(active_points) >= 3:
            draw.line([active_points[-1], active_points[0]], fill=(255,255,255), width=2)
    for idx, (x, y) in enumerate(active_points):
        draw.ellipse((x-5, y-5, x+5, y+5), fill=(255, 80, 80), outline=(255,255,255), width=2)
        draw.text((x+7, y-7), str(idx+1), fill=(255,255,255))
    return base

def draw_grid(ax, canvas_width, canvas_height, grid_spacing_units):
    x = 0
    while x <= canvas_width:
        ax.axvline(x, linewidth=0.4, alpha=0.2, zorder=1)
        x += grid_spacing_units
    y = 0
    while y <= canvas_height:
        ax.axhline(y, linewidth=0.4, alpha=0.2, zorder=1)
        y += grid_spacing_units

def render_plan(concept, zones, background_image, canvas_width, canvas_height, grid_spacing_units):
    fig, ax = plt.subplots(figsize=(12, 8))
    if background_image is not None:
        ax.imshow(background_image, extent=(0, canvas_width, canvas_height, 0), alpha=0.35, zorder=0)
    else:
        ax.set_facecolor("#f7f7f2")
    draw_grid(ax, canvas_width, canvas_height, grid_spacing_units)

    for z in zones:
        pts = z.get("points", [])
        if len(pts) >= 3:
            xs, ys = zip(*(pts + [pts[0]]))
            linestyle = "--" if z["intent"] in ["Existing Tree Root Zone / Keep-Out", "No Plant Zone / Keep-Out"] else "-"
            ax.plot(xs, ys, linewidth=2, linestyle=linestyle, zorder=3)
            ax.text(pts[0][0], pts[0][1], z["name"], fontsize=8, zorder=5)

    for item in concept["items"]:
        if item.get("deleted", False):
            continue
        plant = item["plant"]
        circle = plt.Circle((item["x"], item["y"]), item["radius"], fill=False, linewidth=1.4 if item.get("locked") else 1.0, linestyle="--" if plant.get("form") in ["Tree", "Shrub"] else "-", zorder=4)
        ax.add_patch(circle)
        label = plant["code"] + ("🔒" if item.get("locked") else "")
        ax.text(item["x"], item["y"], label, ha="center", va="center", fontsize=7, fontweight="bold" if item.get("locked") else "normal", zorder=5)

    ax.set_xlim(0, canvas_width)
    ax.set_ylim(canvas_height, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig

def get_image_aspect_ratio(image_path):
    try:
        img = plt.imread(image_path)
        h, w = img.shape[:2]
        return w / h if h else 1
    except Exception:
        return 1

def varied_height(plant):
    tol = HEIGHT_VARIATION_BY_HIERARCHY.get(plant.get("hierarchy"), 0.08)
    return plant.get("elevation_height", 40) * random.uniform(1 - tol, 1 + tol)

def render_elevation(concept, canvas_width):
    fig, ax = plt.subplots(figsize=(12, 4))
    placed = sorted([p for p in concept["items"] if not p.get("deleted", False)], key=lambda item: item["x"])
    for item in placed:
        plant = item["plant"]
        height = varied_height(plant)
        aspect = get_image_aspect_ratio(plant.get("image", ""))
        width = height * aspect
        image_path = plant.get("image", "")
        if os.path.exists(image_path):
            img = plt.imread(image_path)
            ax.imshow(img, extent=(item["x"] - width / 2, item["x"] + width / 2, 0, height), zorder=2)
        else:
            ax.text(item["x"], height / 2, plant["code"], ha="center", va="center", fontsize=8)
    ax.axhline(0, linewidth=1)
    ax.set_xlim(0, canvas_width)
    ax.set_ylim(0, 150)
    ax.axis("off")
    return fig

def escape_svg_text(value):
    return html.escape(str(value), quote=True)

def plan_to_svg(concept, zones, canvas_width, canvas_height, feet_per_canvas_unit):
    svg = StringIO()
    svg.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}">\n')
    svg.write('<rect width="100%" height="100%" fill="white"/>\n')
    for z in zones:
        pts = z.get("points", [])
        if len(pts) < 3:
            continue
        path = " ".join([f"{x:.2f},{y:.2f}" for x, y in pts])
        dash = ' stroke-dasharray="6 4"' if z["intent"] in ["Existing Tree Root Zone / Keep-Out", "No Plant Zone / Keep-Out"] else ""
        svg.write(f'<polygon points="{path}" fill="none" stroke="black" stroke-width="1.5"{dash}/>\n')
        svg.write(f'<text x="{pts[0][0]:.2f}" y="{pts[0][1]:.2f}" font-family="Arial" font-size="10">{escape_svg_text(z["name"])} - {escape_svg_text(z["intent"])}</text>\n')
    for item in concept["items"]:
        if item.get("deleted", False):
            continue
        plant = item["plant"]
        dash = ' stroke-dasharray="6 4"' if plant.get("form") in ["Tree", "Shrub"] else ""
        svg.write(f'<circle cx="{item["x"]:.2f}" cy="{item["y"]:.2f}" r="{item["radius"]:.2f}" fill="none" stroke="black" stroke-width="1.2"{dash}/>\n')
        svg.write(f'<text x="{item["x"]:.2f}" y="{item["y"]:.2f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="8">{escape_svg_text(plant["code"])}</text>\n')
    svg.write(f'<text x="12" y="{canvas_height - 14}" font-family="Arial" font-size="10">Scale: 1 px = {feet_per_canvas_unit:.3f} ft</text>\n')
    svg.write('</svg>')
    return BytesIO(svg.getvalue().encode("utf-8"))

def plan_to_dxf(concept, zones, feet_per_canvas_unit):
    dxf = StringIO()
    dxf.write("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n2\n0\nENDSEC\n")
    dxf.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n")
    for z in zones:
        pts = z.get("points", [])
        if len(pts) < 3:
            continue
        layer = "KEEP_OUT" if z["intent"] in ["Existing Tree Root Zone / Keep-Out", "No Plant Zone / Keep-Out"] else "PLANTING_ZONE"
        closed = pts + [pts[0]]
        for i in range(len(closed) - 1):
            x1, y1 = closed[i]
            x2, y2 = closed[i+1]
            dxf.write(f"0\nLINE\n8\n{layer}\n10\n{x1 * feet_per_canvas_unit:.4f}\n20\n{y1 * feet_per_canvas_unit:.4f}\n30\n0\n11\n{x2 * feet_per_canvas_unit:.4f}\n21\n{y2 * feet_per_canvas_unit:.4f}\n31\n0\n")
    for item in concept["items"]:
        if item.get("deleted", False):
            continue
        plant = item["plant"]
        dxf.write("0\nCIRCLE\n8\nPLANTS\n")
        dxf.write(f"10\n{item['x'] * feet_per_canvas_unit:.4f}\n20\n{item['y'] * feet_per_canvas_unit:.4f}\n30\n0\n40\n{item['radius'] * feet_per_canvas_unit:.4f}\n")
        dxf.write("0\nTEXT\n8\nPLANT_CODES\n")
        dxf.write(f"10\n{item['x'] * feet_per_canvas_unit:.4f}\n20\n{item['y'] * feet_per_canvas_unit:.4f}\n30\n0\n40\n0.35\n1\n{plant['code']}\n")
    dxf.write("0\nENDSEC\n0\nEOF\n")
    return BytesIO(dxf.getvalue().encode("utf-8"))

def schedule_dataframe(concept, state):
    counts = {}
    for item in concept["items"]:
        if item.get("deleted", False):
            continue
        plant = item["plant"]
        counts[plant["name"]] = counts.get(plant["name"], 0) + 1
    rows = []
    for plant_name, count in counts.items():
        plant = next(p for p in PLANTS if p["name"] == plant_name)
        rows.append({
            "Code": plant["code"], "Count": count, "Botanical Name": plant["name"], "Common Name": plant["common_name"],
            "Form": plant["form"], "Role": plant["role"], "Spread Ft": plant["spread_ft"], "Height Ft": plant["height_ft"],
            "Plant Region": state, "Sun": ", ".join(plant["sun"]), "Water": ", ".join(plant["water"]), "Seasonality": plant["seasonality"]
        })
    return pd.DataFrame(rows)

def editable_items_dataframe(concept, feet_per_canvas_unit):
    rows = []
    for item in concept["items"]:
        plant = item["plant"]
        rows.append({
            "id": item["id"],
            "Zone": item.get("zone_name"),
            "Intent": item.get("zone_intent"),
            "Code": plant["code"],
            "Botanical Name": plant["name"],
            "X Ft": round(item["x"] * feet_per_canvas_unit, 2),
            "Y Ft": round(item["y"] * feet_per_canvas_unit, 2),
            "Locked": bool(item.get("locked", False)),
            "Delete": bool(item.get("deleted", False)),
        })
    return pd.DataFrame(rows)

def apply_edit_dataframe(concept, edited_df, runtime_plants, feet_per_canvas_unit):
    plant_by_name = {p["name"]: p for p in runtime_plants}
    by_id = {item["id"]: item for item in concept["items"]}
    for _, row in edited_df.iterrows():
        item_id = row.get("id")
        if item_id not in by_id:
            continue
        item = by_id[item_id]
        if row.get("Botanical Name") in plant_by_name:
            item["plant"] = plant_by_name[row.get("Botanical Name")]
            item["radius"] = item["plant"]["radius"]
        try:
            item["x"] = float(row.get("X Ft")) / feet_per_canvas_unit
            item["y"] = float(row.get("Y Ft")) / feet_per_canvas_unit
        except Exception:
            pass
        item["locked"] = bool(row.get("Locked"))
        item["deleted"] = bool(row.get("Delete"))
    return concept

# -----------------------------
# SIDEBAR
# -----------------------------

with st.sidebar:
    st.markdown("### by The Landscape Library")
    st.markdown("**YODRA Site Concept Generator**")
    st.caption("Upload a full site plan, draw multiple planting zones, generate 3 concepts, edit, lock, regenerate, and export.")

    st.divider()
    generate = st.button("Generate 3 Site Concepts", use_container_width=True, type="primary")

    st.header("Site Plan Upload")
    uploaded_site = st.file_uploader("Upload site plan", type=["pdf", "jpg", "jpeg", "png"])
    pdf_page = 1
    if uploaded_site is not None and uploaded_site.name.lower().endswith(".pdf"):
        pdf_page = st.number_input("PDF page", min_value=1, value=1, step=1)

    site_length_ft = st.number_input("Site horizontal dimension (ft)", min_value=1.0, max_value=float(MAX_SITE_FEET), value=float(DEFAULT_SITE_LENGTH_FEET), step=1.0)
    site_width_ft = st.number_input("Site vertical dimension (ft)", min_value=1.0, max_value=float(MAX_SITE_FEET), value=float(DEFAULT_SITE_WIDTH_FEET), step=1.0)

    canvas_width, canvas_height, feet_per_canvas_unit, grid_spacing_units = get_canvas_setup(site_length_ft, site_width_ft)

    st.header("Site Parameters")
    state = st.selectbox("Plant Region", ["California"])
    usda_zone_options = list(range(5, 11))
    selected_usda_zones = []
    zone_cols = st.columns(3)
    for idx, zone in enumerate(usda_zone_options):
        with zone_cols[idx % 3]:
            if st.checkbox(f"Zone {zone}", value=(zone == 9), key=f"usda_zone_{zone}"):
                selected_usda_zones.append(zone)

    sun = st.selectbox("Sun Exposure", ["Full Sun", "Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"])
    water = st.selectbox("Water Needs", ["Low", "Moderate-Low", "Low-Moderate", "Moderate"])
    density = st.selectbox("Coverage Density", ["Low", "Moderate", "Dense", "Very Dense"], index=1)
    root_buffer_ft = st.slider("Tree/shrub root-zone clearance", min_value=0.0, max_value=10.0, value=4.0, step=0.5)

    target_coverage = DENSITY_OPTIONS[density]
    base_spacing_factor = SPACING_BY_DENSITY[density]
    max_plants_total = MAX_PLANTS_BY_DENSITY[density]

    st.header("Plant Controls")
    runtime_plants = make_runtime_plant_pool(PLANTS, feet_per_canvas_unit)
    filtered_base = filter_plants(runtime_plants, state, selected_usda_zones, sun, water)
    include_names = st.multiselect("Force include plants", [p["name"] for p in runtime_plants])
    exclude_names = st.multiselect("Exclude plants", [p["name"] for p in filtered_base])

    filtered_base = [p for p in filtered_base if p["name"] not in exclude_names]
    for p in runtime_plants:
        if p["name"] in include_names and p["name"] not in [x["name"] for x in filtered_base]:
            filtered_base.append(p)

    st.divider()
    feedback_text = st.text_area("Feedback", placeholder="Share what worked, what felt confusing, or what you want improved.", height=90)
    if st.button("Submit Feedback", use_container_width=True):
        if feedback_text.strip():
            ok, err = log_event(st.session_state.get("user_email"), "feedback_submitted", sun_exposure=sun, water_needs=water, notes=feedback_text.strip())
            st.success("Feedback submitted.") if ok else st.error(f"Feedback was not saved: {err}")
        else:
            st.warning("Enter feedback before submitting.")

# -----------------------------
# ACTIVE IMAGE
# -----------------------------

site_image_raw = uploaded_file_to_image(uploaded_site, int(pdf_page)) if uploaded_site is not None else None
site_image = resize_image_to_canvas(site_image_raw, canvas_width, canvas_height) if site_image_raw is not None else None

# -----------------------------
# MAIN UI
# -----------------------------

left, right = st.columns([2.2, 1])

with left:
    st.subheader("1. Upload Full Site Plan + Draw Planting Zones")
    st.link_button("Watch Tutorial Here →", TUTORIAL_URL)
    st.markdown("""
    <div class="yodra-tip">
        <strong>TIP:</strong> Upload a PDF, JPEG, or PNG site plan. Click around each planting area, assign a zoning design intent, then save the zone. Add keep-out/root-zone areas where YODRA should not place plants.
    </div>
    """, unsafe_allow_html=True)

    if streamlit_image_coordinates is None:
        st.error("Missing package: streamlit-image-coordinates. Add `streamlit-image-coordinates` to requirements.txt.")
    else:
        overlay = render_site_overlay(site_image, st.session_state.zones, st.session_state.active_zone_points, canvas_width, canvas_height)
        clicked = streamlit_image_coordinates(overlay, key=f"site_click_{uploaded_site.name if uploaded_site else 'blank'}_{canvas_width}_{canvas_height}", width=canvas_width)
        if clicked is not None and "x" in clicked and "y" in clicked:
            new_point = (int(clicked["x"]), int(clicked["y"]))
            if st.session_state.last_click != new_point:
                if len(st.session_state.active_zone_points) == 0 or math.dist(st.session_state.active_zone_points[-1], new_point) > 4:
                    st.session_state.active_zone_points.append(new_point)
                st.session_state.last_click = new_point
                st.rerun()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        zone_name = st.text_input("Zone name", value=f"Zone {len(st.session_state.zones) + 1}")
    with c2:
        zone_intent = st.selectbox("Zoning design intent", ZONE_INTENTS)
    with c3:
        if st.button("Save Zone"):
            if len(st.session_state.active_zone_points) < 3:
                st.warning("Add at least 3 points before saving a zone.")
            else:
                st.session_state.zones.append({
                    "id": f"zone_{len(st.session_state.zones) + 1:02d}",
                    "name": zone_name.strip() or f"Zone {len(st.session_state.zones) + 1}",
                    "intent": zone_intent,
                    "points": list(st.session_state.active_zone_points),
                })
                st.session_state.active_zone_points = []
                st.session_state.last_click = None
                st.session_state.concepts = None
                st.rerun()
    with c4:
        if st.button("Undo Point") and st.session_state.active_zone_points:
            st.session_state.active_zone_points = st.session_state.active_zone_points[:-1]
            st.session_state.last_click = None
            st.rerun()

    z1, z2, z3 = st.columns(3)
    with z1:
        if st.button("Clear Active Zone"):
            st.session_state.active_zone_points = []
            st.session_state.last_click = None
            st.rerun()
    with z2:
        if st.button("Remove Last Saved Zone") and st.session_state.zones:
            st.session_state.zones = st.session_state.zones[:-1]
            st.session_state.concepts = None
            st.rerun()
    with z3:
        if st.button("Clear All Zones"):
            st.session_state.zones = []
            st.session_state.active_zone_points = []
            st.session_state.last_click = None
            st.session_state.concepts = None
            st.rerun()

    if st.session_state.zones:
        st.subheader("Saved Zones")
        zones_df = pd.DataFrame([{"Zone": z["name"], "Intent": z["intent"], "Points": len(z["points"]), "Approx. SF": round(canvas_area_to_sqft(normalize_polygon(z["points"]).area, feet_per_canvas_unit)) if normalize_polygon(z["points"]) else 0} for z in st.session_state.zones])
        st.dataframe(zones_df, width="stretch", hide_index=True)

with right:
    st.markdown("<div class='yodra-section-title'>Selected Plant Palette</div>", unsafe_allow_html=True)
    if not filtered_base:
        st.warning("No plants match these parameters yet.")
    else:
        for plant in filtered_base:
            st.markdown(f"<div class='yodra-plant-name'>{plant['name']}</div>", unsafe_allow_html=True)
            st.caption(f"{plant['code']} | {plant['common_name']} | {plant['form']} | {plant['role']} | spread: {plant['spread_ft']} ft")

    st.divider()
    st.markdown("<div class='yodra-section-title'>Don't See Your Region?</div>", unsafe_allow_html=True)
    requested_region = st.text_input("Region", placeholder="Example: Texas, Florida, Pacific Northwest")
    requested_city = st.text_input("City", placeholder="Example: Austin")
    if st.button("Submit Region Request"):
        if requested_region.strip() and requested_city.strip():
            ok, err = log_region_request(st.session_state.get("user_email"), requested_region, requested_city, design_style="Site Concepts")
            st.success("Region request submitted.") if ok else st.error(f"Region request was not saved: {err}")
        else:
            st.warning("Enter both a region and city.")

# -----------------------------
# GENERATE 3 CONCEPTS
# -----------------------------

if generate:
    if supabase is not None and st.session_state.get("user_email"):
        user_check = supabase.table("users").select("*").eq("email", st.session_state.user_email).execute()
        current_user = user_check.data[0] if user_check.data else {}
        if not current_user.get("paid_status", False) and (current_user.get("total_generations") or 0) >= FREE_GENERATION_LIMIT:
            st.warning("You have reached the free generation limit.")
            log_event(st.session_state.user_email, "paywall_shown")
            st.stop()

    if not st.session_state.zones:
        st.warning("Save at least one planting zone before generating concepts.")
    elif not filtered_base:
        st.warning("No plants are available for the selected parameters.")
    else:
        with st.spinner("Generating 3 site concepts with plan and elevation views..."):
            random.seed()
            concepts = []
            for style in CONCEPT_STYLES:
                spacing = base_spacing_factor * STYLE_LOGIC[style]["spacing_multiplier"]
                concepts.append(generate_concept(
                    zones=st.session_state.zones,
                    plant_pool=filtered_base,
                    style=style,
                    target_coverage=target_coverage,
                    spacing_factor=spacing,
                    max_plants_total=max_plants_total,
                    feet_per_canvas_unit=feet_per_canvas_unit,
                    root_buffer_ft=root_buffer_ft,
                    locked_items=[]
                ))
            st.session_state.concepts = concepts
            increment_generation_count(st.session_state.get("user_email"))
            log_event(st.session_state.get("user_email"), "three_concepts_generated", sun_exposure=sun, water_needs=water, design_style=", ".join(CONCEPT_STYLES), notes=f"Zones: {len(st.session_state.zones)}; Density: {density}")
            st.rerun()

# -----------------------------
# CONCEPT RESULTS + EDITING
# -----------------------------

if st.session_state.concepts:
    st.subheader("2. Compare 3 Concepts")
    tabs = st.tabs([f"Concept {i+1}: {c['style']}" for i, c in enumerate(st.session_state.concepts)])

    for idx, tab in enumerate(tabs):
        with tab:
            concept = st.session_state.concepts[idx]
            st.markdown(f"### {concept['style']}")
            st.caption(STYLE_LOGIC[concept["style"]]["description"])

            pcol, ecol = st.columns([1.4, 1])
            with pcol:
                st.markdown("**Plan View**")
                plan_fig = render_plan(concept, st.session_state.zones, site_image, canvas_width, canvas_height, grid_spacing_units)
                st.pyplot(plan_fig)
            with ecol:
                st.markdown("**Elevation View**")
                elev_fig = render_elevation(concept, canvas_width)
                st.pyplot(elev_fig)

            st.markdown("### 3. Adjust, Delete, Lock Plants")
            st.caption("Edit X/Y feet, change species, check Locked, or mark Delete. Locked plants stay fixed when regenerating alternatives.")
            editable_df = editable_items_dataframe(concept, feet_per_canvas_unit)
            plant_names = [p["name"] for p in runtime_plants]
            edited_df = st.data_editor(
                editable_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "id": st.column_config.TextColumn("ID", disabled=True),
                    "Zone": st.column_config.TextColumn("Zone", disabled=True),
                    "Intent": st.column_config.TextColumn("Intent", disabled=True),
                    "Code": st.column_config.TextColumn("Code", disabled=True),
                    "Botanical Name": st.column_config.SelectboxColumn("Botanical Name", options=plant_names),
                    "X Ft": st.column_config.NumberColumn("X Ft", step=0.5),
                    "Y Ft": st.column_config.NumberColumn("Y Ft", step=0.5),
                    "Locked": st.column_config.CheckboxColumn("Locked"),
                    "Delete": st.column_config.CheckboxColumn("Delete"),
                },
                key=f"edit_concept_{idx}"
            )

            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("Apply Edits", key=f"apply_edits_{idx}"):
                    st.session_state.concepts[idx] = apply_edit_dataframe(concept, edited_df, runtime_plants, feet_per_canvas_unit)
                    st.success("Edits applied.")
                    st.rerun()
            with b2:
                if st.button("Regenerate Around Locked Plants", key=f"regen_locked_{idx}"):
                    updated = apply_edit_dataframe(concept, edited_df, runtime_plants, feet_per_canvas_unit)
                    locked = [deepcopy(p) for p in updated["items"] if p.get("locked", False) and not p.get("deleted", False)]
                    spacing = base_spacing_factor * STYLE_LOGIC[updated["style"]]["spacing_multiplier"]
                    st.session_state.concepts[idx] = generate_concept(
                        zones=st.session_state.zones,
                        plant_pool=filtered_base,
                        style=updated["style"],
                        target_coverage=target_coverage,
                        spacing_factor=spacing,
                        max_plants_total=max_plants_total,
                        feet_per_canvas_unit=feet_per_canvas_unit,
                        root_buffer_ft=root_buffer_ft,
                        locked_items=locked,
                    )
                    st.success("Alternative regenerated around locked plants.")
                    st.rerun()
            with b3:
                if st.button("Use This Concept For Export", key=f"use_concept_{idx}"):
                    st.session_state.active_concept_index = idx
                    st.success(f"Concept {idx+1} selected for export.")

            st.markdown("### Plant Schedule")
            schedule_df = schedule_dataframe(concept, state)
            st.dataframe(schedule_df, width="stretch", hide_index=True)

    st.subheader("4. Export Selected Concept")
    export_concept = st.session_state.concepts[st.session_state.active_concept_index]
    st.caption(f"Selected export: Concept {st.session_state.active_concept_index + 1} — {export_concept['style']}")
    export_plan_fig = render_plan(export_concept, st.session_state.zones, site_image, canvas_width, canvas_height, grid_spacing_units)
    export_elev_fig = render_elevation(export_concept, canvas_width)
    export_schedule = schedule_dataframe(export_concept, state)

    exp1, exp2, exp3, exp4, exp5 = st.columns(5)
    with exp1:
        st.download_button("Download Plan PNG", data=fig_to_png_bytes(export_plan_fig), file_name="yodra-site-plan.png", mime="image/png", on_click=lambda: increment_export_count(st.session_state.get("user_email")))
    with exp2:
        st.download_button("Download Plan SVG", data=plan_to_svg(export_concept, st.session_state.zones, canvas_width, canvas_height, feet_per_canvas_unit), file_name="yodra-site-plan.svg", mime="image/svg+xml", on_click=lambda: increment_export_count(st.session_state.get("user_email")))
    with exp3:
        st.download_button("Download Plan DXF", data=plan_to_dxf(export_concept, st.session_state.zones, feet_per_canvas_unit), file_name="yodra-site-plan.dxf", mime="application/dxf", on_click=lambda: increment_export_count(st.session_state.get("user_email")))
    with exp4:
        st.download_button("Download Elevation JPEG", data=fig_to_jpeg_bytes(export_elev_fig), file_name="yodra-site-elevation.jpg", mime="image/jpeg", on_click=lambda: increment_export_count(st.session_state.get("user_email")))
    with exp5:
        st.download_button("Download Schedule CSV", data=export_schedule.to_csv(index=False).encode("utf-8"), file_name="yodra-plant-schedule.csv", mime="text/csv", on_click=lambda: increment_export_count(st.session_state.get("user_email")))

else:
    st.info("Generate 3 concepts after saving at least one planting zone.")
