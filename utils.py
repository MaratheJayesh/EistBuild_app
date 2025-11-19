"""
Utility functions for EstiBuild Streamlit app.

Provides:
- parse_dxf_to_polygons(dxf_path) -> list of shapely Polygons
- compute_areas_and_walls(polygons, wall_thickness, units) -> results dict
- estimate_materials_for_workitems(results, ...) -> materials dict
- render_plan_image_bytes(polygons) -> PNG bytes
- export_measurement_sheets_bytes(results, materials) -> XLSX bytes
"""

import ezdxf
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union, polygonize
import math
import matplotlib.pyplot as plt
from io import BytesIO
import pandas as pd

def parse_dxf_to_polygons(dxf_path):
    """
    Parse a DXF file and attempt to polygonize closed polylines / loops.
    Returns a list of shapely Polygons (in CAD units).
    """
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    geom_lines = []
    for e in msp:
        t = e.dxftype()
        if t == "LINE":
            start = e.dxf.start
            end = e.dxf.end
            geom_lines.append(LineString([start, end]))
        elif t in ("LWPOLYLINE", "POLYLINE"):
            # ezdxf LWPOLYLINE: use get_points()
            try:
                pts = [tuple(p[:2]) if len(p) >= 2 else tuple(p) for p in e.get_points()]
            except Exception:
                # fallback for POLYLINE entity that uses vertices
                try:
                    pts = [tuple(v.dxf.location) for v in e.vertices]
                except Exception:
                    pts = []
            if len(pts) >= 3:
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                geom_lines.append(LineString(pts))

    if not geom_lines:
        return []

    merged = unary_union(geom_lines)
    polys = list(polygonize(merged))
    polys = [poly for poly in polys if poly.area > 1e-6]
    return polys

def compute_areas_and_walls(polygons, wall_thickness=0.2, units="meters"):
    """
    Compute per-polygon area, carpet area (inward offset), perimeter, and
    approximate long/short wall lengths using bounding box method.
    """
    rooms = []
    total_built_up = 0.0
    total_carpet = 0.0
    total_perimeter = 0.0

    for idx, poly in enumerate(polygons, start=1):
        area = poly.area
        perim = poly.length
        try:
            inner = poly.buffer(-wall_thickness)
            carpet_area = inner.area if not inner.is_empty else max(0.0, area - perim * wall_thickness)
        except Exception:
            carpet_area = max(0.0, area - perim * wall_thickness)

        minx, miny, maxx, maxy = poly.bounds
        long_wall = 2 * (maxx - minx)
        short_wall = 2 * (maxy - miny)

        rooms.append({
            "id": idx,
            "area": area,
            "carpet_area": carpet_area,
            "perimeter": perim,
            "long_wall_length": long_wall,
            "short_wall_length": short_wall,
            "bounds": poly.bounds,
        })

        total_built_up += area
        total_carpet += carpet_area
        total_perimeter += perim

    recommended_setback = 1.5
    margin_note = f"Recommended minimum setback/margin around building: {recommended_setback} m (adjust per local rules)."

    return {
        "units": units,
        "wall_thickness": wall_thickness,
        "rooms": rooms,
        "totals": {
            "built_up_area": total_built_up,
            "carpet_area": total_carpet,
            "perimeter": total_perimeter,
        },
        "notes": [margin_note],
    }

