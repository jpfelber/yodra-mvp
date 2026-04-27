import random
import math
import os
from io import BytesIO

import streamlit as st
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, Point
from streamlit_drawable_canvas import st_canvas

st.set_page_config(page_title="AI-Powered Planting Design Engine", layout="wide")

st.title("AI-Powered Planting Design Engine")
st.caption("Draw a planting boundary, generate a hierarchy-based plan, preview elevation, and download results.")

# -----------------------------
# Canvas + Scale
# -----------------------------

CANVAS_WIDTH = 900
CANVAS_HEIGHT = 600
MAX_SITE_FEET = 50

FEET_PER_CANVAS_UNIT = MAX_SITE_FEET / CANVAS_WIDTH

GRID_SPACING_FEET = 5
GRID_SPACING_UNITS = GRID_SPACING_FEET / FEET_PER_CANVAS_UNIT

# -----------------------------
# Density
# -----------------------------

DENSITY_OPTIONS = {
    "Low": 0.30,
    "Moderate": 0.45,
    "Dense": 0.65,
    "Very Dense": 0.90
}

SPACING_BY_DENSITY = {
    "Low": 1.20,
    "Moderate": 1.00,
    "Dense": 0.82,
    "Very Dense": 0.62   # tighter packing
}

MAX_PLANTS_TOTAL = 350

def feet_to_radius(ft):
    return (ft / 2) / FEET_PER_CANVAS_UNIT

# -----------------------------
# Plants
# -----------------------------

PLANTS = [
    {"name": "Carex pansa","code":"CP","radius":feet_to_radius(2),"hierarchy":"Groundcover","sun":["Full Sun","Part Sun"],"water":["Low"],"weight":5,"allows_underplanting":False},
    {"name": "Salvia apiana","code":"SA","radius":feet_to_radius(4),"hierarchy":"Mid Layer","sun":["Full Sun"],"water":["Low"],"weight":3,"allows_underplanting":False},
    {"name": "Muhlenbergia rigens","code":"MR","radius":feet_to_radius(5),"hierarchy":"Accent Layer","sun":["Full Sun","Part Sun"],"water":["Low"],"weight":2,"allows_underplanting":False},
    {"name": "Arctostaphylos 'Howard McMinn'","code":"AHM","radius":feet_to_radius(10),"hierarchy":"Anchor","sun":["Full Sun","Part Sun"],"water":["Low"],"weight":8,"allows_underplanting":True},
]

HIERARCHY_ORDER = ["Anchor","Mid Layer","Accent Layer","Groundcover"]

HIERARCHY_COVERAGE_SPLIT = {
    "Anchor": 0.45,
    "Mid Layer": 0.22,
    "Accent Layer": 0.13,
    "Groundcover": 0.20
}

# -----------------------------
# Helpers
# -----------------------------

def circle_inside(poly,x,y,r):
    return poly.contains(Point(x,y).buffer(r))

def circles_overlap(x,y,r,placed,spacing,plant):
    for p in placed:
        existing = p["plant"]

        if existing.get("allows_underplanting",False):
            continue
        if plant.get("allows_underplanting",False):
            continue

        d = math.dist((x,y),(p["x"],p["y"]))
        if d < (r + p["radius"]) * spacing:
            return True
    return False

def weighted_choice(plants):
    return random.choices(plants,[p["weight"] for p in plants])[0]

def pack_layer(poly,plants,target_area,spacing,existing):
    minx,miny,maxx,maxy = poly.bounds
    placed=[]
    area=0
    attempts=0

    while area < target_area and attempts < 9000 and len(existing)+len(placed) < MAX_PLANTS_TOTAL:
        attempts+=1
        plant=weighted_choice(plants)
        r=plant["radius"]

        x=random.uniform(minx+r,maxx-r)
        y=random.uniform(miny+r,maxy-r)

        if not circle_inside(poly,x,y,r):
            continue

        if circles_overlap(x,y,r,existing+placed,spacing,plant):
            continue

        placed.append({"x":x,"y":y,"radius":r,"plant":plant})
        area += math.pi*r*r

    return placed,area

def pack(poly,plants,target,spacing):
    total_area = poly.area
    target_area = total_area * target

    all_plants=[]
    placed_area=0

    for h in HIERARCHY_ORDER:
        group=[p for p in plants if p["hierarchy"]==h]
        if not group:
            continue

        layer_target = target_area * HIERARCHY_COVERAGE_SPLIT[h]

        # NO loosening — everything respects density
        layer_spacing = spacing

        placed,area = pack_layer(poly,group,layer_target,layer_spacing,all_plants)

        all_plants.extend(placed)
        placed_area += area

    return all_plants, placed_area / total_area

def get_polygon(data):
    if not data: return None
    objs=data.get("objects",[])
    if not objs: return None
    path=objs[0].get("path",[])
    pts=[(p[1],p[2]) for p in path if len(p)>=3]
    return pts if len(pts)>=3 else None

# -----------------------------
# Sidebar
# -----------------------------

with st.sidebar:
    st.markdown("### by The Landscape Library")

    sun = st.selectbox("Sun Exposure",["Full Sun","Part Sun","Shade"])
    water = st.selectbox("Water Needs",["Low","Moderate"])

    density = st.selectbox("Density",["Low","Moderate","Dense","Very Dense"])

    target = DENSITY_OPTIONS[density]
    spacing = SPACING_BY_DENSITY[density]

    st.caption(f"{MAX_SITE_FEET}ft x {MAX_SITE_FEET}ft")
    st.caption(f"Grid: {GRID_SPACING_FEET}ft")

# -----------------------------
# Canvas
# -----------------------------

left,right = st.columns([2,1])

with left:
    canvas = st_canvas(
        height=CANVAS_HEIGHT,
        width=CANVAS_WIDTH,
        drawing_mode="polygon",
        stroke_width=3,
        stroke_color="#111",
        background_color="#f7f7f2",
        key="canvas"
    )

with right:
    st.subheader("Plant Palette")
    for p in PLANTS:
        st.write(p["name"])

# -----------------------------
# Generate
# -----------------------------

if st.button("Generate Planting Layout"):

    with st.spinner("Generating..."):

        pts = get_polygon(canvas.json_data)

        if not pts:
            st.warning("Draw boundary first")
        else:
            poly=Polygon(pts)

            placed,coverage = pack(poly,PLANTS,target,spacing)

            fig,ax = plt.subplots(figsize=(10,6))

            xs,ys = zip(*(pts+[pts[0]]))
            ax.plot(xs,ys)

            for p in placed:
                c = plt.Circle((p["x"],p["y"]),p["radius"],fill=False)
                ax.add_patch(c)
                ax.text(p["x"],p["y"],p["plant"]["code"],ha="center",va="center",fontsize=7)

            ax.set_xlim(0,CANVAS_WIDTH)
            ax.set_ylim(CANVAS_HEIGHT,0)
            ax.set_aspect("equal")
            ax.axis("off")

            st.pyplot(fig)

            st.caption(f"Coverage: {round(coverage*100)}%")
