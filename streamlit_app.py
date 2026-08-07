


import streamlit as st

from datetime import datetime, timezone

try:

    from supabase import create\_client

except Exception:

    create\_client = None

import pandas as pd



\# -------------------------

\# SUPABASE USER TRACKING

\# -------------------------



FREE\_GENERATION\_LIMIT = 999



def get\_supabase\_client():

    if create\_client is None:

        return None

    url = st.secrets.get("SUPABASE\_URL", "")

    key = st.secrets.get("SUPABASE\_SERVICE\_ROLE\_KEY", "")

    if not url or not key:

        return None

    return create\_client(url, key)



supabase = get\_supabase\_client()



def log\_event(email, event\_type, \*\*kwargs):

    """Insert an event using only the columns that exist in the current Supabase events table.



    Current expected columns:

    email, event\_type, created\_at, climate, sun\_exposure, water\_needs,

    design\_style, export\_type, notes.



    Do not add state, zone, density, or plants\_generated\_count unless those columns

    are also added to Supabase. Supabase will reject inserts when unknown columns

    are included.

    """

    if supabase is None or not email:

        return False, "Supabase is not connected or user email is missing."



    event = {

        "email": email,

        "event\_type": event\_type,

        "created\_at": datetime.now(timezone.utc).isoformat(),

        "climate": kwargs.get("climate"),

        "sun\_exposure": kwargs.get("sun\_exposure"),

        "water\_needs": kwargs.get("water\_needs"),

        "design\_style": kwargs.get("design\_style"),

        "export\_type": kwargs.get("export\_type"),

        "notes": kwargs.get("notes"),

    }



    # Remove empty optional fields so Supabase receives a clean payload.

    event = {k: v for k, v in event.items() if v is not None}



    try:

        supabase.table("events").insert(event).execute()

        return True, None

    except Exception as e:

        return False, str(e)





def log\_plant\_request(email, requested\_plant, \*\*kwargs):

    requested\_plant = (requested\_plant or "").strip()

    if not requested\_plant:

        return False, "Plant request is empty."



    ok, err = log\_event(

        email,

        "plant\_requested",

        notes=requested\_plant,

        \*\*kwargs

    )



    # Optional dedicated table. If you create a plant\_requests table in Supabase,

    # this will also save requests there. If that table does not exist, the

    # events table above is still the primary tracking location.

    if supabase is not None and email:

        try:

            supabase.table("plant\_requests").insert({

                "email": email,

                "requested\_plant": requested\_plant,

                "created\_at": datetime.now(timezone.utc).isoformat(),

                "climate": kwargs.get("climate"),

                "sun\_exposure": kwargs.get("sun\_exposure"),

                "water\_needs": kwargs.get("water\_needs"),

                "notes": requested\_plant,

            }).execute()

        except Exception:

            pass



    return ok, err



def get\_or\_create\_user(email):

    email = email.strip().lower()

    if supabase is None:

        return {"email": email, "paid\_status": False, "total\_generations": 0, "total\_exports": 0}



    now = datetime.now(timezone.utc).isoformat()

    result = supabase.table("users").select("\*").eq("email", email).execute()

    if result.data:

        user = result.data[0]

        supabase.table("users").update({"last\_seen": now}).eq("email", email).execute()

        return user



    new\_user = {

        "email": email,

        "first\_seen": now,

        "last\_seen": now,

        "paid\_status": False,

        "total\_generations": 0,

        "total\_exports": 0,

    }

    created = supabase.table("users").insert(new\_user).execute()

    return created.data[0] if created.data else new\_user



def increment\_generation\_count(email):

    if supabase is None:

        return 0

    result = supabase.table("users").select("total\_generations").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_generations") or 0

    new\_count = current + 1

    supabase.table("users").update({

        "total\_generations": new\_count,

        "last\_seen": datetime.now(timezone.utc).isoformat()

    }).eq("email", email).execute()

    return new\_count



def increment\_export\_count(email):

    if supabase is None:

        return

    result = supabase.table("users").select("total\_exports").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_exports") or 0

    supabase.table("users").update({"total\_exports": current + 1}).eq("email", email).execute()



def beta\_email\_gate():

    if "user\_email" not in st.session\_state:

        st.session\_state.user\_email = None

    if st.session\_state.user\_email:

        return True



    st.title("Native Plant Layout Engine by The Landscape Library")

    st.markdown("### Enter your email to begin generating planting layouts.")

    email = st.text\_input("Enter your email to continue")

    if st.button("Continue"):

        if "@" not in email or "." not in email:

            st.error("Please enter a valid email address.")

            st.stop()

        user = get\_or\_create\_user(email)

        st.session\_state.user\_email = user["email"]

        st.session\_state.user\_data = user

        log\_event(user["email"], "app\_opened")

        st.rerun()

    st.stop()



beta\_email\_gate()





\# -------------------------

\# YOUR APP BELOW

\# -------------------------



import random

import math

import os

import html

import base64

from io import BytesIO, StringIO



import matplotlib.pyplot as plt

from PIL import Image, ImageDraw

from shapely.geometry import Polygon, Point

from streamlit\_drawable\_canvas import st\_canvas

try:

    from streamlit\_image\_coordinates import streamlit\_image\_coordinates

except Exception:

    streamlit\_image\_coordinates = None



\# -----------------------------

\# Compatibility patch

\# -----------------------------

\# streamlit-drawable-canvas still calls an older Streamlit helper named

\# st.image.image\_to\_url when using background\_image. Newer Streamlit versions

\# removed that helper, which causes an AttributeError on image upload.

\# This patch restores the expected helper by converting the PIL background image

\# into a browser-safe base64 data URL.

def \_yodra\_image\_to\_url(image, width=None, clamp=False, channels="RGB", output\_format="PNG", image\_id=None):

    """Compatibility helper for streamlit-drawable-canvas background images.



    Newer Streamlit versions removed st.image.image\_to\_url, but

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

    return f"data\:image/png;base64,{encoded}"



try:

    # This is the exact object streamlit-drawable-canvas references: st.image.image\_to\_url

    st.image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



try:

    # Also patch Streamlit's image module for environments that reference it directly.

    import streamlit.elements.image as st\_image

    st\_image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



st.set\_page\_config(

    page\_title="Native Plant Layout Engine",

    layout="wide"

)



st.title("Native Plant Layout Engine")

st.caption("A California native planting layout generator for naturalistic and restorative landscape studies, plant palettes, plan views, elevation views, and schedules.")



\# -----------------------------

\# Canvas + Scale settings

\# -----------------------------



MAX\_CANVAS\_WIDTH = 900

MAX\_CANVAS\_HEIGHT = 600

DEFAULT\_BED\_LENGTH\_FEET = 50

DEFAULT\_BED\_WIDTH\_FEET = 50

MAX\_BED\_FEET = 50



GRID\_SPACING\_FEET = 5



DENSITY\_OPTIONS = {

    "Low": 0.30,

    "Moderate": 0.45,

    "Dense": 0.68,

    "Very Dense": 0.90

}



SPACING\_BY\_DENSITY = {

    "Low": 1.30,

    "Moderate": 1.15,

    "Dense": 1.05,

    "Very Dense": 1.00

}



MAX\_PLANTS\_BY\_DENSITY = {

    "Low": 180,

    "Moderate": 260,

    "Dense": 350,

    "Very Dense": 500

}



\# Placeholder used only while the plant database is being defined.

\# Runtime radii are recalculated after the active bed scale is known.

def feet\_to\_canvas\_radius(width\_ft):

    return width\_ft / 2



\# -----------------------------

\# Plant database

\# -----------------------------



PLANTS = [

    {

        "name": "Carex pansa",

        "common\_name": "Sand Dune Sedge",

        "code": "CP",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 1,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-pansa.webp",

        "elevation\_height": 28,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum latifolium",

        "common\_name": "Coast Buckwheat",

        "code": "EL",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Silver-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-latifolium.webp",

        "elevation\_height": 34,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Festuca californica",

        "common\_name": "California Fescue",

        "code": "FC",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/festuca-californica.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Salvia spathacea",

        "common\_name": "Hummingbird Sage",

        "code": "SS",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/salvia-spathacea.webp",

        "elevation\_height": 42,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Iris douglasiana",

        "common\_name": "Douglas Iris",

        "code": "ID",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/iris-douglasiana.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Arbutus menziesii",

        "common\_name": "Pacific Madrone",

        "code": "AM",

        "state": ["California"],

        "climate": ["Coastal", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 20,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(20),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arbutus-menziesii.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Arctostaphylos densiflora 'Howard McMinn'",

        "common\_name": "Howard McMinn Manzanita",

        "code": "AHM",

        "state": ["California"],

        "climate": ["Coastal", "Inland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 8,

        "height\_ft": 7,

        "radius": feet\_to\_canvas\_radius(8),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arctostaphylos-howard-mcminn.webp",

        "elevation\_height": 105,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

    {

        "name": "Muhlenbergia rigens",

        "common\_name": "Deergrass",

        "code": "MR",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/muhlenbergia-rigens.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Stipa pulchra",

        "common\_name": "Purple Needlegrass",

        "code": "SP",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Golden Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/stipa-pulchra.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Juncus patens",

        "common\_name": "Common Rush",

        "code": "JP",

        "state": ["California"],

        "climate": ["Inland", "Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 3,

        "height\_ft": 3,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/juncus-patens.webp",

        "elevation\_height": 46,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum fasciculatum",

        "common\_name": "California Buckwheat",

        "code": "EF",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-fasciculatum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Epilobium canum",

        "common\_name": "California Fuchsia",

        "code": "EC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Semi-evergreen",

        "image": "plant\_images/epilobium-canum.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Artemisia californica",

        "common\_name": "California Sagebrush",

        "code": "AC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Silver-Grey",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/artemisia-californica.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Quercus chrysolepis",

        "common\_name": "Canyon Live Oak",

        "code": "QC",

        "state": ["California"],

        "climate": ["Inland", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 30,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(30),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/quercus-chrysolepis.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Carex tumulicola",

        "common\_name": "Foothill Sedge",

        "code": "CT",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Sun"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-tumulicola.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Polystichum munitum",

        "common\_name": "Western Sword Fern",

        "code": "PM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 5,

        "usda\_max": 9,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/polystichum-munitum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Heuchera maxima",

        "common\_name": "Island Alum Root",

        "code": "HM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/heuchera-maxima.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Ribes sanguineum",

        "common\_name": "Red-Flowering Currant",

        "code": "RS",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 6,

        "height\_ft": 8,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Deciduous",

        "image": "plant\_images/ribes-sanguineum.webp",

        "elevation\_height": 110,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Woodwardia fimbriata",

        "common\_name": "Giant Chain Fern",

        "code": "WF",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 6,

        "height\_ft": 5,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/woodwardia-fimbriata.webp",

        "elevation\_height": 70,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Acer circinatum",

        "common\_name": "Vine Maple",

        "code": "ACI",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 15,

        "height\_ft": 20,

        "radius": feet\_to\_canvas\_radius(15),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 3,

        "seasonality": "Deciduous",

        "image": "plant\_images/acer-circinatum.webp",

        "elevation\_height": 125,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Heteromeles arbutifolia",

        "common\_name": "Toyon",

        "code": "HA",

        "state": ["California"],

        "climate": ["Woodland", "Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 10,

        "height\_ft": 15,

        "radius": feet\_to\_canvas\_radius(10),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/heteromeles-arbutifolia.webp",

        "elevation\_height": 118,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

]






ROLE\_ORDER = sorted({plant["role"] for plant in PLANTS})



DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES = {

    "Canopy": 12,

    "Structure": 22,

    "Matrix": 44,

    "Accent": 22,

}



def default\_role\_percentage(role):

    return DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES.get(role, 20)



HEIGHT\_VARIATION\_BY\_HIERARCHY = {

    "Anchor": 0.06,

    "Mid Layer": 0.10,

    "Accent Layer": 0.15,

    "Groundcover": 0.08

}



\# -----------------------------

\# Helper functions

\# -----------------------------



def clamp\_dimension(value, fallback):

    try:

        value = float(value)

    except Exception:

        return fallback

    return max(1, min(value, MAX\_BED\_FEET))





def get\_canvas\_setup(length\_ft, width\_ft):

    """Return canvas dimensions and true feet-per-canvas-unit scale.



    length\_ft is horizontal. width\_ft is vertical/depth.

    The canvas preserves the real bed aspect ratio and fits inside the max pixel bounds.

    """

    length\_ft = clamp\_dimension(length\_ft, DEFAULT\_BED\_LENGTH\_FEET)

    width\_ft = clamp\_dimension(width\_ft, DEFAULT\_BED\_WIDTH\_FEET)



    pixels\_per\_foot = min(MAX\_CANVAS\_WIDTH / length\_ft, MAX\_CANVAS\_HEIGHT / width\_ft)

    canvas\_width = max(250, int(round(length\_ft \* pixels\_per\_foot)))

    canvas\_height = max(250, int(round(width\_ft \* pixels\_per\_foot)))

    feet\_per\_canvas\_unit = 1 / pixels\_per\_foot

    grid\_spacing\_units = GRID\_SPACING\_FEET / feet\_per\_canvas\_unit



    return canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units





def make\_runtime\_plant\_pool(plants, feet\_per\_canvas\_unit):

    runtime\_plants = []

    for plant in plants:

        p = plant.copy()

        p["radius"] = (p["spread\_ft"] / 2) / feet\_per\_canvas\_unit

        runtime\_plants.append(p)

    return runtime\_plants





def circle\_inside(poly, x, y, r):

    return poly.contains(Point(x, y).buffer(r))





def circles\_overlap(x, y, r, placed, spacing\_factor, plant=None):

    for p in placed:

        existing\_plant = p["plant"]



        existing\_allows\_underplanting = existing\_plant.get("allows\_underplanting", False)

        current\_allows\_underplanting = plant is not None and plant.get("allows\_underplanting", False)



        if existing\_allows\_underplanting and not current\_allows\_underplanting:

            continue



        if current\_allows\_underplanting and not existing\_allows\_underplanting:

            continue



        distance = math.dist((x, y), (p["x"], p["y"]))

        min\_distance = (r + p["radius"]) \* spacing\_factor



        if distance < min\_distance:

            return True



    return False





def weighted\_choice(plants):

    if not plants:

        return None



    weights = [p.get("weight", 1) for p in plants]

    return random.choices(plants, weights=weights, k=1)[0]





def pack\_layer(poly, plants, target\_area, spacing\_factor, existing\_placed, max\_plants\_total):

    if not plants:

        return [], 0



    minx, miny, maxx, maxy = poly.bounds

    placed\_layer = []

    placed\_area = 0

    attempts = 0

    max\_attempts = 16000



    while (

        placed\_area < target\_area

        and attempts < max\_attempts

        and len(existing\_placed) + len(placed\_layer) < max\_plants\_total

    ):

        attempts += 1



        plant = weighted\_choice(plants)

        if plant is None:

            break



        r = plant["radius"]



        if maxx - minx < r \* 2 or maxy - miny < r \* 2:

            break



        x = random.uniform(minx + r, maxx - r)

        y = random.uniform(miny + r, maxy - r)



        if not circle\_inside(poly, x, y, r):

            continue



        all\_existing = existing\_placed + placed\_layer



        if circles\_overlap(x, y, r, all\_existing, spacing\_factor, plant):

            continue



        placed\_layer.append({"x": x, "y": y, "radius": r, "plant": plant})

        placed\_area += math.pi \* (r \*\* 2)



    return placed\_layer, placed\_area





def pack\_by\_role(poly, plant\_pool, target\_coverage, spacing\_factor, max\_plants\_total, role\_split=None):

    boundary\_area = poly.area



    if boundary\_area <= 0:

        return [], 0



    total\_target\_area = boundary\_area \* target\_coverage

    all\_placed = []

    total\_placed\_area = 0



    active\_roles = [role for role in ROLE\_ORDER if any(p["role"] == role for p in plant\_pool)]



    if not active\_roles:

        return [], 0



    if role\_split is None:

        total\_default = sum(default\_role\_percentage(role) for role in active\_roles) or 1

        role\_split = {

            role: default\_role\_percentage(role) / total\_default

            for role in active\_roles

        }



    for role in active\_roles:

        role\_plants = [p for p in plant\_pool if p["role"] == role]



        if not role\_plants:

            continue



        layer\_target\_area = total\_target\_area \* role\_split.get(role, 0)



        placed\_layer, placed\_area = pack\_layer(

            poly=poly,

            plants=role\_plants,

            target\_area=layer\_target\_area,

            spacing\_factor=spacing\_factor,

            existing\_placed=all\_placed,

            max\_plants\_total=max\_plants\_total

        )



        all\_placed.extend(placed\_layer)

        total\_placed\_area += placed\_area



    return all\_placed, total\_placed\_area / boundary\_area



def sun\_is\_compatible(selected\_sun, plant\_sun\_options):

    sun\_compatibility = {

        "Full Sun": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun"],

        "Full Sun-Part Shade": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade", "Part Shade-Full Shade"],

        "Part Shade": ["Part Shade", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade-Full Shade"],

        "Part Shade-Full Shade": ["Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"],

    }



    compatible\_values = sun\_compatibility.get(selected\_sun, [selected\_sun])

    return any(sun\_value in compatible\_values for sun\_value in plant\_sun\_options)





def water\_is\_compatible(selected\_water, plant\_water\_options):

    water\_compatibility = {

        "Low": ["Low", "Moderate-Low", "Low-Moderate"],

        "Moderate-Low": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Low-Moderate": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Moderate": ["Moderate", "Low-Moderate", "Moderate-Low"],

    }



    compatible\_values = water\_compatibility.get(selected\_water, [selected\_water])

    return any(water\_value in compatible\_values for water\_value in plant\_water\_options)





def hardiness\_is\_compatible(selected\_zones, usda\_min, usda\_max):

    if not selected\_zones:

        return True

    return any(usda\_min <= zone <= usda\_max for zone in selected\_zones)





def filter\_plants(plant\_database, state, climate, selected\_usda\_zones, sun, water):

    return [

        plant for plant in plant\_database

        if state in plant["state"]

        and climate in plant["climate"]

        and hardiness\_is\_compatible(selected\_usda\_zones, plant["usda\_min"], plant["usda\_max"])

        and sun\_is\_compatible(sun, plant["sun"])

        and water\_is\_compatible(water, plant["water"])

    ]



def get\_polygon\_from\_canvas(canvas\_json):

    if canvas\_json is None:

        return None



    objects = canvas\_json.get("objects", [])

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





def normalize\_polygon(points):

    if points is None or len(points) < 3:

        return None

    poly = Polygon(points)

    if not poly.is\_valid:

        poly = poly.buffer(0)

    if poly.is\_empty or poly.area <= 0:

        return None

    return poly





def polygon\_points\_from\_geometry(geom):

    if geom is None or geom.is\_empty:

        return []

    if geom.geom\_type == "Polygon":

        return [(float(x), float(y)) for x, y in list(geom.exterior.coords)[:-1]]

    if geom.geom\_type == "MultiPolygon":

        largest = max(list(geom.geoms), key=lambda g: g.area)

        return [(float(x), float(y)) for x, y in list(largest.exterior.coords)[:-1]]

    return []





def valid\_role\_zones\_for\_boundary(role\_zones, main\_poly):

    valid = {}

    for role, points in (role\_zones or {}).items():

        zone\_poly = normalize\_polygon(points)

        if zone\_poly is None:

            continue

        clipped = zone\_poly.intersection(main\_poly)

        if clipped.is\_empty or clipped.area <= 0:

            continue

        valid[role] = clipped

    return valid





def rectangle\_points(canvas\_width, canvas\_height):

    return [(0, 0), (canvas\_width, 0), (canvas\_width, canvas\_height), (0, canvas\_height)]





def fig\_to\_png\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="png", dpi=200, bbox\_inches="tight", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_jpeg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="jpg", dpi=200, bbox\_inches="tight", facecolor="white", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_svg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="svg", bbox\_inches="tight")

    buffer.seek(0)

    return buffer





def canvas\_area\_to\_sqft(area\_canvas\_units, feet\_per\_canvas\_unit):

    return area\_canvas\_units \* (feet\_per\_canvas\_unit \*\* 2)





def canvas\_length\_to\_feet(length\_canvas\_units, feet\_per\_canvas\_unit):

    return length\_canvas\_units \* feet\_per\_canvas\_unit





def draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units):

    x = 0

    while x <= canvas\_width:

        ax.axvline(x, linewidth=0.4, alpha=0.25)

        x += grid\_spacing\_units



    y = 0

    while y <= canvas\_height:

        ax.axhline(y, linewidth=0.4, alpha=0.25)

        y += grid\_spacing\_units





def get\_image\_aspect\_ratio(image\_path):

    try:

        img = plt.imread(image\_path)

        height\_px, width\_px = img.shape[:2]

        if height\_px == 0:

            return 1

        return width\_px / height\_px

    except Exception:

        return 1





def varied\_height(plant):

    tolerance = HEIGHT\_VARIATION\_BY\_HIERARCHY.get(plant["hierarchy"], 0.08)

    variation = random.uniform(1 - tolerance, 1 + tolerance)

    return plant["elevation\_height"] \* variation





def prepare\_uploaded\_image(uploaded\_file, canvas\_width, canvas\_height):

    if uploaded\_file is None:

        return None, None



    image = Image.open(uploaded\_file).convert("RGB")

    image = image.resize((canvas\_width, canvas\_height))

    image\_array = plt.imread(BytesIO(image\_to\_png\_bytes(image).getvalue()))

    return image, image\_array





def render\_trace\_overlay(image, points, canvas\_width, canvas\_height):

    """Return a PIL image with the uploaded background plus the clicked/traced bedline points.



    This avoids relying on streamlit-drawable-canvas background\_image, which can render

    blank on Streamlit Cloud. Users click around the bedline directly on the image.

    """

    if image is None:

        return None



    overlay = image.copy().convert("RGB")

    overlay = overlay.resize((canvas\_width, canvas\_height))

    draw = ImageDraw\.Draw(overlay)



    if len(points) >= 2:

        draw\.line(points, fill=(255, 255, 255), width=3)



    if len(points) >= 3:

        # Light preview of the closing segment so users understand the final polygon.

        draw\.line([points[-1], points[0]], fill=(255, 255, 255), width=2)



    for idx, (x, y) in enumerate(points):

        r = 5

        draw\.ellipse((x - r, y - r, x + r, y + r), fill=(255, 80, 80), outline=(255, 255, 255), width=2)

        draw\.text((x + 7, y - 7), str(idx + 1), fill=(255, 255, 255))



    return overlay





def image\_to\_png\_bytes(image):

    buffer = BytesIO()

    image.save(buffer, format="PNG")

    buffer.seek(0)

    return buffer





def escape\_svg\_text(value):

    return html.escape(str(value), quote=True)





def plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit, role\_zones=None):

    """Create a clean vector SVG of the plan geometry.



    This avoids relying on Matplotlib's SVG output and gives you true circle/vector objects.

    """

    path\_points = " ".join([f"{x:.2f},{y:.2f}" for x, y in points])

    svg = StringIO()

    svg.write(f'\<svg xmlns="http\://www\.w3.org/2000/svg" width="{canvas\_width}" height="{canvas\_height}" viewBox="0 0 {canvas\_width} {canvas\_height}">\n')

    svg.write('\<rect width="100%" height="100%" fill="white"/>\n')

    svg.write(f'\<polygon points="{path\_points}" fill="none" stroke="black" stroke-width="2"/>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        zone\_path = " ".join([f"{x:.2f},{y:.2f}" for x, y in zone\_points])

        first\_x, first\_y = zone\_points[0]

        svg.write(f'\<polygon points="{zone\_path}" fill="none" stroke="black" stroke-width="1" stroke-dasharray="4 4" opacity="0.45"/>\n')

        svg.write(f'\<text x="{first\_x:.2f}" y="{first\_y:.2f}" font-family="Arial" font-size="10" opacity="0.65">{escape\_svg\_text(role)} zone\</text>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        closed\_zone = zone\_points + [zone\_points[0]]

        layer\_name = f"ROLE\_ZONE\_{role.upper().replace(' ', '\_')}"

        for i in range(len(closed\_zone) - 1):

            x1, y1 = closed\_zone[i]

            x2, y2 = closed\_zone[i + 1]

            dxf.write("0\nLINE\n8\n" + layer\_name + "\n")

            dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

            dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dash = ' stroke-dasharray="6 4"' if plant.get("allows\_underplanting", False) else ""

        weight = "bold" if plant.get("allows\_underplanting", False) else "normal"

        svg.write(f'\<circle cx="{item["x"]:.2f}" cy="{item["y"]:.2f}" r="{item["radius"]:.2f}" fill="none" stroke="black" stroke-width="1.2"{dash}/>\n')

        svg.write(f'\<text x="{item["x"]:.2f}" y="{item["y"]:.2f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="8" font-weight="{weight}">{escape\_svg\_text(plant["code"])}\</text>\n')



    svg.write(f'\<text x="12" y="{canvas\_height - 14}" font-family="Arial" font-size="10">Scale: 1 px = {feet\_per\_canvas\_unit:.3f} ft\</text>\n')

    svg.write('\</svg>')

    return BytesIO(svg.getvalue().encode("utf-8"))





def plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit, role\_zones=None):

    """Export a simple ASCII DXF in real feet.



    AutoCAD, Rhino, Vectorworks, and many CAD tools can open DXF. This is the practical

    Streamlit-friendly alternative to DWG.

    """

    dxf = StringIO()

    dxf.write("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n2\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nENTITIES\n")



    closed\_points = points + [points[0]]

    for i in range(len(closed\_points) - 1):

        x1, y1 = closed\_points[i]

        x2, y2 = closed\_points[i + 1]

        dxf.write("0\nLINE\n8\nBOUNDARY\n")

        dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dxf.write("0\nCIRCLE\n8\nPLANTS\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"40\n{item['radius'] \* feet\_per\_canvas\_unit:.4f}\n")

        dxf.write("0\nTEXT\n8\nPLANT\_CODES\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write("40\n0.35\n")

        dxf.write(f"1\n{plant['code']}\n")



    dxf.write("0\nENDSEC\n0\nEOF\n")

    return BytesIO(dxf.getvalue().encode("utf-8"))



\# -----------------------------

\# Sidebar

\# -----------------------------



with st.sidebar:

    st.markdown("### by The Landscape Library")



    st.header("Input Method")

    input\_method = st.radio(

        "Choose how to define the planting bed",

        ["Draw Boundary", "Upload JPEG Image"],

        index=0

    )



    st.info("Max 50' bed")



    if input\_method == "Upload JPEG Image":

        st.caption("Upload a JPEG image as a scaled reference, then click points around the actual bedline.")

        uploaded\_bed\_image = st.file\_uploader(

            "Upload bed image",

            type=["jpg", "jpeg"]

        )



        bed\_length\_ft = st.number\_input(

            "Image length / horizontal dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=30.0,

            step=1.0

        )



        bed\_width\_ft = st.number\_input(

            "Image width / vertical dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=15.0,

            step=1.0

        )

    else:

        uploaded\_bed\_image = None

        bed\_length\_ft = DEFAULT\_BED\_LENGTH\_FEET

        bed\_width\_ft = DEFAULT\_BED\_WIDTH\_FEET



    canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units = get\_canvas\_setup(

        bed\_length\_ft,

        bed\_width\_ft

    )



    st.header("Site Parameters")



    state = st.selectbox("State", ["California"])

    climate = st.selectbox("California Plant Community", ["Coastal", "Inland", "Dry", "Woodland"])



    st.markdown("\*\*USDA Hardiness\*\*")

    st.caption("Select one or more USDA zones. Plants are included when the selected zone falls between USDA Min and USDA Max in the plant database.")

    usda\_zone\_options = list(range(5, 11))

    default\_usda\_zones = [9]

    selected\_usda\_zones = []

    zone\_cols = st.columns(3)

    for idx, zone in enumerate(usda\_zone\_options):

        with zone\_cols[idx % 3]:

            checked = st.checkbox(f"Zone {zone}", value=zone in default\_usda\_zones, key=f"usda\_zone\_{zone}")

            if checked:

                selected\_usda\_zones.append(zone)



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



    target\_coverage = DENSITY\_OPTIONS[density]

    spacing\_factor = SPACING\_BY\_DENSITY[density]

    max\_plants\_total = MAX\_PLANTS\_BY\_DENSITY[density]



    st.header("Scale")

    st.caption(f"Bed limit: {MAX\_BED\_FEET} ft max length or width")

    st.caption(f"Active bed: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")



\# -----------------------------

\# Active plant database + image prep

\# -----------------------------



runtime\_plants = make\_runtime\_plant\_pool(PLANTS, feet\_per\_canvas\_unit)

selected\_plants = filter\_plants(runtime\_plants, state, climate, selected\_usda\_zones, sun, water)

\# Manual include / exclude controls

all\_matching\_names = [p["name"] for p in selected\_plants]

with st.sidebar:

    st.header("Plant Controls")

    include\_names = st.multiselect("Force include plants", [p["name"] for p in runtime\_plants])

    exclude\_names = st.multiselect("Exclude plants", all\_matching\_names)



    st.header("Role Percentages")

    st.caption("These sliders use the exact Role values from the plant database.")

    role\_percentages = {}

    for role in ROLE\_ORDER:

        role\_percentages[role] = st.slider(role, 0, 100, default\_role\_percentage(role), key=f"role\_pct\_{role}")



    total\_pct = sum(role\_percentages.values())

    if total\_pct == 0:

        total\_pct = 1

    role\_split = {

        role: value / total\_pct

        for role, value in role\_percentages.items()

    }

forced = [p for p in runtime\_plants if p["name"] in include\_names]

selected\_plants = [p for p in selected\_plants if p["name"] not in exclude\_names]

for p in forced:

    if p["name"] not in [sp["name"] for sp in selected\_plants]:

        selected\_plants.append(p)



background\_image = None

background\_array = None



if input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    background\_image, background\_array = prepare\_uploaded\_image(uploaded\_bed\_image, canvas\_width, canvas\_height)



\# -----------------------------

\# Main UI

\# -----------------------------



left, right = st.columns([2, 1])



with left:

    if input\_method == "Draw Boundary":

        st.subheader("1. Draw Planting Boundary")

        st.caption("TIP: Left click to add boundary points. Right click to end nearest the origin point and complete the boundary.")

        st.caption('Drawing canvas: 50\\'-0" horizontal × 50\\'-0" vertical.')



        canvas\_result = st\_canvas(

            fill\_color="rgba(0, 0, 0, 0)",

            stroke\_width=3,

            stroke\_color="#111111",

            background\_color="#f7f7f2",

            height=canvas\_height,

            width=canvas\_width,

            drawing\_mode="polygon",

            key="draw\_boundary\_canvas",

        )

    else:

        st.subheader("1. Upload Scaled Bed Image + Trace Bedline")

        st.caption("Click around the planting bedline in order. Use more points for curves. The final segment closes automatically between the last point and first point.")



        if uploaded\_bed\_image is None:

            st.warning("Upload a JPEG image first, then click points around the actual bedline.")

            canvas\_result = None

        else:

            canvas\_result = None



            if streamlit\_image\_coordinates is None:

                st.error("Missing package: streamlit-image-coordinates. Add streamlit-image-coordinates to requirements.txt, then redeploy.")

            else:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                last\_click\_key = f"last\_click\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"



                if trace\_key not in st.session\_state:

                    st.session\_state[trace\_key] = []

                if last\_click\_key not in st.session\_state:

                    st.session\_state[last\_click\_key] = None



                st.caption("Click points around the bedline in order. Use more points for curves. The final segment closes automatically between the last and first point.")



                overlay\_image = render\_trace\_overlay(

                    background\_image,

                    st.session\_state[trace\_key],

                    canvas\_width,

                    canvas\_height

                )



                clicked = streamlit\_image\_coordinates(

                    overlay\_image,

                    key=f"click\_trace\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}",

                    width=canvas\_width

                )



                if clicked is not None and "x" in clicked and "y" in clicked:

                    new\_point = (int(clicked["x"]), int(clicked["y"]))



                    if st.session\_state[last\_click\_key] != new\_point:

                        existing\_points = st.session\_state[trace\_key]



                        # Prevent accidental double-click duplicates.

                        if len(existing\_points) == 0 or math.dist(existing\_points[-1], new\_point) > 4:

                            existing\_points.append(new\_point)

                            st.session\_state[trace\_key] = existing\_points



                        st.session\_state[last\_click\_key] = new\_point

                        st.rerun()



                b1, b2, b3 = st.columns(3)

                with b1:

                    if st.button("Undo Last Point") and len(st.session\_state[trace\_key]) > 0:

                        st.session\_state[trace\_key] = st.session\_state[trace\_key][:-1]

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b2:

                    if st.button("Clear Trace"):

                        st.session\_state[trace\_key] = []

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b3:

                    st.metric("Trace Points", len(st.session\_state[trace\_key]))



                if len(st.session\_state[trace\_key]) < 3:

                    st.info("Add at least 3 points before generating the planting layout.")



with right:

    st.subheader("Request a Plant")

    requested\_plant = st.text\_input("Plant you want added")

    if st.button("Submit Plant Request"):

        if requested\_plant.strip():

            ok, error\_message = log\_plant\_request(

                st.session\_state.get("user\_email"),

                requested\_plant.strip(),

                state=state,

                zone=", ".join([f"USDA {z}" for z in selected\_usda\_zones]),

                climate=climate,

                sun\_exposure=sun,

                water\_needs=water,

                design\_style="Native Plant Layout Engine",

            )

            if ok:

                st.success("Plant request submitted.")

            else:

                st.error(f"Plant request was not saved: {error\_message}")

        else:

            st.warning("Enter a plant name before submitting.")



    st.subheader("3. Selected Plant Palette")



    if len(selected\_plants) == 0:

        st.warning("No plants match these parameters yet. Try adjusting USDA hardiness, sun exposure, or water needs.")

    else:

        for plant in selected\_plants:

            canopy\_note = " | allows underplanting" if plant.get("allows\_underplanting", False) else ""

            st.write(f"\*\*{plant['name']}\*\*")

            st.caption(

                f"{plant['code']} | {plant['common\_name']} | {plant['form']} | {plant['role']} | spread: {plant['spread\_ft']} ft{canopy\_note}"

            )



\# -----------------------------

\# Boundary metrics

\# -----------------------------



points\_preview = None



if input\_method == "Draw Boundary" and canvas\_result is not None:

    points\_preview = get\_polygon\_from\_canvas(canvas\_result.json\_data)

elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

    points\_preview = st.session\_state.get(trace\_key, [])

    if len(points\_preview) < 3:

        points\_preview = None



if points\_preview is not None:

    preview\_poly = Polygon(points\_preview)



    if not preview\_poly.is\_valid:

        preview\_poly = preview\_poly.buffer(0)



    if preview\_poly.area > 0:

        area\_sqft = canvas\_area\_to\_sqft(preview\_poly.area, feet\_per\_canvas\_unit)

        perimeter\_ft = canvas\_length\_to\_feet(preview\_poly.length, feet\_per\_canvas\_unit)

        minx\_preview, miny\_preview, maxx\_preview, maxy\_preview = preview\_poly.bounds



        width\_ft = canvas\_length\_to\_feet(maxx\_preview - minx\_preview, feet\_per\_canvas\_unit)

        depth\_ft = canvas\_length\_to\_feet(maxy\_preview - miny\_preview, feet\_per\_canvas\_unit)



        st.subheader("Boundary Metrics")



        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Approx. Area", f"{area\_sqft:,.0f} sq ft")

        c2.metric("Approx. Perimeter", f"{perimeter\_ft:,.0f} ft")

        c3.metric("Approx. Length", f"{width\_ft:,.0f} ft")

        c4.metric("Approx. Width", f"{depth\_ft:,.0f} ft")



generate = st.button("Generate Planting Layout", type="primary")



\# -----------------------------

\# Generate

\# -----------------------------



if generate:

    if supabase is not None and st.session\_state.get("user\_email"):

        user\_check = supabase.table("users").select("\*").eq("email", st.session\_state.user\_email).execute()

        current\_user = user\_check.data[0] if user\_check.data else {}

        if not current\_user.get("paid\_status", False) and (current\_user.get("total\_generations") or 0) >= FREE\_GENERATION\_LIMIT:

            st.warning("You have reached the free generation limit.")

            log\_event(st.session\_state.user\_email, "paywall\_shown")

            st.stop()

    try:

        with st.spinner("Generating planting plan and elevation view\..."):

            if input\_method == "Draw Boundary" and canvas\_result is not None:

                points = get\_polygon\_from\_canvas(canvas\_result.json\_data)

            elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                points = st.session\_state.get(trace\_key, [])

                if len(points) < 3:

                    points = None

            else:

                points = None



            if points is None:

                if input\_method == "Draw Boundary":

                    st.warning("Draw a closed polygon boundary first.")

                else:

                    st.warning("Upload a JPEG image and trace a closed polygon boundary first.")



            elif bed\_length\_ft > MAX\_BED\_FEET or bed\_width\_ft > MAX\_BED\_FEET:

                st.warning(f"The bed is too large. Keep the image dimensions at or below {MAX\_BED\_FEET} ft.")



            elif len(selected\_plants) == 0:

                st.warning("No plants are available for the selected site parameters.")



            else:

                poly = normalize\_polygon(points)



                if poly is None:

                    st.warning("The boundary is invalid. Try tracing a clearer closed shape.")



                else:

                    placed\_instances, actual\_coverage = pack\_by\_role(

                        poly=poly,

                        plant\_pool=selected\_plants,

                        target\_coverage=target\_coverage,

                        spacing\_factor=spacing\_factor,

                        max\_plants\_total=max\_plants\_total,

                        role\_split=role\_split

                    )



                    if len(placed\_instances) == 0:

                        st.warning("No plants could fit inside the boundary. Try a larger area, lower density, or different plant parameters.")



                    else:

                        new\_generation\_count = increment\_generation\_count(st.session\_state.get("user\_email"))

                        log\_event(

                            st.session\_state.get("user\_email"),

                            "generation\_run",

                            state=state,

                            zone=", ".join([f"USDA {z}" for z in selected\_usda\_zones]),

                            climate=climate,

                            sun\_exposure=sun,

                            water\_needs=water,

                                        density=density,

                            plants\_generated\_count=len(placed\_instances)

                        )



                        st.subheader("Plan View")



                        fig, ax = plt.subplots(figsize=(10, 10))



                        if background\_array is not None:

                            ax.imshow(background\_array, extent=(0, canvas\_width, canvas\_height, 0), alpha=0.35, zorder=0)



                        xs, ys = zip(\*(points + [points[0]]))

                        ax.plot(xs, ys, linewidth=2, zorder=3)



                        draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units)



                        for item in placed\_instances:

                            plant = item["plant"]



                            if plant.get("allows\_underplanting", False):

                                continue



                            circle = plt.Circle(

                                (item["x"], item["y"]),

                                item["radius"],

                                fill=False,

                                linewidth=1.2,

                                zorder=4

                            )

                            ax.add\_patch(circle)



                            ax.text(

                                item["x"],

                                item["y"],

                                plant["code"],

                                ha="center",

                                va="center",

                                fontsize=8,

                                zorder=5

                            )



                        for item in placed\_instances:

                            plant = item["plant"]



                            if not plant.get("allows\_underplanting", False):

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

                            ax.add\_patch(circle)



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



                        ax.set\_xlim(0, canvas\_width)

                        ax.set\_ylim(canvas\_height, 0)

                        ax.set\_aspect("equal")

                        ax.axis("off")



                        st.pyplot(fig)



                        plan\_png = fig\_to\_png\_bytes(fig)

                        plan\_svg = plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit)

                        plan\_dxf = plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit)



                        d1, d2, d3 = st.columns(3)

                        with d1:

                            st.download\_button(

                                label="Download Plan PNG",

                                data=plan\_png,

                                file\_name="yodra-planting-plan.png",

                                mime="image/png"

                            )

                        with d2:

                            st.download\_button(

                                label="Download Plan SVG",

                                data=plan\_svg,

                                file\_name="yodra-planting-plan.svg",

                                mime="image/svg+xml"

                            )

                        with d3:

                            st.download\_button(

                                label="Download Plan DXF",

                                data=plan\_dxf,

                                file\_name="yodra-planting-plan.dxf",

                                mime="application/dxf"

                            )



                        st.caption(f"Target coverage: {round(target\_coverage \* 100)}%")

                        st.caption(f"Actual generated coverage: {round(actual\_coverage \* 100)}%")

                        st.caption(f"Active bed scale: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")

                        st.caption(f"Maximum plant instances capped at {max\_plants\_total} for app performance.")



                        st.subheader("Elevation View")

                        st.caption("Elevation uses the same plant instances generated in plan view, with subtle height variation.")



                        elev\_fig, elev\_ax = plt.subplots(figsize=(12, 4))



                        placed\_sorted = sorted(placed\_instances, key=lambda item: item["x"])



                        for item in placed\_sorted:

                            plant = item["plant"]

                            image\_path = plant["image"]



                            height = varied\_height(plant)

                            aspect\_ratio = get\_image\_aspect\_ratio(image\_path)

                            width = height \* aspect\_ratio



                            if os.path.exists(image\_path):

                                img = plt.imread(image\_path)



                                elev\_ax.imshow(

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

                                elev\_ax.text(

                                    item["x"],

                                    height / 2,

                                    plant["code"],

                                    ha="center",

                                    va="center",

                                    fontsize=8

                                )



                        elev\_ax.axhline(0, linewidth=1)

                        elev\_ax.set\_xlim(0, canvas\_width)

                        elev\_ax.set\_ylim(0, 140)

                        elev\_ax.axis("off")



                        st.pyplot(elev\_fig)



                        elevation\_png = fig\_to\_png\_bytes(elev\_fig)

                        elevation\_jpeg = fig\_to\_jpeg\_bytes(elev\_fig)



                        e1, e2 = st.columns(2)

                        with e1:

                            st.download\_button(

                                label="Download Elevation PNG",

                                data=elevation\_png,

                                file\_name="yodra-planting-elevation.png",

                                mime="image/png"

                            )

                        with e2:

                            st.download\_button(

                                label="Download Elevation JPEG",

                                data=elevation\_jpeg,

                                file\_name="yodra-planting-elevation.jpg",

                                mime="image/jpeg"

                            )



                        counts = {}

                        for item in placed\_instances:

                            plant = item["plant"]

                            counts[plant["name"]] = counts.get(plant["name"], 0) + 1



                        st.subheader("Plant Schedule")



                        schedule = []

                        for plant\_name, count in counts.items():

                            plant = next(p for p in runtime\_plants if p["name"] == plant\_name)



                            schedule.append({

                                "Code": plant["code"],

                                "Count": count,

                                "Botanical Name": plant["name"],

                                "Common Name": plant["common\_name"],

                                "Form": plant["form"],

                                "Role": plant["role"],

                                "Texture": plant["texture"],

                                "Color Tone": plant["color\_tone"],

                                "Visual Weight": plant["visual\_weight"],

                                "Spread Ft": plant["spread\_ft"],

                                "Height Ft": plant["height\_ft"],

                                "State": state,

                                "Climate": ", ".join(plant["climate"]),

                                "USDA Min": plant["usda\_min"],

                                "USDA Max": plant["usda\_max"],

                                "Sun": ", ".join(plant["sun"]),

                                "Water": ", ".join(plant["water"]),

                                "Seasonality": plant["seasonality"],

                                "Allows Underplanting": plant.get("allows\_underplanting", False)

                            })



                        schedule\_df = pd.DataFrame(schedule)

                        st.dataframe(schedule\_df, width="stretch")



                        csv\_buffer = schedule\_df.to\_csv(index=False).encode("utf-8")

                        st.download\_button(

                            label="Download Plant Schedule CSV / Excel",

                            data=csv\_buffer,

                            file\_name="yodra-plant-schedule.csv",

                            mime="text/csv",

                            on\_click=lambda: increment\_export\_count(st.session\_state.get("user\_email"))

                        )

                        log\_event(st.session\_state.get("user\_email"), "schedule\_export\_ready", export\_type="csv")



    except Exception as e:

        st.error("The app crashed while generating the layout.")

        st.exception(e)





---












































# Version 3.1





import streamlit as st

from datetime import datetime, timezone

try:

    from supabase import create\_client

except Exception:

    create\_client = None

import pandas as pd



\# -------------------------

\# SUPABASE USER TRACKING

\# -------------------------



FREE\_GENERATION\_LIMIT = 999



def get\_supabase\_client():

    if create\_client is None:

        return None

    url = st.secrets.get("SUPABASE\_URL", "")

    key = st.secrets.get("SUPABASE\_SERVICE\_ROLE\_KEY", "")

    if not url or not key:

        return None

    return create\_client(url, key)



supabase = get\_supabase\_client()



def log\_event(email, event\_type, \*\*kwargs):

    """Insert an event using only the columns that exist in the current Supabase events table.



    Current expected columns:

    email, event\_type, created\_at, climate, sun\_exposure, water\_needs,

    design\_style, export\_type, notes.



    Do not add state, zone, density, or plants\_generated\_count unless those columns

    are also added to Supabase. Supabase will reject inserts when unknown columns

    are included.

    """

    if supabase is None or not email:

        return False, "Supabase is not connected or user email is missing."



    event = {

        "email": email,

        "event\_type": event\_type,

        "created\_at": datetime.now(timezone.utc).isoformat(),

        "climate": kwargs.get("climate"),

        "sun\_exposure": kwargs.get("sun\_exposure"),

        "water\_needs": kwargs.get("water\_needs"),

        "design\_style": kwargs.get("design\_style"),

        "export\_type": kwargs.get("export\_type"),

        "notes": kwargs.get("notes"),

    }



    # Remove empty optional fields so Supabase receives a clean payload.

    event = {k: v for k, v in event.items() if v is not None}



    try:

        supabase.table("events").insert(event).execute()

        return True, None

    except Exception as e:

        return False, str(e)





def log\_plant\_request(email, requested\_plant, \*\*kwargs):

    requested\_plant = (requested\_plant or "").strip()

    if not requested\_plant:

        return False, "Plant request is empty."



    ok, err = log\_event(

        email,

        "plant\_requested",

        notes=requested\_plant,

        \*\*kwargs

    )



    # Optional dedicated table. If you create a plant\_requests table in Supabase,

    # this will also save requests there. If that table does not exist, the

    # events table above is still the primary tracking location.

    if supabase is not None and email:

        try:

            supabase.table("plant\_requests").insert({

                "email": email,

                "requested\_plant": requested\_plant,

                "created\_at": datetime.now(timezone.utc).isoformat(),

                "climate": kwargs.get("climate"),

                "sun\_exposure": kwargs.get("sun\_exposure"),

                "water\_needs": kwargs.get("water\_needs"),

                "notes": requested\_plant,

            }).execute()

        except Exception:

            pass



    return ok, err



def get\_or\_create\_user(email):

    email = email.strip().lower()

    if supabase is None:

        return {"email": email, "paid\_status": False, "total\_generations": 0, "total\_exports": 0}



    now = datetime.now(timezone.utc).isoformat()

    result = supabase.table("users").select("\*").eq("email", email).execute()

    if result.data:

        user = result.data[0]

        supabase.table("users").update({"last\_seen": now}).eq("email", email).execute()

        return user



    new\_user = {

        "email": email,

        "first\_seen": now,

        "last\_seen": now,

        "paid\_status": False,

        "total\_generations": 0,

        "total\_exports": 0,

    }

    created = supabase.table("users").insert(new\_user).execute()

    return created.data[0] if created.data else new\_user



def increment\_generation\_count(email):

    if supabase is None:

        return 0

    result = supabase.table("users").select("total\_generations").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_generations") or 0

    new\_count = current + 1

    supabase.table("users").update({

        "total\_generations": new\_count,

        "last\_seen": datetime.now(timezone.utc).isoformat()

    }).eq("email", email).execute()

    return new\_count



def increment\_export\_count(email):

    if supabase is None:

        return

    result = supabase.table("users").select("total\_exports").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_exports") or 0

    supabase.table("users").update({"total\_exports": current + 1}).eq("email", email).execute()



def beta\_email\_gate():

    if "user\_email" not in st.session\_state:

        st.session\_state.user\_email = None

    if st.session\_state.user\_email:

        return True



    st.title("Native Plant Layout Engine by The Landscape Library")

    st.markdown("### Enter your email to begin generating planting layouts.")

    email = st.text\_input("Enter your email to continue")

    if st.button("Continue"):

        if "@" not in email or "." not in email:

            st.error("Please enter a valid email address.")

            st.stop()

        user = get\_or\_create\_user(email)

        st.session\_state.user\_email = user["email"]

        st.session\_state.user\_data = user

        log\_event(user["email"], "app\_opened")

        st.rerun()

    st.stop()



beta\_email\_gate()





\# -------------------------

\# YOUR APP BELOW

\# -------------------------



import random

import math

import os

import html

import base64

from io import BytesIO, StringIO



import matplotlib.pyplot as plt

from PIL import Image, ImageDraw

from shapely.geometry import Polygon, Point

from streamlit\_drawable\_canvas import st\_canvas

try:

    from streamlit\_image\_coordinates import streamlit\_image\_coordinates

except Exception:

    streamlit\_image\_coordinates = None



\# -----------------------------

\# Compatibility patch

\# -----------------------------

\# streamlit-drawable-canvas still calls an older Streamlit helper named

\# st.image.image\_to\_url when using background\_image. Newer Streamlit versions

\# removed that helper, which causes an AttributeError on image upload.

\# This patch restores the expected helper by converting the PIL background image

\# into a browser-safe base64 data URL.

def \_yodra\_image\_to\_url(image, width=None, clamp=False, channels="RGB", output\_format="PNG", image\_id=None):

    """Compatibility helper for streamlit-drawable-canvas background images.



    Newer Streamlit versions removed st.image.image\_to\_url, but

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

    return f"data\:image/png;base64,{encoded}"