def estimate_materials_for_workitems(results, cement_bag_kg=50, plaster_thickness_mm=12, tile_size_mm=600):
    """
    Estimate quantities for a simplified set of 12 work items from
    excavation to painting. These are approximate educational calculations.
    """
    totals = results["totals"]
    built_up = totals["built_up_area"]
    carpet = totals["carpet_area"]
    perimeter = totals["perimeter"]

    # Excavation: assume 1m depth x 1m average width along perimeter
    excavation_volume = perimeter * 1.0 * 1.0

    # Footing assumptions
    footing_depth = 0.5
    footing_width = 0.6
    footing_volume = perimeter * footing_width * footing_depth

    # Slab volume
    slab_thickness = 0.15
    slab_volume = built_up * slab_thickness

    # PCC below slab
    pcc_volume = built_up * 0.10

    # Wall volume (masonry)
    wall_height = 3.0
    wall_volume = perimeter * results["wall_thickness"] * wall_height

    # Bricks
    bricks_per_m3 = 500
    bricks_required = wall_volume * bricks_per_m3

    # Plaster both sides
    wall_area = perimeter * wall_height
    plaster_thickness_m = plaster_thickness_mm / 1000.0
    plaster_volume = wall_area * plaster_thickness_m

    # Tiles (approx on carpet area)
    tile_area_m2 = (tile_size_mm / 1000.0) ** 2
    tiles_required = math.ceil(carpet / tile_area_m2) if tile_area_m2 > 0 else 0

    # Concrete mix estimate (1:2:4), dry volume factor 1.54
    def concrete_materials_for_volume(vol_m3, mix=(1,2,4)):
        factor = 1.54
        dry_volume = vol_m3 * factor
        total_parts = sum(mix)
        cement_part = mix[0]
        cement_volume = dry_volume * (cement_part / total_parts)
        cement_kg = cement_volume * 1440
        cement_bags = cement_kg / cement_bag_kg
        sand_volume = dry_volume * (mix[1] / total_parts)
        agg_volume = dry_volume * (mix[2] / total_parts)
        return {
            "concrete_volume_m3": vol_m3,
            "cement_kg": cement_kg,
            "cement_bags": cement_bags,
            "sand_m3": sand_volume,
            "aggregate_m3": agg_volume,
        }

    total_concrete_volume = slab_volume + footing_volume + pcc_volume
    concrete_mat = concrete_materials_for_volume(total_concrete_volume, mix=(1,2,4))

    # Paint: 1 coat coverage ~10 m2 per litre
    paint_coverage_m2_per_l = 10
    paint_liters = wall_area / paint_coverage_m2_per_l

    # Reinforcement steel estimate (kg)
    steel_per_m3 = 80
    reinforcement_kg = total_concrete_volume * steel_per_m3

    # Prepare a 12-item list
    workitems = [
        {"item": "Excavation", "quantity": excavation_volume, "unit": "m3"},
        {"item": "PCC (under slab)", "quantity": pcc_volume, "unit": "m3"},
        {"item": "Footing concrete", "quantity": footing_volume, "unit": "m3"},
        {"item": "RCC slab/beams", "quantity": slab_volume, "unit": "m3"},
        {"item": "Reinforcement steel", "quantity": reinforcement_kg, "unit": "kg"},
        {"item": "Masonry (bricks)", "quantity": bricks_required, "unit": "nos"},
        {"item": "Sand (for concrete/mortar)", "quantity_m3": concrete_mat["sand_m3"], "unit": "m3"},
        {"item": "Coarse aggregate", "quantity_m3": concrete_mat["aggregate_m3"], "unit": "m3"},
        {"item": "Cement", "quantity": concrete_mat["cement_bags"], "unit": f"bags ({cement_bag_kg}kg)"},
        {"item": "Plaster (both sides)", "quantity": plaster_volume, "unit": "m3"},
        {"item": "Tiles / Flooring", "quantity": tiles_required, "unit": "nos"},
        {"item": "Paint (liters)", "quantity": paint_liters, "unit": "liters"},
    ]

    contingency_note = "Add ~10% contingency for waste and variations."

    return {
        "workitems": workitems,
        "concrete_breakdown": concrete_mat,
        "plaster_volume_m3": plaster_volume,
        "tiles_count": tiles_required,
        "bricks_count": bricks_required,
        "paint_liters": paint_liters,
        "contingency_note": contingency_note,
    }

def render_plan_image_bytes(polygons):
    """
    Render the polygons to a PNG image and return bytes.
    """
    plt.figure(figsize=(6,6))
    for poly in polygons:
        x, y = poly.exterior.xy
        plt.plot(x, y, color="black")
        plt.fill(x, y, alpha=0.1)
    plt.gca().set_aspect("equal", adjustable="box")
    plt.axis("off")
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", pad_inches=0.01)
    plt.close()
    buf.seek(0)
    return buf.read()

def export_measurement_sheets_bytes(results, materials):
    """
    Create an Excel workbook with two sheets: measurement_sheet and abstract_sheet.
    Return bytes of the xlsx file.
    """
    rooms = results["rooms"]
    room_rows = []
    for r in rooms:
        room_rows.append({
            "room_id": r["id"],
            "area_m2": r["area"],
            "carpet_area_m2": r["carpet_area"],
            "perimeter_m": r["perimeter"],
            "long_wall_m": r["long_wall_length"],
            "short_wall_m": r["short_wall_length"]
        })
    df_rooms = pd.DataFrame(room_rows)

    totals = results["totals"]
    abstract_rows = [
        {"description": "Built-up Area (m2)", "quantity": totals["built_up_area"]},
        {"description": "Carpet Area (m2)", "quantity": totals["carpet_area"]},
        {"description": "Perimeter (m)", "quantity": totals["perimeter"]},
    ]
    if materials:
        for w in materials["workitems"]:
            q = w.get("quantity") if "quantity" in w else w.get("quantity_m3", "")
            abstract_rows.append({"description": w["item"], "quantity": q})
    df_abstract = pd.DataFrame(abstract_rows)

    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_rooms.to_excel(writer, sheet_name="measurement_sheet", index=False)
        df_abstract.to_excel(writer, sheet_name="abstract_sheet", index=False)
    out.seek(0)
    return out.read()
