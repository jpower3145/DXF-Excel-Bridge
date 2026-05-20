import math
import statistics
import numpy as np
import ezdxf
from ezdxf.document import Drawing
from ezdxf.path import make_path
from shapely.geometry import MultiPoint
from typing import List, Tuple, Dict, Any, Optional, Callable
import json
import re
import logging
from collections import defaultdict

# constants definition for customisation
THRESHOLD_EQUIPMENT = 1800  # mm - minimum separation between bare equipment edges
SAMPLE_SPACING_POLY = 100 #sample rates along continuous lines
SAMPLE_SPACING_LINE = 250
DEG_STEP_ARC = 5
MAX_X_DEVIATION = 18000 #heuristic fallback if play border is erroneous
MAX_Y_DEVIATION = 80000
MIN_GAP_DISTANCE = 100
FALLBACK_CLOSE_DISTANCE = 150 #if no equipment border found

def transform_point(lx: float, ly: float, insert_x: float, insert_y: float, scale_x: float, scale_y: float, cos_a: float, sin_a: float) -> Tuple[float, float]:
    """Scales and rotates local block coordinates into global world coordinates."""
    #scale and rotate the local line to the global coord system
    sx = lx * scale_x
    sy = ly * scale_y
    wx = insert_x + sx * cos_a - sy * sin_a
    wy = insert_y + sx * sin_a + sy * cos_a
    return wx, wy

def collect_points_from_entity(sub: Any, transform: Callable[[float, float], Tuple[float, float]], doc: Drawing) -> List[Tuple[float, float]]:
    """Extracts and transforms points from a single DXF entity."""
    pts = []
    stype = sub.dxftype()

    if stype == "LWPOLYLINE":
        try:
            # make_path automatically calculates all arcs and bulges
            path = make_path(sub)
            # flattening() breaks the curves into tiny, highly accurate straight lines
            for point in path.flattening(distance=5):
                pts.append(transform(point.x, point.y))
        except (TypeError, ValueError) as e:
            logging.debug(f"LWPOLYLINE flattening failed: {e}")
            # Failsafe: just grab the square vertices like the old code if pathing fails
            pts.extend(transform(v[0], v[1]) for v in sub.vertices())

    elif stype == "POLYLINE":
        verts = list(sub.vertices)
        for k in range(len(verts)):
            v_start = verts[k]
            v_end   = verts[(k + 1) % len(verts)]  # wrap to close the loop
            
            sx, sy = v_start.dxf.location.x, v_start.dxf.location.y
            ex, ey = v_end.dxf.location.x,   v_end.dxf.location.y
            
            start_w = transform(sx, sy)
            end_w   = transform(ex, ey)
            length  = math.hypot(end_w[0] - start_w[0], end_w[1] - start_w[1])
            
            steps = max(2, int(length / SAMPLE_SPACING_POLY))
            
            for i in range(steps + 1):
                t = i / steps
                pts.append(transform(
                    sx + t * (ex - sx),
                    sy + t * (ey - sy)
                ))

    elif stype == "LINE":           
        sx, sy = sub.dxf.start.x, sub.dxf.start.y
        ex, ey = sub.dxf.end.x,   sub.dxf.end.y
        
        # How long is this line in world space after transform
        start_w = transform(sx, sy)
        end_w   = transform(ex, ey)
        length  = math.hypot(end_w[0] - start_w[0], end_w[1] - start_w[1])
        
        # Sample every SAMPLE_SPACING units along the line
        # mm — well below any threshold being checked
        steps = max(2, int(length / SAMPLE_SPACING_LINE))
        
        for k in range(steps + 1):
            t = k / steps
            pts.append(transform(
                sx + t * (ex - sx),
                sy + t * (ey - sy)
            ))

    elif stype == "CIRCLE":
        cx, cy, r = sub.dxf.center.x, sub.dxf.center.y, sub.dxf.radius
        pts.extend(
            transform(cx + r * math.cos(2 * math.pi * i / 1024),
                        cy + r * math.sin(2 * math.pi * i / 1024))
            for i in range(1024)
        )

    elif stype == "ARC":
        #Extract center and radius data from the DXF entity
        cx, cy, r = sub.dxf.center.x, sub.dxf.center.y, sub.dxf.radius
        
        #Convert DXF degrees to Python radians
        start_a = math.radians(sub.dxf.start_angle)
        end_a = math.radians(sub.dxf.end_angle)
        
        #Handle the 360-degree wrap-around crossovers
        if end_a < start_a:
            end_a += 2 * math.pi
            
        #Determines the sample resolution (The experimental line)
        #Calculates the total angle sweep: (end_a - start_a)
        #For example, divides by 5 degrees to get a step count (1 point every 5 degrees).
        steps = max(3, int((end_a - start_a) / math.radians(DEG_STEP_ARC)))
        
        #Generate the points and append to the main list
        pts.extend(
            transform(
                #Extracted data -> equation of a circle: X = cx + r * cos(theta)
                #'theta' is calculated by taking the start angle and adding 
                #a fraction of the total angle based on the current step.
                cx + r * math.cos(start_a + (end_a - start_a) * i / steps),
                cy + r * math.sin(start_a + (end_a - start_a) * i / steps)
            )
            #Loop through the steps
            for i in range(steps + 1)
        )

    elif stype in ("ELLIPSE", "SPLINE"):
        try:
            # make_path natively understands the complex math of splines and ellipses
            path = make_path(sub)
            # flatten it into highly accurate straight line segments
            for point in path.flattening(distance=5):
                pts.append(transform(point.x, point.y))
        except (TypeError, ValueError) as e:
            # If the geometry is corrupted and can't flatten, skip it gracefully
            logging.warning(f"Failed to flatten {stype}: {e}")
            pass

    elif stype == "INSERT":
        #in case the item is nested in 2 local blocks
        #global coords <- outer block <- inner block <- item with lines
        nested = get_block_world_bounds(sub, doc)
        if nested:
            pts.extend(nested['points'])

    return pts