try:

    # This is the exact object streamlit-drawable-canvas references: st.image.image\_to\_url

    st.image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



try:

    # Also patch Streamlit's image module for environments that reference it directly.

    import streamlit.elements.image as st\_image

    st\_image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



st.set\_page\_config(

    page\_title="Native Plant Layout Engine",

    layout="wide"

)



st.title("Native Plant Layout Engine")

st.caption("A California native planting layout generator for naturalistic and restorative landscape studies, plant palettes, plan views, elevation views, and schedules.")



\# -----------------------------

\# Canvas + Scale settings

\# -----------------------------



MAX\_CANVAS\_WIDTH = 900

MAX\_CANVAS\_HEIGHT = 600

DEFAULT\_BED\_LENGTH\_FEET = 50

DEFAULT\_BED\_WIDTH\_FEET = 50

MAX\_BED\_FEET = 50



GRID\_SPACING\_FEET = 5



DENSITY\_OPTIONS = {

    "Low": 0.30,

    "Moderate": 0.45,

    "Dense": 0.68,

    "Very Dense": 0.90

}



SPACING\_BY\_DENSITY = {

    "Low": 1.30,

    "Moderate": 1.15,

    "Dense": 1.05,

    "Very Dense": 1.00

}



MAX\_PLANTS\_BY\_DENSITY = {

    "Low": 180,

    "Moderate": 260,

    "Dense": 350,

    "Very Dense": 500

}



\# Placeholder used only while the plant database is being defined.

\# Runtime radii are recalculated after the active bed scale is known.

def feet\_to\_canvas\_radius(width\_ft):

    return width\_ft / 2



\# -----------------------------

\# Plant database

\# -----------------------------



