import random
import math
import os
from io import BytesIO

import streamlit as st
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

CANVAS_WIDTH = 700
CANVAS_HEIGHT = 700
MAX_SITE_FEET = 30

FEET_PER_CANVAS_UNIT = MAX_SITE_FEET / CANVAS_WIDTH

GRID_SPACING_FEET = 5
GRID_SPACING_UNITS = GRID_SPACING_FEET / FEET_PER_CANVAS_UNIT

TARGET_COVERAGE = 0.50
SPACING_FACTOR = 0.95
MAX_PLANTS_TOTAL = 175

def feet_to_canvas_radius(width_ft):
    return (width_ft / 2) / FEET_PER_CANVAS_UNIT

# -----------------------------
# Plant database
# -----------------------------

PLANTS = [
    {
        "name": "Carex pansa",
        "code": "CP",
        "radius": feet_to_canvas_radius(2),
        "category": "Groundcover",
        "region": ["Coastal"],
        "sun": ["Full Sun", "Part Sun"],
        "water": ["Low"],
        "image": "plant_images/carex-pansa.png",
        "elevation_height": 28,
        "hierarchy": "Groundcover",
        "weight": 5
    },
    {
        "name": "Salvia apiana",
        "code": "SA",
        "radius": feet_to_canvas_radius(4),
        "category": "Shrub",
        "region": ["Coastal"],
        "sun": ["Full Sun"],
        "water": ["Low"],
        "image": "plant_images/salvia-apiana.png",
        "elevation_height": 32,
        "hierarchy": "Mid Layer",
        "weight": 3
    },
    {
        "name": "Muhlenbergia rigens",
        "code": "MR",
        "radius": feet_to_canvas_radius(5),
        "category": "Grass",
        "region": ["Coastal"],
        "sun": ["Full Sun", "Part Sun"],
        "water": ["Low"],
        "image": "plant_images/muhlenbergia-rigens.png",
        "elevation_height": 50,
        "hierarchy": "Accent Layer",
        "weight": 2
    },
    {
        "name": "Arctostaphylos 'Howard McMinn'",
        "code": "AHM",
        "radius": feet_to_canvas_radius(10),
        "category": "Structural Shrub",
        "region": ["Coastal"],
        "sun": ["Full Sun", "Part Sun"],
        "water": ["Low"],
        "image": "plant_images/arctostaphylos-howard-mcminn.png",
        "elevation_height": 120,
        "hierarchy": "Anchor",
        "weight": 1
    },
]

HIERARCHY_ORDER = ["Anchor", "Mid Layer", "Accent Layer", "Groundcover"]

HIERARCHY_COVERAGE_SPLIT = {
    "Anchor": 0.18,
    "Mid Layer": 0.32,
    "Accent Layer": 0.22,
    "Groundcover": 0.28
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

def circles_overlap(x, y, r, placed, spacing_factor):
    for p in placed:
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

def pack_layer(poly, plants, target_area, spacing_factor, existing_placed):
    if not plants:
        return [], 0

    minx, miny, maxx, maxy = poly.bounds
    placed_layer = []
    placed_area = 0
    attempts = 0
    max_attempts = 9000

    while (
        placed_area < target_area
        and attempts < max_attempts
        and len(existing_placed) + len(placed_layer) < MAX_PLANTS_TOTAL
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

        if circles_overlap(x, y, r, all_existing, spacing_factor):
            continue

        placed_layer.append({
            "x": x,
            "y": y,
            "radius": r,
            "plant": plant
        })

        placed_area += math.pi * (r ** 2)

    return placed_layer, placed_area

def pack_by_hierarchy(poly, plant_pool, target_coverage, spacing_factor):
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

        if hierarchy == "Anchor":
            layer_spacing = max(spacing_factor, 1.05)
        elif hierarchy == "Groundcover":
            layer_spacing = min(spacing_factor, 0.88)
        else:
            layer_spacing = spacing_factor

        placed_layer, placed_area = pack_layer(
            poly=poly,
            plants=layer_plants,
            target_area=layer_target_area,
            spacing_factor=layer_spacing,
            existing_placed=all_placed
        )

        all_placed.extend(placed_layer)
        total_placed_area += placed_area

    return all_placed, total_placed_area / boundary_area

def filter_plants(region, sun, water):
    return [
        plant for plant in PLANTS
        if region in plant["region"]
        and sun in plant["sun"]
        and water in plant["water"]
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

def draw_grid(ax, minx, miny, maxx, maxy):
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

    st.header("Site Conditions")

    state = st.selectbox("State", ["California"])
    region = "Coastal"

    sun = st.selectbox("Sun Exposure", ["Full Sun", "Part Sun", "Shade"])
    water = st.selectbox("Water Needs", ["Low", "Moderate"])

    st.header("Scale")
    st.caption(f"Drawing area: {MAX_SITE_FEET} ft x {MAX_SITE_FEET} ft max")
    st.caption(f"Grid: 1 square = {GRID_SPACING_FEET} ft")
    st.caption("Density is fixed for this MVP.")

# -----------------------------
# Main UI
# -----------------------------

left, right = st.columns([2, 1])

with left:
    st.subheader("1. Draw Planting Boundary")
    st.caption(f"Draw within the 30 ft x 30 ft area. Each grid square represents {GRID_SPACING_FEET} ft.")

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

    selected_plants = filter_plants(region, sun, water)

    if len(selected_plants) == 0:
        st.warning("No plants match these conditions yet.")
    else:
        for plant in selected_plants:
            plant_width_ft = plant["radius"] * 2 * FEET_PER_CANVAS_UNIT
            st.write(f"**{plant['name']}**")
            st.caption(
                f"{plant['code']} | {plant['category']} | {plant['hierarchy']} | width: {plant_width_ft:.0f} ft"
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
                st.warning("No plants are available for the selected site conditions.")

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
                        target_coverage=TARGET_COVERAGE,
                        spacing_factor=SPACING_FACTOR
                    )

                    if len(placed_instances) == 0:
                        st.warning("No plants could fit inside the drawn boundary. Try drawing a larger area.")

                    else:
                        st.subheader("Plan View")

                        fig, ax = plt.subplots(figsize=(10, 10))

                        xs, ys = zip(*(points + [points[0]]))
                        ax.plot(xs, ys, linewidth=2)

                        draw_grid(ax, 0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)

                        for item in placed_instances:
                            plant = item["plant"]

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

                        st.caption(f"Target coverage: {round(TARGET_COVERAGE * 100)}%")
                        st.caption(f"Actual generated coverage: {round(actual_coverage * 100)}%")
                        st.caption(f"Scale: full canvas = {MAX_SITE_FEET} ft x {MAX_SITE_FEET} ft")

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
                            plant_width_ft = plant["radius"] * 2 * FEET_PER_CANVAS_UNIT

                            schedule.append({
                                "Code": plant["code"],
                                "Plant": plant["name"],
                                "Category": plant["category"],
                                "Hierarchy": plant["hierarchy"],
                                "Width": f"{plant_width_ft:.0f} ft",
                                "Count": count,
                                "State": state,
                                "Region": ", ".join(plant["region"]),
                                "Sun": ", ".join(plant["sun"]),
                                "Water": ", ".join(plant["water"])
                            })

                        st.dataframe(schedule, width="stretch")

    except Exception as e:
        st.error("The app crashed while generating the layout.")
        st.exception(e)