def get_block_world_bounds(entity: Any, doc: Drawing) -> Optional[Dict[str, Any]]:
    """Calculates the global bounding box for a block reference."""
    #line's co-ordinates are determined by their local block scales
    #therefore we need the local block details to translate lines to global coords
    block_name = entity.dxf.name
    insert_x = entity.dxf.insert.x
    insert_y = entity.dxf.insert.y
    rotation_deg = getattr(entity.dxf, 'rotation', 0)
    scale_x = getattr(entity.dxf, 'xscale', 1.0)
    scale_y = getattr(entity.dxf, 'yscale', 1.0)
    angle = math.radians(rotation_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)

    # Create a local closure for the transform specific to this block instance
    def local_transform(lx: float, ly: float) -> Tuple[float, float]:
        return transform_point(lx, ly, insert_x, insert_y, scale_x, scale_y, cos_a, sin_a)

    en1176_points = []
    unit_spacing_points = []
    equipment_points = []

    try:
        block_def = doc.blocks[block_name]
    except KeyError:
        return None

    #for loop to get all the lines from a certain block
    for sub in block_def:
        try:
            layer = sub.dxf.layer
        except AttributeError:
            continue

        # Collect each boundary layer separately in priority order:
        # EN1176IMPACTAREA is the authoritative clearance zone per EU EN1176 standard
        # UNIT SPACING is the manufacturer's required buffer, used as fallback
        # EQUIPMENT is the bare physical perimeter, last resort with 1800mm threshold
        if layer == "EN1176IMPACTAREA":
            en1176_points.extend(collect_points_from_entity(sub, local_transform, doc))
        elif layer == "UNIT SPACING" or layer == "UNITSPACING":
            unit_spacing_points.extend(collect_points_from_entity(sub, local_transform, doc))
        elif layer == "EQUIPMENT":
            #blocks have contour line noise so need to only look at the tight equipment perimeter
            equipment_points.extend(collect_points_from_entity(sub, local_transform, doc))

    # Use the tightest available boundary — EN1176 > UNIT SPACING > EQUIPMENT
    if en1176_points:
        final_points = en1176_points
        boundary_type = "EN1176IMPACTAREA"
        threshold = 0
    elif unit_spacing_points:
        final_points = unit_spacing_points
        boundary_type = "UNIT SPACING"
        threshold = 0
    elif equipment_points:
        final_points = equipment_points
        boundary_type = "EQUIPMENT"
        threshold = THRESHOLD_EQUIPMENT 
    else:
        return None

    print(f"  [{block_name}] Using {boundary_type} ({len(final_points)} points)")

    #collate all the x and y points
    #perimeter = [[x1...xn],[y1...yn]]
    xs = [p[0] for p in final_points]
    ys = [p[1] for p in final_points]

    return {
        'points': final_points,
        'min_x': min(xs), 'max_x': max(xs),
        'min_y': min(ys), 'max_y': max(ys),
        'width': max(xs) - min(xs),
        'height': max(ys) - min(ys),
        'boundary_type': boundary_type,
        'threshold': threshold,
    }