PLANTS = [

    {

        "name": "Carex pansa",

        "common\_name": "Sand Dune Sedge",

        "code": "CP",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 1,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-pansa.webp",

        "elevation\_height": 28,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum latifolium",

        "common\_name": "Coast Buckwheat",

        "code": "EL",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Silver-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-latifolium.webp",

        "elevation\_height": 34,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Festuca californica",

        "common\_name": "California Fescue",

        "code": "FC",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/festuca-californica.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Salvia spathacea",

        "common\_name": "Hummingbird Sage",

        "code": "SS",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/salvia-spathacea.webp",

        "elevation\_height": 42,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Iris douglasiana",

        "common\_name": "Douglas Iris",

        "code": "ID",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/iris-douglasiana.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Arbutus menziesii",

        "common\_name": "Pacific Madrone",

        "code": "AM",

        "state": ["California"],

        "climate": ["Coastal", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 20,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(20),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arbutus-menziesii.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Arctostaphylos densiflora 'Howard McMinn'",

        "common\_name": "Howard McMinn Manzanita",

        "code": "AHM",

        "state": ["California"],

        "climate": ["Coastal", "Inland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 8,

        "height\_ft": 7,

        "radius": feet\_to\_canvas\_radius(8),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arctostaphylos-howard-mcminn.webp",

        "elevation\_height": 105,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

    {

        "name": "Muhlenbergia rigens",

        "common\_name": "Deergrass",

        "code": "MR",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/muhlenbergia-rigens.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Stipa pulchra",

        "common\_name": "Purple Needlegrass",

        "code": "SP",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Golden Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/stipa-pulchra.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Juncus patens",

        "common\_name": "Common Rush",

        "code": "JP",

        "state": ["California"],

        "climate": ["Inland", "Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 3,

        "height\_ft": 3,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/juncus-patens.webp",

        "elevation\_height": 46,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum fasciculatum",

        "common\_name": "California Buckwheat",

        "code": "EF",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-fasciculatum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Epilobium canum",

        "common\_name": "California Fuchsia",

        "code": "EC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Semi-evergreen",

        "image": "plant\_images/epilobium-canum.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Artemisia californica",

        "common\_name": "California Sagebrush",

        "code": "AC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Silver-Grey",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/artemisia-californica.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Quercus chrysolepis",

        "common\_name": "Canyon Live Oak",

        "code": "QC",

        "state": ["California"],

        "climate": ["Inland", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 30,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(30),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/quercus-chrysolepis.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Carex tumulicola",

        "common\_name": "Foothill Sedge",

        "code": "CT",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Sun"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-tumulicola.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Polystichum munitum",

        "common\_name": "Western Sword Fern",

        "code": "PM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 5,

        "usda\_max": 9,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/polystichum-munitum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Heuchera maxima",

        "common\_name": "Island Alum Root",

        "code": "HM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/heuchera-maxima.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Ribes sanguineum",

        "common\_name": "Red-Flowering Currant",

        "code": "RS",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 6,

        "height\_ft": 8,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Deciduous",

        "image": "plant\_images/ribes-sanguineum.webp",

        "elevation\_height": 110,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Woodwardia fimbriata",

        "common\_name": "Giant Chain Fern",

        "code": "WF",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 6,

        "height\_ft": 5,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/woodwardia-fimbriata.webp",

        "elevation\_height": 70,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Acer circinatum",

        "common\_name": "Vine Maple",

        "code": "ACI",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 15,

        "height\_ft": 20,

        "radius": feet\_to\_canvas\_radius(15),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 3,

        "seasonality": "Deciduous",

        "image": "plant\_images/acer-circinatum.webp",

        "elevation\_height": 125,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Heteromeles arbutifolia",

        "common\_name": "Toyon",

        "code": "HA",

        "state": ["California"],

        "climate": ["Woodland", "Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 10,

        "height\_ft": 15,

        "radius": feet\_to\_canvas\_radius(10),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/heteromeles-arbutifolia.webp",

        "elevation\_height": 118,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

]







STYLE\_FIT\_BY\_CODE = {

    "CP": ["Naturalized", "Contemporary", "Meadow"],

    "EL": ["Naturalized", "Meadow", "Coastal"],

    "FC": ["Naturalized", "Contemporary", "Meadow"],

    "SS": ["Naturalized", "Woodland"],

    "ID": ["Naturalized", "Meadow", "Woodland"],

    "AM": ["Naturalized", "Woodland", "Contemporary"],

    "AHM": ["Contemporary", "Naturalized", "Coastal"],

    "MR": ["Naturalized", "Contemporary", "Meadow"],

    "SP": ["Naturalized", "Meadow"],

    "JP": ["Naturalized", "Meadow", "Contemporary"],

    "EF": ["Naturalized", "Meadow", "Dry"],

    "EC": ["Naturalized", "Meadow", "Dry"],

    "AC": ["Naturalized", "Dry", "Meadow"],

    "QC": ["Naturalized", "Woodland"],

    "CT": ["Naturalized", "Woodland", "Contemporary"],

    "PM": ["Woodland", "Naturalized"],

    "HM": ["Woodland", "Naturalized", "Contemporary"],

    "RS": ["Woodland", "Naturalized"],

    "WF": ["Woodland", "Naturalized"],

    "AV": ["Woodland", "Naturalized", "Contemporary"],

    "HA": ["Woodland", "Contemporary", "Naturalized"],

}



STYLE\_LOGIC = {

    "Naturalized": {

        "species\_limit": 8,

        "spacing\_multiplier": 1.00,

        "description": "Loose, mixed drifts with controlled variation."

    },

    "Contemporary": {

        "species\_limit": 5,

        "spacing\_multiplier": 1.18,

        "description": "Fewer species, stronger repeated masses, and more negative space."

    },

    "Meadow": {

        "species\_limit": 6,

        "spacing\_multiplier": 0.96,

        "description": "Matrix-heavy planting with repeated grasses and seasonal accents."

    },

    "Woodland": {

        "species\_limit": 7,

        "spacing\_multiplier": 1.06,

        "description": "Layered canopy, structure, and understory pockets."

    },

    "Coastal": {

        "species\_limit": 6,

        "spacing\_multiplier": 1.02,

        "description": "Coastal meadow and bluff-compatible plant groupings."

    },

    "Dry": {

        "species\_limit": 6,

        "spacing\_multiplier": 1.08,

        "description": "Drought-tolerant structure with open spacing."

    },

}



DESIGN\_STYLE\_OPTIONS = list(STYLE\_LOGIC.keys())



ROLE\_ORDER = sorted({plant["role"] for plant in PLANTS})



DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES = {

    "Canopy": 12,

    "Structure": 22,

    "Matrix": 44,

    "Accent": 22,

}



def default\_role\_percentage(role):

    return DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES.get(role, 20)



HEIGHT\_VARIATION\_BY\_HIERARCHY = {

    "Anchor": 0.06,

    "Mid Layer": 0.10,

    "Accent Layer": 0.15,

    "Groundcover": 0.08

}



\# -----------------------------

\# Helper functions

\# -----------------------------



def clamp\_dimension(value, fallback):

    try:

        value = float(value)

    except Exception:

        return fallback

    return max(1, min(value, MAX\_BED\_FEET))





def get\_canvas\_setup(length\_ft, width\_ft):

    """Return canvas dimensions and true feet-per-canvas-unit scale.



    length\_ft is horizontal. width\_ft is vertical/depth.

    The canvas preserves the real bed aspect ratio and fits inside the max pixel bounds.

    """

    length\_ft = clamp\_dimension(length\_ft, DEFAULT\_BED\_LENGTH\_FEET)

    width\_ft = clamp\_dimension(width\_ft, DEFAULT\_BED\_WIDTH\_FEET)



    pixels\_per\_foot = min(MAX\_CANVAS\_WIDTH / length\_ft, MAX\_CANVAS\_HEIGHT / width\_ft)

    canvas\_width = max(250, int(round(length\_ft \* pixels\_per\_foot)))

    canvas\_height = max(250, int(round(width\_ft \* pixels\_per\_foot)))

    feet\_per\_canvas\_unit = 1 / pixels\_per\_foot

    grid\_spacing\_units = GRID\_SPACING\_FEET / feet\_per\_canvas\_unit



    return canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units





def make\_runtime\_plant\_pool(plants, feet\_per\_canvas\_unit):

    runtime\_plants = []

    for plant in plants:

        p = plant.copy()

        p["radius"] = (p["spread\_ft"] / 2) / feet\_per\_canvas\_unit

        p["style\_fit"] = STYLE\_FIT\_BY\_CODE.get(p.get("code"), ["Naturalized"])

        runtime\_plants.append(p)

    return runtime\_plants





def circle\_inside(poly, x, y, r):

    return poly.contains(Point(x, y).buffer(r))





def circles\_overlap(x, y, r, placed, spacing\_factor, plant=None):

    for p in placed:

        existing\_plant = p["plant"]



        existing\_allows\_underplanting = existing\_plant.get("allows\_underplanting", False)

        current\_allows\_underplanting = plant is not None and plant.get("allows\_underplanting", False)



        if existing\_allows\_underplanting and not current\_allows\_underplanting:

            continue



        if current\_allows\_underplanting and not existing\_allows\_underplanting:

            continue



        distance = math.dist((x, y), (p["x"], p["y"]))

        min\_distance = (r + p["radius"]) \* spacing\_factor



        if distance < min\_distance:

            return True



    return False





def weighted\_choice(plants):

    if not plants:

        return None



    weights = [p.get("weight", 1) for p in plants]

    return random.choices(plants, weights=weights, k=1)[0]





def pack\_layer(poly, plants, target\_area, spacing\_factor, existing\_placed, max\_plants\_total):

    if not plants:

        return [], 0



    minx, miny, maxx, maxy = poly.bounds

    placed\_layer = []

    placed\_area = 0

    attempts = 0

    max\_attempts = 16000



    while (

        placed\_area < target\_area

        and attempts < max\_attempts

        and len(existing\_placed) + len(placed\_layer) < max\_plants\_total

    ):

        attempts += 1



        plant = weighted\_choice(plants)

        if plant is None:

            break



        r = plant["radius"]



        if maxx - minx < r \* 2 or maxy - miny < r \* 2:

            break



        x = random.uniform(minx + r, maxx - r)

        y = random.uniform(miny + r, maxy - r)



        if not circle\_inside(poly, x, y, r):

            continue



        all\_existing = existing\_placed + placed\_layer



        if circles\_overlap(x, y, r, all\_existing, spacing\_factor, plant):

            continue



        placed\_layer.append({"x": x, "y": y, "radius": r, "plant": plant})

        placed\_area += math.pi \* (r \*\* 2)



    return placed\_layer, placed\_area





def pack\_by\_role(poly, plant\_pool, target\_coverage, spacing\_factor, max\_plants\_total, role\_split=None):

    boundary\_area = poly.area



    if boundary\_area <= 0:

        return [], 0



    total\_target\_area = boundary\_area \* target\_coverage

    all\_placed = []

    total\_placed\_area = 0



    active\_roles = [role for role in ROLE\_ORDER if any(p["role"] == role for p in plant\_pool)]



    if not active\_roles:

        return [], 0



    if role\_split is None:

        total\_default = sum(default\_role\_percentage(role) for role in active\_roles) or 1

        role\_split = {

            role: default\_role\_percentage(role) / total\_default

            for role in active\_roles

        }



    for role in active\_roles:

        role\_plants = [p for p in plant\_pool if p["role"] == role]



        if not role\_plants:

            continue



        layer\_target\_area = total\_target\_area \* role\_split.get(role, 0)



        placed\_layer, placed\_area = pack\_layer(

            poly=poly,

            plants=role\_plants,

            target\_area=layer\_target\_area,

            spacing\_factor=spacing\_factor,

            existing\_placed=all\_placed,

            max\_plants\_total=max\_plants\_total

        )



        all\_placed.extend(placed\_layer)

        total\_placed\_area += placed\_area



    return all\_placed, total\_placed\_area / boundary\_area



def sun\_is\_compatible(selected\_sun, plant\_sun\_options):

    sun\_compatibility = {

        "Full Sun": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun"],

        "Full Sun-Part Shade": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade", "Part Shade-Full Shade"],

        "Part Shade": ["Part Shade", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade-Full Shade"],

        "Part Shade-Full Shade": ["Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"],

    }



    compatible\_values = sun\_compatibility.get(selected\_sun, [selected\_sun])

    return any(sun\_value in compatible\_values for sun\_value in plant\_sun\_options)





def water\_is\_compatible(selected\_water, plant\_water\_options):

    water\_compatibility = {

        "Low": ["Low", "Moderate-Low", "Low-Moderate"],

        "Moderate-Low": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Low-Moderate": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Moderate": ["Moderate", "Low-Moderate", "Moderate-Low"],

    }



    compatible\_values = water\_compatibility.get(selected\_water, [selected\_water])

    return any(water\_value in compatible\_values for water\_value in plant\_water\_options)





def hardiness\_is\_compatible(selected\_zones, usda\_min, usda\_max):

    if not selected\_zones:

        return True

    return any(usda\_min <= zone <= usda\_max for zone in selected\_zones)





def filter\_plants(plant\_database, state, climate, selected\_usda\_zones, sun, water):

    return [

        plant for plant in plant\_database

        if state in plant["state"]

        and climate in plant["climate"]

        and hardiness\_is\_compatible(selected\_usda\_zones, plant["usda\_min"], plant["usda\_max"])

        and sun\_is\_compatible(sun, plant["sun"])

        and water\_is\_compatible(water, plant["water"])

    ]





def filter\_plants\_by\_style(plant\_database, design\_style):

    return [

        plant for plant in plant\_database

        if design\_style in plant.get("style\_fit", [])

    ]





def limit\_palette\_by\_style(plant\_database, design\_style):

    """Keep the generated palette focused so layouts feel intentional.



    Forced-included plants are added after this function, so user intent still wins.

    Sorting favors lower design tiers first, then higher visual weight, then database weight.

    """

    settings = STYLE\_LOGIC.get(design\_style, STYLE\_LOGIC["Naturalized"])

    species\_limit = settings.get("species\_limit", 8)



    if len(plant\_database) <= species\_limit:

        return plant\_database



    sorted\_plants = sorted(

        plant\_database,

        key=lambda p: (

            p.get("design\_tier", 5),

            -p.get("visual\_weight", 1),

            -p.get("weight", 1),

            p.get("name", "")

        )

    )



    selected = sorted\_plants[:species\_limit]



    # Always preserve at least one matrix plant when available.

    if not any(p.get("role") == "Matrix" for p in selected):

        matrix\_candidates = [p for p in sorted\_plants if p.get("role") == "Matrix"]

        if matrix\_candidates and selected:

            selected[-1] = matrix\_candidates[0]



    return selected



def get\_polygon\_from\_canvas(canvas\_json):

    if canvas\_json is None:

        return None



    objects = canvas\_json.get("objects", [])

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





def normalize\_polygon(points):

    if points is None or len(points) < 3:

        return None

    poly = Polygon(points)

    if not poly.is\_valid:

        poly = poly.buffer(0)

    if poly.is\_empty or poly.area <= 0:

        return None

    return poly





def polygon\_points\_from\_geometry(geom):

    if geom is None or geom.is\_empty:

        return []

    if geom.geom\_type == "Polygon":

        return [(float(x), float(y)) for x, y in list(geom.exterior.coords)[:-1]]

    if geom.geom\_type == "MultiPolygon":

        largest = max(list(geom.geoms), key=lambda g: g.area)

        return [(float(x), float(y)) for x, y in list(largest.exterior.coords)[:-1]]

    return []





def valid\_role\_zones\_for\_boundary(role\_zones, main\_poly):

    valid = {}

    for role, points in (role\_zones or {}).items():

        zone\_poly = normalize\_polygon(points)

        if zone\_poly is None:

            continue

        clipped = zone\_poly.intersection(main\_poly)

        if clipped.is\_empty or clipped.area <= 0:

            continue

        valid[role] = clipped

    return valid





def rectangle\_points(canvas\_width, canvas\_height):

    return [(0, 0), (canvas\_width, 0), (canvas\_width, canvas\_height), (0, canvas\_height)]





def fig\_to\_png\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="png", dpi=200, bbox\_inches="tight", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_jpeg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="jpg", dpi=200, bbox\_inches="tight", facecolor="white", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_svg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="svg", bbox\_inches="tight")

    buffer.seek(0)

    return buffer





def canvas\_area\_to\_sqft(area\_canvas\_units, feet\_per\_canvas\_unit):

    return area\_canvas\_units \* (feet\_per\_canvas\_unit \*\* 2)





def canvas\_length\_to\_feet(length\_canvas\_units, feet\_per\_canvas\_unit):

    return length\_canvas\_units \* feet\_per\_canvas\_unit





def draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units):

    x = 0

    while x <= canvas\_width:

        ax.axvline(x, linewidth=0.4, alpha=0.25)

        x += grid\_spacing\_units



    y = 0

    while y <= canvas\_height:

        ax.axhline(y, linewidth=0.4, alpha=0.25)

        y += grid\_spacing\_units





def get\_image\_aspect\_ratio(image\_path):

    try:

        img = plt.imread(image\_path)

        height\_px, width\_px = img.shape[:2]

        if height\_px == 0:

            return 1

        return width\_px / height\_px

    except Exception:

        return 1





def varied\_height(plant):

    tolerance = HEIGHT\_VARIATION\_BY\_HIERARCHY.get(plant["hierarchy"], 0.08)

    variation = random.uniform(1 - tolerance, 1 + tolerance)

    return plant["elevation\_height"] \* variation





def prepare\_uploaded\_image(uploaded\_file, canvas\_width, canvas\_height):

    if uploaded\_file is None:

        return None, None



    image = Image.open(uploaded\_file).convert("RGB")

    image = image.resize((canvas\_width, canvas\_height))

    image\_array = plt.imread(BytesIO(image\_to\_png\_bytes(image).getvalue()))

    return image, image\_array





def render\_trace\_overlay(image, points, canvas\_width, canvas\_height):

    """Return a PIL image with the uploaded background plus the clicked/traced bedline points.



    This avoids relying on streamlit-drawable-canvas background\_image, which can render

    blank on Streamlit Cloud. Users click around the bedline directly on the image.

    """

    if image is None:

        return None



    overlay = image.copy().convert("RGB")

    overlay = overlay.resize((canvas\_width, canvas\_height))

    draw = ImageDraw\.Draw(overlay)



    if len(points) >= 2:

        draw\.line(points, fill=(255, 255, 255), width=3)



    if len(points) >= 3:

        # Light preview of the closing segment so users understand the final polygon.

        draw\.line([points[-1], points[0]], fill=(255, 255, 255), width=2)



    for idx, (x, y) in enumerate(points):

        r = 5

        draw\.ellipse((x - r, y - r, x + r, y + r), fill=(255, 80, 80), outline=(255, 255, 255), width=2)

        draw\.text((x + 7, y - 7), str(idx + 1), fill=(255, 255, 255))



    return overlay





def image\_to\_png\_bytes(image):

    buffer = BytesIO()

    image.save(buffer, format="PNG")

    buffer.seek(0)

    return buffer





def escape\_svg\_text(value):

    return html.escape(str(value), quote=True)





def plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit, role\_zones=None):

    """Create a clean vector SVG of the plan geometry.



    This avoids relying on Matplotlib's SVG output and gives you true circle/vector objects.

    """

    path\_points = " ".join([f"{x:.2f},{y:.2f}" for x, y in points])

    svg = StringIO()

    svg.write(f'\<svg xmlns="http\://www\.w3.org/2000/svg" width="{canvas\_width}" height="{canvas\_height}" viewBox="0 0 {canvas\_width} {canvas\_height}">\n')

    svg.write('\<rect width="100%" height="100%" fill="white"/>\n')

    svg.write(f'\<polygon points="{path\_points}" fill="none" stroke="black" stroke-width="2"/>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        zone\_path = " ".join([f"{x:.2f},{y:.2f}" for x, y in zone\_points])

        first\_x, first\_y = zone\_points[0]

        svg.write(f'\<polygon points="{zone\_path}" fill="none" stroke="black" stroke-width="1" stroke-dasharray="4 4" opacity="0.45"/>\n')

        svg.write(f'\<text x="{first\_x:.2f}" y="{first\_y:.2f}" font-family="Arial" font-size="10" opacity="0.65">{escape\_svg\_text(role)} zone\</text>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        closed\_zone = zone\_points + [zone\_points[0]]

        layer\_name = f"ROLE\_ZONE\_{role.upper().replace(' ', '\_')}"

        for i in range(len(closed\_zone) - 1):

            x1, y1 = closed\_zone[i]

            x2, y2 = closed\_zone[i + 1]

            dxf.write("0\nLINE\n8\n" + layer\_name + "\n")

            dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

            dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dash = ' stroke-dasharray="6 4"' if plant.get("allows\_underplanting", False) else ""

        weight = "bold" if plant.get("allows\_underplanting", False) else "normal"

        svg.write(f'\<circle cx="{item["x"]:.2f}" cy="{item["y"]:.2f}" r="{item["radius"]:.2f}" fill="none" stroke="black" stroke-width="1.2"{dash}/>\n')

        svg.write(f'\<text x="{item["x"]:.2f}" y="{item["y"]:.2f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="8" font-weight="{weight}">{escape\_svg\_text(plant["code"])}\</text>\n')



    svg.write(f'\<text x="12" y="{canvas\_height - 14}" font-family="Arial" font-size="10">Scale: 1 px = {feet\_per\_canvas\_unit:.3f} ft\</text>\n')

    svg.write('\</svg>')

    return BytesIO(svg.getvalue().encode("utf-8"))





def plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit, role\_zones=None):

    """Export a simple ASCII DXF in real feet.



    AutoCAD, Rhino, Vectorworks, and many CAD tools can open DXF. This is the practical

    Streamlit-friendly alternative to DWG.

    """

    dxf = StringIO()

    dxf.write("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n2\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nENTITIES\n")



    closed\_points = points + [points[0]]

    for i in range(len(closed\_points) - 1):

        x1, y1 = closed\_points[i]

        x2, y2 = closed\_points[i + 1]

        dxf.write("0\nLINE\n8\nBOUNDARY\n")

        dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dxf.write("0\nCIRCLE\n8\nPLANTS\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"40\n{item['radius'] \* feet\_per\_canvas\_unit:.4f}\n")

        dxf.write("0\nTEXT\n8\nPLANT\_CODES\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write("40\n0.35\n")

        dxf.write(f"1\n{plant['code']}\n")



    dxf.write("0\nENDSEC\n0\nEOF\n")

    return BytesIO(dxf.getvalue().encode("utf-8"))



\# -----------------------------

\# Sidebar

\# -----------------------------



with st.sidebar:

    st.markdown("### by The Landscape Library")



    st.header("Input Method")

    input\_method = st.radio(

        "Choose how to define the planting bed",

        ["Draw Boundary", "Upload JPEG Image"],

        index=0

    )



    st.info("Max 50' bed")



    if input\_method == "Upload JPEG Image":

        st.caption("Upload a JPEG image as a scaled reference, then click points around the actual bedline.")

        uploaded\_bed\_image = st.file\_uploader(

            "Upload bed image",

            type=["jpg", "jpeg"]

        )



        bed\_length\_ft = st.number\_input(

            "Image length / horizontal dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=30.0,

            step=1.0

        )



        bed\_width\_ft = st.number\_input(

            "Image width / vertical dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=15.0,

            step=1.0

        )

    else:

        uploaded\_bed\_image = None

        bed\_length\_ft = DEFAULT\_BED\_LENGTH\_FEET

        bed\_width\_ft = DEFAULT\_BED\_WIDTH\_FEET



    canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units = get\_canvas\_setup(

        bed\_length\_ft,

        bed\_width\_ft

    )



    st.header("Site Parameters")



    state = st.selectbox("State", ["California"])

    climate = st.selectbox("California Plant Community", ["Coastal", "Inland", "Dry", "Woodland"])



    design\_style = st.selectbox(

        "Design Style",

        DESIGN\_STYLE\_OPTIONS,

        index=0

    )

    st.caption(STYLE\_LOGIC[design\_style]["description"])



    st.markdown("\*\*USDA Hardiness\*\*")

    st.caption("Select one or more USDA zones. Plants are included when the selected zone falls between USDA Min and USDA Max in the plant database.")

    usda\_zone\_options = list(range(5, 11))

    default\_usda\_zones = [9]

    selected\_usda\_zones = []

    zone\_cols = st.columns(3)

    for idx, zone in enumerate(usda\_zone\_options):

        with zone\_cols[idx % 3]:

            checked = st.checkbox(f"Zone {zone}", value=zone in default\_usda\_zones, key=f"usda\_zone\_{zone}")

            if checked:

                selected\_usda\_zones.append(zone)



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



    target\_coverage = DENSITY\_OPTIONS[density]

    spacing\_factor = SPACING\_BY\_DENSITY[density] \* STYLE\_LOGIC[design\_style]["spacing\_multiplier"]

    max\_plants\_total = MAX\_PLANTS\_BY\_DENSITY[density]



    st.header("Scale")

    st.caption(f"Bed limit: {MAX\_BED\_FEET} ft max length or width")

    st.caption(f"Active bed: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")



\# -----------------------------

\# Active plant database + image prep

\# -----------------------------



runtime\_plants = make\_runtime\_plant\_pool(PLANTS, feet\_per\_canvas\_unit)

selected\_plants = filter\_plants(runtime\_plants, state, climate, selected\_usda\_zones, sun, water)

selected\_plants = filter\_plants\_by\_style(selected\_plants, design\_style)



\# Manual include / exclude controls

all\_matching\_names = [p["name"] for p in selected\_plants]

with st.sidebar:

    st.header("Plant Controls")

    include\_names = st.multiselect("Force include plants", [p["name"] for p in runtime\_plants])

    exclude\_names = st.multiselect("Exclude plants", all\_matching\_names)



role\_split = None



forced = [p for p in runtime\_plants if p["name"] in include\_names]

selected\_plants = [p for p in selected\_plants if p["name"] not in exclude\_names]

selected\_plants = limit\_palette\_by\_style(selected\_plants, design\_style)



for p in forced:

    if p["name"] not in [sp["name"] for sp in selected\_plants]:

        selected\_plants.append(p)



background\_image = None

background\_array = None



if input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    background\_image, background\_array = prepare\_uploaded\_image(uploaded\_bed\_image, canvas\_width, canvas\_height)



\# -----------------------------

\# Main UI

\# -----------------------------



left, right = st.columns([2, 1])



with left:

    if input\_method == "Draw Boundary":

        st.subheader("1. Draw Planting Boundary")

        st.caption("TIP: Left click to add boundary points. Right click to end nearest the origin point and complete the boundary.")

        st.caption('Drawing canvas: 50\\'-0" horizontal × 50\\'-0" vertical.')



        canvas\_result = st\_canvas(

            fill\_color="rgba(0, 0, 0, 0)",

            stroke\_width=3,

            stroke\_color="#111111",

            background\_color="#f7f7f2",

            height=canvas\_height,

            width=canvas\_width,

            drawing\_mode="polygon",

            key="draw\_boundary\_canvas",

        )

    else:

        st.subheader("1. Upload Scaled Bed Image + Trace Bedline")

        st.caption("Click around the planting bedline in order. Use more points for curves. The final segment closes automatically between the last point and first point.")



        if uploaded\_bed\_image is None:

            st.warning("Upload a JPEG image first, then click points around the actual bedline.")

            canvas\_result = None

        else:

            canvas\_result = None



            if streamlit\_image\_coordinates is None:

                st.error("Missing package: streamlit-image-coordinates. Add streamlit-image-coordinates to requirements.txt, then redeploy.")

            else:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                last\_click\_key = f"last\_click\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"



                if trace\_key not in st.session\_state:

                    st.session\_state[trace\_key] = []

                if last\_click\_key not in st.session\_state:

                    st.session\_state[last\_click\_key] = None



                st.caption("Click points around the bedline in order. Use more points for curves. The final segment closes automatically between the last and first point.")



                overlay\_image = render\_trace\_overlay(

                    background\_image,

                    st.session\_state[trace\_key],

                    canvas\_width,

                    canvas\_height

                )



                clicked = streamlit\_image\_coordinates(

                    overlay\_image,

                    key=f"click\_trace\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}",

                    width=canvas\_width

                )



                if clicked is not None and "x" in clicked and "y" in clicked:

                    new\_point = (int(clicked["x"]), int(clicked["y"]))



                    if st.session\_state[last\_click\_key] != new\_point:

                        existing\_points = st.session\_state[trace\_key]



                        # Prevent accidental double-click duplicates.

                        if len(existing\_points) == 0 or math.dist(existing\_points[-1], new\_point) > 4:

                            existing\_points.append(new\_point)

                            st.session\_state[trace\_key] = existing\_points



                        st.session\_state[last\_click\_key] = new\_point

                        st.rerun()



                b1, b2, b3 = st.columns(3)

                with b1:

                    if st.button("Undo Last Point") and len(st.session\_state[trace\_key]) > 0:

                        st.session\_state[trace\_key] = st.session\_state[trace\_key][:-1]

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b2:

                    if st.button("Clear Trace"):

                        st.session\_state[trace\_key] = []

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b3:

                    st.metric("Trace Points", len(st.session\_state[trace\_key]))



                if len(st.session\_state[trace\_key]) < 3:

                    st.info("Add at least 3 points before generating the planting layout.")



with right:

    st.subheader("Request a Plant")

    requested\_plant = st.text\_input("Plant you want added")

    if st.button("Submit Plant Request"):

        if requested\_plant.strip():

            ok, error\_message = log\_plant\_request(

                st.session\_state.get("user\_email"),

                requested\_plant.strip(),

                state=state,

                zone=", ".join([f"USDA {z}" for z in selected\_usda\_zones]),

                climate=climate,

                sun\_exposure=sun,

                water\_needs=water,

                design\_style=design\_style,

            )

            if ok:

                st.success("Plant request submitted.")

            else:

                st.error(f"Plant request was not saved: {error\_message}")

        else:

            st.warning("Enter a plant name before submitting.")



    st.subheader("3. Selected Plant Palette")



    if len(selected\_plants) == 0:

        st.warning("No plants match these parameters yet. Try adjusting design style, USDA hardiness, sun exposure, or water needs.")

    else:

        for plant in selected\_plants:

            canopy\_note = " | allows underplanting" if plant.get("allows\_underplanting", False) else ""

            st.write(f"\*\*{plant['name']}\*\*")

            st.caption(

                f"{plant['code']} | {plant['common\_name']} | {plant['form']} | {plant['role']} | spread: {plant['spread\_ft']} ft{canopy\_note}"

            )



\# -----------------------------

\# Boundary metrics

\# -----------------------------



points\_preview = None



if input\_method == "Draw Boundary" and canvas\_result is not None:

    points\_preview = get\_polygon\_from\_canvas(canvas\_result.json\_data)

elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

    points\_preview = st.session\_state.get(trace\_key, [])

    if len(points\_preview) < 3:

        points\_preview = None



if points\_preview is not None:

    preview\_poly = Polygon(points\_preview)



    if not preview\_poly.is\_valid:

        preview\_poly = preview\_poly.buffer(0)



    if preview\_poly.area > 0:

        area\_sqft = canvas\_area\_to\_sqft(preview\_poly.area, feet\_per\_canvas\_unit)

        perimeter\_ft = canvas\_length\_to\_feet(preview\_poly.length, feet\_per\_canvas\_unit)

        minx\_preview, miny\_preview, maxx\_preview, maxy\_preview = preview\_poly.bounds



        width\_ft = canvas\_length\_to\_feet(maxx\_preview - minx\_preview, feet\_per\_canvas\_unit)

        depth\_ft = canvas\_length\_to\_feet(maxy\_preview - miny\_preview, feet\_per\_canvas\_unit)



        st.subheader("Boundary Metrics")



        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Approx. Area", f"{area\_sqft:,.0f} sq ft")

        c2.metric("Approx. Perimeter", f"{perimeter\_ft:,.0f} ft")

        c3.metric("Approx. Length", f"{width\_ft:,.0f} ft")

        c4.metric("Approx. Width", f"{depth\_ft:,.0f} ft")



generate = st.button("Generate Planting Layout", type="primary")



\# -----------------------------

\# Generate

\# -----------------------------



if generate:

    if supabase is not None and st.session\_state.get("user\_email"):

        user\_check = supabase.table("users").select("\*").eq("email", st.session\_state.user\_email).execute()

        current\_user = user\_check.data[0] if user\_check.data else {}

        if not current\_user.get("paid\_status", False) and (current\_user.get("total\_generations") or 0) >= FREE\_GENERATION\_LIMIT:

            st.warning("You have reached the free generation limit.")

            log\_event(st.session\_state.user\_email, "paywall\_shown")

            st.stop()

    try:

        with st.spinner("Generating planting plan and elevation view\..."):

            if input\_method == "Draw Boundary" and canvas\_result is not None:

                points = get\_polygon\_from\_canvas(canvas\_result.json\_data)

            elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                points = st.session\_state.get(trace\_key, [])

                if len(points) < 3:

                    points = None

            else:

                points = None



            if points is None:

                if input\_method == "Draw Boundary":

                    st.warning("Draw a closed polygon boundary first.")

                else:

                    st.warning("Upload a JPEG image and trace a closed polygon boundary first.")



            elif bed\_length\_ft > MAX\_BED\_FEET or bed\_width\_ft > MAX\_BED\_FEET:

                st.warning(f"The bed is too large. Keep the image dimensions at or below {MAX\_BED\_FEET} ft.")



            elif len(selected\_plants) == 0:

                st.warning("No plants are available for the selected site parameters.")



            else:

                poly = normalize\_polygon(points)



                if poly is None:

                    st.warning("The boundary is invalid. Try tracing a clearer closed shape.")



                else:

                    placed\_instances, actual\_coverage = pack\_by\_role(

                        poly=poly,

                        plant\_pool=selected\_plants,

                        target\_coverage=target\_coverage,

                        spacing\_factor=spacing\_factor,

                        max\_plants\_total=max\_plants\_total,

                        role\_split=role\_split

                    )



                    if len(placed\_instances) == 0:

                        st.warning("No plants could fit inside the boundary. Try a larger area, lower density, or different plant parameters.")



                    else:

                        new\_generation\_count = increment\_generation\_count(st.session\_state.get("user\_email"))

                        log\_event(

                            st.session\_state.get("user\_email"),

                            "generation\_run",

                            state=state,

                            zone=", ".join([f"USDA {z}" for z in selected\_usda\_zones]),

                            climate=climate,

                            sun\_exposure=sun,

                            water\_needs=water,

                            design\_style=design\_style,

                            notes=f"Density: {density}; Plants generated: {len(placed\_instances)}"

                        )



                        st.subheader("Plan View")



                        fig, ax = plt.subplots(figsize=(10, 10))



                        if background\_array is not None:

                            ax.imshow(background\_array, extent=(0, canvas\_width, canvas\_height, 0), alpha=0.35, zorder=0)



                        xs, ys = zip(\*(points + [points[0]]))

                        ax.plot(xs, ys, linewidth=2, zorder=3)



                        draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units)



                        for item in placed\_instances:

                            plant = item["plant"]



                            if plant.get("allows\_underplanting", False):

                                continue



                            circle = plt.Circle(

                                (item["x"], item["y"]),

                                item["radius"],

                                fill=False,

                                linewidth=1.2,

                                zorder=4

                            )

                            ax.add\_patch(circle)



                            ax.text(

                                item["x"],

                                item["y"],

                                plant["code"],

                                ha="center",

                                va="center",

                                fontsize=8,

                                zorder=5

                            )



                        for item in placed\_instances:

                            plant = item["plant"]



                            if not plant.get("allows\_underplanting", False):

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

                            ax.add\_patch(circle)



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



                        ax.set\_xlim(0, canvas\_width)

                        ax.set\_ylim(canvas\_height, 0)

                        ax.set\_aspect("equal")

                        ax.axis("off")



                        st.pyplot(fig)



                        plan\_png = fig\_to\_png\_bytes(fig)

                        plan\_svg = plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit)

                        plan\_dxf = plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit)



                        d1, d2, d3 = st.columns(3)

                        with d1:

                            st.download\_button(

                                label="Download Plan PNG",

                                data=plan\_png,

                                file\_name="yodra-planting-plan.png",

                                mime="image/png"

                            )

                        with d2:

                            st.download\_button(

                                label="Download Plan SVG",

                                data=plan\_svg,

                                file\_name="yodra-planting-plan.svg",

                                mime="image/svg+xml"

                            )

                        with d3:

                            st.download\_button(

                                label="Download Plan DXF",

                                data=plan\_dxf,

                                file\_name="yodra-planting-plan.dxf",

                                mime="application/dxf"

                            )



                        st.caption(f"Target coverage: {round(target\_coverage \* 100)}%")

                        st.caption(f"Actual generated coverage: {round(actual\_coverage \* 100)}%")

                        st.caption(f"Active bed scale: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")

                        st.caption(f"Maximum plant instances capped at {max\_plants\_total} for app performance.")



                        st.subheader("Elevation View")

                        st.caption("Elevation uses the same plant instances generated in plan view, with subtle height variation.")



                        elev\_fig, elev\_ax = plt.subplots(figsize=(12, 4))



                        placed\_sorted = sorted(placed\_instances, key=lambda item: item["x"])



                        for item in placed\_sorted:

                            plant = item["plant"]

                            image\_path = plant["image"]



                            height = varied\_height(plant)

                            aspect\_ratio = get\_image\_aspect\_ratio(image\_path)

                            width = height \* aspect\_ratio



                            if os.path.exists(image\_path):

                                img = plt.imread(image\_path)



                                elev\_ax.imshow(

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

                                elev\_ax.text(

                                    item["x"],

                                    height / 2,

                                    plant["code"],

                                    ha="center",

                                    va="center",

                                    fontsize=8

                                )



                        elev\_ax.axhline(0, linewidth=1)

                        elev\_ax.set\_xlim(0, canvas\_width)

                        elev\_ax.set\_ylim(0, 140)

                        elev\_ax.axis("off")



                        st.pyplot(elev\_fig)



                        elevation\_png = fig\_to\_png\_bytes(elev\_fig)

                        elevation\_jpeg = fig\_to\_jpeg\_bytes(elev\_fig)



                        e1, e2 = st.columns(2)

                        with e1:

                            st.download\_button(

                                label="Download Elevation PNG",

                                data=elevation\_png,

                                file\_name="yodra-planting-elevation.png",

                                mime="image/png"

                            )

                        with e2:

                            st.download\_button(

                                label="Download Elevation JPEG",

                                data=elevation\_jpeg,

                                file\_name="yodra-planting-elevation.jpg",

                                mime="image/jpeg"

                            )



                        counts = {}

                        for item in placed\_instances:

                            plant = item["plant"]

                            counts[plant["name"]] = counts.get(plant["name"], 0) + 1



                        st.subheader("Plant Schedule")



                        schedule = []

                        for plant\_name, count in counts.items():

                            plant = next(p for p in runtime\_plants if p["name"] == plant\_name)



                            schedule.append({

                                "Code": plant["code"],

                                "Count": count,

                                "Botanical Name": plant["name"],

                                "Common Name": plant["common\_name"],

                                "Form": plant["form"],

                                "Role": plant["role"],

                                "Texture": plant["texture"],

                                "Color Tone": plant["color\_tone"],

                                "Visual Weight": plant["visual\_weight"],

                                "Spread Ft": plant["spread\_ft"],

                                "Height Ft": plant["height\_ft"],

                                "State": state,

                                "Climate": ", ".join(plant["climate"]),

                                "USDA Min": plant["usda\_min"],

                                "USDA Max": plant["usda\_max"],

                                "Sun": ", ".join(plant["sun"]),

                                "Water": ", ".join(plant["water"]),

                                "Seasonality": plant["seasonality"],

                                "Style Fit": ", ".join(plant.get("style\_fit", [])),

                                "Allows Underplanting": plant.get("allows\_underplanting", False)

                            })



                        schedule\_df = pd.DataFrame(schedule)

                        st.dataframe(schedule\_df, width="stretch")



                        csv\_buffer = schedule\_df.to\_csv(index=False).encode("utf-8")

                        st.download\_button(

                            label="Download Plant Schedule CSV / Excel",

                            data=csv\_buffer,

                            file\_name="yodra-plant-schedule.csv",

                            mime="text/csv",

                            on\_click=lambda: increment\_export\_count(st.session\_state.get("user\_email"))

                        )

                        log\_event(st.session\_state.get("user\_email"), "schedule\_export\_ready", export\_type="csv")



    except Exception as e:

        st.error("The app crashed while generating the layout.")

        st.exception(e)



























---





# Version 3.2





import streamlit as st

from datetime import datetime, timezone

try:

    from supabase import create\_client

except Exception:

    create\_client = None

import pandas as pd



\# -------------------------

\# SUPABASE USER TRACKING

\# -------------------------



FREE\_GENERATION\_LIMIT = 999



def get\_supabase\_client():

    if create\_client is None:

        return None

    url = st.secrets.get("SUPABASE\_URL", "")

    key = st.secrets.get("SUPABASE\_SERVICE\_ROLE\_KEY", "")

    if not url or not key:

        return None

    return create\_client(url, key)



supabase = get\_supabase\_client()



def log\_event(email, event\_type, \*\*kwargs):

    """Insert an event using only the columns that exist in the current Supabase events table.



    Current expected columns:

    email, event\_type, created\_at, climate, sun\_exposure, water\_needs,

    design\_style, export\_type, notes.



    Do not add state, zone, density, or plants\_generated\_count unless those columns

    are also added to Supabase. Supabase will reject inserts when unknown columns

    are included.

    """

    if supabase is None or not email:

        return False, "Supabase is not connected or user email is missing."



    event = {

        "email": email,

        "event\_type": event\_type,

        "created\_at": datetime.now(timezone.utc).isoformat(),

        "climate": kwargs.get("climate"),

        "sun\_exposure": kwargs.get("sun\_exposure"),

        "water\_needs": kwargs.get("water\_needs"),

        "design\_style": kwargs.get("design\_style"),

        "export\_type": kwargs.get("export\_type"),

        "notes": kwargs.get("notes"),

    }



    # Remove empty optional fields so Supabase receives a clean payload.

    event = {k: v for k, v in event.items() if v is not None}



    try:

        supabase.table("events").insert(event).execute()

        return True, None

    except Exception as e:

        return False, str(e)





def log\_plant\_request(email, requested\_plant, \*\*kwargs):

    requested\_plant = (requested\_plant or "").strip()

    if not requested\_plant:

        return False, "Plant request is empty."



    ok, err = log\_event(

        email,

        "plant\_requested",

        notes=requested\_plant,

        \*\*kwargs

    )



    # Optional dedicated table. If you create a plant\_requests table in Supabase,

    # this will also save requests there. If that table does not exist, the

    # events table above is still the primary tracking location.

    if supabase is not None and email:

        try:

            supabase.table("plant\_requests").insert({

                "email": email,

                "requested\_plant": requested\_plant,

                "created\_at": datetime.now(timezone.utc).isoformat(),

                "climate": kwargs.get("climate"),

                "sun\_exposure": kwargs.get("sun\_exposure"),

                "water\_needs": kwargs.get("water\_needs"),

                "notes": requested\_plant,

            }).execute()

        except Exception:

            pass



    return ok, err



def get\_or\_create\_user(email):

    email = email.strip().lower()

    if supabase is None:

        return {"email": email, "paid\_status": False, "total\_generations": 0, "total\_exports": 0}



    now = datetime.now(timezone.utc).isoformat()

    result = supabase.table("users").select("\*").eq("email", email).execute()

    if result.data:

        user = result.data[0]

        supabase.table("users").update({"last\_seen": now}).eq("email", email).execute()

        return user



    new\_user = {

        "email": email,

        "first\_seen": now,

        "last\_seen": now,

        "paid\_status": False,

        "total\_generations": 0,

        "total\_exports": 0,

    }

    created = supabase.table("users").insert(new\_user).execute()

    return created.data[0] if created.data else new\_user



def increment\_generation\_count(email):

    if supabase is None:

        return 0

    result = supabase.table("users").select("total\_generations").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_generations") or 0

    new\_count = current + 1

    supabase.table("users").update({

        "total\_generations": new\_count,

        "last\_seen": datetime.now(timezone.utc).isoformat()

    }).eq("email", email).execute()

    return new\_count



def increment\_export\_count(email):

    if supabase is None:

        return

    result = supabase.table("users").select("total\_exports").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_exports") or 0

    supabase.table("users").update({"total\_exports": current + 1}).eq("email", email).execute()



def beta\_email\_gate():

    if "user\_email" not in st.session\_state:

        st.session\_state.user\_email = None

    if st.session\_state.user\_email:

        return True



    st.title("Native Plant Layout Engine by The Landscape Library")

    st.markdown("### Enter your email to begin generating planting layouts.")

    email = st.text\_input("Enter your email to continue")

    if st.button("Continue"):

        if "@" not in email or "." not in email:

            st.error("Please enter a valid email address.")

            st.stop()

        user = get\_or\_create\_user(email)

        st.session\_state.user\_email = user["email"]

        st.session\_state.user\_data = user

        log\_event(user["email"], "app\_opened")

        st.rerun()

    st.stop()



beta\_email\_gate()





\# -------------------------

\# YOUR APP BELOW

\# -------------------------



import random

import math

import os

import html

import base64

from io import BytesIO, StringIO



import matplotlib.pyplot as plt

from PIL import Image, ImageDraw

from shapely.geometry import Polygon, Point

from streamlit\_drawable\_canvas import st\_canvas

try:

    from streamlit\_image\_coordinates import streamlit\_image\_coordinates

except Exception:

    streamlit\_image\_coordinates = None



\# -----------------------------

\# Compatibility patch

\# -----------------------------

\# streamlit-drawable-canvas still calls an older Streamlit helper named

\# st.image.image\_to\_url when using background\_image. Newer Streamlit versions

\# removed that helper, which causes an AttributeError on image upload.

\# This patch restores the expected helper by converting the PIL background image

\# into a browser-safe base64 data URL.

def \_yodra\_image\_to\_url(image, width=None, clamp=False, channels="RGB", output\_format="PNG", image\_id=None):

    """Compatibility helper for streamlit-drawable-canvas background images.



    Newer Streamlit versions removed st.image.image\_to\_url, but

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

    return f"data\:image/png;base64,{encoded}"



try:

    # This is the exact object streamlit-drawable-canvas references: st.image.image\_to\_url

    st.image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



try:

    # Also patch Streamlit's image module for environments that reference it directly.

    import streamlit.elements.image as st\_image

    st\_image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



st.set\_page\_config(

    page\_title="Native Plant Layout Engine",

    layout="wide"

)



st.title("Native Plant Layout Engine")

st.caption("A California native planting layout generator for naturalistic and restorative landscape studies, plant palettes, plan views, elevation views, and schedules.")



\# -----------------------------

\# Canvas + Scale settings

\# -----------------------------



MAX\_CANVAS\_WIDTH = 900

MAX\_CANVAS\_HEIGHT = 600

DEFAULT\_BED\_LENGTH\_FEET = 50

DEFAULT\_BED\_WIDTH\_FEET = 50

MAX\_BED\_FEET = 50



GRID\_SPACING\_FEET = 5



DENSITY\_OPTIONS = {

    "Low": 0.30,

    "Moderate": 0.45,

    "Dense": 0.68,

    "Very Dense": 0.90

}



SPACING\_BY\_DENSITY = {

    "Low": 1.30,

    "Moderate": 1.15,

    "Dense": 1.05,

    "Very Dense": 1.00

}



MAX\_PLANTS\_BY\_DENSITY = {

    "Low": 180,

    "Moderate": 260,

    "Dense": 350,

    "Very Dense": 500

}



\# Placeholder used only while the plant database is being defined.

\# Runtime radii are recalculated after the active bed scale is known.

def feet\_to\_canvas\_radius(width\_ft):

    return width\_ft / 2



\# -----------------------------

\# Plant database

\# -----------------------------



PLANTS = [

    {

        "name": "Carex pansa",

        "common\_name": "Sand Dune Sedge",

        "code": "CP",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 1,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-pansa.webp",

        "elevation\_height": 28,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum latifolium",

        "common\_name": "Coast Buckwheat",

        "code": "EL",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Silver-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-latifolium.webp",

        "elevation\_height": 34,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Festuca californica",

        "common\_name": "California Fescue",

        "code": "FC",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/festuca-californica.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Salvia spathacea",

        "common\_name": "Hummingbird Sage",

        "code": "SS",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/salvia-spathacea.webp",

        "elevation\_height": 42,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Iris douglasiana",

        "common\_name": "Douglas Iris",

        "code": "ID",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/iris-douglasiana.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Arbutus menziesii",

        "common\_name": "Pacific Madrone",

        "code": "AM",

        "state": ["California"],

        "climate": ["Coastal", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 20,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(20),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arbutus-menziesii.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Arctostaphylos densiflora 'Howard McMinn'",

        "common\_name": "Howard McMinn Manzanita",

        "code": "AHM",

        "state": ["California"],

        "climate": ["Coastal", "Inland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 8,

        "height\_ft": 7,

        "radius": feet\_to\_canvas\_radius(8),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arctostaphylos-howard-mcminn.webp",

        "elevation\_height": 105,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

    {

        "name": "Muhlenbergia rigens",

        "common\_name": "Deergrass",

        "code": "MR",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/muhlenbergia-rigens.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Stipa pulchra",

        "common\_name": "Purple Needlegrass",

        "code": "SP",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Golden Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/stipa-pulchra.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Juncus patens",

        "common\_name": "Common Rush",

        "code": "JP",

        "state": ["California"],

        "climate": ["Inland", "Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 3,

        "height\_ft": 3,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/juncus-patens.webp",

        "elevation\_height": 46,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum fasciculatum",

        "common\_name": "California Buckwheat",

        "code": "EF",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-fasciculatum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Epilobium canum",

        "common\_name": "California Fuchsia",

        "code": "EC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Semi-evergreen",

        "image": "plant\_images/epilobium-canum.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Artemisia californica",

        "common\_name": "California Sagebrush",

        "code": "AC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Silver-Grey",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/artemisia-californica.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Quercus chrysolepis",

        "common\_name": "Canyon Live Oak",

        "code": "QC",

        "state": ["California"],

        "climate": ["Inland", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 30,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(30),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/quercus-chrysolepis.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Carex tumulicola",

        "common\_name": "Foothill Sedge",

        "code": "CT",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Sun"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-tumulicola.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Polystichum munitum",

        "common\_name": "Western Sword Fern",

        "code": "PM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 5,

        "usda\_max": 9,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/polystichum-munitum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Heuchera maxima",

        "common\_name": "Island Alum Root",

        "code": "HM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/heuchera-maxima.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Ribes sanguineum",

        "common\_name": "Red-Flowering Currant",

        "code": "RS",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 6,

        "height\_ft": 8,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Deciduous",

        "image": "plant\_images/ribes-sanguineum.webp",

        "elevation\_height": 110,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Woodwardia fimbriata",

        "common\_name": "Giant Chain Fern",

        "code": "WF",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 6,

        "height\_ft": 5,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/woodwardia-fimbriata.webp",

        "elevation\_height": 70,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Acer circinatum",

        "common\_name": "Vine Maple",

        "code": "ACI",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 15,

        "height\_ft": 20,

        "radius": feet\_to\_canvas\_radius(15),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 3,

        "seasonality": "Deciduous",

        "image": "plant\_images/acer-circinatum.webp",

        "elevation\_height": 125,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Heteromeles arbutifolia",

        "common\_name": "Toyon",

        "code": "HA",

        "state": ["California"],

        "climate": ["Woodland", "Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 10,

        "height\_ft": 15,

        "radius": feet\_to\_canvas\_radius(10),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/heteromeles-arbutifolia.webp",

        "elevation\_height": 118,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

]







STYLE\_FIT\_BY\_CODE = {

    # Wild / Naturalized is intentionally broad: it allows the engine to mix canopy,

    # structure, matrix, and accents after USDA/sun/water filtering.

    "CP": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "EL": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "FC": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "SS": ["Wild / Naturalized", "Perennial Garden", "Woodland Garden"],

    "ID": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Woodland Garden"],

    "AM": ["Wild / Naturalized", "Woodland Garden", "Contemporary"],

    "AHM": ["Contemporary", "Wild / Naturalized", "Dry Garden"],

    "MR": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "SP": ["Wild / Naturalized", "Meadow"],

    "JP": ["Wild / Naturalized", "Meadow", "Contemporary"],

    "EF": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "EC": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "AC": ["Wild / Naturalized", "Dry Garden", "Meadow", "Contemporary"],

    "QC": ["Wild / Naturalized", "Woodland Garden"],

    "CT": ["Wild / Naturalized", "Woodland Garden", "Contemporary"],

    "PM": ["Woodland Garden", "Wild / Naturalized"],

    "HM": ["Woodland Garden", "Wild / Naturalized", "Perennial Garden", "Contemporary"],

    "RS": ["Woodland Garden", "Wild / Naturalized"],

    "WF": ["Woodland Garden", "Wild / Naturalized"],

    "AV": ["Woodland Garden", "Wild / Naturalized", "Contemporary"],

    "HA": ["Woodland Garden", "Contemporary", "Wild / Naturalized", "Dry Garden"],

}



STYLE\_LOGIC = {

    "Wild / Naturalized": {

        "species\_limit": 9,

        "spacing\_multiplier": 1.00,

        "description": "Mixed, ecological planting with canopy, structure, grasses, perennials, and accents.",

        "form\_priority": [],

        "role\_boost": {"Matrix": 1.15, "Accent": 1.05, "Structure": 1.0, "Canopy": 0.8},

    },

    "Contemporary": {

        "species\_limit": 5,

        "spacing\_multiplier": 1.20,

        "description": "Fewer species, stronger repeated masses, cleaner spacing, and more negative space.",

        "form\_priority": ["Grass", "Shrub", "Tree", "Fern", "Perennial"],

        "role\_boost": {"Structure": 1.35, "Matrix": 1.25, "Canopy": 1.0, "Accent": 0.75},

    },

    "Meadow": {

        "species\_limit": 6,

        "spacing\_multiplier": 0.96,

        "description": "Mostly grasses with limited seasonal accents for a meadow-like field condition.",

        "form\_priority": ["Grass", "Perennial", "Shrub"],

        "role\_boost": {"Matrix": 1.6, "Accent": 1.0, "Structure": 0.45, "Canopy": 0.15},

    },

    "Perennial Garden": {

        "species\_limit": 7,

        "spacing\_multiplier": 1.02,

        "description": "Flowering and textural perennial emphasis, supported by restrained matrix plants.",

        "form\_priority": ["Perennial", "Grass"],

        "role\_boost": {"Accent": 1.55, "Matrix": 1.0, "Structure": 0.35, "Canopy": 0.0},

    },

    "Woodland Garden": {

        "species\_limit": 7,

        "spacing\_multiplier": 1.08,

        "description": "Shade-tolerant canopy, structure, ferns, sedges, and understory pockets.",

        "form\_priority": ["Tree", "Shrub", "Fern", "Grass", "Perennial"],

        "role\_boost": {"Canopy": 1.25, "Structure": 1.15, "Matrix": 1.25, "Accent": 1.0},

    },

    "Dry Garden": {

        "species\_limit": 6,

        "spacing\_multiplier": 1.12,

        "description": "Low-water grasses, shrubs, and silver-textured plants with open spacing.",

        "form\_priority": ["Shrub", "Grass", "Perennial"],

        "role\_boost": {"Structure": 1.25, "Matrix": 1.15, "Accent": 1.0, "Canopy": 0.35},

    },

}



DESIGN\_STYLE\_OPTIONS = list(STYLE\_LOGIC.keys())



ROLE\_ORDER = sorted({plant["role"] for plant in PLANTS})



DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES = {

    "Canopy": 12,

    "Structure": 22,

    "Matrix": 44,

    "Accent": 22,

}



def default\_role\_percentage(role):

    return DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES.get(role, 20)



HEIGHT\_VARIATION\_BY\_HIERARCHY = {

    "Anchor": 0.06,

    "Mid Layer": 0.10,

    "Accent Layer": 0.15,

    "Groundcover": 0.08

}



\# -----------------------------

\# Helper functions

\# -----------------------------



def clamp\_dimension(value, fallback):

    try:

        value = float(value)

    except Exception:

        return fallback

    return max(1, min(value, MAX\_BED\_FEET))





def get\_canvas\_setup(length\_ft, width\_ft):

    """Return canvas dimensions and true feet-per-canvas-unit scale.



    length\_ft is horizontal. width\_ft is vertical/depth.

    The canvas preserves the real bed aspect ratio and fits inside the max pixel bounds.

    """

    length\_ft = clamp\_dimension(length\_ft, DEFAULT\_BED\_LENGTH\_FEET)

    width\_ft = clamp\_dimension(width\_ft, DEFAULT\_BED\_WIDTH\_FEET)



    pixels\_per\_foot = min(MAX\_CANVAS\_WIDTH / length\_ft, MAX\_CANVAS\_HEIGHT / width\_ft)

    canvas\_width = max(250, int(round(length\_ft \* pixels\_per\_foot)))

    canvas\_height = max(250, int(round(width\_ft \* pixels\_per\_foot)))

    feet\_per\_canvas\_unit = 1 / pixels\_per\_foot

    grid\_spacing\_units = GRID\_SPACING\_FEET / feet\_per\_canvas\_unit



    return canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units





def make\_runtime\_plant\_pool(plants, feet\_per\_canvas\_unit):

    runtime\_plants = []

    for plant in plants:

        p = plant.copy()

        p["radius"] = (p["spread\_ft"] / 2) / feet\_per\_canvas\_unit

        p["style\_fit"] = STYLE\_FIT\_BY\_CODE.get(p.get("code"), ["Wild / Naturalized"])

        runtime\_plants.append(p)

    return runtime\_plants





def circle\_inside(poly, x, y, r):

    return poly.contains(Point(x, y).buffer(r))





def circles\_overlap(x, y, r, placed, spacing\_factor, plant=None):

    for p in placed:

        existing\_plant = p["plant"]



        existing\_allows\_underplanting = existing\_plant.get("allows\_underplanting", False)

        current\_allows\_underplanting = plant is not None and plant.get("allows\_underplanting", False)



        if existing\_allows\_underplanting and not current\_allows\_underplanting:

            continue



        if current\_allows\_underplanting and not existing\_allows\_underplanting:

            continue



        distance = math.dist((x, y), (p["x"], p["y"]))

        min\_distance = (r + p["radius"]) \* spacing\_factor



        if distance < min\_distance:

            return True



    return False





def weighted\_choice(plants):

    if not plants:

        return None



    weights = [p.get("weight", 1) for p in plants]

    return random.choices(plants, weights=weights, k=1)[0]





def pack\_layer(poly, plants, target\_area, spacing\_factor, existing\_placed, max\_plants\_total):

    if not plants:

        return [], 0



    minx, miny, maxx, maxy = poly.bounds

    placed\_layer = []

    placed\_area = 0

    attempts = 0

    max\_attempts = 16000



    while (

        placed\_area < target\_area

        and attempts < max\_attempts

        and len(existing\_placed) + len(placed\_layer) < max\_plants\_total

    ):

        attempts += 1



        plant = weighted\_choice(plants)

        if plant is None:

            break



        r = plant["radius"]



        if maxx - minx < r \* 2 or maxy - miny < r \* 2:

            break



        x = random.uniform(minx + r, maxx - r)

        y = random.uniform(miny + r, maxy - r)



        if not circle\_inside(poly, x, y, r):

            continue



        all\_existing = existing\_placed + placed\_layer



        if circles\_overlap(x, y, r, all\_existing, spacing\_factor, plant):

            continue



        placed\_layer.append({"x": x, "y": y, "radius": r, "plant": plant})

        placed\_area += math.pi \* (r \*\* 2)



    return placed\_layer, placed\_area





def pack\_by\_role(poly, plant\_pool, target\_coverage, spacing\_factor, max\_plants\_total, role\_split=None):

    boundary\_area = poly.area



    if boundary\_area <= 0:

        return [], 0



    total\_target\_area = boundary\_area \* target\_coverage

    all\_placed = []

    total\_placed\_area = 0



    active\_roles = [role for role in ROLE\_ORDER if any(p["role"] == role for p in plant\_pool)]



    if not active\_roles:

        return [], 0



    if role\_split is None:

        total\_default = sum(default\_role\_percentage(role) for role in active\_roles) or 1

        role\_split = {

            role: default\_role\_percentage(role) / total\_default

            for role in active\_roles

        }



    for role in active\_roles:

        role\_plants = [p for p in plant\_pool if p["role"] == role]



        if not role\_plants:

            continue



        layer\_target\_area = total\_target\_area \* role\_split.get(role, 0)



        placed\_layer, placed\_area = pack\_layer(

            poly=poly,

            plants=role\_plants,

            target\_area=layer\_target\_area,

            spacing\_factor=spacing\_factor,

            existing\_placed=all\_placed,

            max\_plants\_total=max\_plants\_total

        )



        all\_placed.extend(placed\_layer)

        total\_placed\_area += placed\_area



    return all\_placed, total\_placed\_area / boundary\_area



def sun\_is\_compatible(selected\_sun, plant\_sun\_options):

    sun\_compatibility = {

        "Full Sun": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun"],

        "Full Sun-Part Shade": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade", "Part Shade-Full Shade"],

        "Part Shade": ["Part Shade", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade-Full Shade"],

        "Part Shade-Full Shade": ["Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"],

    }



    compatible\_values = sun\_compatibility.get(selected\_sun, [selected\_sun])

    return any(sun\_value in compatible\_values for sun\_value in plant\_sun\_options)





def water\_is\_compatible(selected\_water, plant\_water\_options):

    water\_compatibility = {

        "Low": ["Low", "Moderate-Low", "Low-Moderate"],

        "Moderate-Low": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Low-Moderate": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Moderate": ["Moderate", "Low-Moderate", "Moderate-Low"],

    }



    compatible\_values = water\_compatibility.get(selected\_water, [selected\_water])

    return any(water\_value in compatible\_values for water\_value in plant\_water\_options)





def hardiness\_is\_compatible(selected\_zones, usda\_min, usda\_max):

    if not selected\_zones:

        return True

    return any(usda\_min <= zone <= usda\_max for zone in selected\_zones)





def filter\_plants(plant\_database, state, selected\_usda\_zones, sun, water):

    """Filter plants by site viability only.



    Community Group and Climate remain plant-database intelligence, but they are no

    longer exposed as a left-panel user decision. Design Style now handles the

    creative/composition intent, while USDA, sun, and water handle viability.

    """

    return [

        plant for plant in plant\_database

        if state in plant["state"]

        and hardiness\_is\_compatible(selected\_usda\_zones, plant["usda\_min"], plant["usda\_max"])

        and sun\_is\_compatible(sun, plant["sun"])

        and water\_is\_compatible(water, plant["water"])

    ]





def filter\_plants\_by\_style(plant\_database, design\_style):

    """Filter by the selected design language.



    The style selector replaces the old visible California Plant Community filter.

    Perennial Garden is intentionally strict: it only returns plants with

    Form = Perennial, so the output behaves like a true perennial palette.

    """

    style\_filtered = [

        plant for plant in plant\_database

        if design\_style in plant.get("style\_fit", [])

    ]



    if design\_style == "Perennial Garden":

        style\_filtered = [p for p in style\_filtered if p.get("form") == "Perennial"]



    if design\_style == "Meadow":

        # Meadow should read grass-dominant, but still permits a few seasonal accents.

        style\_filtered = [p for p in style\_filtered if p.get("form") in ["Grass", "Perennial", "Shrub"]]



    if design\_style == "Dry Garden":

        style\_filtered = [p for p in style\_filtered if "Low" in p.get("water", []) or "Low-Moderate" in p.get("water", [])]



    return style\_filtered





def style\_priority\_score(plant, design\_style):

    settings = STYLE\_LOGIC.get(design\_style, STYLE\_LOGIC["Wild / Naturalized"])

    role\_boost = settings.get("role\_boost", {}).get(plant.get("role"), 1.0)

    form\_priority = settings.get("form\_priority", [])



    form\_score = 0

    if form\_priority and plant.get("form") in form\_priority:

        # Earlier listed forms receive higher priority.

        form\_score = len(form\_priority) - form\_priority.index(plant.get("form"))



    # Lower design tier is more important; invert it for scoring.

    tier\_score = 6 - float(plant.get("design\_tier", 5))

    visual\_score = float(plant.get("visual\_weight", 1))

    weight\_score = float(plant.get("weight", 1))



    return (tier\_score \* 2.0 + visual\_score + weight\_score \* 0.4 + form\_score \* 1.5) \* role\_boost





def limit\_palette\_by\_style(plant\_database, design\_style):

    """Keep the generated palette focused so layouts feel intentional.



    Forced-included plants are added after this function, so user intent still wins.

    Sorting favors the selected design style first, then design hierarchy.

    """

    settings = STYLE\_LOGIC.get(design\_style, STYLE\_LOGIC["Wild / Naturalized"])

    species\_limit = settings.get("species\_limit", 8)



    if len(plant\_database) <= species\_limit:

        return plant\_database



    sorted\_plants = sorted(

        plant\_database,

        key=lambda p: (

            -style\_priority\_score(p, design\_style),

            p.get("design\_tier", 5),

            p.get("name", "")

        )

    )



    selected = sorted\_plants[:species\_limit]



    if design\_style == "Meadow":

        # Keep meadow grass-led whenever possible.

        grasses = [p for p in sorted\_plants if p.get("form") == "Grass"]

        non\_grasses = [p for p in selected if p.get("form") != "Grass"]

        min\_grasses = min(len(grasses), max(2, int(round(species\_limit \* 0.6))))

        selected = grasses[:min\_grasses]

        for p in sorted\_plants:

            if p not in selected and len(selected) < species\_limit:

                selected.append(p)



    if design\_style == "Perennial Garden":

        # Stay true to the user's request: only perennials.

        selected = [p for p in selected if p.get("form") == "Perennial"]



    # Preserve at least one matrix plant when the selected style permits matrix plants.

    if design\_style != "Perennial Garden" and not any(p.get("role") == "Matrix" for p in selected):

        matrix\_candidates = [p for p in sorted\_plants if p.get("role") == "Matrix"]

        if matrix\_candidates and selected:

            selected[-1] = matrix\_candidates[0]



    return selected



def get\_polygon\_from\_canvas(canvas\_json):

    if canvas\_json is None:

        return None



    objects = canvas\_json.get("objects", [])

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





def normalize\_polygon(points):

    if points is None or len(points) < 3:

        return None

    poly = Polygon(points)

    if not poly.is\_valid:

        poly = poly.buffer(0)

    if poly.is\_empty or poly.area <= 0:

        return None

    return poly





def polygon\_points\_from\_geometry(geom):

    if geom is None or geom.is\_empty:

        return []

    if geom.geom\_type == "Polygon":

        return [(float(x), float(y)) for x, y in list(geom.exterior.coords)[:-1]]

    if geom.geom\_type == "MultiPolygon":

        largest = max(list(geom.geoms), key=lambda g: g.area)

        return [(float(x), float(y)) for x, y in list(largest.exterior.coords)[:-1]]

    return []





def valid\_role\_zones\_for\_boundary(role\_zones, main\_poly):

    valid = {}

    for role, points in (role\_zones or {}).items():

        zone\_poly = normalize\_polygon(points)

        if zone\_poly is None:

            continue

        clipped = zone\_poly.intersection(main\_poly)

        if clipped.is\_empty or clipped.area <= 0:

            continue

        valid[role] = clipped

    return valid





def rectangle\_points(canvas\_width, canvas\_height):

    return [(0, 0), (canvas\_width, 0), (canvas\_width, canvas\_height), (0, canvas\_height)]





def fig\_to\_png\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="png", dpi=200, bbox\_inches="tight", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_jpeg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="jpg", dpi=200, bbox\_inches="tight", facecolor="white", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_svg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="svg", bbox\_inches="tight")

    buffer.seek(0)

    return buffer





def canvas\_area\_to\_sqft(area\_canvas\_units, feet\_per\_canvas\_unit):

    return area\_canvas\_units \* (feet\_per\_canvas\_unit \*\* 2)





def canvas\_length\_to\_feet(length\_canvas\_units, feet\_per\_canvas\_unit):

    return length\_canvas\_units \* feet\_per\_canvas\_unit





def draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units):

    x = 0

    while x <= canvas\_width:

        ax.axvline(x, linewidth=0.4, alpha=0.25)

        x += grid\_spacing\_units



    y = 0

    while y <= canvas\_height:

        ax.axhline(y, linewidth=0.4, alpha=0.25)

        y += grid\_spacing\_units





def get\_image\_aspect\_ratio(image\_path):

    try:

        img = plt.imread(image\_path)

        height\_px, width\_px = img.shape[:2]

        if height\_px == 0:

            return 1

        return width\_px / height\_px

    except Exception:

        return 1





def varied\_height(plant):

    tolerance = HEIGHT\_VARIATION\_BY\_HIERARCHY.get(plant["hierarchy"], 0.08)

    variation = random.uniform(1 - tolerance, 1 + tolerance)

    return plant["elevation\_height"] \* variation





def prepare\_uploaded\_image(uploaded\_file, canvas\_width, canvas\_height):

    if uploaded\_file is None:

        return None, None



    image = Image.open(uploaded\_file).convert("RGB")

    image = image.resize((canvas\_width, canvas\_height))

    image\_array = plt.imread(BytesIO(image\_to\_png\_bytes(image).getvalue()))

    return image, image\_array





def render\_trace\_overlay(image, points, canvas\_width, canvas\_height):

    """Return a PIL image with the uploaded background plus the clicked/traced bedline points.



    This avoids relying on streamlit-drawable-canvas background\_image, which can render

    blank on Streamlit Cloud. Users click around the bedline directly on the image.

    """

    if image is None:

        return None



    overlay = image.copy().convert("RGB")

    overlay = overlay.resize((canvas\_width, canvas\_height))

    draw = ImageDraw\.Draw(overlay)



    if len(points) >= 2:

        draw\.line(points, fill=(255, 255, 255), width=3)



    if len(points) >= 3:

        # Light preview of the closing segment so users understand the final polygon.

        draw\.line([points[-1], points[0]], fill=(255, 255, 255), width=2)



    for idx, (x, y) in enumerate(points):

        r = 5

        draw\.ellipse((x - r, y - r, x + r, y + r), fill=(255, 80, 80), outline=(255, 255, 255), width=2)

        draw\.text((x + 7, y - 7), str(idx + 1), fill=(255, 255, 255))



    return overlay





def image\_to\_png\_bytes(image):

    buffer = BytesIO()

    image.save(buffer, format="PNG")

    buffer.seek(0)

    return buffer





def escape\_svg\_text(value):

    return html.escape(str(value), quote=True)





def plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit, role\_zones=None):

    """Create a clean vector SVG of the plan geometry.



    This avoids relying on Matplotlib's SVG output and gives you true circle/vector objects.

    """

    path\_points = " ".join([f"{x:.2f},{y:.2f}" for x, y in points])

    svg = StringIO()

    svg.write(f'\<svg xmlns="http\://www\.w3.org/2000/svg" width="{canvas\_width}" height="{canvas\_height}" viewBox="0 0 {canvas\_width} {canvas\_height}">\n')

    svg.write('\<rect width="100%" height="100%" fill="white"/>\n')

    svg.write(f'\<polygon points="{path\_points}" fill="none" stroke="black" stroke-width="2"/>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        zone\_path = " ".join([f"{x:.2f},{y:.2f}" for x, y in zone\_points])

        first\_x, first\_y = zone\_points[0]

        svg.write(f'\<polygon points="{zone\_path}" fill="none" stroke="black" stroke-width="1" stroke-dasharray="4 4" opacity="0.45"/>\n')

        svg.write(f'\<text x="{first\_x:.2f}" y="{first\_y:.2f}" font-family="Arial" font-size="10" opacity="0.65">{escape\_svg\_text(role)} zone\</text>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        closed\_zone = zone\_points + [zone\_points[0]]

        layer\_name = f"ROLE\_ZONE\_{role.upper().replace(' ', '\_')}"

        for i in range(len(closed\_zone) - 1):

            x1, y1 = closed\_zone[i]

            x2, y2 = closed\_zone[i + 1]

            dxf.write("0\nLINE\n8\n" + layer\_name + "\n")

            dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

            dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dash = ' stroke-dasharray="6 4"' if plant.get("allows\_underplanting", False) else ""

        weight = "bold" if plant.get("allows\_underplanting", False) else "normal"

        svg.write(f'\<circle cx="{item["x"]:.2f}" cy="{item["y"]:.2f}" r="{item["radius"]:.2f}" fill="none" stroke="black" stroke-width="1.2"{dash}/>\n')

        svg.write(f'\<text x="{item["x"]:.2f}" y="{item["y"]:.2f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="8" font-weight="{weight}">{escape\_svg\_text(plant["code"])}\</text>\n')



    svg.write(f'\<text x="12" y="{canvas\_height - 14}" font-family="Arial" font-size="10">Scale: 1 px = {feet\_per\_canvas\_unit:.3f} ft\</text>\n')

    svg.write('\</svg>')

    return BytesIO(svg.getvalue().encode("utf-8"))





def plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit, role\_zones=None):

    """Export a simple ASCII DXF in real feet.



    AutoCAD, Rhino, Vectorworks, and many CAD tools can open DXF. This is the practical

    Streamlit-friendly alternative to DWG.

    """

    dxf = StringIO()

    dxf.write("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n2\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nENTITIES\n")



    closed\_points = points + [points[0]]

    for i in range(len(closed\_points) - 1):

        x1, y1 = closed\_points[i]

        x2, y2 = closed\_points[i + 1]

        dxf.write("0\nLINE\n8\nBOUNDARY\n")

        dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dxf.write("0\nCIRCLE\n8\nPLANTS\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"40\n{item['radius'] \* feet\_per\_canvas\_unit:.4f}\n")

        dxf.write("0\nTEXT\n8\nPLANT\_CODES\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write("40\n0.35\n")

        dxf.write(f"1\n{plant['code']}\n")



    dxf.write("0\nENDSEC\n0\nEOF\n")

    return BytesIO(dxf.getvalue().encode("utf-8"))



\# -----------------------------

\# Sidebar

\# -----------------------------



with st.sidebar:

    st.markdown("### by The Landscape Library")



    st.header("Input Method")

    input\_method = st.radio(

        "Choose how to define the planting bed",

        ["Draw Boundary", "Upload JPEG Image"],

        index=0

    )



    st.info("Max 50' bed")



    if input\_method == "Upload JPEG Image":

        st.caption("Upload a JPEG image as a scaled reference, then click points around the actual bedline.")

        uploaded\_bed\_image = st.file\_uploader(

            "Upload bed image",

            type=["jpg", "jpeg"]

        )



        bed\_length\_ft = st.number\_input(

            "Image length / horizontal dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=30.0,

            step=1.0

        )



        bed\_width\_ft = st.number\_input(

            "Image width / vertical dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=15.0,

            step=1.0

        )

    else:

        uploaded\_bed\_image = None

        bed\_length\_ft = DEFAULT\_BED\_LENGTH\_FEET

        bed\_width\_ft = DEFAULT\_BED\_WIDTH\_FEET



    canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units = get\_canvas\_setup(

        bed\_length\_ft,

        bed\_width\_ft

    )



    st.header("Site Parameters")



    state = st.selectbox("State", ["California"])

    climate = "All Compatible Communities"



    design\_style = st.selectbox(

        "Design Style",

        DESIGN\_STYLE\_OPTIONS,

        index=0

    )

    st.caption(STYLE\_LOGIC[design\_style]["description"])



    st.markdown("\*\*USDA Hardiness\*\*")

    st.caption("Select one or more USDA zones. Plants are included when the selected zone falls between USDA Min and USDA Max in the plant database.")

    usda\_zone\_options = list(range(5, 11))

    default\_usda\_zones = [9]

    selected\_usda\_zones = []

    zone\_cols = st.columns(3)

    for idx, zone in enumerate(usda\_zone\_options):

        with zone\_cols[idx % 3]:

            checked = st.checkbox(f"Zone {zone}", value=zone in default\_usda\_zones, key=f"usda\_zone\_{zone}")

            if checked:

                selected\_usda\_zones.append(zone)



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



    target\_coverage = DENSITY\_OPTIONS[density]

    spacing\_factor = SPACING\_BY\_DENSITY[density] \* STYLE\_LOGIC[design\_style]["spacing\_multiplier"]

    max\_plants\_total = MAX\_PLANTS\_BY\_DENSITY[density]



    st.header("Scale")

    st.caption(f"Bed limit: {MAX\_BED\_FEET} ft max length or width")

    st.caption(f"Active bed: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")



\# -----------------------------

\# Active plant database + image prep

\# -----------------------------



runtime\_plants = make\_runtime\_plant\_pool(PLANTS, feet\_per\_canvas\_unit)

selected\_plants = filter\_plants(runtime\_plants, state, selected\_usda\_zones, sun, water)

selected\_plants = filter\_plants\_by\_style(selected\_plants, design\_style)



\# Manual include / exclude controls

all\_matching\_names = [p["name"] for p in selected\_plants]

with st.sidebar:

    st.header("Plant Controls")

    include\_names = st.multiselect("Force include plants", [p["name"] for p in runtime\_plants])

    exclude\_names = st.multiselect("Exclude plants", all\_matching\_names)



role\_split = None



forced = [p for p in runtime\_plants if p["name"] in include\_names]

selected\_plants = [p for p in selected\_plants if p["name"] not in exclude\_names]

selected\_plants = limit\_palette\_by\_style(selected\_plants, design\_style)



for p in forced:

    if p["name"] not in [sp["name"] for sp in selected\_plants]:

        selected\_plants.append(p)



background\_image = None

background\_array = None



if input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    background\_image, background\_array = prepare\_uploaded\_image(uploaded\_bed\_image, canvas\_width, canvas\_height)



\# -----------------------------

\# Main UI

\# -----------------------------



left, right = st.columns([2, 1])



with left:

    if input\_method == "Draw Boundary":

        st.subheader("1. Draw Planting Boundary")

        st.caption("TIP: Left click to add boundary points. Right click to end nearest the origin point and complete the boundary.")

        st.caption('Drawing canvas: 50\\'-0" horizontal × 50\\'-0" vertical.')



        canvas\_result = st\_canvas(

            fill\_color="rgba(0, 0, 0, 0)",

            stroke\_width=3,

            stroke\_color="#111111",

            background\_color="#f7f7f2",

            height=canvas\_height,

            width=canvas\_width,

            drawing\_mode="polygon",

            key="draw\_boundary\_canvas",

        )

    else:

        st.subheader("1. Upload Scaled Bed Image + Trace Bedline")

        st.caption("Click around the planting bedline in order. Use more points for curves. The final segment closes automatically between the last point and first point.")



        if uploaded\_bed\_image is None:

            st.warning("Upload a JPEG image first, then click points around the actual bedline.")

            canvas\_result = None

        else:

            canvas\_result = None



            if streamlit\_image\_coordinates is None:

                st.error("Missing package: streamlit-image-coordinates. Add streamlit-image-coordinates to requirements.txt, then redeploy.")

            else:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                last\_click\_key = f"last\_click\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"



                if trace\_key not in st.session\_state:

                    st.session\_state[trace\_key] = []

                if last\_click\_key not in st.session\_state:

                    st.session\_state[last\_click\_key] = None



                st.caption("Click points around the bedline in order. Use more points for curves. The final segment closes automatically between the last and first point.")



                overlay\_image = render\_trace\_overlay(

                    background\_image,

                    st.session\_state[trace\_key],

                    canvas\_width,

                    canvas\_height

                )



                clicked = streamlit\_image\_coordinates(

                    overlay\_image,

                    key=f"click\_trace\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}",

                    width=canvas\_width

                )



                if clicked is not None and "x" in clicked and "y" in clicked:

                    new\_point = (int(clicked["x"]), int(clicked["y"]))



                    if st.session\_state[last\_click\_key] != new\_point:

                        existing\_points = st.session\_state[trace\_key]



                        # Prevent accidental double-click duplicates.

                        if len(existing\_points) == 0 or math.dist(existing\_points[-1], new\_point) > 4:

                            existing\_points.append(new\_point)

                            st.session\_state[trace\_key] = existing\_points



                        st.session\_state[last\_click\_key] = new\_point

                        st.rerun()



                b1, b2, b3 = st.columns(3)

                with b1:

                    if st.button("Undo Last Point") and len(st.session\_state[trace\_key]) > 0:

                        st.session\_state[trace\_key] = st.session\_state[trace\_key][:-1]

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b2:

                    if st.button("Clear Trace"):

                        st.session\_state[trace\_key] = []

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b3:

                    st.metric("Trace Points", len(st.session\_state[trace\_key]))



                if len(st.session\_state[trace\_key]) < 3:

                    st.info("Add at least 3 points before generating the planting layout.")



with right:

    st.subheader("Request a Plant")

    requested\_plant = st.text\_input("Plant you want added")

    if st.button("Submit Plant Request"):

        if requested\_plant.strip():

            ok, error\_message = log\_plant\_request(

                st.session\_state.get("user\_email"),

                requested\_plant.strip(),

                state=state,

                zone=", ".join([f"USDA {z}" for z in selected\_usda\_zones]),

                climate=climate,

                sun\_exposure=sun,

                water\_needs=water,

                design\_style=design\_style,

            )

            if ok:

                st.success("Plant request submitted.")

            else:

                st.error(f"Plant request was not saved: {error\_message}")

        else:

            st.warning("Enter a plant name before submitting.")



    st.subheader("3. Selected Plant Palette")



    if len(selected\_plants) == 0:

        st.warning("No plants match these parameters yet. Try adjusting design style, USDA hardiness, sun exposure, or water needs.")

    else:

        for plant in selected\_plants:

            canopy\_note = " | allows underplanting" if plant.get("allows\_underplanting", False) else ""

            st.write(f"\*\*{plant['name']}\*\*")

            st.caption(

                f"{plant['code']} | {plant['common\_name']} | {plant['form']} | {plant['role']} | spread: {plant['spread\_ft']} ft{canopy\_note}"

            )



\# -----------------------------

\# Boundary metrics

\# -----------------------------



points\_preview = None



if input\_method == "Draw Boundary" and canvas\_result is not None:

    points\_preview = get\_polygon\_from\_canvas(canvas\_result.json\_data)

elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

    points\_preview = st.session\_state.get(trace\_key, [])

    if len(points\_preview) < 3:

        points\_preview = None



if points\_preview is not None:

    preview\_poly = Polygon(points\_preview)



    if not preview\_poly.is\_valid:

        preview\_poly = preview\_poly.buffer(0)



    if preview\_poly.area > 0:

        area\_sqft = canvas\_area\_to\_sqft(preview\_poly.area, feet\_per\_canvas\_unit)

        perimeter\_ft = canvas\_length\_to\_feet(preview\_poly.length, feet\_per\_canvas\_unit)

        minx\_preview, miny\_preview, maxx\_preview, maxy\_preview = preview\_poly.bounds



        width\_ft = canvas\_length\_to\_feet(maxx\_preview - minx\_preview, feet\_per\_canvas\_unit)

        depth\_ft = canvas\_length\_to\_feet(maxy\_preview - miny\_preview, feet\_per\_canvas\_unit)



        st.subheader("Boundary Metrics")



        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Approx. Area", f"{area\_sqft:,.0f} sq ft")

        c2.metric("Approx. Perimeter", f"{perimeter\_ft:,.0f} ft")

        c3.metric("Approx. Length", f"{width\_ft:,.0f} ft")

        c4.metric("Approx. Width", f"{depth\_ft:,.0f} ft")



generate = st.button("Generate Planting Layout", type="primary")



\# -----------------------------

\# Generate

\# -----------------------------



if generate:

    if supabase is not None and st.session\_state.get("user\_email"):

        user\_check = supabase.table("users").select("\*").eq("email", st.session\_state.user\_email).execute()

        current\_user = user\_check.data[0] if user\_check.data else {}

        if not current\_user.get("paid\_status", False) and (current\_user.get("total\_generations") or 0) >= FREE\_GENERATION\_LIMIT:

            st.warning("You have reached the free generation limit.")

            log\_event(st.session\_state.user\_email, "paywall\_shown")

            st.stop()

    try:

        with st.spinner("Generating planting plan and elevation view\..."):

            if input\_method == "Draw Boundary" and canvas\_result is not None:

                points = get\_polygon\_from\_canvas(canvas\_result.json\_data)

            elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                points = st.session\_state.get(trace\_key, [])

                if len(points) < 3:

                    points = None

            else:

                points = None



            if points is None:

                if input\_method == "Draw Boundary":

                    st.warning("Draw a closed polygon boundary first.")

                else:

                    st.warning("Upload a JPEG image and trace a closed polygon boundary first.")



            elif bed\_length\_ft > MAX\_BED\_FEET or bed\_width\_ft > MAX\_BED\_FEET:

                st.warning(f"The bed is too large. Keep the image dimensions at or below {MAX\_BED\_FEET} ft.")



            elif len(selected\_plants) == 0:

                st.warning("No plants are available for the selected site parameters.")



            else:

                poly = normalize\_polygon(points)



                if poly is None:

                    st.warning("The boundary is invalid. Try tracing a clearer closed shape.")



                else:

                    placed\_instances, actual\_coverage = pack\_by\_role(

                        poly=poly,

                        plant\_pool=selected\_plants,

                        target\_coverage=target\_coverage,

                        spacing\_factor=spacing\_factor,

                        max\_plants\_total=max\_plants\_total,

                        role\_split=role\_split

                    )



                    if len(placed\_instances) == 0:

                        st.warning("No plants could fit inside the boundary. Try a larger area, lower density, or different plant parameters.")



                    else:

                        new\_generation\_count = increment\_generation\_count(st.session\_state.get("user\_email"))

                        log\_event(

                            st.session\_state.get("user\_email"),

                            "generation\_run",

                            state=state,

                            zone=", ".join([f"USDA {z}" for z in selected\_usda\_zones]),

                            climate=climate,

                            sun\_exposure=sun,

                            water\_needs=water,

                            design\_style=design\_style,

                            notes=f"Density: {density}; Plants generated: {len(placed\_instances)}"

                        )



                        st.subheader("Plan View")



                        fig, ax = plt.subplots(figsize=(10, 10))



                        if background\_array is not None:

                            ax.imshow(background\_array, extent=(0, canvas\_width, canvas\_height, 0), alpha=0.35, zorder=0)



                        xs, ys = zip(\*(points + [points[0]]))

                        ax.plot(xs, ys, linewidth=2, zorder=3)



                        draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units)



                        for item in placed\_instances:

                            plant = item["plant"]



                            if plant.get("allows\_underplanting", False):

                                continue



                            circle = plt.Circle(

                                (item["x"], item["y"]),

                                item["radius"],

                                fill=False,

                                linewidth=1.2,

                                zorder=4

                            )

                            ax.add\_patch(circle)



                            ax.text(

                                item["x"],

                                item["y"],

                                plant["code"],

                                ha="center",

                                va="center",

                                fontsize=8,

                                zorder=5

                            )



                        for item in placed\_instances:

                            plant = item["plant"]



                            if not plant.get("allows\_underplanting", False):

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

                            ax.add\_patch(circle)



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



                        ax.set\_xlim(0, canvas\_width)

                        ax.set\_ylim(canvas\_height, 0)

                        ax.set\_aspect("equal")

                        ax.axis("off")



                        st.pyplot(fig)



                        plan\_png = fig\_to\_png\_bytes(fig)

                        plan\_svg = plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit)

                        plan\_dxf = plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit)



                        d1, d2, d3 = st.columns(3)

                        with d1:

                            st.download\_button(

                                label="Download Plan PNG",

                                data=plan\_png,

                                file\_name="yodra-planting-plan.png",

                                mime="image/png"

                            )

                        with d2:

                            st.download\_button(

                                label="Download Plan SVG",

                                data=plan\_svg,

                                file\_name="yodra-planting-plan.svg",

                                mime="image/svg+xml"

                            )

                        with d3:

                            st.download\_button(

                                label="Download Plan DXF",

                                data=plan\_dxf,

                                file\_name="yodra-planting-plan.dxf",

                                mime="application/dxf"

                            )



                        st.caption(f"Target coverage: {round(target\_coverage \* 100)}%")

                        st.caption(f"Actual generated coverage: {round(actual\_coverage \* 100)}%")

                        st.caption(f"Active bed scale: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")

                        st.caption(f"Maximum plant instances capped at {max\_plants\_total} for app performance.")



                        st.subheader("Elevation View")

                        st.caption("Elevation uses the same plant instances generated in plan view, with subtle height variation.")



                        elev\_fig, elev\_ax = plt.subplots(figsize=(12, 4))



                        placed\_sorted = sorted(placed\_instances, key=lambda item: item["x"])



                        for item in placed\_sorted:

                            plant = item["plant"]

                            image\_path = plant["image"]



                            height = varied\_height(plant)

                            aspect\_ratio = get\_image\_aspect\_ratio(image\_path)

                            width = height \* aspect\_ratio



                            if os.path.exists(image\_path):

                                img = plt.imread(image\_path)



                                elev\_ax.imshow(

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

                                elev\_ax.text(

                                    item["x"],

                                    height / 2,

                                    plant["code"],

                                    ha="center",

                                    va="center",

                                    fontsize=8

                                )



                        elev\_ax.axhline(0, linewidth=1)

                        elev\_ax.set\_xlim(0, canvas\_width)

                        elev\_ax.set\_ylim(0, 140)

                        elev\_ax.axis("off")



                        st.pyplot(elev\_fig)



                        elevation\_png = fig\_to\_png\_bytes(elev\_fig)

                        elevation\_jpeg = fig\_to\_jpeg\_bytes(elev\_fig)



                        e1, e2 = st.columns(2)

                        with e1:

                            st.download\_button(

                                label="Download Elevation PNG",

                                data=elevation\_png,

                                file\_name="yodra-planting-elevation.png",

                                mime="image/png"

                            )

                        with e2:

                            st.download\_button(

                                label="Download Elevation JPEG",

                                data=elevation\_jpeg,

                                file\_name="yodra-planting-elevation.jpg",

                                mime="image/jpeg"

                            )



                        counts = {}

                        for item in placed\_instances:

                            plant = item["plant"]

                            counts[plant["name"]] = counts.get(plant["name"], 0) + 1



                        st.subheader("Plant Schedule")



                        schedule = []

                        for plant\_name, count in counts.items():

                            plant = next(p for p in runtime\_plants if p["name"] == plant\_name)



                            schedule.append({

                                "Code": plant["code"],

                                "Count": count,

                                "Botanical Name": plant["name"],

                                "Common Name": plant["common\_name"],

                                "Form": plant["form"],

                                "Role": plant["role"],

                                "Texture": plant["texture"],

                                "Color Tone": plant["color\_tone"],

                                "Visual Weight": plant["visual\_weight"],

                                "Spread Ft": plant["spread\_ft"],

                                "Height Ft": plant["height\_ft"],

                                "State": state,

                                "Climate": ", ".join(plant["climate"]),

                                "USDA Min": plant["usda\_min"],

                                "USDA Max": plant["usda\_max"],

                                "Sun": ", ".join(plant["sun"]),

                                "Water": ", ".join(plant["water"]),

                                "Seasonality": plant["seasonality"],

                                "Style Fit": ", ".join(plant.get("style\_fit", [])),

                                "Allows Underplanting": plant.get("allows\_underplanting", False)

                            })



                        schedule\_df = pd.DataFrame(schedule)

                        st.dataframe(schedule\_df, width="stretch")



                        csv\_buffer = schedule\_df.to\_csv(index=False).encode("utf-8")

                        st.download\_button(

                            label="Download Plant Schedule CSV / Excel",

                            data=csv\_buffer,

                            file\_name="yodra-plant-schedule.csv",

                            mime="text/csv",

                            on\_click=lambda: increment\_export\_count(st.session\_state.get("user\_email"))

                        )

                        log\_event(st.session\_state.get("user\_email"), "schedule\_export\_ready", export\_type="csv")



    except Exception as e:

        st.error("The app crashed while generating the layout.")

        st.exception(e)










































---




# Version 3.3






import streamlit as st

from datetime import datetime, timezone

try:

    from supabase import create\_client

except Exception:

    create\_client = None

import pandas as pd



\# -------------------------

\# SUPABASE USER TRACKING

\# -------------------------



FREE\_GENERATION\_LIMIT = 999



def get\_supabase\_client():

    if create\_client is None:

        return None

    url = st.secrets.get("SUPABASE\_URL", "")

    key = st.secrets.get("SUPABASE\_SERVICE\_ROLE\_KEY", "")

    if not url or not key:

        return None

    return create\_client(url, key)



supabase = get\_supabase\_client()



def log\_event(email, event\_type, \*\*kwargs):

    """Insert an event using only the columns that exist in the current Supabase events table.



    Current expected columns:

    email, event\_type, created\_at, climate, sun\_exposure, water\_needs,

    design\_style, export\_type, notes.



    Do not add state, zone, density, or plants\_generated\_count unless those columns

    are also added to Supabase. Supabase will reject inserts when unknown columns

    are included.

    """

    if supabase is None or not email:

        return False, "Supabase is not connected or user email is missing."



    event = {

        "email": email,

        "event\_type": event\_type,

        "created\_at": datetime.now(timezone.utc).isoformat(),

        "climate": kwargs.get("climate"),

        "sun\_exposure": kwargs.get("sun\_exposure"),

        "water\_needs": kwargs.get("water\_needs"),

        "design\_style": kwargs.get("design\_style"),

        "export\_type": kwargs.get("export\_type"),

        "notes": kwargs.get("notes"),

    }



    # Remove empty optional fields so Supabase receives a clean payload.

    event = {k: v for k, v in event.items() if v is not None}



    try:

        supabase.table("events").insert(event).execute()

        return True, None

    except Exception as e:

        return False, str(e)





def log\_plant\_request(email, requested\_plant, \*\*kwargs):

    requested\_plant = (requested\_plant or "").strip()

    if not requested\_plant:

        return False, "Plant request is empty."



    ok, err = log\_event(

        email,

        "plant\_requested",

        notes=requested\_plant,

        \*\*kwargs

    )



    # Optional dedicated table. If you create a plant\_requests table in Supabase,

    # this will also save requests there. If that table does not exist, the

    # events table above is still the primary tracking location.

    if supabase is not None and email:

        try:

            supabase.table("plant\_requests").insert({

                "email": email,

                "requested\_plant": requested\_plant,

                "created\_at": datetime.now(timezone.utc).isoformat(),

                "climate": kwargs.get("climate"),

                "sun\_exposure": kwargs.get("sun\_exposure"),

                "water\_needs": kwargs.get("water\_needs"),

                "notes": requested\_plant,

            }).execute()

        except Exception:

            pass



    return ok, err





def log\_region\_request(email, requested\_region, requested\_city, \*\*kwargs):

    """Save a region request into the existing Supabase events table.



    This uses event\_type='region\_requested' and stores the requested region/city

    inside the existing notes column so no new Supabase columns are required.

    """

    requested\_region = (requested\_region or "").strip()

    requested\_city = (requested\_city or "").strip()



    if not requested\_region:

        return False, "Region request is empty."

    if not requested\_city:

        return False, "City is empty."



    notes = f"Requested Region: {requested\_region} | City: {requested\_city}"



    ok, err = log\_event(

        email,

        "region\_requested",

        notes=notes,

        \*\*kwargs

    )



    # Optional dedicated table. The events table above remains the primary save

    # location. If region\_requests does not exist, this silently falls back to events only.

    if supabase is not None and email:

        try:

            supabase.table("region\_requests").insert({

                "email": email,

                "requested\_region": requested\_region,

                "requested\_city": requested\_city,

                "created\_at": datetime.now(timezone.utc).isoformat(),

                "climate": kwargs.get("climate"),

                "sun\_exposure": kwargs.get("sun\_exposure"),

                "water\_needs": kwargs.get("water\_needs"),

                "design\_style": kwargs.get("design\_style"),

                "notes": notes,

            }).execute()

        except Exception:

            pass



    return ok, err





def get\_or\_create\_user(email):

    email = email.strip().lower()

    if supabase is None:

        return {"email": email, "paid\_status": False, "total\_generations": 0, "total\_exports": 0}



    now = datetime.now(timezone.utc).isoformat()

    result = supabase.table("users").select("\*").eq("email", email).execute()

    if result.data:

        user = result.data[0]

        supabase.table("users").update({"last\_seen": now}).eq("email", email).execute()

        return user



    new\_user = {

        "email": email,

        "first\_seen": now,

        "last\_seen": now,

        "paid\_status": False,

        "total\_generations": 0,

        "total\_exports": 0,

    }

    created = supabase.table("users").insert(new\_user).execute()

    return created.data[0] if created.data else new\_user



def increment\_generation\_count(email):

    if supabase is None:

        return 0

    result = supabase.table("users").select("total\_generations").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_generations") or 0

    new\_count = current + 1

    supabase.table("users").update({

        "total\_generations": new\_count,

        "last\_seen": datetime.now(timezone.utc).isoformat()

    }).eq("email", email).execute()

    return new\_count



def increment\_export\_count(email):

    if supabase is None:

        return

    result = supabase.table("users").select("total\_exports").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_exports") or 0

    supabase.table("users").update({"total\_exports": current + 1}).eq("email", email).execute()



def beta\_email\_gate():

    if "user\_email" not in st.session\_state:

        st.session\_state.user\_email = None

    if st.session\_state.user\_email:

        return True



    st.markdown("""

    \<div style="display\:flex;align-items\:center;gap:10px;flex-wrap\:wrap;">

        \<h1 style="margin:0;line-height:1.1;">Generate Planting Concepts in Minutes\</h1>

        \<span style="

            background:#f3f4f6;

            border:1px solid #e5e7eb;

            padding:3px 10px;

            border-radius:999px;

            font-size:12px;

            font-weight:700;

            letter-spacing:0.02em;

        ">

            Beta

        \</span>

    \</div>

    """, unsafe\_allow\_html=True)

    st.markdown("Visualize spacing, explore plant combinations, and build preliminary plant palettes.")

    st.caption("California Plant Database Available")

    st.caption("Texas and Florida Coming Soon")

    email = st.text\_input("Enter your email to continue")

    if st.button("Start Designing"):

        if "@" not in email or "." not in email:

            st.error("Please enter a valid email address.")

            st.stop()

        user = get\_or\_create\_user(email)

        st.session\_state.user\_email = user["email"]

        st.session\_state.user\_data = user

        log\_event(user["email"], "app\_opened")

        st.rerun()

    st.stop()



beta\_email\_gate()





\# -------------------------

\# YOUR APP BELOW

\# -------------------------



import random

import math

import os

import html

import base64

from io import BytesIO, StringIO



import matplotlib.pyplot as plt

from PIL import Image, ImageDraw

from shapely.geometry import Polygon, Point

from streamlit\_drawable\_canvas import st\_canvas

try:

    from streamlit\_image\_coordinates import streamlit\_image\_coordinates

except Exception:

    streamlit\_image\_coordinates = None



\# -----------------------------

\# Compatibility patch

\# -----------------------------

\# streamlit-drawable-canvas still calls an older Streamlit helper named

\# st.image.image\_to\_url when using background\_image. Newer Streamlit versions

\# removed that helper, which causes an AttributeError on image upload.

\# This patch restores the expected helper by converting the PIL background image

\# into a browser-safe base64 data URL.

def \_yodra\_image\_to\_url(image, width=None, clamp=False, channels="RGB", output\_format="PNG", image\_id=None):

    """Compatibility helper for streamlit-drawable-canvas background images.



    Newer Streamlit versions removed st.image.image\_to\_url, but

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

    return f"data\:image/png;base64,{encoded}"



try:

    # This is the exact object streamlit-drawable-canvas references: st.image.image\_to\_url

    st.image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



try:

    # Also patch Streamlit's image module for environments that reference it directly.

    import streamlit.elements.image as st\_image

    st\_image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



st.set\_page\_config(

    page\_title="Generate Planting Concepts",

    layout="wide"

)



title\_col, badge\_col = st.columns([8, 1])

with title\_col:

    st.title("Generate Planting Concepts in Minutes")

with badge\_col:

    st.markdown(

        """

        \<div style="

            margin-top:14px;

            background:#f3f4f6;

            border:1px solid #e5e7eb;

            padding:4px 10px;

            border-radius:999px;

            text-align\:center;

            font-size:12px;

            font-weight:700;

            letter-spacing:0.02em;

        ">

            Beta

        \</div>

        """,

        unsafe\_allow\_html=True,

    )



st.caption("Visualize spacing, explore plant combinations, and build preliminary plant palettes.")

st.info("California Plant Database Available • Texas and Florida Coming Soon")



\# -----------------------------

\# Canvas + Scale settings

\# -----------------------------



MAX\_CANVAS\_WIDTH = 900

MAX\_CANVAS\_HEIGHT = 600

DEFAULT\_BED\_LENGTH\_FEET = 50

DEFAULT\_BED\_WIDTH\_FEET = 50

MAX\_BED\_FEET = 50



GRID\_SPACING\_FEET = 5



DENSITY\_OPTIONS = {

    "Low": 0.30,

    "Moderate": 0.45,

    "Dense": 0.68,

    "Very Dense": 0.90

}



SPACING\_BY\_DENSITY = {

    "Low": 1.30,

    "Moderate": 1.15,

    "Dense": 1.05,

    "Very Dense": 1.00

}



MAX\_PLANTS\_BY\_DENSITY = {

    "Low": 180,

    "Moderate": 260,

    "Dense": 350,

    "Very Dense": 500

}



\# Placeholder used only while the plant database is being defined.

\# Runtime radii are recalculated after the active bed scale is known.

def feet\_to\_canvas\_radius(width\_ft):

    return width\_ft / 2



\# -----------------------------

\# Plant database

\# -----------------------------



PLANTS = [

    {

        "name": "Carex pansa",

        "common\_name": "Sand Dune Sedge",

        "code": "CP",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 1,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-pansa.webp",

        "elevation\_height": 28,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum latifolium",

        "common\_name": "Coast Buckwheat",

        "code": "EL",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Silver-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-latifolium.webp",

        "elevation\_height": 34,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Festuca californica",

        "common\_name": "California Fescue",

        "code": "FC",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/festuca-californica.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Salvia spathacea",

        "common\_name": "Hummingbird Sage",

        "code": "SS",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/salvia-spathacea.webp",

        "elevation\_height": 42,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Iris douglasiana",

        "common\_name": "Douglas Iris",

        "code": "ID",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/iris-douglasiana.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Arbutus menziesii",

        "common\_name": "Pacific Madrone",

        "code": "AM",

        "state": ["California"],

        "climate": ["Coastal", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 20,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(20),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arbutus-menziesii.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Arctostaphylos densiflora 'Howard McMinn'",

        "common\_name": "Howard McMinn Manzanita",

        "code": "AHM",

        "state": ["California"],

        "climate": ["Coastal", "Inland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 8,

        "height\_ft": 7,

        "radius": feet\_to\_canvas\_radius(8),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arctostaphylos-howard-mcminn.webp",

        "elevation\_height": 105,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

    {

        "name": "Muhlenbergia rigens",

        "common\_name": "Deergrass",

        "code": "MR",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/muhlenbergia-rigens.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Stipa pulchra",

        "common\_name": "Purple Needlegrass",

        "code": "SP",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Golden Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/stipa-pulchra.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Juncus patens",

        "common\_name": "Common Rush",

        "code": "JP",

        "state": ["California"],

        "climate": ["Inland", "Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 3,

        "height\_ft": 3,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/juncus-patens.webp",

        "elevation\_height": 46,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum fasciculatum",

        "common\_name": "California Buckwheat",

        "code": "EF",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-fasciculatum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Epilobium canum",

        "common\_name": "California Fuchsia",

        "code": "EC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Semi-evergreen",

        "image": "plant\_images/epilobium-canum.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Artemisia californica",

        "common\_name": "California Sagebrush",

        "code": "AC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Silver-Grey",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/artemisia-californica.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Quercus chrysolepis",

        "common\_name": "Canyon Live Oak",

        "code": "QC",

        "state": ["California"],

        "climate": ["Inland", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 30,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(30),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/quercus-chrysolepis.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Carex tumulicola",

        "common\_name": "Foothill Sedge",

        "code": "CT",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Sun"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-tumulicola.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Polystichum munitum",

        "common\_name": "Western Sword Fern",

        "code": "PM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 5,

        "usda\_max": 9,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/polystichum-munitum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Heuchera maxima",

        "common\_name": "Island Alum Root",

        "code": "HM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/heuchera-maxima.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Ribes sanguineum",

        "common\_name": "Red-Flowering Currant",

        "code": "RS",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 6,

        "height\_ft": 8,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Deciduous",

        "image": "plant\_images/ribes-sanguineum.webp",

        "elevation\_height": 110,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Woodwardia fimbriata",

        "common\_name": "Giant Chain Fern",

        "code": "WF",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 6,

        "height\_ft": 5,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/woodwardia-fimbriata.webp",

        "elevation\_height": 70,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Acer circinatum",

        "common\_name": "Vine Maple",

        "code": "ACI",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 15,

        "height\_ft": 20,

        "radius": feet\_to\_canvas\_radius(15),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 3,

        "seasonality": "Deciduous",

        "image": "plant\_images/acer-circinatum.webp",

        "elevation\_height": 125,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Heteromeles arbutifolia",

        "common\_name": "Toyon",

        "code": "HA",

        "state": ["California"],

        "climate": ["Woodland", "Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 10,

        "height\_ft": 15,

        "radius": feet\_to\_canvas\_radius(10),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/heteromeles-arbutifolia.webp",

        "elevation\_height": 118,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

]







STYLE\_FIT\_BY\_CODE = {

    # Wild / Naturalized is intentionally broad: it allows the engine to mix canopy,

    # structure, matrix, and accents after USDA/sun/water filtering.

    "CP": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "EL": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "FC": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "SS": ["Wild / Naturalized", "Perennial Garden", "Woodland Garden"],

    "ID": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Woodland Garden"],

    "AM": ["Wild / Naturalized", "Woodland Garden", "Contemporary"],

    "AHM": ["Contemporary", "Wild / Naturalized", "Dry Garden"],

    "MR": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "SP": ["Wild / Naturalized", "Meadow"],

    "JP": ["Wild / Naturalized", "Meadow", "Contemporary"],

    "EF": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "EC": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "AC": ["Wild / Naturalized", "Dry Garden", "Meadow", "Contemporary"],

    "QC": ["Wild / Naturalized", "Woodland Garden"],

    "CT": ["Wild / Naturalized", "Woodland Garden", "Contemporary"],

    "PM": ["Woodland Garden", "Wild / Naturalized"],

    "HM": ["Woodland Garden", "Wild / Naturalized", "Perennial Garden", "Contemporary"],

    "RS": ["Woodland Garden", "Wild / Naturalized"],

    "WF": ["Woodland Garden", "Wild / Naturalized"],

    "AV": ["Woodland Garden", "Wild / Naturalized", "Contemporary"],

    "HA": ["Woodland Garden", "Contemporary", "Wild / Naturalized", "Dry Garden"],

}



STYLE\_LOGIC = {

    "Wild / Naturalized": {

        "species\_limit": 9,

        "spacing\_multiplier": 1.00,

        "description": "Mixed, ecological planting with canopy, structure, grasses, perennials, and accents.",

        "form\_priority": [],

        "role\_boost": {"Matrix": 1.15, "Accent": 1.05, "Structure": 1.0, "Canopy": 0.8},

    },

    "Contemporary": {

        "species\_limit": 5,

        "spacing\_multiplier": 1.20,

        "description": "Fewer species, stronger repeated masses, cleaner spacing, and more negative space.",

        "form\_priority": ["Grass", "Shrub", "Tree", "Fern", "Perennial"],

        "role\_boost": {"Structure": 1.35, "Matrix": 1.25, "Canopy": 1.0, "Accent": 0.75},

    },

    "Meadow": {

        "species\_limit": 6,

        "spacing\_multiplier": 0.96,

        "description": "Mostly grasses with limited seasonal accents for a meadow-like field condition.",

        "form\_priority": ["Grass", "Perennial", "Shrub"],

        "role\_boost": {"Matrix": 1.6, "Accent": 1.0, "Structure": 0.45, "Canopy": 0.15},

    },

    "Perennial Garden": {

        "species\_limit": 7,

        "spacing\_multiplier": 1.02,

        "description": "Flowering and textural perennial emphasis, supported by restrained matrix plants.",

        "form\_priority": ["Perennial", "Grass"],

        "role\_boost": {"Accent": 1.55, "Matrix": 1.0, "Structure": 0.35, "Canopy": 0.0},

    },

    "Woodland Garden": {

        "species\_limit": 7,

        "spacing\_multiplier": 1.08,

        "description": "Shade-tolerant canopy, structure, ferns, sedges, and understory pockets.",

        "form\_priority": ["Tree", "Shrub", "Fern", "Grass", "Perennial"],

        "role\_boost": {"Canopy": 1.25, "Structure": 1.15, "Matrix": 1.25, "Accent": 1.0},

    },

    "Dry Garden": {

        "species\_limit": 6,

        "spacing\_multiplier": 1.12,

        "description": "Low-water grasses, shrubs, and silver-textured plants with open spacing.",

        "form\_priority": ["Shrub", "Grass", "Perennial"],

        "role\_boost": {"Structure": 1.25, "Matrix": 1.15, "Accent": 1.0, "Canopy": 0.35},

    },

}



DESIGN\_STYLE\_OPTIONS = list(STYLE\_LOGIC.keys())



ROLE\_ORDER = sorted({plant["role"] for plant in PLANTS})



DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES = {

    "Canopy": 12,

    "Structure": 22,

    "Matrix": 44,

    "Accent": 22,

}



def default\_role\_percentage(role):

    return DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES.get(role, 20)



HEIGHT\_VARIATION\_BY\_HIERARCHY = {

    "Anchor": 0.06,

    "Mid Layer": 0.10,

    "Accent Layer": 0.15,

    "Groundcover": 0.08

}



\# -----------------------------

\# Helper functions

\# -----------------------------



def clamp\_dimension(value, fallback):

    try:

        value = float(value)

    except Exception:

        return fallback

    return max(1, min(value, MAX\_BED\_FEET))





def get\_canvas\_setup(length\_ft, width\_ft):

    """Return canvas dimensions and true feet-per-canvas-unit scale.



    length\_ft is horizontal. width\_ft is vertical/depth.

    The canvas preserves the real bed aspect ratio and fits inside the max pixel bounds.

    """

    length\_ft = clamp\_dimension(length\_ft, DEFAULT\_BED\_LENGTH\_FEET)

    width\_ft = clamp\_dimension(width\_ft, DEFAULT\_BED\_WIDTH\_FEET)



    pixels\_per\_foot = min(MAX\_CANVAS\_WIDTH / length\_ft, MAX\_CANVAS\_HEIGHT / width\_ft)

    canvas\_width = max(250, int(round(length\_ft \* pixels\_per\_foot)))

    canvas\_height = max(250, int(round(width\_ft \* pixels\_per\_foot)))

    feet\_per\_canvas\_unit = 1 / pixels\_per\_foot

    grid\_spacing\_units = GRID\_SPACING\_FEET / feet\_per\_canvas\_unit



    return canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units





def make\_runtime\_plant\_pool(plants, feet\_per\_canvas\_unit):

    runtime\_plants = []

    for plant in plants:

        p = plant.copy()

        p["radius"] = (p["spread\_ft"] / 2) / feet\_per\_canvas\_unit

        p["style\_fit"] = STYLE\_FIT\_BY\_CODE.get(p.get("code"), ["Wild / Naturalized"])

        runtime\_plants.append(p)

    return runtime\_plants





def circle\_inside(poly, x, y, r):

    return poly.contains(Point(x, y).buffer(r))





def circles\_overlap(x, y, r, placed, spacing\_factor, plant=None):

    for p in placed:

        existing\_plant = p["plant"]



        existing\_allows\_underplanting = existing\_plant.get("allows\_underplanting", False)

        current\_allows\_underplanting = plant is not None and plant.get("allows\_underplanting", False)



        if existing\_allows\_underplanting and not current\_allows\_underplanting:

            continue



        if current\_allows\_underplanting and not existing\_allows\_underplanting:

            continue



        distance = math.dist((x, y), (p["x"], p["y"]))

        min\_distance = (r + p["radius"]) \* spacing\_factor



        if distance < min\_distance:

            return True



    return False





def weighted\_choice(plants):

    if not plants:

        return None



    weights = [p.get("weight", 1) for p in plants]

    return random.choices(plants, weights=weights, k=1)[0]





def pack\_layer(poly, plants, target\_area, spacing\_factor, existing\_placed, max\_plants\_total):

    if not plants:

        return [], 0



    minx, miny, maxx, maxy = poly.bounds

    placed\_layer = []

    placed\_area = 0

    attempts = 0

    max\_attempts = 16000



    while (

        placed\_area < target\_area

        and attempts < max\_attempts

        and len(existing\_placed) + len(placed\_layer) < max\_plants\_total

    ):

        attempts += 1



        plant = weighted\_choice(plants)

        if plant is None:

            break



        r = plant["radius"]



        if maxx - minx < r \* 2 or maxy - miny < r \* 2:

            break



        x = random.uniform(minx + r, maxx - r)

        y = random.uniform(miny + r, maxy - r)



        if not circle\_inside(poly, x, y, r):

            continue



        all\_existing = existing\_placed + placed\_layer



        if circles\_overlap(x, y, r, all\_existing, spacing\_factor, plant):

            continue



        placed\_layer.append({"x": x, "y": y, "radius": r, "plant": plant})

        placed\_area += math.pi \* (r \*\* 2)



    return placed\_layer, placed\_area





def pack\_by\_role(poly, plant\_pool, target\_coverage, spacing\_factor, max\_plants\_total, role\_split=None):

    boundary\_area = poly.area



    if boundary\_area <= 0:

        return [], 0



    total\_target\_area = boundary\_area \* target\_coverage

    all\_placed = []

    total\_placed\_area = 0



    active\_roles = [role for role in ROLE\_ORDER if any(p["role"] == role for p in plant\_pool)]



    if not active\_roles:

        return [], 0



    if role\_split is None:

        total\_default = sum(default\_role\_percentage(role) for role in active\_roles) or 1

        role\_split = {

            role: default\_role\_percentage(role) / total\_default

            for role in active\_roles

        }



    for role in active\_roles:

        role\_plants = [p for p in plant\_pool if p["role"] == role]



        if not role\_plants:

            continue



        layer\_target\_area = total\_target\_area \* role\_split.get(role, 0)



        placed\_layer, placed\_area = pack\_layer(

            poly=poly,

            plants=role\_plants,

            target\_area=layer\_target\_area,

            spacing\_factor=spacing\_factor,

            existing\_placed=all\_placed,

            max\_plants\_total=max\_plants\_total

        )



        all\_placed.extend(placed\_layer)

        total\_placed\_area += placed\_area



    return all\_placed, total\_placed\_area / boundary\_area



def sun\_is\_compatible(selected\_sun, plant\_sun\_options):

    sun\_compatibility = {

        "Full Sun": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun"],

        "Full Sun-Part Shade": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade", "Part Shade-Full Shade"],

        "Part Shade": ["Part Shade", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade-Full Shade"],

        "Part Shade-Full Shade": ["Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"],

    }



    compatible\_values = sun\_compatibility.get(selected\_sun, [selected\_sun])

    return any(sun\_value in compatible\_values for sun\_value in plant\_sun\_options)





def water\_is\_compatible(selected\_water, plant\_water\_options):

    water\_compatibility = {

        "Low": ["Low", "Moderate-Low", "Low-Moderate"],

        "Moderate-Low": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Low-Moderate": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Moderate": ["Moderate", "Low-Moderate", "Moderate-Low"],

    }



    compatible\_values = water\_compatibility.get(selected\_water, [selected\_water])

    return any(water\_value in compatible\_values for water\_value in plant\_water\_options)





def hardiness\_is\_compatible(selected\_zones, usda\_min, usda\_max):

    if not selected\_zones:

        return True

    return any(usda\_min <= zone <= usda\_max for zone in selected\_zones)





def filter\_plants(plant\_database, state, selected\_usda\_zones, sun, water):

    """Filter plants by site viability only.



    Community Group and Climate remain plant-database intelligence, but they are no

    longer exposed as a left-panel user decision. Design Style now handles the

    creative/composition intent, while USDA, sun, and water handle viability.

    """

    return [

        plant for plant in plant\_database

        if state in plant["state"]

        and hardiness\_is\_compatible(selected\_usda\_zones, plant["usda\_min"], plant["usda\_max"])

        and sun\_is\_compatible(sun, plant["sun"])

        and water\_is\_compatible(water, plant["water"])

    ]





def filter\_plants\_by\_style(plant\_database, design\_style):

    """Filter by the selected design language.



    The style selector replaces the old visible California Plant Community filter.

    Perennial Garden is intentionally strict: it only returns plants with

    Form = Perennial, so the output behaves like a true perennial palette.

    """

    style\_filtered = [

        plant for plant in plant\_database

        if design\_style in plant.get("style\_fit", [])

    ]



    if design\_style == "Perennial Garden":

        style\_filtered = [p for p in style\_filtered if p.get("form") == "Perennial"]



    if design\_style == "Meadow":

        # Meadow should read grass-dominant, but still permits a few seasonal accents.

        style\_filtered = [p for p in style\_filtered if p.get("form") in ["Grass", "Perennial", "Shrub"]]



    if design\_style == "Dry Garden":

        style\_filtered = [p for p in style\_filtered if "Low" in p.get("water", []) or "Low-Moderate" in p.get("water", [])]



    return style\_filtered





def style\_priority\_score(plant, design\_style):

    settings = STYLE\_LOGIC.get(design\_style, STYLE\_LOGIC["Wild / Naturalized"])

    role\_boost = settings.get("role\_boost", {}).get(plant.get("role"), 1.0)

    form\_priority = settings.get("form\_priority", [])



    form\_score = 0

    if form\_priority and plant.get("form") in form\_priority:

        # Earlier listed forms receive higher priority.

        form\_score = len(form\_priority) - form\_priority.index(plant.get("form"))



    # Lower design tier is more important; invert it for scoring.

    tier\_score = 6 - float(plant.get("design\_tier", 5))

    visual\_score = float(plant.get("visual\_weight", 1))

    weight\_score = float(plant.get("weight", 1))



    return (tier\_score \* 2.0 + visual\_score + weight\_score \* 0.4 + form\_score \* 1.5) \* role\_boost





def limit\_palette\_by\_style(plant\_database, design\_style):

    """Keep the generated palette focused so layouts feel intentional.



    Forced-included plants are added after this function, so user intent still wins.

    Sorting favors the selected design style first, then design hierarchy.

    """

    settings = STYLE\_LOGIC.get(design\_style, STYLE\_LOGIC["Wild / Naturalized"])

    species\_limit = settings.get("species\_limit", 8)



    if len(plant\_database) <= species\_limit:

        return plant\_database



    sorted\_plants = sorted(

        plant\_database,

        key=lambda p: (

            -style\_priority\_score(p, design\_style),

            p.get("design\_tier", 5),

            p.get("name", "")

        )

    )



    selected = sorted\_plants[:species\_limit]



    if design\_style == "Meadow":

        # Keep meadow grass-led whenever possible.

        grasses = [p for p in sorted\_plants if p.get("form") == "Grass"]

        non\_grasses = [p for p in selected if p.get("form") != "Grass"]

        min\_grasses = min(len(grasses), max(2, int(round(species\_limit \* 0.6))))

        selected = grasses[:min\_grasses]

        for p in sorted\_plants:

            if p not in selected and len(selected) < species\_limit:

                selected.append(p)



    if design\_style == "Perennial Garden":

        # Stay true to the user's request: only perennials.

        selected = [p for p in selected if p.get("form") == "Perennial"]



    # Preserve at least one matrix plant when the selected style permits matrix plants.

    if design\_style != "Perennial Garden" and not any(p.get("role") == "Matrix" for p in selected):

        matrix\_candidates = [p for p in sorted\_plants if p.get("role") == "Matrix"]

        if matrix\_candidates and selected:

            selected[-1] = matrix\_candidates[0]



    return selected



def get\_polygon\_from\_canvas(canvas\_json):

    if canvas\_json is None:

        return None



    objects = canvas\_json.get("objects", [])

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





def normalize\_polygon(points):

    if points is None or len(points) < 3:

        return None

    poly = Polygon(points)

    if not poly.is\_valid:

        poly = poly.buffer(0)

    if poly.is\_empty or poly.area <= 0:

        return None

    return poly





def polygon\_points\_from\_geometry(geom):

    if geom is None or geom.is\_empty:

        return []

    if geom.geom\_type == "Polygon":

        return [(float(x), float(y)) for x, y in list(geom.exterior.coords)[:-1]]

    if geom.geom\_type == "MultiPolygon":

        largest = max(list(geom.geoms), key=lambda g: g.area)

        return [(float(x), float(y)) for x, y in list(largest.exterior.coords)[:-1]]

    return []





def valid\_role\_zones\_for\_boundary(role\_zones, main\_poly):

    valid = {}

    for role, points in (role\_zones or {}).items():

        zone\_poly = normalize\_polygon(points)

        if zone\_poly is None:

            continue

        clipped = zone\_poly.intersection(main\_poly)

        if clipped.is\_empty or clipped.area <= 0:

            continue

        valid[role] = clipped

    return valid





def rectangle\_points(canvas\_width, canvas\_height):

    return [(0, 0), (canvas\_width, 0), (canvas\_width, canvas\_height), (0, canvas\_height)]





def fig\_to\_png\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="png", dpi=200, bbox\_inches="tight", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_jpeg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="jpg", dpi=200, bbox\_inches="tight", facecolor="white", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_svg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="svg", bbox\_inches="tight")

    buffer.seek(0)

    return buffer





def canvas\_area\_to\_sqft(area\_canvas\_units, feet\_per\_canvas\_unit):

    return area\_canvas\_units \* (feet\_per\_canvas\_unit \*\* 2)





def canvas\_length\_to\_feet(length\_canvas\_units, feet\_per\_canvas\_unit):

    return length\_canvas\_units \* feet\_per\_canvas\_unit





def draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units):

    x = 0

    while x <= canvas\_width:

        ax.axvline(x, linewidth=0.4, alpha=0.25)

        x += grid\_spacing\_units



    y = 0

    while y <= canvas\_height:

        ax.axhline(y, linewidth=0.4, alpha=0.25)

        y += grid\_spacing\_units





def get\_image\_aspect\_ratio(image\_path):

    try:

        img = plt.imread(image\_path)

        height\_px, width\_px = img.shape[:2]

        if height\_px == 0:

            return 1

        return width\_px / height\_px

    except Exception:

        return 1





def varied\_height(plant):

    tolerance = HEIGHT\_VARIATION\_BY\_HIERARCHY.get(plant["hierarchy"], 0.08)

    variation = random.uniform(1 - tolerance, 1 + tolerance)

    return plant["elevation\_height"] \* variation





def prepare\_uploaded\_image(uploaded\_file, canvas\_width, canvas\_height):

    if uploaded\_file is None:

        return None, None



    image = Image.open(uploaded\_file).convert("RGB")

    image = image.resize((canvas\_width, canvas\_height))

    image\_array = plt.imread(BytesIO(image\_to\_png\_bytes(image).getvalue()))

    return image, image\_array





def render\_trace\_overlay(image, points, canvas\_width, canvas\_height):

    """Return a PIL image with the uploaded background plus the clicked/traced bedline points.



    This avoids relying on streamlit-drawable-canvas background\_image, which can render

    blank on Streamlit Cloud. Users click around the bedline directly on the image.

    """

    if image is None:

        return None



    overlay = image.copy().convert("RGB")

    overlay = overlay.resize((canvas\_width, canvas\_height))

    draw = ImageDraw\.Draw(overlay)



    if len(points) >= 2:

        draw\.line(points, fill=(255, 255, 255), width=3)



    if len(points) >= 3:

        # Light preview of the closing segment so users understand the final polygon.

        draw\.line([points[-1], points[0]], fill=(255, 255, 255), width=2)



    for idx, (x, y) in enumerate(points):

        r = 5

        draw\.ellipse((x - r, y - r, x + r, y + r), fill=(255, 80, 80), outline=(255, 255, 255), width=2)

        draw\.text((x + 7, y - 7), str(idx + 1), fill=(255, 255, 255))



    return overlay





def image\_to\_png\_bytes(image):

    buffer = BytesIO()

    image.save(buffer, format="PNG")

    buffer.seek(0)

    return buffer





def escape\_svg\_text(value):

    return html.escape(str(value), quote=True)





def plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit, role\_zones=None):

    """Create a clean vector SVG of the plan geometry.



    This avoids relying on Matplotlib's SVG output and gives you true circle/vector objects.

    """

    path\_points = " ".join([f"{x:.2f},{y:.2f}" for x, y in points])

    svg = StringIO()

    svg.write(f'\<svg xmlns="http\://www\.w3.org/2000/svg" width="{canvas\_width}" height="{canvas\_height}" viewBox="0 0 {canvas\_width} {canvas\_height}">\n')

    svg.write('\<rect width="100%" height="100%" fill="white"/>\n')

    svg.write(f'\<polygon points="{path\_points}" fill="none" stroke="black" stroke-width="2"/>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        zone\_path = " ".join([f"{x:.2f},{y:.2f}" for x, y in zone\_points])

        first\_x, first\_y = zone\_points[0]

        svg.write(f'\<polygon points="{zone\_path}" fill="none" stroke="black" stroke-width="1" stroke-dasharray="4 4" opacity="0.45"/>\n')

        svg.write(f'\<text x="{first\_x:.2f}" y="{first\_y:.2f}" font-family="Arial" font-size="10" opacity="0.65">{escape\_svg\_text(role)} zone\</text>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        closed\_zone = zone\_points + [zone\_points[0]]

        layer\_name = f"ROLE\_ZONE\_{role.upper().replace(' ', '\_')}"

        for i in range(len(closed\_zone) - 1):

            x1, y1 = closed\_zone[i]

            x2, y2 = closed\_zone[i + 1]

            dxf.write("0\nLINE\n8\n" + layer\_name + "\n")

            dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

            dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dash = ' stroke-dasharray="6 4"' if plant.get("allows\_underplanting", False) else ""

        weight = "bold" if plant.get("allows\_underplanting", False) else "normal"

        svg.write(f'\<circle cx="{item["x"]:.2f}" cy="{item["y"]:.2f}" r="{item["radius"]:.2f}" fill="none" stroke="black" stroke-width="1.2"{dash}/>\n')

        svg.write(f'\<text x="{item["x"]:.2f}" y="{item["y"]:.2f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="8" font-weight="{weight}">{escape\_svg\_text(plant["code"])}\</text>\n')



    svg.write(f'\<text x="12" y="{canvas\_height - 14}" font-family="Arial" font-size="10">Scale: 1 px = {feet\_per\_canvas\_unit:.3f} ft\</text>\n')

    svg.write('\</svg>')

    return BytesIO(svg.getvalue().encode("utf-8"))





def plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit, role\_zones=None):

    """Export a simple ASCII DXF in real feet.



    AutoCAD, Rhino, Vectorworks, and many CAD tools can open DXF. This is the practical

    Streamlit-friendly alternative to DWG.

    """

    dxf = StringIO()

    dxf.write("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n2\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nENTITIES\n")



    closed\_points = points + [points[0]]

    for i in range(len(closed\_points) - 1):

        x1, y1 = closed\_points[i]

        x2, y2 = closed\_points[i + 1]

        dxf.write("0\nLINE\n8\nBOUNDARY\n")

        dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dxf.write("0\nCIRCLE\n8\nPLANTS\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"40\n{item['radius'] \* feet\_per\_canvas\_unit:.4f}\n")

        dxf.write("0\nTEXT\n8\nPLANT\_CODES\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write("40\n0.35\n")

        dxf.write(f"1\n{plant['code']}\n")



    dxf.write("0\nENDSEC\n0\nEOF\n")

    return BytesIO(dxf.getvalue().encode("utf-8"))



\# -----------------------------

\# Sidebar

\# -----------------------------



with st.sidebar:

    st.markdown("### by The Landscape Library")



    st.header("Input Method")

    input\_method = st.radio(

        "Choose how to define the planting bed",

        ["Draw Boundary", "Upload JPEG Image"],

        index=0

    )



    st.info("Max 50' bed")



    if input\_method == "Upload JPEG Image":

        st.caption("Upload a JPEG image as a scaled reference, then click points around the actual bedline.")

        uploaded\_bed\_image = st.file\_uploader(

            "Upload bed image",

            type=["jpg", "jpeg"]

        )



        bed\_length\_ft = st.number\_input(

            "Image length / horizontal dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=30.0,

            step=1.0

        )



        bed\_width\_ft = st.number\_input(

            "Image width / vertical dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=15.0,

            step=1.0

        )

    else:

        uploaded\_bed\_image = None

        bed\_length\_ft = DEFAULT\_BED\_LENGTH\_FEET

        bed\_width\_ft = DEFAULT\_BED\_WIDTH\_FEET



    canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units = get\_canvas\_setup(

        bed\_length\_ft,

        bed\_width\_ft

    )



    st.header("Site Parameters")



    state = st.selectbox("Plant Region", ["California"])

    climate = "All Compatible Communities"



    design\_style = st.selectbox(

        "Design Style",

        DESIGN\_STYLE\_OPTIONS,

        index=0

    )

    st.caption(STYLE\_LOGIC[design\_style]["description"])



    st.markdown("\*\*USDA Hardiness\*\*")

    st.caption("Select one or more USDA zones. Plants are included when the selected zone falls between USDA Min and USDA Max in the plant database.")

    usda\_zone\_options = list(range(5, 11))

    default\_usda\_zones = [9]

    selected\_usda\_zones = []

    zone\_cols = st.columns(3)

    for idx, zone in enumerate(usda\_zone\_options):

        with zone\_cols[idx % 3]:

            checked = st.checkbox(f"Zone {zone}", value=zone in default\_usda\_zones, key=f"usda\_zone\_{zone}")

            if checked:

                selected\_usda\_zones.append(zone)



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



    target\_coverage = DENSITY\_OPTIONS[density]

    spacing\_factor = SPACING\_BY\_DENSITY[density] \* STYLE\_LOGIC[design\_style]["spacing\_multiplier"]

    max\_plants\_total = MAX\_PLANTS\_BY\_DENSITY[density]



    st.header("Scale")

    st.caption(f"Bed limit: {MAX\_BED\_FEET} ft max length or width")

    st.caption(f"Active bed: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")



\# -----------------------------

\# Active plant database + image prep

\# -----------------------------



runtime\_plants = make\_runtime\_plant\_pool(PLANTS, feet\_per\_canvas\_unit)

selected\_plants = filter\_plants(runtime\_plants, state, selected\_usda\_zones, sun, water)

selected\_plants = filter\_plants\_by\_style(selected\_plants, design\_style)



\# Manual include / exclude controls

all\_matching\_names = [p["name"] for p in selected\_plants]

with st.sidebar:

    st.header("Plant Controls")

    include\_names = st.multiselect("Force include plants", [p["name"] for p in runtime\_plants])

    exclude\_names = st.multiselect("Exclude plants", all\_matching\_names)



    st.divider()

    generate = st.button(

        "Generate Planting Layout",

        type="primary",

        use\_container\_width=True

    )



role\_split = None



forced = [p for p in runtime\_plants if p["name"] in include\_names]

selected\_plants = [p for p in selected\_plants if p["name"] not in exclude\_names]

selected\_plants = limit\_palette\_by\_style(selected\_plants, design\_style)



for p in forced:

    if p["name"] not in [sp["name"] for sp in selected\_plants]:

        selected\_plants.append(p)



background\_image = None

background\_array = None



if input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    background\_image, background\_array = prepare\_uploaded\_image(uploaded\_bed\_image, canvas\_width, canvas\_height)



\# -----------------------------

\# Main UI

\# -----------------------------



left, right = st.columns([2, 1])



with left:

    if input\_method == "Draw Boundary":

        st.subheader("1. Draw Planting Boundary")

        st.caption("TIP: Left click to add boundary points. Right click to end nearest the origin point and complete the boundary.")

        st.caption('Drawing canvas: 50\\'-0" horizontal × 50\\'-0" vertical.')



        canvas\_result = st\_canvas(

            fill\_color="rgba(0, 0, 0, 0)",

            stroke\_width=3,

            stroke\_color="#111111",

            background\_color="#f7f7f2",

            height=canvas\_height,

            width=canvas\_width,

            drawing\_mode="polygon",

            key="draw\_boundary\_canvas",

        )

    else:

        st.subheader("1. Upload Scaled Bed Image + Trace Bedline")

        st.caption("Click around the planting bedline in order. Use more points for curves. The final segment closes automatically between the last point and first point.")



        if uploaded\_bed\_image is None:

            st.warning("Upload a JPEG image first, then click points around the actual bedline.")

            canvas\_result = None

        else:

            canvas\_result = None



            if streamlit\_image\_coordinates is None:

                st.error("Missing package: streamlit-image-coordinates. Add streamlit-image-coordinates to requirements.txt, then redeploy.")

            else:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                last\_click\_key = f"last\_click\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"



                if trace\_key not in st.session\_state:

                    st.session\_state[trace\_key] = []

                if last\_click\_key not in st.session\_state:

                    st.session\_state[last\_click\_key] = None



                st.caption("Click points around the bedline in order. Use more points for curves. The final segment closes automatically between the last and first point.")



                overlay\_image = render\_trace\_overlay(

                    background\_image,

                    st.session\_state[trace\_key],

                    canvas\_width,

                    canvas\_height

                )



                clicked = streamlit\_image\_coordinates(

                    overlay\_image,

                    key=f"click\_trace\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}",

                    width=canvas\_width

                )



                if clicked is not None and "x" in clicked and "y" in clicked:

                    new\_point = (int(clicked["x"]), int(clicked["y"]))



                    if st.session\_state[last\_click\_key] != new\_point:

                        existing\_points = st.session\_state[trace\_key]



                        # Prevent accidental double-click duplicates.

                        if len(existing\_points) == 0 or math.dist(existing\_points[-1], new\_point) > 4:

                            existing\_points.append(new\_point)

                            st.session\_state[trace\_key] = existing\_points



                        st.session\_state[last\_click\_key] = new\_point

                        st.rerun()



                b1, b2, b3 = st.columns(3)

                with b1:

                    if st.button("Undo Last Point") and len(st.session\_state[trace\_key]) > 0:

                        st.session\_state[trace\_key] = st.session\_state[trace\_key][:-1]

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b2:

                    if st.button("Clear Trace"):

                        st.session\_state[trace\_key] = []

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b3:

                    st.metric("Trace Points", len(st.session\_state[trace\_key]))



                if len(st.session\_state[trace\_key]) < 3:

                    st.info("Add at least 3 points before generating the planting layout.")



with right:

    st.subheader("Don't See Your Region?")

    st.caption("Request the next region you'd like added.")



    requested\_region = st.text\_input(

        "Region",

        placeholder="Example: Texas, Florida, Pacific Northwest"

    )



    requested\_city = st.text\_input(

        "City",

        placeholder="Example: Austin"

    )



    if st.button("Submit"):

        if requested\_region.strip() and requested\_city.strip():

            ok, error\_message = log\_region\_request(

                st.session\_state.get("user\_email"),

                requested\_region,

                requested\_city,

                climate=climate,

                sun\_exposure=sun,

                water\_needs=water,

                design\_style=design\_style,

            )

            if ok:

                st.success("Region request submitted.")

            else:

                st.error(f"Region request was not saved: {error\_message}")

        elif not requested\_region.strip():

            st.warning("Enter a region before submitting.")

        else:

            st.warning("Enter a city before submitting.")



    st.subheader("3. Selected Plant Palette")



    if len(selected\_plants) == 0:

        st.warning("No plants match these parameters yet. Try adjusting design style, USDA hardiness, sun exposure, or water needs.")

    else:

        for plant in selected\_plants:

            canopy\_note = " | allows underplanting" if plant.get("allows\_underplanting", False) else ""

            st.write(f"\*\*{plant['name']}\*\*")

            st.caption(

                f"{plant['code']} | {plant['common\_name']} | {plant['form']} | {plant['role']} | spread: {plant['spread\_ft']} ft{canopy\_note}"

            )



\# -----------------------------

\# Boundary metrics

\# -----------------------------



points\_preview = None



if input\_method == "Draw Boundary" and canvas\_result is not None:

    points\_preview = get\_polygon\_from\_canvas(canvas\_result.json\_data)

elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

    points\_preview = st.session\_state.get(trace\_key, [])

    if len(points\_preview) < 3:

        points\_preview = None



if points\_preview is not None:

    preview\_poly = Polygon(points\_preview)



    if not preview\_poly.is\_valid:

        preview\_poly = preview\_poly.buffer(0)



    if preview\_poly.area > 0:

        area\_sqft = canvas\_area\_to\_sqft(preview\_poly.area, feet\_per\_canvas\_unit)

        perimeter\_ft = canvas\_length\_to\_feet(preview\_poly.length, feet\_per\_canvas\_unit)

        minx\_preview, miny\_preview, maxx\_preview, maxy\_preview = preview\_poly.bounds



        width\_ft = canvas\_length\_to\_feet(maxx\_preview - minx\_preview, feet\_per\_canvas\_unit)

        depth\_ft = canvas\_length\_to\_feet(maxy\_preview - miny\_preview, feet\_per\_canvas\_unit)



        st.subheader("Boundary Metrics")



        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Approx. Area", f"{area\_sqft:,.0f} sq ft")

        c2.metric("Approx. Perimeter", f"{perimeter\_ft:,.0f} ft")

        c3.metric("Approx. Length", f"{width\_ft:,.0f} ft")

        c4.metric("Approx. Width", f"{depth\_ft:,.0f} ft")



\# -----------------------------

\# Generate

\# -----------------------------



if generate:

    if supabase is not None and st.session\_state.get("user\_email"):

        user\_check = supabase.table("users").select("\*").eq("email", st.session\_state.user\_email).execute()

        current\_user = user\_check.data[0] if user\_check.data else {}

        if not current\_user.get("paid\_status", False) and (current\_user.get("total\_generations") or 0) >= FREE\_GENERATION\_LIMIT:

            st.warning("You have reached the free generation limit.")

            log\_event(st.session\_state.user\_email, "paywall\_shown")

            st.stop()

    try:

        with st.spinner("Generating planting plan and elevation view\..."):

            if input\_method == "Draw Boundary" and canvas\_result is not None:

                points = get\_polygon\_from\_canvas(canvas\_result.json\_data)

            elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                points = st.session\_state.get(trace\_key, [])

                if len(points) < 3:

                    points = None

            else:

                points = None



            if points is None:

                if input\_method == "Draw Boundary":

                    st.warning("Draw a closed polygon boundary first.")

                else:

                    st.warning("Upload a JPEG image and trace a closed polygon boundary first.")



            elif bed\_length\_ft > MAX\_BED\_FEET or bed\_width\_ft > MAX\_BED\_FEET:

                st.warning(f"The bed is too large. Keep the image dimensions at or below {MAX\_BED\_FEET} ft.")



            elif len(selected\_plants) == 0:

                st.warning("No plants are available for the selected site parameters.")



            else:

                poly = normalize\_polygon(points)



                if poly is None:

                    st.warning("The boundary is invalid. Try tracing a clearer closed shape.")



                else:

                    placed\_instances, actual\_coverage = pack\_by\_role(

                        poly=poly,

                        plant\_pool=selected\_plants,

                        target\_coverage=target\_coverage,

                        spacing\_factor=spacing\_factor,

                        max\_plants\_total=max\_plants\_total,

                        role\_split=role\_split

                    )



                    if len(placed\_instances) == 0:

                        st.warning("No plants could fit inside the boundary. Try a larger area, lower density, or different plant parameters.")



                    else:

                        new\_generation\_count = increment\_generation\_count(st.session\_state.get("user\_email"))

                        log\_event(

                            st.session\_state.get("user\_email"),

                            "generation\_run",

                            state=state,

                            zone=", ".join([f"USDA {z}" for z in selected\_usda\_zones]),

                            climate=climate,

                            sun\_exposure=sun,

                            water\_needs=water,

                            design\_style=design\_style,

                            notes=f"Density: {density}; Plants generated: {len(placed\_instances)}"

                        )



                        st.subheader("Plan View")



                        fig, ax = plt.subplots(figsize=(10, 10))



                        if background\_array is not None:

                            ax.imshow(background\_array, extent=(0, canvas\_width, canvas\_height, 0), alpha=0.35, zorder=0)



                        xs, ys = zip(\*(points + [points[0]]))

                        ax.plot(xs, ys, linewidth=2, zorder=3)



                        draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units)



                        for item in placed\_instances:

                            plant = item["plant"]



                            if plant.get("allows\_underplanting", False):

                                continue



                            circle = plt.Circle(

                                (item["x"], item["y"]),

                                item["radius"],

                                fill=False,

                                linewidth=1.2,

                                zorder=4

                            )

                            ax.add\_patch(circle)



                            ax.text(

                                item["x"],

                                item["y"],

                                plant["code"],

                                ha="center",

                                va="center",

                                fontsize=8,

                                zorder=5

                            )



                        for item in placed\_instances:

                            plant = item["plant"]



                            if not plant.get("allows\_underplanting", False):

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

                            ax.add\_patch(circle)



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



                        ax.set\_xlim(0, canvas\_width)

                        ax.set\_ylim(canvas\_height, 0)

                        ax.set\_aspect("equal")

                        ax.axis("off")



                        st.pyplot(fig)



                        plan\_png = fig\_to\_png\_bytes(fig)

                        plan\_svg = plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit)

                        plan\_dxf = plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit)



                        d1, d2, d3 = st.columns(3)

                        with d1:

                            st.download\_button(

                                label="Download Plan PNG",

                                data=plan\_png,

                                file\_name="yodra-planting-plan.png",

                                mime="image/png"

                            )

                        with d2:

                            st.download\_button(

                                label="Download Plan SVG",

                                data=plan\_svg,

                                file\_name="yodra-planting-plan.svg",

                                mime="image/svg+xml"

                            )

                        with d3:

                            st.download\_button(

                                label="Download Plan DXF",

                                data=plan\_dxf,

                                file\_name="yodra-planting-plan.dxf",

                                mime="application/dxf"

                            )



                        st.caption(f"Target coverage: {round(target\_coverage \* 100)}%")

                        st.caption(f"Actual generated coverage: {round(actual\_coverage \* 100)}%")

                        st.caption(f"Active bed scale: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")

                        st.caption(f"Maximum plant instances capped at {max\_plants\_total} for app performance.")



                        st.subheader("Elevation View")

                        st.caption("Elevation uses the same plant instances generated in plan view, with subtle height variation.")



                        elev\_fig, elev\_ax = plt.subplots(figsize=(12, 4))



                        placed\_sorted = sorted(placed\_instances, key=lambda item: item["x"])



                        for item in placed\_sorted:

                            plant = item["plant"]

                            image\_path = plant["image"]



                            height = varied\_height(plant)

                            aspect\_ratio = get\_image\_aspect\_ratio(image\_path)

                            width = height \* aspect\_ratio



                            if os.path.exists(image\_path):

                                img = plt.imread(image\_path)



                                elev\_ax.imshow(

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

                                elev\_ax.text(

                                    item["x"],

                                    height / 2,

                                    plant["code"],

                                    ha="center",

                                    va="center",

                                    fontsize=8

                                )



                        elev\_ax.axhline(0, linewidth=1)

                        elev\_ax.set\_xlim(0, canvas\_width)

                        elev\_ax.set\_ylim(0, 140)

                        elev\_ax.axis("off")



                        st.pyplot(elev\_fig)



                        elevation\_png = fig\_to\_png\_bytes(elev\_fig)

                        elevation\_jpeg = fig\_to\_jpeg\_bytes(elev\_fig)



                        e1, e2 = st.columns(2)

                        with e1:

                            st.download\_button(

                                label="Download Elevation PNG",

                                data=elevation\_png,

                                file\_name="yodra-planting-elevation.png",

                                mime="image/png"

                            )

                        with e2:

                            st.download\_button(

                                label="Download Elevation JPEG",

                                data=elevation\_jpeg,

                                file\_name="yodra-planting-elevation.jpg",

                                mime="image/jpeg"

                            )



                        counts = {}

                        for item in placed\_instances:

                            plant = item["plant"]

                            counts[plant["name"]] = counts.get(plant["name"], 0) + 1



                        st.subheader("Plant Schedule")



                        schedule = []

                        for plant\_name, count in counts.items():

                            plant = next(p for p in runtime\_plants if p["name"] == plant\_name)



                            schedule.append({

                                "Code": plant["code"],

                                "Count": count,

                                "Botanical Name": plant["name"],

                                "Common Name": plant["common\_name"],

                                "Form": plant["form"],

                                "Role": plant["role"],

                                "Texture": plant["texture"],

                                "Color Tone": plant["color\_tone"],

                                "Visual Weight": plant["visual\_weight"],

                                "Spread Ft": plant["spread\_ft"],

                                "Height Ft": plant["height\_ft"],

                                "Plant Region": state,

                                "Climate": ", ".join(plant["climate"]),

                                "USDA Min": plant["usda\_min"],

                                "USDA Max": plant["usda\_max"],

                                "Sun": ", ".join(plant["sun"]),

                                "Water": ", ".join(plant["water"]),

                                "Seasonality": plant["seasonality"],

                                "Style Fit": ", ".join(plant.get("style\_fit", [])),

                                "Allows Underplanting": plant.get("allows\_underplanting", False)

                            })



                        schedule\_df = pd.DataFrame(schedule)

                        st.dataframe(schedule\_df, width="stretch")



                        csv\_buffer = schedule\_df.to\_csv(index=False).encode("utf-8")

                        st.download\_button(

                            label="Download Plant Schedule CSV / Excel",

                            data=csv\_buffer,

                            file\_name="yodra-plant-schedule.csv",

                            mime="text/csv",

                            on\_click=lambda: increment\_export\_count(st.session\_state.get("user\_email"))

                        )

                        log\_event(st.session\_state.get("user\_email"), "schedule\_export\_ready", export\_type="csv")



    except Exception as e:

        st.error("The app crashed while generating the layout.")

        st.exception(e)


















---














# Version 3.4





import streamlit as st

from datetime import datetime, timezone

try:

    from supabase import create\_client

except Exception:

    create\_client = None

import pandas as pd



\# -------------------------

\# SUPABASE USER TRACKING

\# -------------------------



FREE\_GENERATION\_LIMIT = 999



def get\_supabase\_client():

    if create\_client is None:

        return None

    url = st.secrets.get("SUPABASE\_URL", "")

    key = st.secrets.get("SUPABASE\_SERVICE\_ROLE\_KEY", "")

    if not url or not key:

        return None

    return create\_client(url, key)



supabase = get\_supabase\_client()



def log\_event(email, event\_type, \*\*kwargs):

    """Insert an event using only the columns that exist in the current Supabase events table.



    Current expected columns:

    email, event\_type, created\_at, climate, sun\_exposure, water\_needs,

    design\_style, export\_type, notes.



    Do not add state, zone, density, or plants\_generated\_count unless those columns

    are also added to Supabase. Supabase will reject inserts when unknown columns

    are included.

    """

    if supabase is None or not email:

        return False, "Supabase is not connected or user email is missing."



    event = {

        "email": email,

        "event\_type": event\_type,

        "created\_at": datetime.now(timezone.utc).isoformat(),

        "climate": kwargs.get("climate"),

        "sun\_exposure": kwargs.get("sun\_exposure"),

        "water\_needs": kwargs.get("water\_needs"),

        "design\_style": kwargs.get("design\_style"),

        "export\_type": kwargs.get("export\_type"),

        "notes": kwargs.get("notes"),

    }



    # Remove empty optional fields so Supabase receives a clean payload.

    event = {k: v for k, v in event.items() if v is not None}



    try:

        supabase.table("events").insert(event).execute()

        return True, None

    except Exception as e:

        return False, str(e)





def log\_plant\_request(email, requested\_plant, \*\*kwargs):

    requested\_plant = (requested\_plant or "").strip()

    if not requested\_plant:

        return False, "Plant request is empty."



    ok, err = log\_event(

        email,

        "plant\_requested",

        notes=requested\_plant,

        \*\*kwargs

    )



    # Optional dedicated table. If you create a plant\_requests table in Supabase,

    # this will also save requests there. If that table does not exist, the

    # events table above is still the primary tracking location.

    if supabase is not None and email:

        try:

            supabase.table("plant\_requests").insert({

                "email": email,

                "requested\_plant": requested\_plant,

                "created\_at": datetime.now(timezone.utc).isoformat(),

                "climate": kwargs.get("climate"),

                "sun\_exposure": kwargs.get("sun\_exposure"),

                "water\_needs": kwargs.get("water\_needs"),

                "notes": requested\_plant,

            }).execute()

        except Exception:

            pass



    return ok, err





def log\_region\_request(email, requested\_region, requested\_city, \*\*kwargs):

    """Save a region request into the existing Supabase events table.



    This uses event\_type='region\_requested' and stores the requested region/city

    inside the existing notes column so no new Supabase columns are required.

    """

    requested\_region = (requested\_region or "").strip()

    requested\_city = (requested\_city or "").strip()



    if not requested\_region:

        return False, "Region request is empty."

    if not requested\_city:

        return False, "City is empty."



    notes = f"Requested Region: {requested\_region} | City: {requested\_city}"



    ok, err = log\_event(

        email,

        "region\_requested",

        notes=notes,

        \*\*kwargs

    )



    # Optional dedicated table. The events table above remains the primary save

    # location. If region\_requests does not exist, this silently falls back to events only.

    if supabase is not None and email:

        try:

            supabase.table("region\_requests").insert({

                "email": email,

                "requested\_region": requested\_region,

                "requested\_city": requested\_city,

                "created\_at": datetime.now(timezone.utc).isoformat(),

                "climate": kwargs.get("climate"),

                "sun\_exposure": kwargs.get("sun\_exposure"),

                "water\_needs": kwargs.get("water\_needs"),

                "design\_style": kwargs.get("design\_style"),

                "notes": notes,

            }).execute()

        except Exception:

            pass



    return ok, err





def get\_or\_create\_user(email):

    email = email.strip().lower()

    if supabase is None:

        return {"email": email, "paid\_status": False, "total\_generations": 0, "total\_exports": 0}



    now = datetime.now(timezone.utc).isoformat()

    result = supabase.table("users").select("\*").eq("email", email).execute()

    if result.data:

        user = result.data[0]

        supabase.table("users").update({"last\_seen": now}).eq("email", email).execute()

        return user



    new\_user = {

        "email": email,

        "first\_seen": now,

        "last\_seen": now,

        "paid\_status": False,

        "total\_generations": 0,

        "total\_exports": 0,

    }

    created = supabase.table("users").insert(new\_user).execute()

    return created.data[0] if created.data else new\_user



def increment\_generation\_count(email):

    if supabase is None:

        return 0

    result = supabase.table("users").select("total\_generations").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_generations") or 0

    new\_count = current + 1

    supabase.table("users").update({

        "total\_generations": new\_count,

        "last\_seen": datetime.now(timezone.utc).isoformat()

    }).eq("email", email).execute()

    return new\_count



def increment\_export\_count(email):

    if supabase is None:

        return

    result = supabase.table("users").select("total\_exports").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_exports") or 0

    supabase.table("users").update({"total\_exports": current + 1}).eq("email", email).execute()



def beta\_email\_gate():

    if "user\_email" not in st.session\_state:

        st.session\_state.user\_email = None

    if st.session\_state.user\_email:

        return True



    st.markdown("""

    \<div style="display\:flex;align-items\:center;gap:10px;flex-wrap\:wrap;">

        \<h1 style="margin:0;line-height:1.1;">Generate Planting Concepts in Minutes\</h1>

        \<span style="

            background:#f3f4f6;

            border:1px solid #e5e7eb;

            padding:3px 10px;

            border-radius:999px;

            font-size:12px;

            font-weight:700;

            letter-spacing:0.02em;

        ">

            Beta

        \</span>

    \</div>

    """, unsafe\_allow\_html=True)

    st.markdown("Visualize spacing, explore plant combinations, and build preliminary plant palettes.")

    st.caption("California Plant Database Available")

    st.caption("Texas and Florida Coming Soon")

    email = st.text\_input("Enter your email to continue")

    if st.button("Start Designing"):

        if "@" not in email or "." not in email:

            st.error("Please enter a valid email address.")

            st.stop()

        user = get\_or\_create\_user(email)

        st.session\_state.user\_email = user["email"]

        st.session\_state.user\_data = user

        log\_event(user["email"], "app\_opened")

        st.rerun()

    st.stop()



beta\_email\_gate()





\# -------------------------

\# YOUR APP BELOW

\# -------------------------



import random

import math

import os

import html

import base64

from io import BytesIO, StringIO



import matplotlib.pyplot as plt

from PIL import Image, ImageDraw

from shapely.geometry import Polygon, Point

from streamlit\_drawable\_canvas import st\_canvas

try:

    from streamlit\_image\_coordinates import streamlit\_image\_coordinates

except Exception:

    streamlit\_image\_coordinates = None

\# -----------------------------

\# Compatibility patch

\# -----------------------------

\# streamlit-drawable-canvas still calls an older Streamlit helper named

\# st.image.image\_to\_url when using background\_image. Newer Streamlit versions

\# removed that helper, which causes an AttributeError on image upload.

\# This patch restores the expected helper by converting the PIL background image

\# into a browser-safe base64 data URL.

def \_yodra\_image\_to\_url(image, width=None, clamp=False, channels="RGB", output\_format="PNG", image\_id=None):

    """Compatibility helper for streamlit-drawable-canvas background images.



    Newer Streamlit versions removed st.image.image\_to\_url, but

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

    return f"data\:image/png;base64,{encoded}"



try:

    # This is the exact object streamlit-drawable-canvas references: st.image.image\_to\_url

    st.image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



try:

    # Also patch Streamlit's image module for environments that reference it directly.

    import streamlit.elements.image as st\_image

    st\_image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



st.set\_page\_config(

    page\_title="Generate Planting Concepts",

    layout="wide"

)



title\_col, badge\_col = st.columns([8, 1])

with title\_col:

    st.title("Generate Planting Concepts in Minutes")

with badge\_col:

    st.markdown(

        """

        \<div style="

            margin-top:14px;

            background:#f3f4f6;

            border:1px solid #e5e7eb;

            padding:4px 10px;

            border-radius:999px;

            text-align\:center;

            font-size:12px;

            font-weight:700;

            letter-spacing:0.02em;

        ">

            Beta

        \</div>

        """,

        unsafe\_allow\_html=True,

    )



st.caption("Visualize spacing, explore plant combinations, and build preliminary plant palettes.")

st.info("California Plant Database Available • Texas and Florida Coming Soon")



\# -----------------------------

\# Canvas + Scale settings

\# -----------------------------



MAX\_CANVAS\_WIDTH = 900

MAX\_CANVAS\_HEIGHT = 600

DEFAULT\_BED\_LENGTH\_FEET = 50

DEFAULT\_BED\_WIDTH\_FEET = 50

MAX\_BED\_FEET = 50



GRID\_SPACING\_FEET = 5



DENSITY\_OPTIONS = {

    "Low": 0.30,

    "Moderate": 0.45,

    "Dense": 0.68,

    "Very Dense": 0.90

}



SPACING\_BY\_DENSITY = {

    "Low": 1.30,

    "Moderate": 1.15,

    "Dense": 1.05,

    "Very Dense": 1.00

}



MAX\_PLANTS\_BY\_DENSITY = {

    "Low": 180,

    "Moderate": 260,

    "Dense": 350,

    "Very Dense": 500

}



\# Placeholder used only while the plant database is being defined.

\# Runtime radii are recalculated after the active bed scale is known.

def feet\_to\_canvas\_radius(width\_ft):

    return width\_ft / 2



\# -----------------------------

\# Plant database

\# -----------------------------



PLANTS = [

    {

        "name": "Carex pansa",

        "common\_name": "Sand Dune Sedge",

        "code": "CP",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 1,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-pansa.webp",

        "elevation\_height": 28,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum latifolium",

        "common\_name": "Coast Buckwheat",

        "code": "EL",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Silver-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-latifolium.webp",

        "elevation\_height": 34,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Festuca californica",

        "common\_name": "California Fescue",

        "code": "FC",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/festuca-californica.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Salvia spathacea",

        "common\_name": "Hummingbird Sage",

        "code": "SS",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/salvia-spathacea.webp",

        "elevation\_height": 42,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Iris douglasiana",

        "common\_name": "Douglas Iris",

        "code": "ID",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/iris-douglasiana.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Arbutus menziesii",

        "common\_name": "Pacific Madrone",

        "code": "AM",

        "state": ["California"],

        "climate": ["Coastal", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 20,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(20),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arbutus-menziesii.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Arctostaphylos densiflora 'Howard McMinn'",

        "common\_name": "Howard McMinn Manzanita",

        "code": "AHM",

        "state": ["California"],

        "climate": ["Coastal", "Inland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 8,

        "height\_ft": 7,

        "radius": feet\_to\_canvas\_radius(8),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arctostaphylos-howard-mcminn.webp",

        "elevation\_height": 105,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

    {

        "name": "Muhlenbergia rigens",

        "common\_name": "Deergrass",

        "code": "MR",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/muhlenbergia-rigens.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Stipa pulchra",

        "common\_name": "Purple Needlegrass",

        "code": "SP",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Golden Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/stipa-pulchra.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Juncus patens",

        "common\_name": "Common Rush",

        "code": "JP",

        "state": ["California"],

        "climate": ["Inland", "Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 3,

        "height\_ft": 3,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/juncus-patens.webp",

        "elevation\_height": 46,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum fasciculatum",

        "common\_name": "California Buckwheat",

        "code": "EF",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-fasciculatum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Epilobium canum",

        "common\_name": "California Fuchsia",

        "code": "EC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Semi-evergreen",

        "image": "plant\_images/epilobium-canum.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Artemisia californica",

        "common\_name": "California Sagebrush",

        "code": "AC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Silver-Grey",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/artemisia-californica.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Quercus chrysolepis",

        "common\_name": "Canyon Live Oak",

        "code": "QC",

        "state": ["California"],

        "climate": ["Inland", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 30,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(30),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/quercus-chrysolepis.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Carex tumulicola",

        "common\_name": "Foothill Sedge",

        "code": "CT",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Sun"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-tumulicola.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Polystichum munitum",

        "common\_name": "Western Sword Fern",

        "code": "PM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 5,

        "usda\_max": 9,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/polystichum-munitum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Heuchera maxima",

        "common\_name": "Island Alum Root",

        "code": "HM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/heuchera-maxima.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Ribes sanguineum",

        "common\_name": "Red-Flowering Currant",

        "code": "RS",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 6,

        "height\_ft": 8,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Deciduous",

        "image": "plant\_images/ribes-sanguineum.webp",

        "elevation\_height": 110,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Woodwardia fimbriata",

        "common\_name": "Giant Chain Fern",

        "code": "WF",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 6,

        "height\_ft": 5,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/woodwardia-fimbriata.webp",

        "elevation\_height": 70,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Acer circinatum",

        "common\_name": "Vine Maple",

        "code": "ACI",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 15,

        "height\_ft": 20,

        "radius": feet\_to\_canvas\_radius(15),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 3,

        "seasonality": "Deciduous",

        "image": "plant\_images/acer-circinatum.webp",

        "elevation\_height": 125,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Heteromeles arbutifolia",

        "common\_name": "Toyon",

        "code": "HA",

        "state": ["California"],

        "climate": ["Woodland", "Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 10,

        "height\_ft": 15,

        "radius": feet\_to\_canvas\_radius(10),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/heteromeles-arbutifolia.webp",

        "elevation\_height": 118,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

]







STYLE\_FIT\_BY\_CODE = {

    # Wild / Naturalized is intentionally broad: it allows the engine to mix canopy,

    # structure, matrix, and accents after USDA/sun/water filtering.

    "CP": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "EL": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "FC": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "SS": ["Wild / Naturalized", "Perennial Garden", "Woodland Garden"],

    "ID": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Woodland Garden"],

    "AM": ["Wild / Naturalized", "Woodland Garden", "Contemporary"],

    "AHM": ["Contemporary", "Wild / Naturalized", "Dry Garden"],

    "MR": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "SP": ["Wild / Naturalized", "Meadow"],

    "JP": ["Wild / Naturalized", "Meadow", "Contemporary"],

    "EF": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "EC": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "AC": ["Wild / Naturalized", "Dry Garden", "Meadow", "Contemporary"],

    "QC": ["Wild / Naturalized", "Woodland Garden"],

    "CT": ["Wild / Naturalized", "Woodland Garden", "Contemporary"],

    "PM": ["Woodland Garden", "Wild / Naturalized"],

    "HM": ["Woodland Garden", "Wild / Naturalized", "Perennial Garden", "Contemporary"],

    "RS": ["Woodland Garden", "Wild / Naturalized"],

    "WF": ["Woodland Garden", "Wild / Naturalized"],

    "AV": ["Woodland Garden", "Wild / Naturalized", "Contemporary"],

    "HA": ["Woodland Garden", "Contemporary", "Wild / Naturalized", "Dry Garden"],

}



STYLE\_LOGIC = {

    "Wild / Naturalized": {

        "species\_limit": 9,

        "spacing\_multiplier": 1.00,

        "description": "Mixed, ecological planting with canopy, structure, grasses, perennials, and accents.",

        "form\_priority": [],

        "role\_boost": {"Matrix": 1.15, "Accent": 1.05, "Structure": 1.0, "Canopy": 0.8},

    },

    "Contemporary": {

        "species\_limit": 5,

        "spacing\_multiplier": 1.20,

        "description": "Fewer species, stronger repeated masses, cleaner spacing, and more negative space.",

        "form\_priority": ["Grass", "Shrub", "Tree", "Fern", "Perennial"],

        "role\_boost": {"Structure": 1.35, "Matrix": 1.25, "Canopy": 1.0, "Accent": 0.75},

    },

    "Meadow": {

        "species\_limit": 6,

        "spacing\_multiplier": 0.96,

        "description": "Mostly grasses with limited seasonal accents for a meadow-like field condition.",

        "form\_priority": ["Grass", "Perennial", "Shrub"],

        "role\_boost": {"Matrix": 1.6, "Accent": 1.0, "Structure": 0.45, "Canopy": 0.15},

    },

    "Perennial Garden": {

        "species\_limit": 7,

        "spacing\_multiplier": 1.02,

        "description": "Flowering and textural perennial emphasis, supported by restrained matrix plants.",

        "form\_priority": ["Perennial", "Grass"],

        "role\_boost": {"Accent": 1.55, "Matrix": 1.0, "Structure": 0.35, "Canopy": 0.0},

    },

    "Woodland Garden": {

        "species\_limit": 7,

        "spacing\_multiplier": 1.08,

        "description": "Shade-tolerant canopy, structure, ferns, sedges, and understory pockets.",

        "form\_priority": ["Tree", "Shrub", "Fern", "Grass", "Perennial"],

        "role\_boost": {"Canopy": 1.25, "Structure": 1.15, "Matrix": 1.25, "Accent": 1.0},

    },

    "Dry Garden": {

        "species\_limit": 6,

        "spacing\_multiplier": 1.12,

        "description": "Low-water grasses, shrubs, and silver-textured plants with open spacing.",

        "form\_priority": ["Shrub", "Grass", "Perennial"],

        "role\_boost": {"Structure": 1.25, "Matrix": 1.15, "Accent": 1.0, "Canopy": 0.35},

    },

}



DESIGN\_STYLE\_OPTIONS = list(STYLE\_LOGIC.keys())



ROLE\_ORDER = sorted({plant["role"] for plant in PLANTS})



DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES = {

    "Canopy": 12,

    "Structure": 22,

    "Matrix": 44,

    "Accent": 22,

}



def default\_role\_percentage(role):

    return DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES.get(role, 20)



HEIGHT\_VARIATION\_BY\_HIERARCHY = {

    "Anchor": 0.06,

    "Mid Layer": 0.10,

    "Accent Layer": 0.15,

    "Groundcover": 0.08

}



\# -----------------------------

\# Helper functions

\# -----------------------------



def clamp\_dimension(value, fallback):

    try:

        value = float(value)

    except Exception:

        return fallback

    return max(1, min(value, MAX\_BED\_FEET))





def get\_canvas\_setup(length\_ft, width\_ft):

    """Return canvas dimensions and true feet-per-canvas-unit scale.



    length\_ft is horizontal. width\_ft is vertical/depth.

    The canvas preserves the real bed aspect ratio and fits inside the max pixel bounds.

    """

    length\_ft = clamp\_dimension(length\_ft, DEFAULT\_BED\_LENGTH\_FEET)

    width\_ft = clamp\_dimension(width\_ft, DEFAULT\_BED\_WIDTH\_FEET)



    pixels\_per\_foot = min(MAX\_CANVAS\_WIDTH / length\_ft, MAX\_CANVAS\_HEIGHT / width\_ft)

    canvas\_width = max(250, int(round(length\_ft \* pixels\_per\_foot)))

    canvas\_height = max(250, int(round(width\_ft \* pixels\_per\_foot)))

    feet\_per\_canvas\_unit = 1 / pixels\_per\_foot

    grid\_spacing\_units = GRID\_SPACING\_FEET / feet\_per\_canvas\_unit



    return canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units





def make\_runtime\_plant\_pool(plants, feet\_per\_canvas\_unit):

    runtime\_plants = []

    for plant in plants:

        p = plant.copy()

        p["radius"] = (p["spread\_ft"] / 2) / feet\_per\_canvas\_unit

        p["style\_fit"] = STYLE\_FIT\_BY\_CODE.get(p.get("code"), ["Wild / Naturalized"])

        runtime\_plants.append(p)

    return runtime\_plants





def circle\_inside(poly, x, y, r):

    return poly.contains(Point(x, y).buffer(r))





def circles\_overlap(x, y, r, placed, spacing\_factor, plant=None):

    for p in placed:

        existing\_plant = p["plant"]



        existing\_allows\_underplanting = existing\_plant.get("allows\_underplanting", False)

        current\_allows\_underplanting = plant is not None and plant.get("allows\_underplanting", False)



        if existing\_allows\_underplanting and not current\_allows\_underplanting:

            continue



        if current\_allows\_underplanting and not existing\_allows\_underplanting:

            continue



        distance = math.dist((x, y), (p["x"], p["y"]))

        min\_distance = (r + p["radius"]) \* spacing\_factor



        if distance < min\_distance:

            return True



    return False





def weighted\_choice(plants):

    if not plants:

        return None



    weights = [p.get("weight", 1) for p in plants]

    return random.choices(plants, weights=weights, k=1)[0]





def pack\_layer(poly, plants, target\_area, spacing\_factor, existing\_placed, max\_plants\_total):

    if not plants:

        return [], 0



    minx, miny, maxx, maxy = poly.bounds

    placed\_layer = []

    placed\_area = 0

    attempts = 0

    max\_attempts = 16000



    while (

        placed\_area < target\_area

        and attempts < max\_attempts

        and len(existing\_placed) + len(placed\_layer) < max\_plants\_total

    ):

        attempts += 1



        plant = weighted\_choice(plants)

        if plant is None:

            break



        r = plant["radius"]



        if maxx - minx < r \* 2 or maxy - miny < r \* 2:

            break



        x = random.uniform(minx + r, maxx - r)

        y = random.uniform(miny + r, maxy - r)



        if not circle\_inside(poly, x, y, r):

            continue



        all\_existing = existing\_placed + placed\_layer



        if circles\_overlap(x, y, r, all\_existing, spacing\_factor, plant):

            continue



        placed\_layer.append({"x": x, "y": y, "radius": r, "plant": plant})

        placed\_area += math.pi \* (r \*\* 2)



    return placed\_layer, placed\_area





def pack\_by\_role(poly, plant\_pool, target\_coverage, spacing\_factor, max\_plants\_total, role\_split=None):

    boundary\_area = poly.area



    if boundary\_area <= 0:

        return [], 0



    total\_target\_area = boundary\_area \* target\_coverage

    all\_placed = []

    total\_placed\_area = 0



    active\_roles = [role for role in ROLE\_ORDER if any(p["role"] == role for p in plant\_pool)]



    if not active\_roles:

        return [], 0



    if role\_split is None:

        total\_default = sum(default\_role\_percentage(role) for role in active\_roles) or 1

        role\_split = {

            role: default\_role\_percentage(role) / total\_default

            for role in active\_roles

        }



    for role in active\_roles:

        role\_plants = [p for p in plant\_pool if p["role"] == role]



        if not role\_plants:

            continue



        layer\_target\_area = total\_target\_area \* role\_split.get(role, 0)



        placed\_layer, placed\_area = pack\_layer(

            poly=poly,

            plants=role\_plants,

            target\_area=layer\_target\_area,

            spacing\_factor=spacing\_factor,

            existing\_placed=all\_placed,

            max\_plants\_total=max\_plants\_total

        )



        all\_placed.extend(placed\_layer)

        total\_placed\_area += placed\_area



    return all\_placed, total\_placed\_area / boundary\_area



def sun\_is\_compatible(selected\_sun, plant\_sun\_options):

    sun\_compatibility = {

        "Full Sun": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun"],

        "Full Sun-Part Shade": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade", "Part Shade-Full Shade"],

        "Part Shade": ["Part Shade", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade-Full Shade"],

        "Part Shade-Full Shade": ["Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"],

    }



    compatible\_values = sun\_compatibility.get(selected\_sun, [selected\_sun])

    return any(sun\_value in compatible\_values for sun\_value in plant\_sun\_options)





def water\_is\_compatible(selected\_water, plant\_water\_options):

    water\_compatibility = {

        "Low": ["Low", "Moderate-Low", "Low-Moderate"],

        "Moderate-Low": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Low-Moderate": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Moderate": ["Moderate", "Low-Moderate", "Moderate-Low"],

    }



    compatible\_values = water\_compatibility.get(selected\_water, [selected\_water])

    return any(water\_value in compatible\_values for water\_value in plant\_water\_options)





def hardiness\_is\_compatible(selected\_zones, usda\_min, usda\_max):

    if not selected\_zones:

        return True

    return any(usda\_min <= zone <= usda\_max for zone in selected\_zones)





def filter\_plants(plant\_database, state, selected\_usda\_zones, sun, water):

    """Filter plants by site viability only.



    Community Group and Climate remain plant-database intelligence, but they are no

    longer exposed as a left-panel user decision. Design Style now handles the

    creative/composition intent, while USDA, sun, and water handle viability.

    """

    return [

        plant for plant in plant\_database

        if state in plant["state"]

        and hardiness\_is\_compatible(selected\_usda\_zones, plant["usda\_min"], plant["usda\_max"])

        and sun\_is\_compatible(sun, plant["sun"])

        and water\_is\_compatible(water, plant["water"])

    ]





def filter\_plants\_by\_style(plant\_database, design\_style):

    """Filter by the selected design language.



    The style selector replaces the old visible California Plant Community filter.

    Perennial Garden is intentionally strict: it only returns plants with

    Form = Perennial, so the output behaves like a true perennial palette.

    """

    style\_filtered = [

        plant for plant in plant\_database

        if design\_style in plant.get("style\_fit", [])

    ]



    if design\_style == "Perennial Garden":

        style\_filtered = [p for p in style\_filtered if p.get("form") == "Perennial"]



    if design\_style == "Meadow":

        # Meadow should read grass-dominant, but still permits a few seasonal accents.

        style\_filtered = [p for p in style\_filtered if p.get("form") in ["Grass", "Perennial", "Shrub"]]



    if design\_style == "Dry Garden":

        style\_filtered = [p for p in style\_filtered if "Low" in p.get("water", []) or "Low-Moderate" in p.get("water", [])]



    return style\_filtered





def style\_priority\_score(plant, design\_style):

    settings = STYLE\_LOGIC.get(design\_style, STYLE\_LOGIC["Wild / Naturalized"])

    role\_boost = settings.get("role\_boost", {}).get(plant.get("role"), 1.0)

    form\_priority = settings.get("form\_priority", [])



    form\_score = 0

    if form\_priority and plant.get("form") in form\_priority:

        # Earlier listed forms receive higher priority.

        form\_score = len(form\_priority) - form\_priority.index(plant.get("form"))



    # Lower design tier is more important; invert it for scoring.

    tier\_score = 6 - float(plant.get("design\_tier", 5))

    visual\_score = float(plant.get("visual\_weight", 1))

    weight\_score = float(plant.get("weight", 1))



    return (tier\_score \* 2.0 + visual\_score + weight\_score \* 0.4 + form\_score \* 1.5) \* role\_boost





def limit\_palette\_by\_style(plant\_database, design\_style):

    """Keep the generated palette focused so layouts feel intentional.



    Forced-included plants are added after this function, so user intent still wins.

    Sorting favors the selected design style first, then design hierarchy.

    """

    settings = STYLE\_LOGIC.get(design\_style, STYLE\_LOGIC["Wild / Naturalized"])

    species\_limit = settings.get("species\_limit", 8)



    if len(plant\_database) <= species\_limit:

        return plant\_database



    sorted\_plants = sorted(

        plant\_database,

        key=lambda p: (

            -style\_priority\_score(p, design\_style),

            p.get("design\_tier", 5),

            p.get("name", "")

        )

    )



    selected = sorted\_plants[:species\_limit]



    if design\_style == "Meadow":

        # Keep meadow grass-led whenever possible.

        grasses = [p for p in sorted\_plants if p.get("form") == "Grass"]

        non\_grasses = [p for p in selected if p.get("form") != "Grass"]

        min\_grasses = min(len(grasses), max(2, int(round(species\_limit \* 0.6))))

        selected = grasses[:min\_grasses]

        for p in sorted\_plants:

            if p not in selected and len(selected) < species\_limit:

                selected.append(p)



    if design\_style == "Perennial Garden":

        # Stay true to the user's request: only perennials.

        selected = [p for p in selected if p.get("form") == "Perennial"]



    # Preserve at least one matrix plant when the selected style permits matrix plants.

    if design\_style != "Perennial Garden" and not any(p.get("role") == "Matrix" for p in selected):

        matrix\_candidates = [p for p in sorted\_plants if p.get("role") == "Matrix"]

        if matrix\_candidates and selected:

            selected[-1] = matrix\_candidates[0]



    return selected



def get\_polygon\_from\_canvas(canvas\_json):

    if canvas\_json is None:

        return None



    objects = canvas\_json.get("objects", [])

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





def normalize\_polygon(points):

    if points is None or len(points) < 3:

        return None

    poly = Polygon(points)

    if not poly.is\_valid:

        poly = poly.buffer(0)

    if poly.is\_empty or poly.area <= 0:

        return None

    return poly





def polygon\_points\_from\_geometry(geom):

    if geom is None or geom.is\_empty:

        return []

    if geom.geom\_type == "Polygon":

        return [(float(x), float(y)) for x, y in list(geom.exterior.coords)[:-1]]

    if geom.geom\_type == "MultiPolygon":

        largest = max(list(geom.geoms), key=lambda g: g.area)

        return [(float(x), float(y)) for x, y in list(largest.exterior.coords)[:-1]]

    return []





def valid\_role\_zones\_for\_boundary(role\_zones, main\_poly):

    valid = {}

    for role, points in (role\_zones or {}).items():

        zone\_poly = normalize\_polygon(points)

        if zone\_poly is None:

            continue

        clipped = zone\_poly.intersection(main\_poly)

        if clipped.is\_empty or clipped.area <= 0:

            continue

        valid[role] = clipped

    return valid





def rectangle\_points(canvas\_width, canvas\_height):

    return [(0, 0), (canvas\_width, 0), (canvas\_width, canvas\_height), (0, canvas\_height)]





def fig\_to\_png\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="png", dpi=200, bbox\_inches="tight", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_jpeg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="jpg", dpi=200, bbox\_inches="tight", facecolor="white", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_svg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="svg", bbox\_inches="tight")

    buffer.seek(0)

    return buffer





def canvas\_area\_to\_sqft(area\_canvas\_units, feet\_per\_canvas\_unit):

    return area\_canvas\_units \* (feet\_per\_canvas\_unit \*\* 2)





def canvas\_length\_to\_feet(length\_canvas\_units, feet\_per\_canvas\_unit):

    return length\_canvas\_units \* feet\_per\_canvas\_unit





def draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units):

    x = 0

    while x <= canvas\_width:

        ax.axvline(x, linewidth=0.4, alpha=0.25)

        x += grid\_spacing\_units



    y = 0

    while y <= canvas\_height:

        ax.axhline(y, linewidth=0.4, alpha=0.25)

        y += grid\_spacing\_units





def get\_image\_aspect\_ratio(image\_path):

    try:

        img = plt.imread(image\_path)

        height\_px, width\_px = img.shape[:2]

        if height\_px == 0:

            return 1

        return width\_px / height\_px

    except Exception:

        return 1





def varied\_height(plant):

    tolerance = HEIGHT\_VARIATION\_BY\_HIERARCHY.get(plant["hierarchy"], 0.08)

    variation = random.uniform(1 - tolerance, 1 + tolerance)

    return plant["elevation\_height"] \* variation





def prepare\_uploaded\_image(uploaded\_file, canvas\_width, canvas\_height):

    if uploaded\_file is None:

        return None, None



    image = Image.open(uploaded\_file).convert("RGB")

    image = image.resize((canvas\_width, canvas\_height))

    image\_array = plt.imread(BytesIO(image\_to\_png\_bytes(image).getvalue()))

    return image, image\_array





def render\_trace\_overlay(image, points, canvas\_width, canvas\_height):

    """Return a PIL image with the uploaded background plus the clicked/traced bedline points.



    This avoids relying on streamlit-drawable-canvas background\_image, which can render

    blank on Streamlit Cloud. Users click around the bedline directly on the image.

    """

    if image is None:

        return None



    overlay = image.copy().convert("RGB")

    overlay = overlay.resize((canvas\_width, canvas\_height))

    draw = ImageDraw\.Draw(overlay)



    if len(points) >= 2:

        draw\.line(points, fill=(255, 255, 255), width=3)



    if len(points) >= 3:

        # Light preview of the closing segment so users understand the final polygon.

        draw\.line([points[-1], points[0]], fill=(255, 255, 255), width=2)



    for idx, (x, y) in enumerate(points):

        r = 5

        draw\.ellipse((x - r, y - r, x + r, y + r), fill=(255, 80, 80), outline=(255, 255, 255), width=2)

        draw\.text((x + 7, y - 7), str(idx + 1), fill=(255, 255, 255))



    return overlay





def image\_to\_png\_bytes(image):

    buffer = BytesIO()

    image.save(buffer, format="PNG")

    buffer.seek(0)

    return buffer





def escape\_svg\_text(value):

    return html.escape(str(value), quote=True)





def plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit, role\_zones=None):

    """Create a clean vector SVG of the plan geometry.



    This avoids relying on Matplotlib's SVG output and gives you true circle/vector objects.

    """

    path\_points = " ".join([f"{x:.2f},{y:.2f}" for x, y in points])

    svg = StringIO()

    svg.write(f'\<svg xmlns="http\://www\.w3.org/2000/svg" width="{canvas\_width}" height="{canvas\_height}" viewBox="0 0 {canvas\_width} {canvas\_height}">\n')

    svg.write('\<rect width="100%" height="100%" fill="white"/>\n')

    svg.write(f'\<polygon points="{path\_points}" fill="none" stroke="black" stroke-width="2"/>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        zone\_path = " ".join([f"{x:.2f},{y:.2f}" for x, y in zone\_points])

        first\_x, first\_y = zone\_points[0]

        svg.write(f'\<polygon points="{zone\_path}" fill="none" stroke="black" stroke-width="1" stroke-dasharray="4 4" opacity="0.45"/>\n')

        svg.write(f'\<text x="{first\_x:.2f}" y="{first\_y:.2f}" font-family="Arial" font-size="10" opacity="0.65">{escape\_svg\_text(role)} zone\</text>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        closed\_zone = zone\_points + [zone\_points[0]]

        layer\_name = f"ROLE\_ZONE\_{role.upper().replace(' ', '\_')}"

        for i in range(len(closed\_zone) - 1):

            x1, y1 = closed\_zone[i]

            x2, y2 = closed\_zone[i + 1]

            dxf.write("0\nLINE\n8\n" + layer\_name + "\n")

            dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

            dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dash = ' stroke-dasharray="6 4"' if plant.get("allows\_underplanting", False) else ""

        weight = "bold" if plant.get("allows\_underplanting", False) else "normal"

        svg.write(f'\<circle cx="{item["x"]:.2f}" cy="{item["y"]:.2f}" r="{item["radius"]:.2f}" fill="none" stroke="black" stroke-width="1.2"{dash}/>\n')

        svg.write(f'\<text x="{item["x"]:.2f}" y="{item["y"]:.2f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="8" font-weight="{weight}">{escape\_svg\_text(plant["code"])}\</text>\n')



    svg.write(f'\<text x="12" y="{canvas\_height - 14}" font-family="Arial" font-size="10">Scale: 1 px = {feet\_per\_canvas\_unit:.3f} ft\</text>\n')

    svg.write('\</svg>')

    return BytesIO(svg.getvalue().encode("utf-8"))





def plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit, role\_zones=None):

    """Export a simple ASCII DXF in real feet.



    AutoCAD, Rhino, Vectorworks, and many CAD tools can open DXF. This is the practical

    Streamlit-friendly alternative to DWG.

    """

    dxf = StringIO()

    dxf.write("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n2\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nENTITIES\n")



    closed\_points = points + [points[0]]

    for i in range(len(closed\_points) - 1):

        x1, y1 = closed\_points[i]

        x2, y2 = closed\_points[i + 1]

        dxf.write("0\nLINE\n8\nBOUNDARY\n")

        dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dxf.write("0\nCIRCLE\n8\nPLANTS\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"40\n{item['radius'] \* feet\_per\_canvas\_unit:.4f}\n")

        dxf.write("0\nTEXT\n8\nPLANT\_CODES\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write("40\n0.35\n")

        dxf.write(f"1\n{plant['code']}\n")



    dxf.write("0\nENDSEC\n0\nEOF\n")

    return BytesIO(dxf.getvalue().encode("utf-8"))



\# -----------------------------

\# Sidebar

\# -----------------------------



with st.sidebar:

    st.markdown("### by The Landscape Library")



    st.header("Input Method")

    input\_method = st.radio(

        "Choose how to define the planting bed",

        ["Draw Boundary", "Upload JPEG Image"],

        index=0

    )



    st.info("Max 50' bed")



    if input\_method == "Upload JPEG Image":

        st.caption("Upload a JPEG image as a scaled reference, then click points around the actual bedline.")

        uploaded\_bed\_image = st.file\_uploader(

            "Upload bed image",

            type=["jpg", "jpeg"]

        )



        bed\_length\_ft = st.number\_input(

            "Image length / horizontal dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=30.0,

            step=1.0

        )



        bed\_width\_ft = st.number\_input(

            "Image width / vertical dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=15.0,

            step=1.0

        )

    else:

        uploaded\_bed\_image = None

        bed\_length\_ft = DEFAULT\_BED\_LENGTH\_FEET

        bed\_width\_ft = DEFAULT\_BED\_WIDTH\_FEET



    canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units = get\_canvas\_setup(

        bed\_length\_ft,

        bed\_width\_ft

    )



    st.header("Site Parameters")



    state = st.selectbox("Plant Region", ["California"])

    climate = "All Compatible Communities"



    design\_style = st.selectbox(

        "Design Style",

        DESIGN\_STYLE\_OPTIONS,

        index=0

    )

    st.caption(STYLE\_LOGIC[design\_style]["description"])



    st.markdown("\*\*USDA Hardiness\*\*")

    st.caption("Select one or more USDA zones. Plants are included when the selected zone falls between USDA Min and USDA Max in the plant database.")

    usda\_zone\_options = list(range(5, 11))

    default\_usda\_zones = [9]

    selected\_usda\_zones = []

    zone\_cols = st.columns(3)

    for idx, zone in enumerate(usda\_zone\_options):

        with zone\_cols[idx % 3]:

            checked = st.checkbox(f"Zone {zone}", value=zone in default\_usda\_zones, key=f"usda\_zone\_{zone}")

            if checked:

                selected\_usda\_zones.append(zone)



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



    target\_coverage = DENSITY\_OPTIONS[density]

    spacing\_factor = SPACING\_BY\_DENSITY[density] \* STYLE\_LOGIC[design\_style]["spacing\_multiplier"]

    max\_plants\_total = MAX\_PLANTS\_BY\_DENSITY[density]



    st.header("Scale")

    st.caption(f"Bed limit: {MAX\_BED\_FEET} ft max length or width")

    st.caption(f"Active bed: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")



\# -----------------------------

\# Active plant database + image prep

\# -----------------------------



runtime\_plants = make\_runtime\_plant\_pool(PLANTS, feet\_per\_canvas\_unit)

selected\_plants = filter\_plants(runtime\_plants, state, selected\_usda\_zones, sun, water)

selected\_plants = filter\_plants\_by\_style(selected\_plants, design\_style)



\# Manual include / exclude controls

all\_matching\_names = [p["name"] for p in selected\_plants]

with st.sidebar:

    st.header("Plant Controls")

    include\_names = st.multiselect("Force include plants", [p["name"] for p in runtime\_plants])

    exclude\_names = st.multiselect("Exclude plants", all\_matching\_names)



    st.divider()

    generate = st.button(

        "Generate Planting Layout",

        type="primary",

        use\_container\_width=True

    )



    feedback\_text = st.text\_area(

        "Feedback",

        placeholder="Share what worked, what felt confusing, or what you want improved.",

        height=100

    )



    if st.button("Submit Feedback", use\_container\_width=True):

        if feedback\_text.strip():

            ok, error\_message = log\_event(

                st.session\_state.get("user\_email"),

                "feedback\_submitted",

                climate=climate,

                sun\_exposure=sun,

                water\_needs=water,

                design\_style=design\_style,

                notes=feedback\_text.strip()

            )

            if ok:

                st.success("Feedback submitted.")

            else:

                st.error(f"Feedback was not saved: {error\_message}")

        else:

            st.warning("Enter feedback before submitting.")



role\_split = None



forced = [p for p in runtime\_plants if p["name"] in include\_names]

selected\_plants = [p for p in selected\_plants if p["name"] not in exclude\_names]

selected\_plants = limit\_palette\_by\_style(selected\_plants, design\_style)



for p in forced:

    if p["name"] not in [sp["name"] for sp in selected\_plants]:

        selected\_plants.append(p)



background\_image = None

background\_array = None



if input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    background\_image, background\_array = prepare\_uploaded\_image(uploaded\_bed\_image, canvas\_width, canvas\_height)



\# -----------------------------

\# Main UI

\# -----------------------------



left, right = st.columns([2, 1])



with left:

    if input\_method == "Draw Boundary":

        st.subheader("1. Draw Planting Boundary")

        st.caption("TIP: Left click to add boundary points. Right click to end nearest the origin point and complete the boundary.")

        st.caption('Drawing canvas: 50\\'-0" horizontal × 50\\'-0" vertical.')



        canvas\_result = st\_canvas(

            fill\_color="rgba(0, 0, 0, 0)",

            stroke\_width=3,

            stroke\_color="#111111",

            background\_color="#f7f7f2",

            height=canvas\_height,

            width=canvas\_width,

            drawing\_mode="polygon",

            key="draw\_boundary\_canvas",

        )

    else:

        st.subheader("1. Upload Scaled Bed Image + Trace Bedline")

        st.caption("Click points around the planting bedline in order. Use more points for curves. The final segment closes automatically.")



        if uploaded\_bed\_image is None:

            st.warning("Upload a JPEG image first, then click points around the actual bedline.")

            canvas\_result = None

        else:

            canvas\_result = None



            if streamlit\_image\_coordinates is None:

                st.error("Missing package: streamlit-image-coordinates. Add streamlit-image-coordinates to requirements.txt, then redeploy.")

                st.code("streamlit-image-coordinates", language="text")

            else:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                last\_click\_key = f"last\_click\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"



                if trace\_key not in st.session\_state:

                    st.session\_state[trace\_key] = []

                if last\_click\_key not in st.session\_state:

                    st.session\_state[last\_click\_key] = None



                overlay\_image = render\_trace\_overlay(

                    background\_image,

                    st.session\_state[trace\_key],

                    canvas\_width,

                    canvas\_height

                )



                clicked = streamlit\_image\_coordinates(

                    overlay\_image,

                    key=f"click\_trace\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}",

                    width=canvas\_width

                )



                if clicked is not None and "x" in clicked and "y" in clicked:

                    new\_point = (int(clicked["x"]), int(clicked["y"]))



                    if st.session\_state[last\_click\_key] != new\_point:

                        existing\_points = st.session\_state[trace\_key]



                        # Prevent accidental double-click duplicates.

                        if len(existing\_points) == 0 or math.dist(existing\_points[-1], new\_point) > 4:

                            existing\_points.append(new\_point)

                            st.session\_state[trace\_key] = existing\_points



                        st.session\_state[last\_click\_key] = new\_point

                        st.rerun()



                b1, b2, b3 = st.columns(3)

                with b1:

                    if st.button("Undo Last Point") and len(st.session\_state[trace\_key]) > 0:

                        st.session\_state[trace\_key] = st.session\_state[trace\_key][:-1]

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b2:

                    if st.button("Clear Trace"):

                        st.session\_state[trace\_key] = []

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b3:

                    st.metric("Trace Points", len(st.session\_state[trace\_key]))



                if len(st.session\_state[trace\_key]) < 3:

                    st.info("Add at least 3 points before generating the planting layout.")



with right:

    st.subheader("Don't See Your Region?")

    st.caption("Request the next region you'd like added.")



    requested\_region = st.text\_input(

        "Region",

        placeholder="Example: Texas, Florida, Pacific Northwest"

    )



    requested\_city = st.text\_input(

        "City",

        placeholder="Example: Austin"

    )



    if st.button("Submit"):

        if requested\_region.strip() and requested\_city.strip():

            ok, error\_message = log\_region\_request(

                st.session\_state.get("user\_email"),

                requested\_region,

                requested\_city,

                climate=climate,

                sun\_exposure=sun,

                water\_needs=water,

                design\_style=design\_style,

            )

            if ok:

                st.success("Region request submitted.")

            else:

                st.error(f"Region request was not saved: {error\_message}")

        elif not requested\_region.strip():

            st.warning("Enter a region before submitting.")

        else:

            st.warning("Enter a city before submitting.")



    st.subheader("3. Selected Plant Palette")



    if len(selected\_plants) == 0:

        st.warning("No plants match these parameters yet. Try adjusting design style, USDA hardiness, sun exposure, or water needs.")

    else:

        for plant in selected\_plants:

            canopy\_note = " | allows underplanting" if plant.get("allows\_underplanting", False) else ""

            st.write(f"\*\*{plant['name']}\*\*")

            st.caption(

                f"{plant['code']} | {plant['common\_name']} | {plant['form']} | {plant['role']} | spread: {plant['spread\_ft']} ft{canopy\_note}"

            )



\# -----------------------------

\# Boundary metrics

\# -----------------------------



points\_preview = None



if input\_method == "Draw Boundary" and canvas\_result is not None:

    points\_preview = get\_polygon\_from\_canvas(canvas\_result.json\_data)

elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

    points\_preview = st.session\_state.get(trace\_key, [])

    if len(points\_preview) < 3:

        points\_preview = None



if points\_preview is not None:

    preview\_poly = Polygon(points\_preview)



    if not preview\_poly.is\_valid:

        preview\_poly = preview\_poly.buffer(0)



    if preview\_poly.area > 0:

        area\_sqft = canvas\_area\_to\_sqft(preview\_poly.area, feet\_per\_canvas\_unit)

        perimeter\_ft = canvas\_length\_to\_feet(preview\_poly.length, feet\_per\_canvas\_unit)

        minx\_preview, miny\_preview, maxx\_preview, maxy\_preview = preview\_poly.bounds



        width\_ft = canvas\_length\_to\_feet(maxx\_preview - minx\_preview, feet\_per\_canvas\_unit)

        depth\_ft = canvas\_length\_to\_feet(maxy\_preview - miny\_preview, feet\_per\_canvas\_unit)



        st.subheader("Boundary Metrics")



        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Approx. Area", f"{area\_sqft:,.0f} sq ft")

        c2.metric("Approx. Perimeter", f"{perimeter\_ft:,.0f} ft")

        c3.metric("Approx. Length", f"{width\_ft:,.0f} ft")

        c4.metric("Approx. Width", f"{depth\_ft:,.0f} ft")



\# -----------------------------

\# Generate

\# -----------------------------



if generate:

    if supabase is not None and st.session\_state.get("user\_email"):

        user\_check = supabase.table("users").select("\*").eq("email", st.session\_state.user\_email).execute()

        current\_user = user\_check.data[0] if user\_check.data else {}

        if not current\_user.get("paid\_status", False) and (current\_user.get("total\_generations") or 0) >= FREE\_GENERATION\_LIMIT:

            st.warning("You have reached the free generation limit.")

            log\_event(st.session\_state.user\_email, "paywall\_shown")

            st.stop()

    try:

        with st.spinner("Generating planting plan and elevation view\..."):

            if input\_method == "Draw Boundary" and canvas\_result is not None:

                points = get\_polygon\_from\_canvas(canvas\_result.json\_data)

            elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                points = st.session\_state.get(trace\_key, [])

                if len(points) < 3:

                    points = None

            else:

                points = None



            if points is None:

                if input\_method == "Draw Boundary":

                    st.warning("Draw a closed polygon boundary first.")

                else:

                    st.warning("Upload a JPEG image and trace a closed polygon boundary first.")



            elif bed\_length\_ft > MAX\_BED\_FEET or bed\_width\_ft > MAX\_BED\_FEET:

                st.warning(f"The bed is too large. Keep the image dimensions at or below {MAX\_BED\_FEET} ft.")



            elif len(selected\_plants) == 0:

                st.warning("No plants are available for the selected site parameters.")



            else:

                poly = normalize\_polygon(points)



                if poly is None:

                    st.warning("The boundary is invalid. Try tracing a clearer closed shape.")



                else:

                    placed\_instances, actual\_coverage = pack\_by\_role(

                        poly=poly,

                        plant\_pool=selected\_plants,

                        target\_coverage=target\_coverage,

                        spacing\_factor=spacing\_factor,

                        max\_plants\_total=max\_plants\_total,

                        role\_split=role\_split

                    )



                    if len(placed\_instances) == 0:

                        st.warning("No plants could fit inside the boundary. Try a larger area, lower density, or different plant parameters.")



                    else:

                        new\_generation\_count = increment\_generation\_count(st.session\_state.get("user\_email"))

                        log\_event(

                            st.session\_state.get("user\_email"),

                            "generation\_run",

                            state=state,

                            zone=", ".join([f"USDA {z}" for z in selected\_usda\_zones]),

                            climate=climate,

                            sun\_exposure=sun,

                            water\_needs=water,

                            design\_style=design\_style,

                            notes=f"Density: {density}; Plants generated: {len(placed\_instances)}"

                        )



                        st.subheader("Plan View")



                        fig, ax = plt.subplots(figsize=(10, 10))



                        if background\_array is not None:

                            ax.imshow(background\_array, extent=(0, canvas\_width, canvas\_height, 0), alpha=0.35, zorder=0)



                        xs, ys = zip(\*(points + [points[0]]))

                        ax.plot(xs, ys, linewidth=2, zorder=3)



                        draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units)



                        for item in placed\_instances:

                            plant = item["plant"]



                            if plant.get("allows\_underplanting", False):

                                continue



                            circle = plt.Circle(

                                (item["x"], item["y"]),

                                item["radius"],

                                fill=False,

                                linewidth=1.2,

                                zorder=4

                            )

                            ax.add\_patch(circle)



                            ax.text(

                                item["x"],

                                item["y"],

                                plant["code"],

                                ha="center",

                                va="center",

                                fontsize=8,

                                zorder=5

                            )



                        for item in placed\_instances:

                            plant = item["plant"]



                            if not plant.get("allows\_underplanting", False):

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

                            ax.add\_patch(circle)



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



                        ax.set\_xlim(0, canvas\_width)

                        ax.set\_ylim(canvas\_height, 0)

                        ax.set\_aspect("equal")

                        ax.axis("off")



                        st.pyplot(fig)



                        plan\_png = fig\_to\_png\_bytes(fig)

                        plan\_svg = plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit)

                        plan\_dxf = plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit)



                        d1, d2, d3 = st.columns(3)

                        with d1:

                            st.download\_button(

                                label="Download Plan PNG",

                                data=plan\_png,

                                file\_name="yodra-planting-plan.png",

                                mime="image/png",

                                on\_click="ignore"

                            )

                        with d2:

                            st.download\_button(

                                label="Download Plan SVG",

                                data=plan\_svg,

                                file\_name="yodra-planting-plan.svg",

                                mime="image/svg+xml",

                                on\_click="ignore"

                            )

                        with d3:

                            st.download\_button(

                                label="Download Plan DXF",

                                data=plan\_dxf,

                                file\_name="yodra-planting-plan.dxf",

                                mime="application/dxf",

                                on\_click="ignore"

                            )



                        st.caption(f"Target coverage: {round(target\_coverage \* 100)}%")

                        st.caption(f"Actual generated coverage: {round(actual\_coverage \* 100)}%")

                        st.caption(f"Active bed scale: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")

                        st.caption(f"Maximum plant instances capped at {max\_plants\_total} for app performance.")



                        st.subheader("Elevation View")

                        st.caption("Elevation uses the same plant instances generated in plan view, with subtle height variation.")



                        elev\_fig, elev\_ax = plt.subplots(figsize=(12, 4))



                        placed\_sorted = sorted(placed\_instances, key=lambda item: item["x"])



                        for item in placed\_sorted:

                            plant = item["plant"]

                            image\_path = plant["image"]



                            height = varied\_height(plant)

                            aspect\_ratio = get\_image\_aspect\_ratio(image\_path)

                            width = height \* aspect\_ratio



                            if os.path.exists(image\_path):

                                img = plt.imread(image\_path)



                                elev\_ax.imshow(

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

                                elev\_ax.text(

                                    item["x"],

                                    height / 2,

                                    plant["code"],

                                    ha="center",

                                    va="center",

                                    fontsize=8

                                )



                        elev\_ax.axhline(0, linewidth=1)

                        elev\_ax.set\_xlim(0, canvas\_width)

                        elev\_ax.set\_ylim(0, 140)

                        elev\_ax.axis("off")



                        st.pyplot(elev\_fig)



                        elevation\_png = fig\_to\_png\_bytes(elev\_fig)

                        elevation\_jpeg = fig\_to\_jpeg\_bytes(elev\_fig)



                        e1, e2 = st.columns(2)

                        with e1:

                            st.download\_button(

                                label="Download Elevation PNG",

                                data=elevation\_png,

                                file\_name="yodra-planting-elevation.png",

                                mime="image/png",

                                on\_click="ignore"

                            )

                        with e2:

                            st.download\_button(

                                label="Download Elevation JPEG",

                                data=elevation\_jpeg,

                                file\_name="yodra-planting-elevation.jpg",

                                mime="image/jpeg",

                                on\_click="ignore"

                            )



                        counts = {}

                        for item in placed\_instances:

                            plant = item["plant"]

                            counts[plant["name"]] = counts.get(plant["name"], 0) + 1



                        st.subheader("Plant Schedule")



                        schedule = []

                        for plant\_name, count in counts.items():

                            plant = next(p for p in runtime\_plants if p["name"] == plant\_name)



                            schedule.append({

                                "Code": plant["code"],

                                "Count": count,

                                "Botanical Name": plant["name"],

                                "Common Name": plant["common\_name"],

                                "Form": plant["form"],

                                "Role": plant["role"],

                                "Texture": plant["texture"],

                                "Color Tone": plant["color\_tone"],

                                "Visual Weight": plant["visual\_weight"],

                                "Spread Ft": plant["spread\_ft"],

                                "Height Ft": plant["height\_ft"],

                                "Plant Region": state,

                                "Climate": ", ".join(plant["climate"]),

                                "USDA Min": plant["usda\_min"],

                                "USDA Max": plant["usda\_max"],

                                "Sun": ", ".join(plant["sun"]),

                                "Water": ", ".join(plant["water"]),

                                "Seasonality": plant["seasonality"],

                                "Style Fit": ", ".join(plant.get("style\_fit", [])),

                                "Allows Underplanting": plant.get("allows\_underplanting", False)

                            })



                        schedule\_df = pd.DataFrame(schedule)

                        st.dataframe(schedule\_df, width="stretch")



                        csv\_buffer = schedule\_df.to\_csv(index=False).encode("utf-8")

                        st.download\_button(

                            label="Download Plant Schedule CSV / Excel",

                            data=csv\_buffer,

                            file\_name="yodra-plant-schedule.csv",

                            mime="text/csv",

                            on\_click="ignore"

                        )

                        # Export downloads use on\_click="ignore" so Streamlit does not rerun

                        # and users do not lose their generated layout. Because this is

                        # a frontend-only download, export clicks are intentionally not

                        # logged here. This keeps Supabase cleaner and avoids noisy

                        # schedule\_export\_ready rows.



    except Exception as e:

        st.error("The app crashed while generating the layout.")

        st.exception(e)



















---



























# Version 3.5






import streamlit as st

from datetime import datetime, timezone

try:

    from supabase import create\_client

except Exception:

    create\_client = None

import pandas as pd



\# -------------------------

\# SUPABASE USER TRACKING

\# -------------------------



FREE\_GENERATION\_LIMIT = 999



def get\_supabase\_client():

    if create\_client is None:

        return None

    url = st.secrets.get("SUPABASE\_URL", "")

    key = st.secrets.get("SUPABASE\_SERVICE\_ROLE\_KEY", "")

    if not url or not key:

        return None

    return create\_client(url, key)



supabase = get\_supabase\_client()



def log\_event(email, event\_type, \*\*kwargs):

    """Insert an event using only the columns that exist in the current Supabase events table.



    Current expected columns:

    email, event\_type, created\_at, climate, sun\_exposure, water\_needs,

    design\_style, export\_type, notes.



    Do not add state, zone, density, or plants\_generated\_count unless those columns

    are also added to Supabase. Supabase will reject inserts when unknown columns

    are included.

    """

    if supabase is None or not email:

        return False, "Supabase is not connected or user email is missing."



    event = {

        "email": email,

        "event\_type": event\_type,

        "created\_at": datetime.now(timezone.utc).isoformat(),

        "climate": kwargs.get("climate"),

        "sun\_exposure": kwargs.get("sun\_exposure"),

        "water\_needs": kwargs.get("water\_needs"),

        "design\_style": kwargs.get("design\_style"),

        "export\_type": kwargs.get("export\_type"),

        "notes": kwargs.get("notes"),

    }



    # Remove empty optional fields so Supabase receives a clean payload.

    event = {k: v for k, v in event.items() if v is not None}



    try:

        supabase.table("events").insert(event).execute()

        return True, None

    except Exception as e:

        return False, str(e)





def log\_plant\_request(email, requested\_plant, \*\*kwargs):

    requested\_plant = (requested\_plant or "").strip()

    if not requested\_plant:

        return False, "Plant request is empty."



    ok, err = log\_event(

        email,

        "plant\_requested",

        notes=requested\_plant,

        \*\*kwargs

    )



    # Optional dedicated table. If you create a plant\_requests table in Supabase,

    # this will also save requests there. If that table does not exist, the

    # events table above is still the primary tracking location.

    if supabase is not None and email:

        try:

            supabase.table("plant\_requests").insert({

                "email": email,

                "requested\_plant": requested\_plant,

                "created\_at": datetime.now(timezone.utc).isoformat(),

                "climate": kwargs.get("climate"),

                "sun\_exposure": kwargs.get("sun\_exposure"),

                "water\_needs": kwargs.get("water\_needs"),

                "notes": requested\_plant,

            }).execute()

        except Exception:

            pass



    return ok, err





def log\_region\_request(email, requested\_region, requested\_city, \*\*kwargs):

    """Save a region request into the existing Supabase events table.



    This uses event\_type='region\_requested' and stores the requested region/city

    inside the existing notes column so no new Supabase columns are required.

    """

    requested\_region = (requested\_region or "").strip()

    requested\_city = (requested\_city or "").strip()



    if not requested\_region:

        return False, "Region request is empty."

    if not requested\_city:

        return False, "City is empty."



    notes = f"Requested Region: {requested\_region} | City: {requested\_city}"



    ok, err = log\_event(

        email,

        "region\_requested",

        notes=notes,

        \*\*kwargs

    )



    # Optional dedicated table. The events table above remains the primary save

    # location. If region\_requests does not exist, this silently falls back to events only.

    if supabase is not None and email:

        try:

            supabase.table("region\_requests").insert({

                "email": email,

                "requested\_region": requested\_region,

                "requested\_city": requested\_city,

                "created\_at": datetime.now(timezone.utc).isoformat(),

                "climate": kwargs.get("climate"),

                "sun\_exposure": kwargs.get("sun\_exposure"),

                "water\_needs": kwargs.get("water\_needs"),

                "design\_style": kwargs.get("design\_style"),

                "notes": notes,

            }).execute()

        except Exception:

            pass



    return ok, err





def get\_or\_create\_user(email):

    email = email.strip().lower()

    if supabase is None:

        return {"email": email, "paid\_status": False, "total\_generations": 0, "total\_exports": 0}



    now = datetime.now(timezone.utc).isoformat()

    result = supabase.table("users").select("\*").eq("email", email).execute()

    if result.data:

        user = result.data[0]

        supabase.table("users").update({"last\_seen": now}).eq("email", email).execute()

        return user



    new\_user = {

        "email": email,

        "first\_seen": now,

        "last\_seen": now,

        "paid\_status": False,

        "total\_generations": 0,

        "total\_exports": 0,

    }

    created = supabase.table("users").insert(new\_user).execute()

    return created.data[0] if created.data else new\_user



def increment\_generation\_count(email):

    if supabase is None:

        return 0

    result = supabase.table("users").select("total\_generations").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_generations") or 0

    new\_count = current + 1

    supabase.table("users").update({

        "total\_generations": new\_count,

        "last\_seen": datetime.now(timezone.utc).isoformat()

    }).eq("email", email).execute()

    return new\_count



def increment\_export\_count(email):

    if supabase is None:

        return

    result = supabase.table("users").select("total\_exports").eq("email", email).execute()

    current = 0

    if result.data:

        current = result.data[0].get("total\_exports") or 0

    supabase.table("users").update({"total\_exports": current + 1}).eq("email", email).execute()



def beta\_email\_gate():

    if "user\_email" not in st.session\_state:

        st.session\_state.user\_email = None

    if st.session\_state.user\_email:

        return True



    st.markdown("""

    \<div style="display\:flex;align-items\:center;gap:10px;flex-wrap\:wrap;">

        \<h1 style="margin:0;line-height:1.1;">Generate Planting Concepts in Minutes\</h1>

        \<span style="

            background:#f3f4f6;

            border:1px solid #e5e7eb;

            padding:3px 10px;

            border-radius:999px;

            font-size:12px;

            font-weight:700;

            letter-spacing:0.02em;

        ">

            Beta

        \</span>

    \</div>

    """, unsafe\_allow\_html=True)

    st.markdown("Visualize spacing, explore plant combinations, and build preliminary plant palettes.")

    st.caption("California Plant Database Available")

    st.caption("Texas and Florida Coming Soon")

    email = st.text\_input("Enter your email to continue")

    if st.button("Start Designing"):

        if "@" not in email or "." not in email:

            st.error("Please enter a valid email address.")

            st.stop()

        user = get\_or\_create\_user(email)

        st.session\_state.user\_email = user["email"]

        st.session\_state.user\_data = user

        log\_event(user["email"], "app\_opened")

        st.rerun()

    st.stop()



beta\_email\_gate()



TUTORIAL\_URL = "https\://youtu.be/mOuwuhSc2Gs"



\# -------------------------

\# YOUR APP BELOW

\# -------------------------



import random

import math

import os

import html

import base64

from io import BytesIO, StringIO



import matplotlib.pyplot as plt

from PIL import Image, ImageDraw

from shapely.geometry import Polygon, Point

from streamlit\_drawable\_canvas import st\_canvas

try:

    from streamlit\_image\_coordinates import streamlit\_image\_coordinates

except Exception:

    streamlit\_image\_coordinates = None



\# -----------------------------

\# Compatibility patch

\# -----------------------------

\# streamlit-drawable-canvas still calls an older Streamlit helper named

\# st.image.image\_to\_url when using background\_image. Newer Streamlit versions

\# removed that helper, which causes an AttributeError on image upload.

\# This patch restores the expected helper by converting the PIL background image

\# into a browser-safe base64 data URL.

def \_yodra\_image\_to\_url(image, width=None, clamp=False, channels="RGB", output\_format="PNG", image\_id=None):

    """Compatibility helper for streamlit-drawable-canvas background images.



    Newer Streamlit versions removed st.image.image\_to\_url, but

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

    return f"data\:image/png;base64,{encoded}"



try:

    # This is the exact object streamlit-drawable-canvas references: st.image.image\_to\_url

    st.image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



try:

    # Also patch Streamlit's image module for environments that reference it directly.

    import streamlit.elements.image as st\_image

    st\_image.image\_to\_url = \_yodra\_image\_to\_url

except Exception:

    pass



st.set\_page\_config(

    page\_title="Generate Planting Concepts",

    layout="wide"

)



title\_col, badge\_col = st.columns([8, 1])

with title\_col:

    st.title("Generate Planting Concepts in Minutes")

with badge\_col:

    st.markdown(

        """

        \<div style="

            margin-top:14px;

            background:#f3f4f6;

            border:1px solid #e5e7eb;

            padding:4px 10px;

            border-radius:999px;

            text-align\:center;

            font-size:12px;

            font-weight:700;

            letter-spacing:0.02em;

        ">

            Beta

        \</div>

        """,

        unsafe\_allow\_html=True,

    )



st.caption("Visualize spacing, explore plant combinations, and build preliminary plant palettes.")

st.info("California Plant Database Available • Texas and Florida Coming Soon")



\# -----------------------------

\# Canvas + Scale settings

\# -----------------------------



MAX\_CANVAS\_WIDTH = 900

MAX\_CANVAS\_HEIGHT = 600

DEFAULT\_BED\_LENGTH\_FEET = 50

DEFAULT\_BED\_WIDTH\_FEET = 50

MAX\_BED\_FEET = 50



GRID\_SPACING\_FEET = 5



DENSITY\_OPTIONS = {

    "Low": 0.30,

    "Moderate": 0.45,

    "Dense": 0.68,

    "Very Dense": 0.90

}



SPACING\_BY\_DENSITY = {

    "Low": 1.30,

    "Moderate": 1.15,

    "Dense": 1.05,

    "Very Dense": 1.00

}



MAX\_PLANTS\_BY\_DENSITY = {

    "Low": 180,

    "Moderate": 260,

    "Dense": 350,

    "Very Dense": 500

}



\# Placeholder used only while the plant database is being defined.

\# Runtime radii are recalculated after the active bed scale is known.

def feet\_to\_canvas\_radius(width\_ft):

    return width\_ft / 2



\# -----------------------------

\# Plant database

\# -----------------------------



PLANTS = [

    {

        "name": "Carex pansa",

        "common\_name": "Sand Dune Sedge",

        "code": "CP",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 1,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-pansa.webp",

        "elevation\_height": 28,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum latifolium",

        "common\_name": "Coast Buckwheat",

        "code": "EL",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Silver-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-latifolium.webp",

        "elevation\_height": 34,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Festuca californica",

        "common\_name": "California Fescue",

        "code": "FC",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/festuca-californica.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Salvia spathacea",

        "common\_name": "Hummingbird Sage",

        "code": "SS",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/salvia-spathacea.webp",

        "elevation\_height": 42,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Iris douglasiana",

        "common\_name": "Douglas Iris",

        "code": "ID",

        "state": ["California"],

        "climate": ["Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/iris-douglasiana.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Arbutus menziesii",

        "common\_name": "Pacific Madrone",

        "code": "AM",

        "state": ["California"],

        "climate": ["Coastal", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 20,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(20),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arbutus-menziesii.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Arctostaphylos densiflora 'Howard McMinn'",

        "common\_name": "Howard McMinn Manzanita",

        "code": "AHM",

        "state": ["California"],

        "climate": ["Coastal", "Inland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 8,

        "height\_ft": 7,

        "radius": feet\_to\_canvas\_radius(8),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/arctostaphylos-howard-mcminn.webp",

        "elevation\_height": 105,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

    {

        "name": "Muhlenbergia rigens",

        "common\_name": "Deergrass",

        "code": "MR",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/muhlenbergia-rigens.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Stipa pulchra",

        "common\_name": "Purple Needlegrass",

        "code": "SP",

        "state": ["California"],

        "climate": ["Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Golden Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/stipa-pulchra.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Juncus patens",

        "common\_name": "Common Rush",

        "code": "JP",

        "state": ["California"],

        "climate": ["Inland", "Coastal"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low-Moderate"],

        "spread\_ft": 3,

        "height\_ft": 3,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Blue-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/juncus-patens.webp",

        "elevation\_height": 46,

        "hierarchy": "Groundcover",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Eriogonum fasciculatum",

        "common\_name": "California Buckwheat",

        "code": "EF",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Grey-Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/eriogonum-fasciculatum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Epilobium canum",

        "common\_name": "California Fuchsia",

        "code": "EC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Semi-evergreen",

        "image": "plant\_images/epilobium-canum.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Artemisia californica",

        "common\_name": "California Sagebrush",

        "code": "AC",

        "state": ["California"],

        "climate": ["Inland", "Dry"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Full Sun"],

        "water": ["Low"],

        "spread\_ft": 5,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(5),

        "form": "Shrub",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Silver-Grey",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/artemisia-californica.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Quercus chrysolepis",

        "common\_name": "Canyon Live Oak",

        "code": "QC",

        "state": ["California"],

        "climate": ["Inland", "Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 30,

        "height\_ft": 40,

        "radius": feet\_to\_canvas\_radius(30),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/quercus-chrysolepis.webp",

        "elevation\_height": 135,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Carex tumulicola",

        "common\_name": "Foothill Sedge",

        "code": "CT",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Sun"],

        "water": ["Moderate-Low"],

        "spread\_ft": 2,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(2),

        "form": "Grass",

        "role": "Matrix",

        "texture": "Fine",

        "color\_tone": "Green",

        "visual\_weight": 1,

        "seasonality": "Evergreen",

        "image": "plant\_images/carex-tumulicola.webp",

        "elevation\_height": 34,

        "hierarchy": "Groundcover",

        "weight": 5,

        "allows\_underplanting": False

    },

    {

        "name": "Polystichum munitum",

        "common\_name": "Western Sword Fern",

        "code": "PM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 5,

        "usda\_max": 9,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 4,

        "height\_ft": 4,

        "radius": feet\_to\_canvas\_radius(4),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/polystichum-munitum.webp",

        "elevation\_height": 58,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Heuchera maxima",

        "common\_name": "Island Alum Root",

        "code": "HM",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 8,

        "usda\_max": 10,

        "sun": ["Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 3,

        "height\_ft": 2,

        "radius": feet\_to\_canvas\_radius(3),

        "form": "Perennial",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Evergreen",

        "image": "plant\_images/heuchera-maxima.webp",

        "elevation\_height": 42,

        "hierarchy": "Accent Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Ribes sanguineum",

        "common\_name": "Red-Flowering Currant",

        "code": "RS",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Moderate-Low"],

        "spread\_ft": 6,

        "height\_ft": 8,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Shrub",

        "role": "Accent",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 2,

        "seasonality": "Deciduous",

        "image": "plant\_images/ribes-sanguineum.webp",

        "elevation\_height": 110,

        "hierarchy": "Mid Layer",

        "weight": 3,

        "allows\_underplanting": False

    },

    {

        "name": "Woodwardia fimbriata",

        "common\_name": "Giant Chain Fern",

        "code": "WF",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Part Shade-Full Shade"],

        "water": ["Moderate"],

        "spread\_ft": 6,

        "height\_ft": 5,

        "radius": feet\_to\_canvas\_radius(6),

        "form": "Fern",

        "role": "Matrix",

        "texture": "Bold",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/woodwardia-fimbriata.webp",

        "elevation\_height": 70,

        "hierarchy": "Mid Layer",

        "weight": 4,

        "allows\_underplanting": False

    },

    {

        "name": "Acer circinatum",

        "common\_name": "Vine Maple",

        "code": "ACI",

        "state": ["California"],

        "climate": ["Woodland"],

        "usda\_min": 6,

        "usda\_max": 9,

        "sun": ["Part Shade"],

        "water": ["Moderate"],

        "spread\_ft": 15,

        "height\_ft": 20,

        "radius": feet\_to\_canvas\_radius(15),

        "form": "Tree",

        "role": "Canopy",

        "texture": "Medium",

        "color\_tone": "Green",

        "visual\_weight": 3,

        "seasonality": "Deciduous",

        "image": "plant\_images/acer-circinatum.webp",

        "elevation\_height": 125,

        "hierarchy": "Anchor",

        "weight": 1,

        "allows\_underplanting": True

    },

    {

        "name": "Heteromeles arbutifolia",

        "common\_name": "Toyon",

        "code": "HA",

        "state": ["California"],

        "climate": ["Woodland", "Inland"],

        "usda\_min": 7,

        "usda\_max": 10,

        "sun": ["Full Sun-Part Shade"],

        "water": ["Low"],

        "spread\_ft": 10,

        "height\_ft": 15,

        "radius": feet\_to\_canvas\_radius(10),

        "form": "Shrub",

        "role": "Structure",

        "texture": "Medium",

        "color\_tone": "Dark Green",

        "visual\_weight": 3,

        "seasonality": "Evergreen",

        "image": "plant\_images/heteromeles-arbutifolia.webp",

        "elevation\_height": 118,

        "hierarchy": "Anchor",

        "weight": 2,

        "allows\_underplanting": True

    },

]







STYLE\_FIT\_BY\_CODE = {

    # Wild / Naturalized is intentionally broad: it allows the engine to mix canopy,

    # structure, matrix, and accents after USDA/sun/water filtering.

    "CP": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "EL": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "FC": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "SS": ["Wild / Naturalized", "Perennial Garden", "Woodland Garden"],

    "ID": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Woodland Garden"],

    "AM": ["Wild / Naturalized", "Woodland Garden", "Contemporary"],

    "AHM": ["Contemporary", "Wild / Naturalized", "Dry Garden"],

    "MR": ["Wild / Naturalized", "Contemporary", "Meadow"],

    "SP": ["Wild / Naturalized", "Meadow"],

    "JP": ["Wild / Naturalized", "Meadow", "Contemporary"],

    "EF": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "EC": ["Wild / Naturalized", "Meadow", "Perennial Garden", "Dry Garden"],

    "AC": ["Wild / Naturalized", "Dry Garden", "Meadow", "Contemporary"],

    "QC": ["Wild / Naturalized", "Woodland Garden"],

    "CT": ["Wild / Naturalized", "Woodland Garden", "Contemporary"],

    "PM": ["Woodland Garden", "Wild / Naturalized"],

    "HM": ["Woodland Garden", "Wild / Naturalized", "Perennial Garden", "Contemporary"],

    "RS": ["Woodland Garden", "Wild / Naturalized"],

    "WF": ["Woodland Garden", "Wild / Naturalized"],

    "AV": ["Woodland Garden", "Wild / Naturalized", "Contemporary"],

    "HA": ["Woodland Garden", "Contemporary", "Wild / Naturalized", "Dry Garden"],

}



STYLE\_LOGIC = {

    "Wild / Naturalized": {

        "species\_limit": 9,

        "spacing\_multiplier": 1.00,

        "description": "Mixed, ecological planting with canopy, structure, grasses, perennials, and accents.",

        "form\_priority": [],

        "role\_boost": {"Matrix": 1.15, "Accent": 1.05, "Structure": 1.0, "Canopy": 0.8},

    },

    "Contemporary": {

        "species\_limit": 5,

        "spacing\_multiplier": 1.20,

        "description": "Fewer species, stronger repeated masses, cleaner spacing, and more negative space.",

        "form\_priority": ["Grass", "Shrub", "Tree", "Fern", "Perennial"],

        "role\_boost": {"Structure": 1.35, "Matrix": 1.25, "Canopy": 1.0, "Accent": 0.75},

    },

    "Meadow": {

        "species\_limit": 6,

        "spacing\_multiplier": 0.96,

        "description": "Mostly grasses with limited seasonal accents for a meadow-like field condition.",

        "form\_priority": ["Grass", "Perennial", "Shrub"],

        "role\_boost": {"Matrix": 1.6, "Accent": 1.0, "Structure": 0.45, "Canopy": 0.15},

    },

    "Perennial Garden": {

        "species\_limit": 7,

        "spacing\_multiplier": 1.02,

        "description": "Flowering and textural perennial emphasis, supported by restrained matrix plants.",

        "form\_priority": ["Perennial", "Grass"],

        "role\_boost": {"Accent": 1.55, "Matrix": 1.0, "Structure": 0.35, "Canopy": 0.0},

    },

    "Woodland Garden": {

        "species\_limit": 7,

        "spacing\_multiplier": 1.08,

        "description": "Shade-tolerant canopy, structure, ferns, sedges, and understory pockets.",

        "form\_priority": ["Tree", "Shrub", "Fern", "Grass", "Perennial"],

        "role\_boost": {"Canopy": 1.25, "Structure": 1.15, "Matrix": 1.25, "Accent": 1.0},

    },

    "Dry Garden": {

        "species\_limit": 6,

        "spacing\_multiplier": 1.12,

        "description": "Low-water grasses, shrubs, and silver-textured plants with open spacing.",

        "form\_priority": ["Shrub", "Grass", "Perennial"],

        "role\_boost": {"Structure": 1.25, "Matrix": 1.15, "Accent": 1.0, "Canopy": 0.35},

    },

}



DESIGN\_STYLE\_OPTIONS = list(STYLE\_LOGIC.keys())



ROLE\_ORDER = sorted({plant["role"] for plant in PLANTS})



DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES = {

    "Canopy": 12,

    "Structure": 22,

    "Matrix": 44,

    "Accent": 22,

}



def default\_role\_percentage(role):

    return DEFAULT\_ROLE\_COVERAGE\_PERCENTAGES.get(role, 20)



HEIGHT\_VARIATION\_BY\_HIERARCHY = {

    "Anchor": 0.06,

    "Mid Layer": 0.10,

    "Accent Layer": 0.15,

    "Groundcover": 0.08

}



\# -----------------------------

\# Helper functions

\# -----------------------------



def clamp\_dimension(value, fallback):

    try:

        value = float(value)

    except Exception:

        return fallback

    return max(1, min(value, MAX\_BED\_FEET))





def get\_canvas\_setup(length\_ft, width\_ft):

    """Return canvas dimensions and true feet-per-canvas-unit scale.



    length\_ft is horizontal. width\_ft is vertical/depth.

    The canvas preserves the real bed aspect ratio and fits inside the max pixel bounds.

    """

    length\_ft = clamp\_dimension(length\_ft, DEFAULT\_BED\_LENGTH\_FEET)

    width\_ft = clamp\_dimension(width\_ft, DEFAULT\_BED\_WIDTH\_FEET)



    pixels\_per\_foot = min(MAX\_CANVAS\_WIDTH / length\_ft, MAX\_CANVAS\_HEIGHT / width\_ft)

    canvas\_width = max(250, int(round(length\_ft \* pixels\_per\_foot)))

    canvas\_height = max(250, int(round(width\_ft \* pixels\_per\_foot)))

    feet\_per\_canvas\_unit = 1 / pixels\_per\_foot

    grid\_spacing\_units = GRID\_SPACING\_FEET / feet\_per\_canvas\_unit



    return canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units





def make\_runtime\_plant\_pool(plants, feet\_per\_canvas\_unit):

    runtime\_plants = []

    for plant in plants:

        p = plant.copy()

        p["radius"] = (p["spread\_ft"] / 2) / feet\_per\_canvas\_unit

        p["style\_fit"] = STYLE\_FIT\_BY\_CODE.get(p.get("code"), ["Wild / Naturalized"])

        runtime\_plants.append(p)

    return runtime\_plants





def circle\_inside(poly, x, y, r):

    return poly.contains(Point(x, y).buffer(r))





def circles\_overlap(x, y, r, placed, spacing\_factor, plant=None):

    for p in placed:

        existing\_plant = p["plant"]



        existing\_allows\_underplanting = existing\_plant.get("allows\_underplanting", False)

        current\_allows\_underplanting = plant is not None and plant.get("allows\_underplanting", False)



        if existing\_allows\_underplanting and not current\_allows\_underplanting:

            continue



        if current\_allows\_underplanting and not existing\_allows\_underplanting:

            continue



        distance = math.dist((x, y), (p["x"], p["y"]))

        min\_distance = (r + p["radius"]) \* spacing\_factor



        if distance < min\_distance:

            return True



    return False





def weighted\_choice(plants):

    if not plants:

        return None



    weights = [p.get("weight", 1) for p in plants]

    return random.choices(plants, weights=weights, k=1)[0]





def pack\_layer(poly, plants, target\_area, spacing\_factor, existing\_placed, max\_plants\_total):

    if not plants:

        return [], 0



    minx, miny, maxx, maxy = poly.bounds

    placed\_layer = []

    placed\_area = 0

    attempts = 0

    max\_attempts = 16000



    while (

        placed\_area < target\_area

        and attempts < max\_attempts

        and len(existing\_placed) + len(placed\_layer) < max\_plants\_total

    ):

        attempts += 1



        plant = weighted\_choice(plants)

        if plant is None:

            break



        r = plant["radius"]



        if maxx - minx < r \* 2 or maxy - miny < r \* 2:

            break



        x = random.uniform(minx + r, maxx - r)

        y = random.uniform(miny + r, maxy - r)



        if not circle\_inside(poly, x, y, r):

            continue



        all\_existing = existing\_placed + placed\_layer



        if circles\_overlap(x, y, r, all\_existing, spacing\_factor, plant):

            continue



        placed\_layer.append({"x": x, "y": y, "radius": r, "plant": plant})

        placed\_area += math.pi \* (r \*\* 2)



    return placed\_layer, placed\_area





def pack\_by\_role(poly, plant\_pool, target\_coverage, spacing\_factor, max\_plants\_total, role\_split=None):

    boundary\_area = poly.area



    if boundary\_area <= 0:

        return [], 0



    total\_target\_area = boundary\_area \* target\_coverage

    all\_placed = []

    total\_placed\_area = 0



    active\_roles = [role for role in ROLE\_ORDER if any(p["role"] == role for p in plant\_pool)]



    if not active\_roles:

        return [], 0



    if role\_split is None:

        total\_default = sum(default\_role\_percentage(role) for role in active\_roles) or 1

        role\_split = {

            role: default\_role\_percentage(role) / total\_default

            for role in active\_roles

        }



    for role in active\_roles:

        role\_plants = [p for p in plant\_pool if p["role"] == role]



        if not role\_plants:

            continue



        layer\_target\_area = total\_target\_area \* role\_split.get(role, 0)



        placed\_layer, placed\_area = pack\_layer(

            poly=poly,

            plants=role\_plants,

            target\_area=layer\_target\_area,

            spacing\_factor=spacing\_factor,

            existing\_placed=all\_placed,

            max\_plants\_total=max\_plants\_total

        )



        all\_placed.extend(placed\_layer)

        total\_placed\_area += placed\_area



    return all\_placed, total\_placed\_area / boundary\_area



def sun\_is\_compatible(selected\_sun, plant\_sun\_options):

    sun\_compatibility = {

        "Full Sun": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun"],

        "Full Sun-Part Shade": ["Full Sun", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade", "Part Shade-Full Shade"],

        "Part Shade": ["Part Shade", "Full Sun-Part Shade", "Part Shade-Full Sun", "Part Shade-Full Shade"],

        "Part Shade-Full Shade": ["Full Sun-Part Shade", "Part Shade", "Part Shade-Full Shade"],

    }



    compatible\_values = sun\_compatibility.get(selected\_sun, [selected\_sun])

    return any(sun\_value in compatible\_values for sun\_value in plant\_sun\_options)





def water\_is\_compatible(selected\_water, plant\_water\_options):

    water\_compatibility = {

        "Low": ["Low", "Moderate-Low", "Low-Moderate"],

        "Moderate-Low": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Low-Moderate": ["Low", "Moderate-Low", "Low-Moderate", "Moderate"],

        "Moderate": ["Moderate", "Low-Moderate", "Moderate-Low"],

    }



    compatible\_values = water\_compatibility.get(selected\_water, [selected\_water])

    return any(water\_value in compatible\_values for water\_value in plant\_water\_options)





def hardiness\_is\_compatible(selected\_zones, usda\_min, usda\_max):

    if not selected\_zones:

        return True

    return any(usda\_min <= zone <= usda\_max for zone in selected\_zones)





def filter\_plants(plant\_database, state, selected\_usda\_zones, sun, water):

    """Filter plants by site viability only.



    Community Group and Climate remain plant-database intelligence, but they are no

    longer exposed as a left-panel user decision. Design Style now handles the

    creative/composition intent, while USDA, sun, and water handle viability.

    """

    return [

        plant for plant in plant\_database

        if state in plant["state"]

        and hardiness\_is\_compatible(selected\_usda\_zones, plant["usda\_min"], plant["usda\_max"])

        and sun\_is\_compatible(sun, plant["sun"])

        and water\_is\_compatible(water, plant["water"])

    ]





def filter\_plants\_by\_style(plant\_database, design\_style):

    """Filter by the selected design language.



    The style selector replaces the old visible California Plant Community filter.

    Perennial Garden is intentionally strict: it only returns plants with

    Form = Perennial, so the output behaves like a true perennial palette.

    """

    style\_filtered = [

        plant for plant in plant\_database

        if design\_style in plant.get("style\_fit", [])

    ]



    if design\_style == "Perennial Garden":

        style\_filtered = [p for p in style\_filtered if p.get("form") == "Perennial"]



    if design\_style == "Meadow":

        # Meadow should read grass-dominant, but still permits a few seasonal accents.

        style\_filtered = [p for p in style\_filtered if p.get("form") in ["Grass", "Perennial", "Shrub"]]



    if design\_style == "Dry Garden":

        style\_filtered = [p for p in style\_filtered if "Low" in p.get("water", []) or "Low-Moderate" in p.get("water", [])]



    return style\_filtered





def style\_priority\_score(plant, design\_style):

    settings = STYLE\_LOGIC.get(design\_style, STYLE\_LOGIC["Wild / Naturalized"])

    role\_boost = settings.get("role\_boost", {}).get(plant.get("role"), 1.0)

    form\_priority = settings.get("form\_priority", [])



    form\_score = 0

    if form\_priority and plant.get("form") in form\_priority:

        # Earlier listed forms receive higher priority.

        form\_score = len(form\_priority) - form\_priority.index(plant.get("form"))



    # Lower design tier is more important; invert it for scoring.

    tier\_score = 6 - float(plant.get("design\_tier", 5))

    visual\_score = float(plant.get("visual\_weight", 1))

    weight\_score = float(plant.get("weight", 1))



    return (tier\_score \* 2.0 + visual\_score + weight\_score \* 0.4 + form\_score \* 1.5) \* role\_boost





def limit\_palette\_by\_style(plant\_database, design\_style):

    """Keep the generated palette focused so layouts feel intentional.



    Forced-included plants are added after this function, so user intent still wins.

    Sorting favors the selected design style first, then design hierarchy.

    """

    settings = STYLE\_LOGIC.get(design\_style, STYLE\_LOGIC["Wild / Naturalized"])

    species\_limit = settings.get("species\_limit", 8)



    if len(plant\_database) <= species\_limit:

        return plant\_database



    sorted\_plants = sorted(

        plant\_database,

        key=lambda p: (

            -style\_priority\_score(p, design\_style),

            p.get("design\_tier", 5),

            p.get("name", "")

        )

    )



    selected = sorted\_plants[:species\_limit]



    if design\_style == "Meadow":

        # Keep meadow grass-led whenever possible.

        grasses = [p for p in sorted\_plants if p.get("form") == "Grass"]

        non\_grasses = [p for p in selected if p.get("form") != "Grass"]

        min\_grasses = min(len(grasses), max(2, int(round(species\_limit \* 0.6))))

        selected = grasses[:min\_grasses]

        for p in sorted\_plants:

            if p not in selected and len(selected) < species\_limit:

                selected.append(p)



    if design\_style == "Perennial Garden":

        # Stay true to the user's request: only perennials.

        selected = [p for p in selected if p.get("form") == "Perennial"]



    # Preserve at least one matrix plant when the selected style permits matrix plants.

    if design\_style != "Perennial Garden" and not any(p.get("role") == "Matrix" for p in selected):

        matrix\_candidates = [p for p in sorted\_plants if p.get("role") == "Matrix"]

        if matrix\_candidates and selected:

            selected[-1] = matrix\_candidates[0]



    return selected



def get\_polygon\_from\_canvas(canvas\_json):

    if canvas\_json is None:

        return None



    objects = canvas\_json.get("objects", [])

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





def normalize\_polygon(points):

    if points is None or len(points) < 3:

        return None

    poly = Polygon(points)

    if not poly.is\_valid:

        poly = poly.buffer(0)

    if poly.is\_empty or poly.area <= 0:

        return None

    return poly





def polygon\_points\_from\_geometry(geom):

    if geom is None or geom.is\_empty:

        return []

    if geom.geom\_type == "Polygon":

        return [(float(x), float(y)) for x, y in list(geom.exterior.coords)[:-1]]

    if geom.geom\_type == "MultiPolygon":

        largest = max(list(geom.geoms), key=lambda g: g.area)

        return [(float(x), float(y)) for x, y in list(largest.exterior.coords)[:-1]]

    return []





def valid\_role\_zones\_for\_boundary(role\_zones, main\_poly):

    valid = {}

    for role, points in (role\_zones or {}).items():

        zone\_poly = normalize\_polygon(points)

        if zone\_poly is None:

            continue

        clipped = zone\_poly.intersection(main\_poly)

        if clipped.is\_empty or clipped.area <= 0:

            continue

        valid[role] = clipped

    return valid





def rectangle\_points(canvas\_width, canvas\_height):

    return [(0, 0), (canvas\_width, 0), (canvas\_width, canvas\_height), (0, canvas\_height)]





def fig\_to\_png\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="png", dpi=200, bbox\_inches="tight", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_jpeg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="jpg", dpi=200, bbox\_inches="tight", facecolor="white", transparent=False)

    buffer.seek(0)

    return buffer





def fig\_to\_svg\_bytes(fig):

    buffer = BytesIO()

    fig.savefig(buffer, format="svg", bbox\_inches="tight")

    buffer.seek(0)

    return buffer





def canvas\_area\_to\_sqft(area\_canvas\_units, feet\_per\_canvas\_unit):

    return area\_canvas\_units \* (feet\_per\_canvas\_unit \*\* 2)





def canvas\_length\_to\_feet(length\_canvas\_units, feet\_per\_canvas\_unit):

    return length\_canvas\_units \* feet\_per\_canvas\_unit





def draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units):

    x = 0

    while x <= canvas\_width:

        ax.axvline(x, linewidth=0.4, alpha=0.25)

        x += grid\_spacing\_units



    y = 0

    while y <= canvas\_height:

        ax.axhline(y, linewidth=0.4, alpha=0.25)

        y += grid\_spacing\_units





def get\_image\_aspect\_ratio(image\_path):

    try:

        img = plt.imread(image\_path)

        height\_px, width\_px = img.shape[:2]

        if height\_px == 0:

            return 1

        return width\_px / height\_px

    except Exception:

        return 1





def varied\_height(plant):

    tolerance = HEIGHT\_VARIATION\_BY\_HIERARCHY.get(plant["hierarchy"], 0.08)

    variation = random.uniform(1 - tolerance, 1 + tolerance)

    return plant["elevation\_height"] \* variation





def prepare\_uploaded\_image(uploaded\_file, canvas\_width, canvas\_height):

    if uploaded\_file is None:

        return None, None



    image = Image.open(uploaded\_file).convert("RGB")

    image = image.resize((canvas\_width, canvas\_height))

    image\_array = plt.imread(BytesIO(image\_to\_png\_bytes(image).getvalue()))

    return image, image\_array





def render\_trace\_overlay(image, points, canvas\_width, canvas\_height):

    """Return a PIL image with the uploaded background plus the clicked/traced bedline points.



    This avoids relying on streamlit-drawable-canvas background\_image, which can render

    blank on Streamlit Cloud. Users click around the bedline directly on the image.

    """

    if image is None:

        return None



    overlay = image.copy().convert("RGB")

    overlay = overlay.resize((canvas\_width, canvas\_height))

    draw = ImageDraw\.Draw(overlay)



    if len(points) >= 2:

        draw\.line(points, fill=(255, 255, 255), width=3)



    if len(points) >= 3:

        # Light preview of the closing segment so users understand the final polygon.

        draw\.line([points[-1], points[0]], fill=(255, 255, 255), width=2)



    for idx, (x, y) in enumerate(points):

        r = 5

        draw\.ellipse((x - r, y - r, x + r, y + r), fill=(255, 80, 80), outline=(255, 255, 255), width=2)

        draw\.text((x + 7, y - 7), str(idx + 1), fill=(255, 255, 255))



    return overlay





def image\_to\_png\_bytes(image):

    buffer = BytesIO()

    image.save(buffer, format="PNG")

    buffer.seek(0)

    return buffer





def escape\_svg\_text(value):

    return html.escape(str(value), quote=True)





def plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit, role\_zones=None):

    """Create a clean vector SVG of the plan geometry.



    This avoids relying on Matplotlib's SVG output and gives you true circle/vector objects.

    """

    path\_points = " ".join([f"{x:.2f},{y:.2f}" for x, y in points])

    svg = StringIO()

    svg.write(f'\<svg xmlns="http\://www\.w3.org/2000/svg" width="{canvas\_width}" height="{canvas\_height}" viewBox="0 0 {canvas\_width} {canvas\_height}">\n')

    svg.write('\<rect width="100%" height="100%" fill="white"/>\n')

    svg.write(f'\<polygon points="{path\_points}" fill="none" stroke="black" stroke-width="2"/>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        zone\_path = " ".join([f"{x:.2f},{y:.2f}" for x, y in zone\_points])

        first\_x, first\_y = zone\_points[0]

        svg.write(f'\<polygon points="{zone\_path}" fill="none" stroke="black" stroke-width="1" stroke-dasharray="4 4" opacity="0.45"/>\n')

        svg.write(f'\<text x="{first\_x:.2f}" y="{first\_y:.2f}" font-family="Arial" font-size="10" opacity="0.65">{escape\_svg\_text(role)} zone\</text>\n')



    for role, zone\_points in (role\_zones or {}).items():

        if not zone\_points or len(zone\_points) < 3:

            continue

        closed\_zone = zone\_points + [zone\_points[0]]

        layer\_name = f"ROLE\_ZONE\_{role.upper().replace(' ', '\_')}"

        for i in range(len(closed\_zone) - 1):

            x1, y1 = closed\_zone[i]

            x2, y2 = closed\_zone[i + 1]

            dxf.write("0\nLINE\n8\n" + layer\_name + "\n")

            dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

            dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dash = ' stroke-dasharray="6 4"' if plant.get("allows\_underplanting", False) else ""

        weight = "bold" if plant.get("allows\_underplanting", False) else "normal"

        svg.write(f'\<circle cx="{item["x"]:.2f}" cy="{item["y"]:.2f}" r="{item["radius"]:.2f}" fill="none" stroke="black" stroke-width="1.2"{dash}/>\n')

        svg.write(f'\<text x="{item["x"]:.2f}" y="{item["y"]:.2f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="8" font-weight="{weight}">{escape\_svg\_text(plant["code"])}\</text>\n')



    svg.write(f'\<text x="12" y="{canvas\_height - 14}" font-family="Arial" font-size="10">Scale: 1 px = {feet\_per\_canvas\_unit:.3f} ft\</text>\n')

    svg.write('\</svg>')

    return BytesIO(svg.getvalue().encode("utf-8"))





def plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit, role\_zones=None):

    """Export a simple ASCII DXF in real feet.



    AutoCAD, Rhino, Vectorworks, and many CAD tools can open DXF. This is the practical

    Streamlit-friendly alternative to DWG.

    """

    dxf = StringIO()

    dxf.write("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n2\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n")

    dxf.write("0\nSECTION\n2\nENTITIES\n")



    closed\_points = points + [points[0]]

    for i in range(len(closed\_points) - 1):

        x1, y1 = closed\_points[i]

        x2, y2 = closed\_points[i + 1]

        dxf.write("0\nLINE\n8\nBOUNDARY\n")

        dxf.write(f"10\n{x1 \* feet\_per\_canvas\_unit:.4f}\n20\n{y1 \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"11\n{x2 \* feet\_per\_canvas\_unit:.4f}\n21\n{y2 \* feet\_per\_canvas\_unit:.4f}\n31\n0\n")



    for item in placed\_instances:

        plant = item["plant"]

        dxf.write("0\nCIRCLE\n8\nPLANTS\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write(f"40\n{item['radius'] \* feet\_per\_canvas\_unit:.4f}\n")

        dxf.write("0\nTEXT\n8\nPLANT\_CODES\n")

        dxf.write(f"10\n{item['x'] \* feet\_per\_canvas\_unit:.4f}\n20\n{item['y'] \* feet\_per\_canvas\_unit:.4f}\n30\n0\n")

        dxf.write("40\n0.35\n")

        dxf.write(f"1\n{plant['code']}\n")



    dxf.write("0\nENDSEC\n0\nEOF\n")

    return BytesIO(dxf.getvalue().encode("utf-8"))



\# -----------------------------

\# Sidebar

\# -----------------------------



with st.sidebar:

    st.markdown("### by The Landscape Library")



    st.header("Input Method")

    input\_method = st.radio(

        "Choose how to define the planting bed",

        ["Draw Boundary", "Upload JPEG Image"],

        index=0

    )



    st.info("Max 50' bed")



    if input\_method == "Upload JPEG Image":

        st.caption("Upload a JPEG image as a scaled reference, then click points around the actual bedline.")

        uploaded\_bed\_image = st.file\_uploader(

            "Upload bed image",

            type=["jpg", "jpeg"]

        )



        bed\_length\_ft = st.number\_input(

            "Image length / horizontal dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=30.0,

            step=1.0

        )



        bed\_width\_ft = st.number\_input(

            "Image width / vertical dimension (ft)",

            min\_value=1.0,

            max\_value=float(MAX\_BED\_FEET),

            value=15.0,

            step=1.0

        )

    else:

        uploaded\_bed\_image = None

        bed\_length\_ft = DEFAULT\_BED\_LENGTH\_FEET

        bed\_width\_ft = DEFAULT\_BED\_WIDTH\_FEET



    canvas\_width, canvas\_height, feet\_per\_canvas\_unit, grid\_spacing\_units = get\_canvas\_setup(

        bed\_length\_ft,

        bed\_width\_ft

    )



    st.header("Site Parameters")



    state = st.selectbox("Plant Region", ["California"])

    climate = "All Compatible Communities"



    design\_style = st.selectbox(

        "Design Style",

        DESIGN\_STYLE\_OPTIONS,

        index=0

    )

    st.caption(STYLE\_LOGIC[design\_style]["description"])



    st.markdown("\*\*USDA Hardiness\*\*")

    st.caption("Select one or more USDA zones. Plants are included when the selected zone falls between USDA Min and USDA Max in the plant database.")

    usda\_zone\_options = list(range(5, 11))

    default\_usda\_zones = [9]

    selected\_usda\_zones = []

    zone\_cols = st.columns(3)

    for idx, zone in enumerate(usda\_zone\_options):

        with zone\_cols[idx % 3]:

            checked = st.checkbox(f"Zone {zone}", value=zone in default\_usda\_zones, key=f"usda\_zone\_{zone}")

            if checked:

                selected\_usda\_zones.append(zone)



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



    target\_coverage = DENSITY\_OPTIONS[density]

    spacing\_factor = SPACING\_BY\_DENSITY[density] \* STYLE\_LOGIC[design\_style]["spacing\_multiplier"]

    max\_plants\_total = MAX\_PLANTS\_BY\_DENSITY[density]



    st.header("Scale")

    st.caption(f"Bed limit: {MAX\_BED\_FEET} ft max length or width")

    st.caption(f"Active bed: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")



\# -----------------------------

\# Active plant database + image prep

\# -----------------------------



runtime\_plants = make\_runtime\_plant\_pool(PLANTS, feet\_per\_canvas\_unit)

selected\_plants = filter\_plants(runtime\_plants, state, selected\_usda\_zones, sun, water)

selected\_plants = filter\_plants\_by\_style(selected\_plants, design\_style)



\# Manual include / exclude controls

all\_matching\_names = [p["name"] for p in selected\_plants]

with st.sidebar:

    st.header("Plant Controls")

    include\_names = st.multiselect("Force include plants", [p["name"] for p in runtime\_plants])

    exclude\_names = st.multiselect("Exclude plants", all\_matching\_names)



    st.divider()

    generate = st.button(

        "Generate Planting Layout",

        type="primary",

        use\_container\_width=True

    )



    feedback\_text = st.text\_area(

        "Feedback",

        placeholder="Share what worked, what felt confusing, or what you want improved.",

        height=100

    )



    if st.button("Submit Feedback", use\_container\_width=True):

        if feedback\_text.strip():

            ok, error\_message = log\_event(

                st.session\_state.get("user\_email"),

                "feedback\_submitted",

                climate=climate,

                sun\_exposure=sun,

                water\_needs=water,

                design\_style=design\_style,

                notes=feedback\_text.strip()

            )

            if ok:

                st.success("Feedback submitted.")

            else:

                st.error(f"Feedback was not saved: {error\_message}")

        else:

            st.warning("Enter feedback before submitting.")



role\_split = None



forced = [p for p in runtime\_plants if p["name"] in include\_names]

selected\_plants = [p for p in selected\_plants if p["name"] not in exclude\_names]

selected\_plants = limit\_palette\_by\_style(selected\_plants, design\_style)



for p in forced:

    if p["name"] not in [sp["name"] for sp in selected\_plants]:

        selected\_plants.append(p)



background\_image = None

background\_array = None



if input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    background\_image, background\_array = prepare\_uploaded\_image(uploaded\_bed\_image, canvas\_width, canvas\_height)



\# -----------------------------

\# Main UI

\# -----------------------------



left, right = st.columns([2, 1])



with left:

    if input\_method == "Draw Boundary":

        st.subheader("1. Draw Planting Boundary")

        st.link\_button("Watch Tutorial Here →", TUTORIAL\_URL, use\_container\_width=False)

        st.warning("TIP: Left click to add boundary points. Right click near the first point to finish the boundary. Drawing canvas: 50\\'-0\\" horizontal × 50\\'-0\\" vertical.")



        canvas\_result = st\_canvas(

            fill\_color="rgba(0, 0, 0, 0)",

            stroke\_width=3,

            stroke\_color="#111111",

            background\_color="#f7f7f2",

            height=canvas\_height,

            width=canvas\_width,

            drawing\_mode="polygon",

            key="draw\_boundary\_canvas",

        )

    else:

        st.subheader("1. Upload Scaled Bed Image + Trace Bedline")

        st.link\_button("Watch Tutorial Here →", TUTORIAL\_URL, use\_container\_width=False)

        st.warning("TIP: Click points around the planting bedline in order. Use more points for curves. The final segment closes automatically between the last point and first point.")



        if uploaded\_bed\_image is None:

            st.warning("Upload a JPEG image first, then click points around the actual bedline.")

            canvas\_result = None

        else:

            canvas\_result = None



            if streamlit\_image\_coordinates is None:

                st.error("Missing package: streamlit-image-coordinates. Add streamlit-image-coordinates to requirements.txt, then redeploy.")

            else:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                last\_click\_key = f"last\_click\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"



                if trace\_key not in st.session\_state:

                    st.session\_state[trace\_key] = []

                if last\_click\_key not in st.session\_state:

                    st.session\_state[last\_click\_key] = None



                overlay\_image = render\_trace\_overlay(

                    background\_image,

                    st.session\_state[trace\_key],

                    canvas\_width,

                    canvas\_height

                )



                clicked = streamlit\_image\_coordinates(

                    overlay\_image,

                    key=f"click\_trace\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}",

                    width=canvas\_width

                )



                if clicked is not None and "x" in clicked and "y" in clicked:

                    new\_point = (int(clicked["x"]), int(clicked["y"]))



                    if st.session\_state[last\_click\_key] != new\_point:

                        existing\_points = st.session\_state[trace\_key]



                        # Prevent accidental double-click duplicates.

                        if len(existing\_points) == 0 or math.dist(existing\_points[-1], new\_point) > 4:

                            existing\_points.append(new\_point)

                            st.session\_state[trace\_key] = existing\_points



                        st.session\_state[last\_click\_key] = new\_point

                        st.rerun()



                b1, b2, b3 = st.columns(3)

                with b1:

                    if st.button("Undo Last Point") and len(st.session\_state[trace\_key]) > 0:

                        st.session\_state[trace\_key] = st.session\_state[trace\_key][:-1]

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b2:

                    if st.button("Clear Trace"):

                        st.session\_state[trace\_key] = []

                        st.session\_state[last\_click\_key] = None

                        st.rerun()

                with b3:

                    st.metric("Trace Points", len(st.session\_state[trace\_key]))



                if len(st.session\_state[trace\_key]) < 3:

                    st.info("Add at least 3 points before generating the planting layout.")



with right:

    st.subheader("Don't See Your Region?")

    st.caption("Request the next region you'd like added.")



    requested\_region = st.text\_input(

        "Region",

        placeholder="Example: Texas, Florida, Pacific Northwest"

    )



    requested\_city = st.text\_input(

        "City",

        placeholder="Example: Austin"

    )



    if st.button("Submit"):

        if requested\_region.strip() and requested\_city.strip():

            ok, error\_message = log\_region\_request(

                st.session\_state.get("user\_email"),

                requested\_region,

                requested\_city,

                climate=climate,

                sun\_exposure=sun,

                water\_needs=water,

                design\_style=design\_style,

            )

            if ok:

                st.success("Region request submitted.")

            else:

                st.error(f"Region request was not saved: {error\_message}")

        elif not requested\_region.strip():

            st.warning("Enter a region before submitting.")

        else:

            st.warning("Enter a city before submitting.")



    st.subheader("3. Selected Plant Palette")



    if len(selected\_plants) == 0:

        st.warning("No plants match these parameters yet. Try adjusting design style, USDA hardiness, sun exposure, or water needs.")

    else:

        for plant in selected\_plants:

            canopy\_note = " | allows underplanting" if plant.get("allows\_underplanting", False) else ""

            st.write(f"\*\*{plant['name']}\*\*")

            st.caption(

                f"{plant['code']} | {plant['common\_name']} | {plant['form']} | {plant['role']} | spread: {plant['spread\_ft']} ft{canopy\_note}"

            )



\# -----------------------------

\# Boundary metrics

\# -----------------------------



points\_preview = None



if input\_method == "Draw Boundary" and canvas\_result is not None:

    points\_preview = get\_polygon\_from\_canvas(canvas\_result.json\_data)

elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

    trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

    points\_preview = st.session\_state.get(trace\_key, [])

    if len(points\_preview) < 3:

        points\_preview = None



if points\_preview is not None:

    preview\_poly = Polygon(points\_preview)



    if not preview\_poly.is\_valid:

        preview\_poly = preview\_poly.buffer(0)



    if preview\_poly.area > 0:

        area\_sqft = canvas\_area\_to\_sqft(preview\_poly.area, feet\_per\_canvas\_unit)

        perimeter\_ft = canvas\_length\_to\_feet(preview\_poly.length, feet\_per\_canvas\_unit)

        minx\_preview, miny\_preview, maxx\_preview, maxy\_preview = preview\_poly.bounds



        width\_ft = canvas\_length\_to\_feet(maxx\_preview - minx\_preview, feet\_per\_canvas\_unit)

        depth\_ft = canvas\_length\_to\_feet(maxy\_preview - miny\_preview, feet\_per\_canvas\_unit)



        st.subheader("Boundary Metrics")



        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Approx. Area", f"{area\_sqft:,.0f} sq ft")

        c2.metric("Approx. Perimeter", f"{perimeter\_ft:,.0f} ft")

        c3.metric("Approx. Length", f"{width\_ft:,.0f} ft")

        c4.metric("Approx. Width", f"{depth\_ft:,.0f} ft")



\# -----------------------------

\# Generate

\# -----------------------------



if generate:

    if supabase is not None and st.session\_state.get("user\_email"):

        user\_check = supabase.table("users").select("\*").eq("email", st.session\_state.user\_email).execute()

        current\_user = user\_check.data[0] if user\_check.data else {}

        if not current\_user.get("paid\_status", False) and (current\_user.get("total\_generations") or 0) >= FREE\_GENERATION\_LIMIT:

            st.warning("You have reached the free generation limit.")

            log\_event(st.session\_state.user\_email, "paywall\_shown")

            st.stop()

    try:

        with st.spinner("Generating planting plan and elevation view\..."):

            if input\_method == "Draw Boundary" and canvas\_result is not None:

                points = get\_polygon\_from\_canvas(canvas\_result.json\_data)

            elif input\_method == "Upload JPEG Image" and uploaded\_bed\_image is not None:

                trace\_key = f"trace\_points\_{uploaded\_bed\_image.name}\_{canvas\_width}\_{canvas\_height}"

                points = st.session\_state.get(trace\_key, [])

                if len(points) < 3:

                    points = None

            else:

                points = None



            if points is None:

                if input\_method == "Draw Boundary":

                    st.warning("Draw a closed polygon boundary first.")

                else:

                    st.warning("Upload a JPEG image and trace a closed polygon boundary first.")



            elif bed\_length\_ft > MAX\_BED\_FEET or bed\_width\_ft > MAX\_BED\_FEET:

                st.warning(f"The bed is too large. Keep the image dimensions at or below {MAX\_BED\_FEET} ft.")



            elif len(selected\_plants) == 0:

                st.warning("No plants are available for the selected site parameters.")



            else:

                poly = normalize\_polygon(points)



                if poly is None:

                    st.warning("The boundary is invalid. Try tracing a clearer closed shape.")



                else:

                    placed\_instances, actual\_coverage = pack\_by\_role(

                        poly=poly,

                        plant\_pool=selected\_plants,

                        target\_coverage=target\_coverage,

                        spacing\_factor=spacing\_factor,

                        max\_plants\_total=max\_plants\_total,

                        role\_split=role\_split

                    )



                    if len(placed\_instances) == 0:

                        st.warning("No plants could fit inside the boundary. Try a larger area, lower density, or different plant parameters.")



                    else:

                        new\_generation\_count = increment\_generation\_count(st.session\_state.get("user\_email"))

                        log\_event(

                            st.session\_state.get("user\_email"),

                            "generation\_run",

                            state=state,

                            zone=", ".join([f"USDA {z}" for z in selected\_usda\_zones]),

                            climate=climate,

                            sun\_exposure=sun,

                            water\_needs=water,

                            design\_style=design\_style,

                            notes=f"Density: {density}; Plants generated: {len(placed\_instances)}"

                        )



                        st.subheader("Plan View")



                        fig, ax = plt.subplots(figsize=(10, 10))



                        if background\_array is not None:

                            ax.imshow(background\_array, extent=(0, canvas\_width, canvas\_height, 0), alpha=0.35, zorder=0)



                        xs, ys = zip(\*(points + [points[0]]))

                        ax.plot(xs, ys, linewidth=2, zorder=3)



                        draw\_grid(ax, canvas\_width, canvas\_height, grid\_spacing\_units)



                        for item in placed\_instances:

                            plant = item["plant"]



                            if plant.get("allows\_underplanting", False):

                                continue



                            circle = plt.Circle(

                                (item["x"], item["y"]),

                                item["radius"],

                                fill=False,

                                linewidth=1.2,

                                zorder=4

                            )

                            ax.add\_patch(circle)



                            ax.text(

                                item["x"],

                                item["y"],

                                plant["code"],

                                ha="center",

                                va="center",

                                fontsize=8,

                                zorder=5

                            )



                        for item in placed\_instances:

                            plant = item["plant"]



                            if not plant.get("allows\_underplanting", False):

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

                            ax.add\_patch(circle)



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



                        ax.set\_xlim(0, canvas\_width)

                        ax.set\_ylim(canvas\_height, 0)

                        ax.set\_aspect("equal")

                        ax.axis("off")



                        st.pyplot(fig)



                        plan\_png = fig\_to\_png\_bytes(fig)

                        plan\_svg = plan\_to\_svg(points, placed\_instances, canvas\_width, canvas\_height, feet\_per\_canvas\_unit)

                        plan\_dxf = plan\_to\_dxf(points, placed\_instances, feet\_per\_canvas\_unit)



                        d1, d2, d3 = st.columns(3)

                        with d1:

                            st.download\_button(

                                label="Download Plan PNG",

                                data=plan\_png,

                                file\_name="yodra-planting-plan.png",

                                mime="image/png",

                                on\_click="ignore"

                            )

                        with d2:

                            st.download\_button(

                                label="Download Plan SVG",

                                data=plan\_svg,

                                file\_name="yodra-planting-plan.svg",

                                mime="image/svg+xml",

                                on\_click="ignore"

                            )

                        with d3:

                            st.download\_button(

                                label="Download Plan DXF",

                                data=plan\_dxf,

                                file\_name="yodra-planting-plan.dxf",

                                mime="application/dxf",

                                on\_click="ignore"

                            )



                        st.caption(f"Target coverage: {round(target\_coverage \* 100)}%")

                        st.caption(f"Actual generated coverage: {round(actual\_coverage \* 100)}%")

                        st.caption(f"Active bed scale: {bed\_length\_ft:.0f} ft x {bed\_width\_ft:.0f} ft")

                        st.caption(f"Maximum plant instances capped at {max\_plants\_total} for app performance.")



                        st.subheader("Elevation View")

                        st.caption("Elevation uses the same plant instances generated in plan view, with subtle height variation.")



                        elev\_fig, elev\_ax = plt.subplots(figsize=(12, 4))



                        placed\_sorted = sorted(placed\_instances, key=lambda item: item["x"])



                        for item in placed\_sorted:

                            plant = item["plant"]

                            image\_path = plant["image"]



                            height = varied\_height(plant)

                            aspect\_ratio = get\_image\_aspect\_ratio(image\_path)

                            width = height \* aspect\_ratio



                            if os.path.exists(image\_path):

                                img = plt.imread(image\_path)



                                elev\_ax.imshow(

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

                                elev\_ax.text(

                                    item["x"],

                                    height / 2,

                                    plant["code"],

                                    ha="center",

                                    va="center",

                                    fontsize=8

                                )



                        elev\_ax.axhline(0, linewidth=1)

                        elev\_ax.set\_xlim(0, canvas\_width)

                        elev\_ax.set\_ylim(0, 140)

                        elev\_ax.axis("off")



                        st.pyplot(elev\_fig)



                        elevation\_png = fig\_to\_png\_bytes(elev\_fig)

                        elevation\_jpeg = fig\_to\_jpeg\_bytes(elev\_fig)



                        e1, e2 = st.columns(2)

                        with e1:

                            st.download\_button(

                                label="Download Elevation PNG",

                                data=elevation\_png,

                                file\_name="yodra-planting-elevation.png",

                                mime="image/png",

                                on\_click="ignore"

                            )

                        with e2:

                            st.download\_button(

                                label="Download Elevation JPEG",

                                data=elevation\_jpeg,

                                file\_name="yodra-planting-elevation.jpg",

                                mime="image/jpeg",

                                on\_click="ignore"

                            )



                        counts = {}

                        for item in placed\_instances:

                            plant = item["plant"]

                            counts[plant["name"]] = counts.get(plant["name"], 0) + 1



                        st.subheader("Plant Schedule")



                        schedule = []

                        for plant\_name, count in counts.items():

                            plant = next(p for p in runtime\_plants if p["name"] == plant\_name)



                            schedule.append({

                                "Code": plant["code"],

                                "Count": count,

                                "Botanical Name": plant["name"],

                                "Common Name": plant["common\_name"],

                                "Form": plant["form"],

                                "Role": plant["role"],

                                "Texture": plant["texture"],

                                "Color Tone": plant["color\_tone"],

                                "Visual Weight": plant["visual\_weight"],

                                "Spread Ft": plant["spread\_ft"],

                                "Height Ft": plant["height\_ft"],

                                "Plant Region": state,

                                "Climate": ", ".join(plant["climate"]),

                                "USDA Min": plant["usda\_min"],

                                "USDA Max": plant["usda\_max"],

                                "Sun": ", ".join(plant["sun"]),

                                "Water": ", ".join(plant["water"]),

                                "Seasonality": plant["seasonality"],

                                "Style Fit": ", ".join(plant.get("style\_fit", [])),

                                "Allows Underplanting": plant.get("allows\_underplanting", False)

                            })



                        schedule\_df = pd.DataFrame(schedule)

                        st.dataframe(schedule\_df, width="stretch")



                        csv\_buffer = schedule\_df.to\_csv(index=False).encode("utf-8")

                        st.download\_button(

                            label="Download Plant Schedule CSV / Excel",

                            data=csv\_buffer,

                            file\_name="yodra-plant-schedule.csv",

                            mime="text/csv",

                            on\_click="ignore"

                        )

                        # Download buttons use on\_click="ignore" so Streamlit does not rerun

                        # and users keep their generated plan/elevation after exporting.



    except Exception as e:

        st.error("The app crashed while generating the layout.")

        st.exception(e)
