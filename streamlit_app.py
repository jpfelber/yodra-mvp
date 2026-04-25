import random
import math
import os
from io import BytesIO

import streamlit as st
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, Point
from streamlit_drawable_canvas import st_canvas

st.set_page_config(
    page_title="California Native Planting Generator",
    layout="wide"
)

st.title("California Native Planting Layout Generator")
st.caption("Draw a planting boundary, generate a hierarchy-based plan, preview the matching elevation, and download the result.")

PLANTS = [
    {
        "name": "Carex pansa",
        "radius": 10,
        "category": "Groundcover",
        "region": ["Coastal"],
        "sun": ["Full Sun", "Part Sun"],
        "water": ["Low", "Moderate"],
        "image": "plant_images/carex-pansa.png",
        "elevation_height": 28,
        "hierarchy": "Groundcover",
        "weight": 5
    },
    {
        "name": "Salvia apiana",
        "radius": 14,
        "category": "Shrub",
        "region": ["Coastal", "Inland", "Foothill"],
        "sun": ["Full Sun"],
        "water": ["Low"],
        "image": "plant_images/salvia-apiana.png",
        "elevation_height": 32,
        "hierarchy": "Mid Layer",
        "weight": 3
    },
    {
        "name": "Muhlenbergia rigens",
        "radius": 18,
        "category": "Grass",
        "region": ["Coastal", "Inland", "Foothill"],
        "sun": ["Full Sun", "Part Sun"],
        "water": ["Low", "Moderate"],
        "image": "plant_images/muhlenbergia-rigens.png",
        "elevation_height": 50,
        "hierarchy": "Accent Layer",
        "weight": 2
    },
    {
        "name": "Arctostaphylos 'Howard McMinn'",
        "radius": 22,
        "category": "Structural Shrub",
        "region": ["Coastal", "Inland", "Foothill"],
        "sun": ["Full Sun", "Part Sun"],
        "water": ["Low"],
        "image": "plant_images/arctostaphylos-howard-mcminn.png",
        "elevation_height": 120,
        "hierarchy": "Anchor",
        "weight": 1
    },
    {
        "name": "Acamptopappus shockleyi",
        "radius": 12,
        "category": "Desert Shrub",
        "region": ["Desert", "Inland"],
        "sun": ["Full Sun"],
        "water": ["Low"],
        "image": "plant_images/acamptopappus-shockleyi.png",
        "elevation_height": 45,
        "hierarchy": "Mid Layer",
        "weight": 3
    },
]

HIERARCHY_ORDER = ["Anchor", "Mid Layer", "Accent Layer", "Groundcover"]

HIERARCHY_COVERAGE_SPLIT = {
    "Anchor": 0.18,
    "Mid Layer": 0.32,
    "Accent Layer": 0.22,
    "Groundcover": 0.28
}

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
    weights = [p.get("weight", 1) for p in plants]
    return random.choices(plants, weights=weights, k=1)[0]

def pack_layer(poly, plants, target_area, spacing_factor, existing_placed):
    minx, miny, maxx, maxy = poly.bounds
    placed_layer = []
    placed_area = 0

    attempts = 0
    max_attempts = 9000

    while placed_area < target_area and attempts < max_attempts:
        attempts += 1

        plant = weighted_choice(plants)
        r = plant["radius"]

        x = random.uniform(minx + r, maxx - r)
        y = random.uniform(miny + r, maxy - r)

        if not circle_inside(poly, x, y, r):
            continue

        all_existing = existing_placed + placed_layer

        if circles_overlap(x, y, r, all_existing, spacing_factor):
            continue

        placed = {
            "x": x,
            "y": y,
            "radius": r,
            "plant": plant
        }

        placed_layer.append(placed)
        placed_area += math.pi * (r ** 2)

    return placed_layer, placed_area

def pack_by_hierarchy(poly, plant_pool, target_coverage, spacing_factor):
    boundary_area = poly.area
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

with st.sidebar:
    st.header("Site Conditions")

    region = st.selectbox("California Region", ["Coastal", "Inland", "Foothill", "Desert"])
    sun = st.selectbox("Sun Exposure", ["Full Sun", "Part Sun", "Shade"])
    water = st.selectbox("Water Needs", ["Low", "Moderate"])

    st.header("Density")

    density = st.selectbox(
        "Coverage Density",
        ["Loose", "Medium", "Dense", "Very Dense"]
    )

    target_coverage = {
        "Loose": 0.35,
        "Medium": 0.50,
        "Dense": 0.65,
        "Very Dense": 0.78
    }[density]

    spacing_factor = st.slider(
        "Spacing Tightness",
        min_value=0.75,
        max_value=1.25,
        value=0.95,
        step=0.05
    )

left, right = st.columns([2, 1])

with left:
    st.subheader("1. Draw Planting Boundary")

    canvas_result = st_canvas(
        fill_color="rgba(0, 0, 0, 0)",
        stroke_width=3,
        stroke_color="#111111",
        background_color="#f7f7f2",
        height=450,
        width=700,
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
            st.write(f"**{plant['name']}**")
            st.caption(f"{plant['category']} | {plant['hierarchy']} | radius: {plant['radius']}")

generate = st.button("Generate Planting Layout", type="primary")

if generate:
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
                target_coverage=target_coverage,
                spacing_factor=spacing_factor
            )

            st.subheader("Plan View")

            fig, ax = plt.subplots(figsize=(10, 7))

            xs, ys = zip(*(points + [points[0]]))
            ax.plot(xs, ys, linewidth=2)

            for item in placed_instances:
                plant = item["plant"]

                circle = plt.Circle(
                    (item["x"], item["y"]),
                    item["radius"],
                    fill=False,
                    linewidth=1.2
                )
                ax.add_patch(circle)

                label = plant["name"].split()[0][0] + plant["name"].split()[-1][0]

                ax.text(
                    item["x"],
                    item["y"],
                    label,
                    ha="center",
                    va="center",
                    fontsize=8
                )

            minx, miny, maxx, maxy = poly.bounds
            ax.set_xlim(minx - 40, maxx + 40)
            ax.set_ylim(maxy + 40, miny - 40)
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

            st.subheader("Elevation View")
            st.caption("Elevation uses the same plant instances generated in plan view.")

            elev_fig, elev_ax = plt.subplots(figsize=(12, 4))

            placed_sorted = sorted(placed_instances, key=lambda item: item["x"])

            for item in placed_sorted:
                plant = item["plant"]
                image_path = plant["image"]
                height = plant["elevation_height"]
                width = plant["radius"] * 2.2

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
                        plant["name"],
                        ha="center",
                        va="center",
                        fontsize=8
                    )

            elev_ax.axhline(0, linewidth=1)
            elev_ax.set_xlim(minx - 40, maxx + 40)
            elev_ax.set_ylim(0, 130)
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
                    "Plant": plant["name"],
                    "Category": plant["category"],
                    "Hierarchy": plant["hierarchy"],
                    "Count": count,
                    "Region": ", ".join(plant["region"]),
                    "Sun": ", ".join(plant["sun"]),
                    "Water": ", ".join(plant["water"])
                })

            st.dataframe(schedule, use_container_width=True)