def extract_drawing_items(dxf: Drawing) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Scans the DXF for surfacing bounds and valid equipment placements."""
    #initialise dictionaries to track items
    items_and_quantity = {}
    msp = dxf.modelspace()

    all_points = []

    #look on the surface layer
    for entity in msp.query('*[layer=="SURFACING"]'):
        #ignore surface elements that aren't the hatch (want the bound box)
        if entity.dxftype() != "HATCH":
            continue

        for path in entity.paths:
            try:
                #PolylinePath with exactly 4 vertices means its a grid of tiles
                #these are AutoCAD's internal hatch pattern grid cells, not site boundaries
                if hasattr(path, 'vertices'):
                    if len(path.vertices) == 4:
                        continue #ignore them
                    all_points.extend((v[0], v[1]) for v in path.vertices)

                elif hasattr(path, 'edges'):
                    for edge in path.edges:
                        etype = edge.EDGE_TYPE
                        if etype == "LineEdge":
                            all_points += [(edge.start[0], edge.start[1]),
                                           (edge.end[0],   edge.end[1])]
                        elif etype == "ArcEdge":
                            cx, cy, r = edge.center[0], edge.center[1], edge.radius
                            all_points += [(cx - r, cy - r), (cx + r, cy + r)]
                        elif etype in ("EllipseEdge", "SplineEdge"):
                            pts = getattr(edge, 'control_points',
                                  getattr(edge, 'fit_points', []))
                            all_points.extend((p[0], p[1]) for p in pts)

            except Exception as e:
                logging.debug(f"Hatch path parsing failed: {e}")
                continue

    site_bounds = None
    if all_points:
        xs, ys = zip(*all_points)
        site_bounds = {
            'min_x': min(xs), 'max_x': max(xs),
            'min_y': min(ys), 'max_y': max(ys)
        }
        print(f"Surface bounds: X({site_bounds['min_x']:.2f}, {site_bounds['max_x']:.2f}), "
              f"Y({site_bounds['min_y']:.2f}, {site_bounds['max_y']:.2f})")

    median_x = median_y = None
    #^did we not enter the if to set the defined bounding box (rare)
    #median of items points is used as a back up to the bbox if it fails
    if site_bounds is None:
        all_x, all_y = [], []
        #look for items
        for entity in msp.query('INSERT'):
            if entity.dxf.name.upper().startswith('PLAN'):
                #create master list of centre points
                all_x.append(entity.dxf.insert[0])
                all_y.append(entity.dxf.insert[1])
        
        if all_x and all_y:
            #calculate a median of all the items as a BACKUP for the centre
            median_x = statistics.median(all_x)
            median_y = statistics.median(all_y)
            print(f"MEDIAN CENTER POINT: X: {median_x:,.2f}, Y: {median_y:,.2f}")

    def is_within_site(unit_bounds: Optional[Dict[str, Any]], x: float, y: float) -> bool:
        #was the bounding box found
        if site_bounds is not None:
            #was the item b. box found
            if unit_bounds is not None:
                #is the item within the global b. box
                return (unit_bounds['min_x'] >= site_bounds['min_x'] and
                        unit_bounds['max_x'] <= site_bounds['max_x'] and
                        unit_bounds['min_y'] >= site_bounds['min_y'] and
                        unit_bounds['max_y'] <= site_bounds['max_y'])
            #no item b. box so use centre point coords
            else:
                return (site_bounds['min_x'] <= x <= site_bounds['max_x'] and
                        site_bounds['min_y'] <= y <= site_bounds['max_y'])
        #median must have been set
        else:
            if median_x is None or median_y is None:
                return True #failsafe if the drawing is completely empty
            #heuristic range i used away from median (imperfect)
            return abs(x - median_x) <= MAX_X_DEVIATION and abs(y - median_y) <= MAX_Y_DEVIATION
        
    #initialise visualisation table
    print(f"{'Equipment Name':<30} | {'X Coord':<15} | {'Y Coord':<15} | {'Status':<12}")
    print("-" * 80)

    #dictionary to temporarily hold everything while we scan
    summary_data = {}
    all_valid_bounds = [] 
    
    #scan for the items
    for entity in msp.query('INSERT'):
        item_name = entity.dxf.name
        if not item_name.upper().startswith('PLAN'):
            continue

        #get centre point as back up if no b. box
        x = round(entity.dxf.insert[0], 2)
        y = round(entity.dxf.insert[1], 2)
        #query item b. box
        bounds = get_block_world_bounds(entity, dxf)
        #no b. box found
        if bounds is None:
            print(f"No geometry found for block: {entity.dxf.name}")
        else:
            #print perimeter of bounding box for this item
            print(f"{entity.dxf.name} BOUNDS: {bounds['min_x'], bounds['max_x'], bounds['min_y'], bounds['max_y']}")
        
        #is this item in the play area bounding box
        within = is_within_site(bounds, x, y)

        #if not seen, initialise new entry with name as key
        if item_name not in summary_data:
            summary_data[item_name] = {'valid_pos': [], 'outlier_pos': [], 'valid_bounds': []}
        
        if within:
            #its in the play area, so note the centre coords
            summary_data[item_name]['valid_pos'].append((x, y))
            if bounds:
                #its in the play area so note all the bounds (perimeter lines)
                summary_data[item_name]['valid_bounds'].append(bounds)
        else:
            #its not in the play area, still add for table visualisation
            summary_data[item_name]['outlier_pos'].append((x, y))

    #build the final table and the data structures
    print(f"{'Equipment Name':<30} | {'Qty':<4} | {'Status':<8} | {'Coordinates (X, Y)'}")
    print("-" * 100)

    for name, data in summary_data.items():
        clean_name = name.replace('PLAN ', '').strip()
        #get all its positions, whether inside or outside play area
        valid_coords = data['valid_pos']
        outlier_coords = data['outlier_pos']
        
        #print and store the valid, inside-site items
        if valid_coords:
            qty = len(valid_coords)
            #joins all coordinates into a single comma-separated string
            coords_str = ", ".join([f"({x}, {y})" for x, y in valid_coords])
            #OK is used to show its in the play area
            print(f"{clean_name:<30} | {qty:<4} | {'OK':<8} | {coords_str}")
            
            #populate the dictionary for comparison against quote
            items_and_quantity[name] = {
                'Quantity': qty,
                'Position': valid_coords,
                'Bounds': data['valid_bounds']
            }
            
            #get all the bounds of the items that are valid in a master list
            for i, pos in enumerate(valid_coords):
                if data['valid_bounds'] and i < len(data['valid_bounds']):
                    all_valid_bounds.append({
                        'name': name,
                        'bounds': data['valid_bounds'][i],
                        'position': pos
                    })
        
        #print the outliers so you know what was skipped
        if outlier_coords:
            qty = len(outlier_coords)
            coords_str = ", ".join([f"({x}, {y})" for x, y in outlier_coords])
            #OUTLIER in table to show this isnt being counted
            print(f"{clean_name:<30} | {qty:<4} | {'OUTLIER':<8} | {coords_str}")

    print("-" * 100)
    
    print("\n--- FINAL BOUNDING BOX SUMMARY ---")
    for item in all_valid_bounds:
        name = item['name'].replace('PLAN ', '').strip()
        bound = item['bounds']
        
        #ranges of bound box
        min_x, max_x = round(bound['min_x'], 2), round(bound['max_x'], 2)
        min_y, max_y = round(bound['min_y'], 2), round(bound['max_y'], 2)
        
        print(f"{name:<30} | X: {min_x} to {max_x} | Y: {min_y} to {max_y}")
    
    return items_and_quantity, all_valid_bounds

def points_to_polygon(points: List[Tuple[float, float]]) -> Optional[Any]:
    """Convert a list of (x,y) points to a Shapely Convex Hull."""
    try:
        # MultiPoint doesn't care about order. 
        # convex_hull wraps them in a valid, unbroken polygon.
        return MultiPoint(points).convex_hull 
    except Exception as e:
        logging.debug(f"Shapely polygon conversion failed: {e}")
        return None

def check_distances(all_valid_bounds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Calculates spatial overlaps and distance violations between parsed items."""
    
    try:
        with open('spacing_exclusion_codes.json', 'r') as f:
            exclusions = json.load(f)
    except FileNotFoundError:
        logging.warning("spacing_exclusion_codes.json not found. Proceeding without exclusions.")
        exclusions = {}
    
    #this assigns a key to each equipment type section
    #e.g. if a violation should be ignored they must both have the matching name code
    # Use a set to avoid adding the same section twice for one code
    section_map = defaultdict(set)

    for section_name, items in exclusions.items():
        for item_entry in items:
            item_code = item_entry[0]
            # Add the section name to the set of sections associated with this code
            section_map[item_code].add(section_name)   

    conflicts = []

    for i, item_a in enumerate(all_valid_bounds):
        for j, item_b in enumerate(all_valid_bounds):
            #already been conversely checked
            if j <= i:
                continue

            if "Bin" in item_a['name'] or "Gate" in item_a['name'] or "Bin" in item_b['name'] or "Gate" in item_b['name']:
                continue

            code_1 =  re.findall(r'\b[A-Z]+\b', item_a['name'].replace("PLAN",''))
            code_2 = re.findall(r'\b[A-Z]+\b', item_b['name'].replace("PLAN",''))

            print(item_a['name'], "CODE 1  IS", code_1)
            print(item_b['name'], "CODE 2  IS", code_2)

            # Retrieve the sets of sections (returns an empty set if code not found)
            if len(code_1) > 0 and len(code_2) > 0:
                sections_1 = section_map.get(code_1[-1], set())
                sections_2 = section_map.get(code_2[-1], set())

                # Check for overlap between the two sets
                common_sections = sections_1.intersection(sections_2)

                if common_sections:
                    # They share at least one section
                    print(f"Ignoring conflict: Both {code_1} and {code_2} appear in: {common_sections}")
                    continue

            pts_a = np.array(item_a['bounds']['points'])
            pts_b = np.array(item_b['bounds']['points'])

            bounds_a, bounds_b = item_a['bounds'], item_b['bounds']
            x_gap = max(bounds_a['min_x'] - bounds_b['max_x'], bounds_b['min_x'] - bounds_a['max_x'], 0)
            y_gap = max(bounds_a['min_y'] - bounds_b['max_y'], bounds_b['min_y'] - bounds_a['max_y'], 0)
            #if either of the minimal linear distances are > the 1.5m, it's impossibe these are too close
            if max(x_gap, y_gap) > MIN_GAP_DISTANCE:
                continue

            #recreate the polygon perimeters
            poly_a = points_to_polygon(item_a['bounds']['points'])
            poly_b = points_to_polygon(item_b['bounds']['points'])

            violation_type = None

            if poly_a and poly_b:
                if poly_a.exterior.intersects(poly_b):
                    violation_type = "OVERLAP"
            else:
                # Shapely failed — fall back to point-to-point
                diff = pts_a[:, None, :] - pts_b[None, :, :]
                dist_sq = (diff ** 2).sum(axis=2)
                close_mask = dist_sq < FALLBACK_CLOSE_DISTANCE ** 2
                if close_mask.any():
                    violation_type = "TOO CLOSE (fallback)"

            if violation_type:
                conflicts.append({
                    "equipment_a": item_a['name'],
                    "equipment_b": item_b['name'],
                    "boundary_used_a": item_a['bounds']['boundary_type'],
                    "boundary_used_b": item_b['bounds']['boundary_type'],
                    "violation_type": violation_type,
                })
    
    if conflicts:
        print(f"\n--- {len(conflicts)} SPACING VIOLATIONS ---")
        for c in conflicts:
            print(f"  {c['equipment_a']} <-> {c['equipment_b']} | "
                  f"{c['violation_type']} | "
                  f"boundaries: {c['boundary_used_a']} / {c['boundary_used_b']}")
    else:
        print("no spacing issues")

    return conflicts