import napari
import geojson
from shapely.geometry import shape, Polygon, MultiPolygon, Point, mapping
from shapely import is_valid
import openslide
import numpy as np
from scipy.spatial import Voronoi, voronoi_plot_2d
from magicgui import magicgui
from qtpy.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget, QCheckBox, QTabWidget
from datetime import datetime
from tifffile import imwrite, imread
import random, os
import cv2
import json
from itertools import cycle
from . import qupath2palm

# Global variable to store the count label
global_count_label = None

# Global variable for the area label
global_area_label = None

global_scaling_factor = 1
global_extract_level = 2

# Global variable to store the warp matrix for PALM export
global_warp_matrix = None

# Global variable to store the last used directory
global_last_directory = None

# Default warp matrix constant (standard slide-to-PALM transform)
DEFAULT_WARP_MATRIX = np.array([
    [2.63438951e-01, -5.02264734e-04, 88412.9333],
    [6.01104348e-04,  2.63626480e-01, 26064.1732]
])

IDENTITY_WARP_MATRIX = np.array([
    [1., 0., 0.],
    [0., 1., 0.]
])

# Glasbey-like distinct colors for visualization (20 colors)
GLASBEY_COLORS = [
    '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
    '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe',
    '#008080', '#e6beff', '#9a6324', '#fffac8', '#800000',
    '#aaffc3', '#808000', '#ffd8b1', '#000075', '#808080'
]

def parse_source_points_tsv(file_path):
    """Read a TSV file with x/y header and return the first 3 data rows as np.float32 array of shape (3, 2)."""
    points = []
    with open(file_path, "r") as f:
        header = f.readline()  # skip header
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            points.append([float(parts[0]), float(parts[1])])
            if len(points) == 3:
                break
    if len(points) != 3:
        raise ValueError(f"Expected 3 coordinate pairs, found {len(points)}")
    return np.array(points, dtype=np.float32)


def parse_palm_destination_points(file_path):
    """Read a PALM element file and extract coordinates from lines starting with '.\\t'.

    Expected format: '.\\t97817.1,54024.0'
    Returns first 3 coordinates as np.float32 array of shape (3, 2).
    """
    points = []
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith(".\t"):
                coord_str = line.split("\t")[1]
                x, y = coord_str.split(",")
                points.append([float(x), float(y)])
                if len(points) == 3:
                    break
    if len(points) != 3:
        raise ValueError(f"Expected 3 coordinate pairs from '.' lines, found {len(points)}")
    return np.array(points, dtype=np.float32)


def compute_affine_from_points(src_pts, dst_pts):
    """Compute a 2x3 affine transformation matrix from 3 source and 3 destination points."""
    return cv2.getAffineTransform(src_pts, dst_pts)


def calculate_caliper(polygon):
    """Calculate caliper (longest dimension) using minimum rotated rectangle."""
    try:
        rect = polygon.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)
        side1 = ((coords[1][0]-coords[0][0])**2 + (coords[1][1]-coords[0][1])**2)**0.5
        side2 = ((coords[2][0]-coords[1][0])**2 + (coords[2][1]-coords[1][1])**2)**0.5
        return max(side1, side2)
    except:
        return polygon.length  # Fallback

# Function to update the area display when a shape is selected
def update_selected_area(layer):
    global global_area_label
    if global_area_label is None or layer is None:
        return
    
    if hasattr(layer, 'selected_data') and layer.selected_data:
        # If exactly one shape is selected, calculate and display its area
        if len(layer.selected_data) == 1:
            selected_index = list(layer.selected_data)[0]
            selected_shape = layer.data[selected_index]
            # Convert to Polygon to calculate area
            polygon = Polygon(selected_shape)
            area = polygon.area
            global_area_label.setText(f"Selected area: {area:.2f} square pixels")
        else:
            # If multiple shapes are selected, show total area
            total_area = 0
            for index in layer.selected_data:
                polygon = Polygon(layer.data[index])
                total_area += polygon.area
            global_area_label.setText(f"Total selected area: {total_area:.2f} square pixels")
    else:
        # No shape selected
        global_area_label.setText("Selected area: None")

# Save settings to a JSON file
def save_settings(settings_dict, output_dir):
    """
    Save settings to a JSON file in the specified output directory.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = os.path.join(output_dir, f'settings_{timestamp}.json')

    with open(filename, 'w') as f:
        json.dump(settings_dict, f, indent=2)

    print(f"Saved settings to: {filename}")
    return filename


def load_settings(file_path):
    """
    Load settings from a JSON file.
    Returns a dictionary of settings or None if loading fails.
    """
    try:
        with open(file_path, 'r') as f:
            settings = json.load(f)
        print(f"Loaded settings from: {file_path}")
        return settings
    except Exception as e:
        print(f"Error loading settings: {e}")
        return None

def load_geojson(file_path, scale): # scale parameter is now used for the scaling_factor
    with open(file_path) as f:
        data = geojson.load(f)
    annotations = []
    annotation_names = []
    
    for feature in data['features']:
        polygon = shape(feature['geometry'])
        # Apply scaling factor here (divide coordinates)
        # Ensure scale is not zero to avoid division by zero errors
        effective_scale = scale if scale != 0 else 1
        scaled_coords = [(y / effective_scale, x / effective_scale) for x, y in polygon.exterior.coords]  # Flip x and y
        annotations.append(Polygon(scaled_coords))
        
        # Get the name from properties, or use "annotation" as default
        name = feature['properties'].get('name', 'annotation')
        annotation_names.append(name)
    
    return annotations, annotation_names

# Function to determine the number of digits needed for formatting
def get_digits_for_formatting(count):
    return max(4, len(str(count - 1)))  # At least 4 digits, or more if needed

# # Function to divide a polygon into 4 equal parts with tile names
# def divide_into_four(polygon, gap_size, min_area, original_name):
#     minx, miny, maxx, maxy = polygon.bounds
#     width = (maxx - minx) / 2 - gap_size / 2
#     height = (maxy - miny) / 2 - gap_size / 2

#     parts = []
#     tile_names = []
#     tile_count = 0
#     digits = get_digits_for_formatting(4)  # Always 4 parts

#     candidates = [
#         Polygon([(minx, miny), (minx + width, miny), (minx + width, miny + height), (minx, miny + height)]),
#         Polygon([(minx + width + gap_size, miny), (maxx, miny), (maxx, miny + height), (minx + width + gap_size, miny + height)]),
#         Polygon([(minx, miny + height + gap_size), (minx + width, miny + height + gap_size), (minx + width, maxy), (minx, maxy)]),
#         Polygon([(minx + width + gap_size, miny + height + gap_size), (maxx, miny + height + gap_size), (maxx, maxy), (minx + width + gap_size, maxy)])
#     ]

#     if all(part.area >= min_area for part in candidates):
#         for part in candidates:
#             parts.append(part)
#             tile_names.append(f"{original_name}_{tile_count:0{digits}d}")
#             tile_count += 1

#     return parts, tile_names

# Function to divide a polygon into 4 equal parts, masked, and ensure 4 parts are returned if possible
def divide_into_four(polygon, gap_size, min_area, original_name, pad_to_expected=True):
    """
    Returns:
        parts: list of Polygon objects
        tile_names: list of names for each part
        is_fake: list of booleans indicating which parts are fake padding tiles
    """
    minx, miny, maxx, maxy = polygon.bounds
    width = (maxx - minx) / 2 - gap_size / 2
    height = (maxy - miny) / 2 - gap_size / 2

    parts = []
    tile_names = []
    is_fake = []  # Track which tiles are fake padding
    tile_count = 0
    digits = get_digits_for_formatting(4)  # Always 4 parts target

    # Define the four rectangular regions based on the bounding box and gap
    rect_candidates = [
        Polygon([(minx, miny), (minx + width, miny), (minx + width, miny + height), (minx, miny + height)]), # Top-left
        Polygon([(minx + width + gap_size, miny), (maxx, miny), (maxx, miny + height), (minx + width + gap_size, miny + height)]), # Top-right
        Polygon([(minx, miny + height + gap_size), (minx + width, miny + height + gap_size), (minx + width, maxy), (minx, maxy)]), # Bottom-left
        Polygon([(minx + width + gap_size, miny + height + gap_size), (maxx, miny + height + gap_size), (maxx, maxy), (minx + width + gap_size, maxy)]) # Bottom-right
    ]

    # Intersect each rectangle with the original polygon
    current_tile_index = 0 # Use a separate index for naming
    for rect in rect_candidates:
        if rect.intersects(polygon):
            intersection = rect.intersection(polygon)
            if not intersection.is_empty:
                if isinstance(intersection, Polygon):
                    if intersection.area >= min_area:
                        parts.append(intersection)
                        tile_names.append(f"{original_name}_{current_tile_index:0{digits}d}")
                        is_fake.append(False)
                        current_tile_index += 1
                elif isinstance(intersection, MultiPolygon):
                    for single_poly in intersection.geoms:
                         if single_poly.area >= min_area:
                             parts.append(single_poly)
                             tile_names.append(f"{original_name}_{current_tile_index:0{digits}d}")
                             is_fake.append(False)
                             current_tile_index += 1
                             # Stop adding if we already reached 4 parts from a multipolygon, though unlikely needed
                             # if current_tile_index >= 4: break
        # if current_tile_index >= 4: break # Stop processing rects if we already have 4 parts


    # Pad the list to ensure it has 4 elements if possible using tiny placeholder dots
    expected_count = 4
    num_parts_found = len(parts)
    if pad_to_expected and 0 < num_parts_found < expected_count:
        num_needed = expected_count - num_parts_found
        # Create tiny dot at centroid of first valid part
        reference_part = parts[0]
        centroid = reference_part.centroid
        fake_radius = 1.0  # 1 pixel radius - minimal but valid
        fake_minitile = centroid.buffer(fake_radius)

        print(f"Warning: Only {num_parts_found} valid parts found for '{original_name}'. Adding {num_needed} fake minitile(s).")

        for i in range(num_needed):
            parts.append(fake_minitile)
            tile_names.append(f"{original_name}_{current_tile_index:0{digits}d}")
            is_fake.append(True)  # Mark as fake padding tile
            current_tile_index += 1

    # If num_parts_found is 0 or already at expected count, do nothing extra.

    return parts, tile_names, is_fake


def divide_into_grid(polygon, num_cols, num_rows, gap_size, min_area, original_name, pad_to_expected=True):
    """
    Divide a polygon into a grid of num_cols x num_rows minitiles.
    Similar to divide_into_four but with configurable grid dimensions.

    Args:
        pad_to_expected: If True, pad with tiny placeholder dots to ensure
                         uniform minitile count (num_cols * num_rows) for PALM well mapping.

    Returns:
        parts: list of Polygon objects
        tile_names: list of names for each part
        is_fake: list of booleans indicating which parts are fake padding tiles
    """
    minx, miny, maxx, maxy = polygon.bounds
    total_width = maxx - minx
    total_height = maxy - miny

    # Calculate cell dimensions accounting for gaps
    total_gap_x = gap_size * (num_cols - 1)
    total_gap_y = gap_size * (num_rows - 1)
    cell_width = (total_width - total_gap_x) / num_cols
    cell_height = (total_height - total_gap_y) / num_rows

    parts = []
    tile_names = []
    is_fake = []  # Track which tiles are fake padding
    expected_count = num_cols * num_rows
    digits = get_digits_for_formatting(expected_count)
    current_tile_index = 0

    for row in range(num_rows):
        for col in range(num_cols):
            # Calculate cell bounds
            x0 = minx + col * (cell_width + gap_size)
            y0 = miny + row * (cell_height + gap_size)
            x1 = x0 + cell_width
            y1 = y0 + cell_height

            rect = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

            if rect.intersects(polygon):
                intersection = rect.intersection(polygon)
                if not intersection.is_empty:
                    if isinstance(intersection, Polygon):
                        if intersection.area >= min_area:
                            parts.append(intersection)
                            tile_names.append(f"{original_name}_{current_tile_index:0{digits}d}")
                            is_fake.append(False)
                            current_tile_index += 1
                    elif isinstance(intersection, MultiPolygon):
                        for single_poly in intersection.geoms:
                            if single_poly.area >= min_area:
                                parts.append(single_poly)
                                tile_names.append(f"{original_name}_{current_tile_index:0{digits}d}")
                                is_fake.append(False)
                                current_tile_index += 1

    # Pad with fake minitiles if fewer than expected (for PALM well mapping)
    num_parts_found = len(parts)
    if pad_to_expected and 0 < num_parts_found < expected_count:
        num_needed = expected_count - num_parts_found
        # Create tiny dot at centroid of first valid part
        reference_part = parts[0]
        centroid = reference_part.centroid
        fake_radius = 1.0  # 1 pixel radius - minimal but valid
        fake_minitile = centroid.buffer(fake_radius)

        print(f"Warning: Only {num_parts_found} valid parts found for '{original_name}' (expected {expected_count}). Adding {num_needed} fake minitile(s).")

        for i in range(num_needed):
            parts.append(fake_minitile)
            tile_names.append(f"{original_name}_{current_tile_index:0{digits}d}")
            is_fake.append(True)  # Mark as fake padding tile
            current_tile_index += 1

    return parts, tile_names, is_fake


# Split Polygon into Tiles with Gap
def split_polygon(polygon, tile_size, gap, original_name):
    min_x, min_y, max_x, max_y = polygon.bounds
    tiles = []
    tile_names = []
    tile_count = 0
    
    # Calculate number of expected tiles for digit formatting
    x_tiles = int(np.ceil((max_x - min_x) / (tile_size + gap)))
    y_tiles = int(np.ceil((max_y - min_y) / (tile_size + gap)))
    total_possible_tiles = x_tiles * y_tiles
    digits = get_digits_for_formatting(total_possible_tiles)
    
    def add_polygons(intersection, base_name, count, digits):
        """Add individual polygons from intersection (handles MultiPolygon)."""
        if isinstance(intersection, Polygon):
            tiles.append(intersection)
            tile_names.append(f"{base_name}_{count:0{digits}d}")
            return count + 1
        elif isinstance(intersection, MultiPolygon):
            for idx, poly in enumerate(intersection.geoms):
                tiles.append(poly)
                tile_names.append(f"{base_name}_{count + idx:0{digits}d}")
            return count + len(intersection.geoms)
        return count

    adjusted_tile_size = tile_size + gap
    for x in np.arange(min_x, max_x, adjusted_tile_size):
        for y in np.arange(min_y, max_y, adjusted_tile_size):
            tile = Polygon([
                (x, y),
                (x + tile_size, y),
                (x + tile_size, y + tile_size),
                (x, y + tile_size)
            ])
            if tile.intersects(polygon):
                intersection = tile.intersection(polygon)
                tile_count = add_polygons(intersection, original_name, tile_count, digits)
    
    return tiles, tile_names

# Split Polygon into Hexagonal Tiles with Gap - multipolygon
def split_hexagonal(polygon, tile_size, gap, original_name):
    min_x, min_y, max_x, max_y = polygon.bounds
    tiles = []
    tile_names = []
    tile_count = 0

    # Calculate the height and width of a hexagon
    hex_width = tile_size * 3 ** 0.5
    hex_height = tile_size * 1.5

    # Adjust for gaps
    adjusted_width = hex_width + gap
    adjusted_height = hex_height + gap

    # Determine number of tiles
    x_tiles = int(np.ceil((max_x - min_x) / adjusted_width))
    y_tiles = int(np.ceil((max_y - min_y) / adjusted_height))
    total_possible_tiles = x_tiles * y_tiles
    digits = len(str(total_possible_tiles))

    def add_polygons(intersection, base_name, count, digits):
        """Add individual polygons from intersection (handles MultiPolygon)."""
        if isinstance(intersection, Polygon):
            tiles.append(intersection)
            tile_names.append(f"{base_name}_{count:0{digits}d}")
            return count + 1
        elif isinstance(intersection, MultiPolygon):
            for idx, poly in enumerate(intersection.geoms):
                tiles.append(poly)
                tile_names.append(f"{base_name}_{count + idx:0{digits}d}")
            return count + len(intersection.geoms)
        return count

    for row in range(y_tiles):
        for col in range(x_tiles):
            x_offset = min_x + col * adjusted_width
            y_offset = min_y + row * adjusted_height

            # Offset every other row to create hex pattern
            if row % 2 == 1:
                x_offset += hex_width / 2

            # Define hexagon vertices
            hex_tile = Polygon([
                (x_offset, y_offset),
                (x_offset + hex_width / 2, y_offset - tile_size / 2),
                (x_offset + hex_width, y_offset),
                (x_offset + hex_width, y_offset + tile_size),
                (x_offset + hex_width / 2, y_offset + tile_size * 1.5),
                (x_offset, y_offset + tile_size)
            ])

            if hex_tile.intersects(polygon):
                intersection = hex_tile.intersection(polygon)
                tile_count = add_polygons(intersection, original_name, tile_count, digits)

    return tiles, tile_names

# Split Polygon into Voronoi Shapes with adjustable gap
def split_voronoi(polygon, num_points=100, gap_size=0, original_name="annotation"):
    min_x, min_y, max_x, max_y = polygon.bounds
    points = np.random.rand(num_points, 2)
    points[:, 0] = points[:, 0] * (max_x - min_x) + min_x
    points[:, 1] = points[:, 1] * (max_y - min_y) + min_y
    vor = Voronoi(points)

    tiles = []
    tile_names = []
    
    # Calculate digits for formatting
    digits = get_digits_for_formatting(num_points)
    tile_count = 0
    
    def add_polygons(intersection, base_name, count, digits):
        """Add individual polygons from intersection (handles MultiPolygon)."""
        if isinstance(intersection, Polygon):
            tiles.append(intersection)
            tile_names.append(f"{base_name}_{count:0{digits}d}")
            return count + 1
        elif isinstance(intersection, MultiPolygon):
            for idx, poly in enumerate(intersection.geoms):
                tiles.append(poly)
                tile_names.append(f"{base_name}_{count + idx:0{digits}d}")
            return count + len(intersection.geoms)
        return count
        
    for region_index in vor.regions:
        if len(region_index) > 0 and -1 not in region_index:
            region_coords = [vor.vertices[i] for i in region_index]
            # Apply buffer (gap) before intersection check
            region_polygon = Polygon(region_coords).buffer(-gap_size) if gap_size > 0 else Polygon(region_coords)
            # Check validity and intersection
            if region_polygon.is_valid and not region_polygon.is_empty and region_polygon.intersects(polygon):
                 intersection = region_polygon.intersection(polygon)
                 if not intersection.is_empty: # Ensure intersection is not empty before adding
                      tile_count = add_polygons(intersection, original_name, tile_count, digits)
    
    return tiles, tile_names


def split_equal_area(polygon, n, gap_size=0, original_name="annotation", n_iterations=20):
    """Divide polygon into n roughly equal-area tiles using Monte Carlo Lloyd's algorithm.

    Generates uniform sample points inside the polygon, then iteratively assigns each
    sample to its nearest seed and moves the seed to the mean of its assigned samples.
    This directly optimises for equal sample-point assignment (equal area), unlike
    geometric-centroid Lloyd's which does not guarantee equal areas for irregular polygons.
    """
    from shapely.prepared import prep

    min_x, min_y, max_x, max_y = polygon.bounds
    rng = np.random.default_rng()

    # Generate uniform sample points inside the polygon via rejection sampling
    n_samples = max(5000, n * 500)
    prepared = prep(polygon)
    samples = []
    while len(samples) < n_samples:
        batch = np.column_stack([
            rng.uniform(min_x, max_x, n_samples * 4),
            rng.uniform(min_y, max_y, n_samples * 4),
        ])
        inside = np.array([prepared.contains(Point(x, y)) for x, y in batch])
        samples.extend(batch[inside].tolist())
    samples = np.array(samples[:n_samples])

    if len(samples) < n:
        return [], []

    # Initialise seeds by picking n evenly spaced samples
    indices = np.round(np.linspace(0, len(samples) - 1, n)).astype(int)
    seeds = samples[indices].copy()

    # Monte Carlo Lloyd's iterations
    for _ in range(n_iterations):
        # Assign each sample to its nearest seed (vectorised)
        dists = np.linalg.norm(samples[:, None, :] - seeds[None, :, :], axis=2)  # (n_samples, n)
        assignments = np.argmin(dists, axis=1)
        new_seeds = seeds.copy()
        for i in range(n):
            mask = assignments == i
            if mask.sum() > 0:
                new_seeds[i] = samples[mask].mean(axis=0)
        seeds = new_seeds

    # Build Voronoi regions from converged seeds and clip to polygon
    def compute_clipped_regions(pts):
        mirrored = np.vstack([
            pts,
            np.column_stack([2 * min_x - pts[:, 0], pts[:, 1]]),
            np.column_stack([2 * max_x - pts[:, 0], pts[:, 1]]),
            np.column_stack([pts[:, 0], 2 * min_y - pts[:, 1]]),
            np.column_stack([pts[:, 0], 2 * max_y - pts[:, 1]]),
        ])
        vor = Voronoi(mirrored)
        regions = []
        for i in range(len(pts)):
            region_idx = vor.point_region[i]
            region = vor.regions[region_idx]
            if -1 in region or len(region) == 0:
                regions.append(None)
                continue
            region_coords = vor.vertices[region]
            try:
                region_poly = Polygon(region_coords).intersection(polygon)
                regions.append(region_poly if region_poly.is_valid and not region_poly.is_empty else None)
            except Exception:
                regions.append(None)
        return regions

    final_regions = compute_clipped_regions(seeds)
    tiles, tile_names = [], []
    digits = get_digits_for_formatting(len(final_regions))
    idx = 1
    for region in final_regions:
        if region is None or region.is_empty:
            continue
        if gap_size > 0:
            region = region.buffer(-gap_size / 2)
            if region is None or region.is_empty:
                continue
        region = region.buffer(0)
        if isinstance(region, MultiPolygon):
            for part in region.geoms:
                if not part.is_empty:
                    tiles.append(part)
                    tile_names.append(f"{original_name}_{idx:0{digits}d}")
                    idx += 1
        elif not region.is_empty:
            tiles.append(region)
            tile_names.append(f"{original_name}_{idx:0{digits}d}")
            idx += 1
    return tiles, tile_names


# Modified save_geojson to accept and use scaling_factor
def save_geojson(shapes, shape_names, min_area, scaling_factor, randomize=False, bias_to_small=False, parent_areas=None):
    global global_last_directory

    start_dir = global_last_directory or ""
    file_path, _ = QFileDialog.getSaveFileName(None, 'Save Annotations', start_dir, 'GeoJSON Files (*.geojson)')
    if file_path:
        global_last_directory = os.path.dirname(file_path)
        features = []
        
        # Create a list of indices, shapes, and names
        if parent_areas is None:
            # Default behavior if parent_areas is not provided
            shape_data = list(zip(range(len(shapes)), shapes, shape_names, [None]*len(shapes)))
        else:
            shape_data = list(zip(range(len(shapes)), shapes, shape_names, parent_areas))
        
        # Randomize if requested
        if randomize:
            if bias_to_small and parent_areas is not None:
                # Biased randomization based on parent areas
                # Sort by parent area (ascending) with a random factor to maintain some randomness
                # Smaller parent objects get a better random factor to appear earlier
                random_weights = [random.random() * (1/area if area > 0 else 1) for area in parent_areas]
                shape_data = sorted(shape_data, key=lambda x: (-random_weights[x[0]]))
            else:
                # Standard randomization
                random.shuffle(shape_data)
        
        # Re-index after randomization
        if randomize:
            new_shape_data = []
            digits = get_digits_for_formatting(len(shape_data))
            
            for i, data in enumerate(shape_data):
                # Extract original components based on whether parent_areas was included
                if len(data) == 4:  # With parent_areas
                    _, shape_obj, name_base, _ = data
                else:  # Without parent_areas
                    _, shape_obj, name_base = data
                
                # Extract the original name without the number
                # original_name = name_base # name_base.split("_")[0] if "_" in name_base else name_base # Keep full name for re-indexing
                original_name_parts = name_base.split('_')
                if len(original_name_parts) > 1 and original_name_parts[-1].isdigit():
                   original_name = '_'.join(original_name_parts[:-1]) # Use name before last underscore if it looks like an index
                else:
                   original_name = name_base # Otherwise use the full name base
                   
                new_name = f"{original_name}_{i:0{digits}d}"
                new_shape_data.append((i, shape_obj, new_name, None)) # Parent area not needed after sorting
            shape_data = new_shape_data
        
        # Create the features
        print(scaling_factor)
        effective_scale = scaling_factor if scaling_factor != 0 else 1 # Avoid multiplying by zero

        for i, shape_obj, name, _ in shape_data:
            # Ensure shape_obj is a numpy array before converting to Polygon
            if isinstance(shape_obj, np.ndarray):
                 polygon = Polygon(shape_obj)
            elif isinstance(shape_obj, Polygon): # It might already be a polygon from splitting
                 polygon = shape_obj
            else:
                 print(f"Warning: Skipping unsupported shape type for {name}: {type(shape_obj)}")
                 continue # Skip if not a type we can handle

            if polygon.area >= min_area:
                 # Scale coordinates UP before saving
                 scaled_coords_xy = [(x * effective_scale, y * effective_scale) for x, y in polygon.exterior.coords]
                 # GeoJSON expects (longitude, latitude) which corresponds to (x, y) in image coords
                 # However, the load function flips them assuming input is (long, lat) -> (y, x)
                 # So, to reverse this on save, we should save as (y, x) which means (scaled_y, scaled_x)
                 # Let's stick to the original save format: [[(y, x) for x, y in polygon.exterior.coords]]
                 # Apply scaling to the original x, y and maintain the (y, x) output structure
                 geojson_coords = [[(sy, sx) for sx, sy in scaled_coords_xy]]

                 features.append({
                     'type': 'Feature',
                     'geometry': {'type': 'Polygon', 'coordinates': geojson_coords},
                     'properties': {'name': name}
                 })
        
        geojson_data = {'type': 'FeatureCollection', 'features': features}
        with open(file_path, 'w') as f:
            geojson.dump(geojson_data, f)
        return file_path
    return None


def save_palm_text(geojson_path, warp_mat=None):
    """
    Save PALM elements text files from GeoJSON.
    Outputs both CenterRoboLPC (irregular) and RoboLPC (new) formats.
    """
    # Use identity matrix if no warp matrix provided
    if warp_mat is None:
        warp_mat = np.array([[1., 0., 0.], [0., 1., 0.]])

    base_path = geojson_path.rsplit('.', 1)[0]

    # Generate irregular format (CenterRoboLPC)
    palm_irregular = qupath2palm.qupath2palm_affine_irregular(
        geojson_path, warp_mat, print_to_screen=False)
    irregular_path = base_path + '_CenterRoboLPC.txt'
    with open(irregular_path, 'w') as f:
        f.write(palm_irregular)
    print(f"Saved PALM (CenterRoboLPC): {irregular_path}")

    # Generate new format (RoboLPC)
    palm_new = qupath2palm.qupath2palm_affine_new(
        geojson_path, warp_mat, print_to_screen=False)
    new_path = base_path + '_RoboLPC.txt'
    with open(new_path, 'w') as f:
        f.write(palm_new)
    print(f"Saved PALM (RoboLPC): {new_path}")

    return irregular_path, new_path


def visualize_palm_shapes(viewer, geojson_path, warp_mat, tile_type):
    """
    Save two PNG visualizations of transformed PALM coordinates and add preview layer to viewer.
    - _PALM_preview_parent.png: color-codes shapes by parent tile (glasbey palette)
    - _PALM_preview_order.png: color-codes shapes by output order (viridis — blue=first, yellow=last)
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPolygon

    with open(geojson_path) as f:
        data = json.load(f)
    features = data.get('features', [])

    if not features:
        print("No features to visualize")
        return None

    parent_colors = {}
    color_cycle = cycle(GLASBEY_COLORS)

    patches_parent = []
    patches_order = []
    colors_parent = []
    colors_order = []
    shapes = []
    edge_colors_parent = []
    names = []
    n = len(features)

    for idx, feature in enumerate(features):
        coords = feature['geometry']['coordinates'][0]
        name = feature['properties'].get('name', '')

        coords_np = np.float32(coords)
        transformed = cv2.transform(coords_np[None, :, :], warp_mat)[0]

        # Parent-tile color (glasbey palette)
        if tile_type == "Directly to minitiles":
            parts = name.split('_')
            if len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
                parent = '_'.join(parts[:-1])
            else:
                parent = name
        else:
            parent = name

        if parent not in parent_colors:
            parent_colors[parent] = next(color_cycle)
        c_parent = parent_colors[parent]

        # Output-order color (viridis)
        t = idx / max(n - 1, 1)
        c_order = plt.cm.viridis(t)[:3]

        patches_parent.append(MplPolygon(transformed, closed=True))
        colors_parent.append(c_parent)
        patches_order.append(MplPolygon(transformed, closed=True))
        colors_order.append(c_order)

        shapes.append(transformed)
        edge_colors_parent.append(c_parent)
        names.append(name)

    base_path = geojson_path.rsplit('.', 1)[0]

    # === PNG 1: colored by parent tile ===
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    for patch, color in zip(patches_parent, colors_parent):
        patch.set_edgecolor(color)
        patch.set_facecolor('none')
        patch.set_linewidth(1)
        ax.add_patch(patch)
    ax.autoscale()
    ax.set_aspect('equal')
    ax.set_xlabel('PALM X coordinate')
    ax.set_ylabel('PALM Y coordinate')
    ax.set_title(f'PALM Preview: parent tile — {n} shapes ({len(parent_colors)} parent regions)')
    ax.grid(True, alpha=0.3)
    fig.text(0.5, 0.01, 'Color = parent tile (each tile has a distinct color)', ha='center', fontsize=9, style='italic')
    png_parent = base_path + '_PALM_preview_parent.png'
    plt.savefig(png_parent, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"Saved PALM preview (parent): {png_parent}")

    # === PNG 2: colored by output order ===
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    for patch, color in zip(patches_order, colors_order):
        patch.set_edgecolor(color)
        patch.set_facecolor('none')
        patch.set_linewidth(1)
        ax.add_patch(patch)
    ax.autoscale()
    ax.set_aspect('equal')
    ax.set_xlabel('PALM X coordinate')
    ax.set_ylabel('PALM Y coordinate')
    ax.set_title(f'PALM Preview: output order — {n} shapes')
    ax.grid(True, alpha=0.3)
    sm = plt.cm.ScalarMappable(cmap='viridis', norm=plt.Normalize(vmin=0, vmax=n - 1))
    sm.set_array([])
    plt.colorbar(sm, ax=ax, label='Output index (0 = first in file)')
    fig.text(0.5, 0.01, 'Color = output order: blue (first) → yellow (last in output file)', ha='center', fontsize=9, style='italic')
    png_order = base_path + '_PALM_preview_order.png'
    plt.savefig(png_order, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"Saved PALM preview (order): {png_order}")

    # === Add napari preview layer (parent-tile coloring) ===
    if 'PALM Preview' in viewer.layers:
        viewer.layers.remove('PALM Preview')

    if shapes:
        layer = viewer.add_shapes(
            shapes,
            name='PALM Preview',
            shape_type='polygon',
            edge_color=edge_colors_parent,
            face_color=[0, 0, 0, 0],
            edge_width=2
        )
        layer.annotation_names = names
        print(f"Added PALM Preview layer with {len(shapes)} shapes")

    return png_parent


@magicgui(
    call_button='Apply Warp Matrix',
    warp_type={
        'label': 'Warp Matrix',
        'choices': ['Default', 'Identity', 'Custom (load file)', 'Compute from points'],
        'value': 'Default',
        'tooltip': 'Default: Standard slide-to-PALM transform. Identity: No transform. Custom: Load from file. Compute from points: Calculate from source TSV and PALM destination files.'
    }
)
def select_warp_matrix_gui(warp_type: str = 'Default'):
    """Select warp matrix type for PALM coordinate transformation."""
    global global_warp_matrix, global_last_directory

    if warp_type == 'Default':
        global_warp_matrix = DEFAULT_WARP_MATRIX.copy()
        print(f"Using default warp matrix:\n{global_warp_matrix}")
    elif warp_type == 'Identity':
        global_warp_matrix = IDENTITY_WARP_MATRIX.copy()
        print("Using identity matrix (no transformation)")
    elif warp_type == 'Custom (load file)':
        start_dir = global_last_directory or ''
        file_path, _ = QFileDialog.getOpenFileName(
            None, 'Select Warp Matrix File', start_dir,
            'Numpy Files (*.npy);;Text Files (*.txt);;All Files (*)'
        )
        if file_path:
            global_last_directory = os.path.dirname(file_path)
            try:
                if file_path.endswith('.npy'):
                    global_warp_matrix = np.load(file_path)
                else:
                    global_warp_matrix = np.loadtxt(file_path)

                if global_warp_matrix.shape != (2, 3):
                    print(f"Warning: Expected 2x3 matrix, got {global_warp_matrix.shape}")
                print(f"Loaded custom warp matrix:\n{global_warp_matrix}")
            except Exception as e:
                print(f"Error loading warp matrix: {e}")
                global_warp_matrix = DEFAULT_WARP_MATRIX.copy()
        else:
            print("No file selected, keeping previous matrix")
    elif warp_type == 'Compute from points':
        start_dir = global_last_directory or ''
        src_path, _ = QFileDialog.getOpenFileName(
            None, 'Select Source Points TSV File', start_dir,
            'TSV Files (*.tsv);;Text Files (*.txt);;All Files (*)'
        )
        if not src_path:
            print("No source file selected, keeping previous matrix")
            return
        global_last_directory = os.path.dirname(src_path)

        dst_path, _ = QFileDialog.getOpenFileName(
            None, 'Select PALM Destination Points File', global_last_directory,
            'All Files (*);;Text Files (*.txt)'
        )
        if not dst_path:
            print("No destination file selected, keeping previous matrix")
            return

        try:
            src_pts = parse_source_points_tsv(src_path)
            dst_pts = parse_palm_destination_points(dst_path)
            matrix = compute_affine_from_points(src_pts, dst_pts)

            global_warp_matrix = matrix
            print(f"Source points:\n{src_pts}")
            print(f"Destination points:\n{dst_pts}")
            print(f"Computed warp matrix:\n{matrix}")

            # Auto-save the computed matrix alongside the source file
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            save_dir = os.path.dirname(src_path)
            npy_path = os.path.join(save_dir, f"warp_matrix_{timestamp}.npy")
            txt_path = os.path.join(save_dir, f"warp_matrix_{timestamp}.txt")
            np.save(npy_path, matrix)
            np.savetxt(txt_path, matrix)
            print(f"Saved computed matrix to:\n  {npy_path}\n  {txt_path}")
        except Exception as e:
            print(f"Error computing warp matrix: {e}")
            global_warp_matrix = DEFAULT_WARP_MATRIX.copy()
            print("Falling back to default warp matrix")


# Modified apply_splitting to include scaling_factor and tooltips
@magicgui(call_button='Apply',
          num_tiles={
              'label': 'num tiles', 'min': 0, 'max': 100000,
              'tooltip': 'Maximum number of tiles to output. 0 = unlimited.'
          },
          tile_size={
              'label': 'Tile size (µm)', 'min': 1, 'max': 999000,
              'tooltip': 'Size of each tile in micrometers for Square/Hexagonal tiling.'
          },
          gap_size={
              'label': 'Gap size (µm)', 'min': 0, 'max': 5000,
              'tooltip': 'Space between tiles in micrometers. Prevents overlap during laser capture.'
          },
          num_points={
              'label': 'N tiles (Voronoi / Equal Area)', 'min': 4, 'max': 10000,
              'tooltip': 'Number of seed points for Voronoi tessellation, or target number of tiles for Equal Area mode.'
          },
          max_size={
              'label': 'Max caliper size (µm)', 'min': 1, 'max': 10000,
              'tooltip': 'Polygons larger than this (longest dimension) will be split into tiles.'
          },
          min_area={
              'label': 'Min area filter (µm²)', 'min': 0, 'max': 1000000000,
              'tooltip': 'Tiles smaller than this area are discarded.'
          },
          pixel_size={
              'label': 'Pixel size (µm/px)', 'min': 0.01, 'max': 10.0, 'step': 0.0001, 'value': 0.2627,
              'tooltip': 'Micrometers per pixel. Instrument-specific (default 0.2627 for standard scanner).'
          },
          randomize_objects={
              'label': 'Randomize objects', 'widget_type': 'Checkbox',
              'tooltip': 'Shuffle tile order in output file for unbiased sampling.'
          },
          bias_to_small={
              'label': 'Bias to small', 'widget_type': 'Checkbox',
              'tooltip': 'When randomizing, prioritize tiles from smaller parent regions.'
          },
          keep_names={
              'label': 'Keep original names', 'widget_type': 'Checkbox', 'value': True,
              'tooltip': 'Preserve original annotation names in tile names.'
          },
          tile_type={
              'label': 'Tile type',
              'choices': ['Square', 'Hexagonal', 'Voronoi', 'Equal Area', 'Divide into 4', 'Directly to minitiles'],
              'value': 'Directly to minitiles',
              'tooltip': 'Square: Grid. Hexagonal: Honeycomb. Voronoi: Random tessellation. Equal Area: N roughly equal-area tiles via Lloyd\'s algorithm. Divide into 4: Quadrants. Directly to minitiles: Grid then quadrants.'
          },
          pad_minitiles={
              'label': 'Pad minitiles', 'widget_type': 'Checkbox', 'value': True,
              'tooltip': 'Add tiny placeholder dots to ensure uniform minitile count per tile (for PALM well mapping).'
          },
          equal_area_iterations={
              'label': 'Equal Area iterations', 'min': 1, 'max': 200, 'value': 20,
              'tooltip': 'Number of Lloyd\'s algorithm iterations for Equal Area tiling. More iterations = more uniform areas but slower.'
          })
def apply_splitting(viewer: napari.Viewer, num_tiles: int = 0, tile_size: float = 500.0, gap_size: float = 50.0,
                    num_points: int = 700, max_size: float = 130.0, min_area: float = 50000.0,
                    randomize_objects: bool = False, bias_to_small: bool = False, keep_names: bool = True,
                    tile_type: str = "Directly to minitiles", pixel_size: float = 0.2627, pad_minitiles: bool = True,
                    equal_area_iterations: int = 20):

    global global_scaling_factor, global_extract_level, global_warp_matrix
    scaling_factor = global_scaling_factor

    # Get the Annotations layer directly from viewer (required for tabbed GUI)
    layer = None
    if 'Annotations' in viewer.layers:
        layer = viewer.layers['Annotations']
    if layer is None or not isinstance(layer, napari.layers.Shapes) or not layer.data:
         print("No 'Annotations' shapes layer found or layer is empty. Load annotations first.")
         return

    # Account for pyramid level: effective pixel size = pixel_size * 4^level
    effective_pixel_size = pixel_size * (4 ** global_extract_level)
    print(f"Using effective pixel size: {effective_pixel_size:.4f} µm/px (level {global_extract_level})")

    # Convert micron inputs to pixel values (at extracted resolution)
    tile_size_px = tile_size / effective_pixel_size
    gap_size_px = gap_size / effective_pixel_size
    max_size_px = max_size / effective_pixel_size
    min_area_px = min_area / (effective_pixel_size * effective_pixel_size)  # Area is squared

    # Auto-set max caliper for "Divide into 4" mode
    if tile_type == "Divide into 4" and layer.data:
        min_caliper_px = float('inf')
        for polygon_data in layer.data:
            poly = Polygon(polygon_data)
            if poly.is_valid:
                caliper = calculate_caliper(poly)
                if caliper < min_caliper_px:
                    min_caliper_px = caliper
        if min_caliper_px < float('inf'):
            auto_max_um = (min_caliper_px * effective_pixel_size) * 0.99
            apply_splitting.max_size.value = auto_max_um  # Update UI
            max_size_px = min_caliper_px * 0.99
            print(f"Auto-set max caliper to {auto_max_um:.1f} µm (all objects will be divided)")

    new_shapes = []
    new_shape_names = []
    parent_areas = []  # Store the area of the parent polygon for each tile
    all_stage1_tiles = []  # (tile, tile_name, parent_area) for "Directly to minitiles" — shuffled then split after main loop
    
    # Get original annotation names (if available) or create default ones
    original_names = getattr(layer, 'annotation_names', [f'annotation_{i}' for i in range(len(layer.data))])
    
    # Ensure original_names list length matches data length
    if len(original_names) != len(layer.data):
         print(f"Warning: Mismatch between number of shapes ({len(layer.data)}) and names ({len(original_names)}). Generating default names.")
         original_names = [f'annotation_{i}' for i in range(len(layer.data))]
         
    # Process names if keep_names is false
    processed_names = []
    if not keep_names:
        for name_base in original_names:
             # Attempt to find a base name if it ends with _<digits>
             parts = name_base.split('_')
             if len(parts) > 1 and parts[-1].isdigit():
                 processed_names.append('_'.join(parts[:-1]))
             else:
                 processed_names.append(name_base) # Keep original if no pattern detected
    else:
         processed_names = original_names

    for i, (polygon_data, original_name) in enumerate(zip(layer.data, processed_names)):
         try:
             polygon = Polygon(polygon_data)
             if not polygon.is_valid:
                 print(f"Warning: Invalid geometry for shape {i} ('{original_name}'). Attempting to fix.")
                 polygon = polygon.buffer(0) # Attempt to fix invalid geometry
                 if not polygon.is_valid:
                     print(f"Error: Could not fix invalid geometry for shape {i} ('{original_name}'). Skipping.")
                     continue # Skip this polygon

             parent_area = polygon.area # Area in pixels^2

             # Check polygon caliper (longest dimension) against max_size in pixels
             polygon_caliper = calculate_caliper(polygon)
             if polygon_caliper > max_size_px:
                 split_occurred = False
                 tiles_is_fake = []  # Initialize for all modes; only populated for modes that support padding
                 if tile_type == "Voronoi":
                     tiles, tile_names = split_voronoi(polygon, num_points=num_points, gap_size=gap_size_px, original_name=original_name)
                     tiles_is_fake = [False] * len(tiles)  # No fake tiles for Voronoi
                     split_occurred = True
                 elif tile_type == "Equal Area":
                     tiles, tile_names = split_equal_area(polygon, n=num_points, gap_size=gap_size_px, original_name=original_name, n_iterations=equal_area_iterations)
                     tiles_is_fake = [False] * len(tiles)
                     split_occurred = True
                 elif tile_type == "Divide into 4":
                     tiles, tile_names, tiles_is_fake = divide_into_four(polygon, gap_size_px, min_area_px, original_name, pad_to_expected=pad_minitiles)
                     split_occurred = True
                 elif tile_type == "Square":
                     tiles, tile_names = split_polygon(polygon, tile_size_px, gap_size_px, original_name)
                     tiles_is_fake = [False] * len(tiles)  # No fake tiles for Square
                     split_occurred = True
                 elif tile_type == "Hexagonal":
                     tiles, tile_names = split_hexagonal(polygon, tile_size_px, gap_size_px, original_name)
                     tiles_is_fake = [False] * len(tiles)  # No fake tiles for Hexagonal
                     split_occurred = True
                 elif tile_type == "Directly to minitiles":
                     # Stage 1: collect intermediate tiles; Stage 2 (minitile splitting) runs
                     # after the main loop so tile-level randomization can happen between stages
                     intermediate_tiles, intermediate_names = split_polygon(polygon, tile_size_px, gap_size_px, original_name)
                     for int_tile, int_name in zip(intermediate_tiles, intermediate_names):
                         all_stage1_tiles.append((int_tile, int_name, parent_area))
                     continue  # skip split_occurred handling; Stage 2 appends to new_shapes post-loop

                 if split_occurred and tiles: # Only add if splitting happened and resulted in tiles
                    # Filter by min_area, but always keep fake padding tiles
                    for tile, name, is_fake in zip(tiles, tile_names, tiles_is_fake):
                        if tile.area >= min_area_px or is_fake:
                            new_shapes.append(np.array(tile.exterior.coords))
                            new_shape_names.append(name)
                            parent_areas.append(parent_area)
                 elif not split_occurred: # If no split type matched, keep original if area > min_area
                      if parent_area >= min_area_px:
                          new_shapes.append(np.array(polygon.exterior.coords))
                          new_shape_names.append(original_name)
                          parent_areas.append(parent_area)
                 elif split_occurred and not tiles: # Splitting happened but produced no tiles (e.g., due to min_area filter in divide_into_four)
                      print(f"Note: Splitting '{original_name}' resulted in no tiles meeting criteria.")
                      # Optionally keep original if > min_area? Or discard as per logic? Currently discards.
                      # If you want to keep the original in this case:
                      # if parent_area >= min_area_px:
                      #    new_shapes.append(np.array(polygon.exterior.coords))
                      #    new_shape_names.append(original_name)
                      #    parent_areas.append(parent_area)

             else: # Polygon length is not > max_size_px
                 if parent_area >= min_area_px: # Keep original only if it meets min area criteria
                    new_shapes.append(np.array(polygon.exterior.coords))
                    new_shape_names.append(original_name)
                    parent_areas.append(parent_area)
         except Exception as e:
             print(f"Error processing shape {i} ('{original_name}'): {e}")
             continue # Skip to the next shape

    # "Directly to minitiles" Stage 2: optionally shuffle at tile level, then subdivide into minitiles
    if tile_type == "Directly to minitiles" and all_stage1_tiles:
        if randomize_objects:
            if bias_to_small:
                tile_parent_areas = [pa for _, _, pa in all_stage1_tiles]
                random_weights = [random.random() * (1 / a if a > 0 else 1) for a in tile_parent_areas]
                all_stage1_tiles = [x for _, x in sorted(zip(random_weights, all_stage1_tiles), reverse=True)]
            else:
                random.shuffle(all_stage1_tiles)

        half_gap = gap_size_px / 2
        threshold_px = 500.0 / effective_pixel_size
        max_minitile_px = 300.0 / effective_pixel_size

        if tile_size_px <= threshold_px:
            target_minitile_count = 4
        else:
            target_cols = max(2, int(np.ceil((tile_size_px + half_gap) / (max_minitile_px + half_gap))))
            target_rows = target_cols
            target_minitile_count = target_cols * target_rows

        for s1_tile, s1_name, s1_parent_area in all_stage1_tiles:
            if tile_size_px <= threshold_px:
                mini_tiles, mini_names, mini_is_fake = divide_into_four(s1_tile, half_gap, min_area_px, s1_name, pad_to_expected=False)
            else:
                tb = s1_tile.bounds
                num_cols = max(2, int(np.ceil((tb[2] - tb[0] + half_gap) / (max_minitile_px + half_gap))))
                num_rows = max(2, int(np.ceil((tb[3] - tb[1] + half_gap) / (max_minitile_px + half_gap))))
                mini_tiles, mini_names, mini_is_fake = divide_into_grid(s1_tile, num_cols, num_rows, half_gap, min_area_px, s1_name, pad_to_expected=False)

            if pad_minitiles and 0 < len(mini_tiles) < target_minitile_count:
                num_needed = target_minitile_count - len(mini_tiles)
                reference_part = mini_tiles[0]
                centroid = reference_part.centroid
                fake_minitile = centroid.buffer(1.0)
                digits = get_digits_for_formatting(target_minitile_count)
                current_idx = len(mini_tiles)
                print(f"Padding '{s1_name}': {len(mini_tiles)} -> {target_minitile_count} minitiles (+{num_needed} fake)")
                for _ in range(num_needed):
                    mini_tiles.append(fake_minitile)
                    mini_names.append(f"{s1_name}_{current_idx:0{digits}d}")
                    mini_is_fake.append(True)
                    current_idx += 1

            for mt, mn, mf in zip(mini_tiles, mini_names, mini_is_fake):
                if mt.area >= min_area_px or mf:
                    new_shapes.append(np.array(mt.exterior.coords))
                    new_shape_names.append(mn)
                    parent_areas.append(s1_parent_area)

    if not new_shapes:
         print("No shapes left after processing and filtering. Layer will be empty.")
         layer.data = []
         layer.annotation_names = []
         layer.parent_areas = []
    elif not num_tiles == 0:
         new_shapes = new_shapes[:num_tiles]
         new_shape_names = new_shape_names[:num_tiles]
         layer.data = new_shapes
         layer.annotation_names = new_shape_names  # Store names as a property of the layer
         layer.parent_areas = parent_areas  # Store parent areas as a property of the layer
    else:
         layer.data = new_shapes
         layer.annotation_names = new_shape_names  # Store names as a property of the layer
         layer.parent_areas = parent_areas  # Store parent areas as a property of the layer
    
    # Pass scaling_factor to save functions
    # For "Directly to minitiles", tile-level randomization already happened before Stage 2; don't shuffle again
    effective_randomize = False if tile_type == "Directly to minitiles" else randomize_objects
    geojson_path = save_geojson(new_shapes, new_shape_names, 0, scaling_factor, effective_randomize, bias_to_small, parent_areas) # Min area filter applied above, pass 0 here

    # Save PALM text files and visualization alongside GeoJSON
    if geojson_path:
        warp_mat_to_use = global_warp_matrix if global_warp_matrix is not None else DEFAULT_WARP_MATRIX
        save_palm_text(geojson_path, warp_mat_to_use)
        # Save PALM preview as PNG and add to viewer
        visualize_palm_shapes(viewer, geojson_path, warp_mat_to_use, tile_type)

        # Save settings as JSON in the same folder as GeoJSON
        output_dir = os.path.dirname(geojson_path)
        settings_dict = {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "image": {
                "extract_level": global_extract_level,
                "pixel_size_um": pixel_size,
                "effective_pixel_size_um": effective_pixel_size
            },
            "tiling": {
                "tile_type": tile_type,
                "tile_size_um": tile_size,
                "gap_size_um": gap_size,
                "num_points": num_points
            },
            "filtering": {
                "max_caliper_um": max_size,
                "min_area_um2": min_area,
                "num_tiles_limit": num_tiles
            },
            "output": {
                "randomize_objects": randomize_objects,
                "bias_to_small": bias_to_small,
                "keep_names": keep_names,
                "scaling_factor": scaling_factor,
                "pad_minitiles": pad_minitiles
            }
        }
        save_settings(settings_dict, output_dir)
    update_object_count(layer)
    # Force redraw/refresh
    layer.refresh()
    print(f"Processing complete. {len(new_shapes)} shapes remaining.")

# Allow user to delete selected objects and keep count of total objects
def update_object_count(layer):
    global global_count_label
    if global_count_label is not None and layer is not None:
        global_count_label.setText(f"Total objects: {len(layer.data)}")

def on_key_press(event, layer):
    if layer is None:
        return
        
    if event.key == 'Delete' and hasattr(layer, 'selected_data') and layer.selected_data:
        # Create a new list of shapes and names without the selected ones
        new_data = []
        new_names = []
        # Get names, ensuring list exists and has correct length
        current_names = getattr(layer, 'annotation_names', [f'annotation_{i}' for i in range(len(layer.data))])
        if len(current_names) != len(layer.data):
             current_names = [f'annotation_{i}' for i in range(len(layer.data))] # Regenerate if mismatch

        indices_to_keep = set(range(len(layer.data))) - layer.selected_data

        new_data = [layer.data[i] for i in indices_to_keep]
        new_names = [current_names[i] for i in indices_to_keep]
            
        layer.data = new_data
        # Update annotation names stored in the layer object if the attribute exists
        if hasattr(layer, 'annotation_names'):
            layer.annotation_names = new_names
        # Also update parent areas if they exist
        if hasattr(layer, 'parent_areas'):
            current_parent_areas = layer.parent_areas
            if len(current_parent_areas) == len(current_names): # Check if parent_areas was consistent
                 layer.parent_areas = [current_parent_areas[i] for i in indices_to_keep]
            else:
                 layer.parent_areas = [0]*len(new_data) # Reset if inconsistent

        layer.selected_data = set()  # Clear selected data
        update_object_count(layer)
        layer.refresh() # Force redraw


# Convert SVS to TIFF
def convert_svs_to_tiff(input_path, output_path, level=0):
    print(f"Converting SVS '{input_path}' level {level} to TIFF '{output_path}'...")
    try:
        slide = openslide.OpenSlide(input_path)
        # Ensure requested level exists
        if level >= slide.level_count:
             print(f"Warning: Level {level} not available. Using level 0.")
             level = 0
        dims = slide.level_dimensions[level]
        print(f"Reading region (0,0) at level {level} with dimensions {dims}...")
        # Read region and convert to RGB numpy array
        image_pil = slide.read_region((0, 0), level, dims).convert('RGB')
        image_np = np.array(image_pil)
        print(f"Saving TIFF image...")
        imwrite(output_path, image_np, imagej=True) # Use imagej=True for better compatibility maybe?
        scale_factor = slide.level_downsamples[level]
        slide.close()
        print("Conversion complete.")
        return scale_factor, output_path # Return scale and path
    except openslide.OpenSlideError as e:
        print(f"Error opening SVS file: {e}")
        return None, None
    except Exception as e:
        print(f"An error occurred during conversion: {e}")
        return None, None


@magicgui(call_button='Load Image',
    multiscale={
        'label': 'Load as pyramidal', 'widget_type': 'Checkbox',
        'tooltip': 'Load image with multiple resolution levels for faster navigation.'
    },
    level={
        'label': 'Extract level', 'min': 0, 'max': 16, 'step': 1, 'value': 2,
        'tooltip': 'SVS pyramid level to extract (0=full resolution, higher=smaller). Each level is 4x smaller.'
    })
def load_image_gui(viewer: napari.Viewer, multiscale: bool = False, level: int = 2):
    global global_scaling_factor, global_extract_level, global_last_directory

    start_dir = global_last_directory or os.path.expanduser("~")
    file_path, _ = QFileDialog.getOpenFileName(None, 'Select Image', start_dir, 'Images (*.svs *.tiff *.tif)')
    
    image_to_load = None
    scale_factor = global_scaling_factor # Default scale
    loaded_path = None

    if file_path:
        global_last_directory = os.path.dirname(file_path)
        file_path_lower = file_path.lower()
        if file_path_lower.endswith('.svs'):
            tiff_path = file_path.rsplit('.', 1)[0] + f'_level{level}.tiff' # Indicate level in filename
            if not os.path.exists(tiff_path):
                 scale_factor, loaded_path = convert_svs_to_tiff(file_path, tiff_path, level=level)
                 if loaded_path is None: return # Conversion failed
            else:
                 print(f"Using existing TIFF: {tiff_path}")
                 # Try to read scale factor from SVS even if TIFF exists
                 try:
                      slide = openslide.OpenSlide(file_path)
                      if 0 < slide.level_count:
                           scale_factor = slide.level_downsamples[0]
                      slide.close()
                 except Exception as e:
                      print(f"Could not read scale factor from SVS file {file_path}: {e}. Assuming scale factor 1.")
                      scale_factor = 1
                 loaded_path = tiff_path

            # Load the (potentially newly created) TIFF
            if loaded_path and os.path.exists(loaded_path):
                 try:
                     image_to_load = imread(loaded_path)
                 except Exception as e:
                     print(f"Error reading TIFF file {loaded_path}: {e}")
                     return
            else:
                 print(f"Error: TIFF file {loaded_path} not found after conversion attempt.")
                 return

        elif file_path_lower.endswith(('.tiff', '.tif')):
            try:
                image_to_load = imread(file_path)
                loaded_path = file_path
                # For TIFFs, we don't know the original SVS scale factor unless stored in metadata (not handled here)
                scale_factor = 1 # Assume base resolution for TIFFs
            except Exception as e:
                print(f"Error reading TIFF file {file_path}: {e}")
                return
        else:
            print("Unsupported file format selected.")
            return

        if image_to_load is not None:
            # Clear existing image layers before adding new one
            for layer in list(viewer.layers):
                 if isinstance(layer, napari.layers.Image):
                      viewer.layers.remove(layer)
                      
            layer_name = os.path.basename(loaded_path)
            if multiscale:
                # Simple multiscale by downsampling (adjust factors as needed)
                data = [image_to_load]
                factors = [2, 4, 8, 16] # Example downscaling factors
                for factor in factors:
                     try: # Handle potential issues with dimensions not divisible by factor
                          downsampled = image_to_load[::factor, ::factor]
                          if downsampled.size > 0: # Check if downsampling resulted in empty image
                               data.append(downsampled)
                          else: break # Stop if image becomes too small
                     except IndexError: # Catch potential errors if factor is too large
                          break
                print(f"Adding multiscale image with {len(data)} levels.")
                viewer.add_image(data, name=layer_name, metadata={'scale': scale_factor, 'path': loaded_path}, rgb=True)
            else:
                print("Adding single-scale image.")
                viewer.add_image(image_to_load, name=layer_name, metadata={'scale': scale_factor, 'path': loaded_path}, rgb=True)
            
            # Reset view after loading new image
            viewer.reset_view()

            # Store level and auto-set GeoJSON scaling factor = 4^level
            global_extract_level = level
            auto_scaling = 4 ** level
            load_geojson_gui.scaling_factor.value = auto_scaling
            print(f"Auto-set GeoJSON scaling factor to {auto_scaling} (4^{level})")
        else:
             print("Failed to load image.")


def make_names_unique(names):
    """Return a list of unique names by appending an index to duplicates."""
    name_counts = {}
    unique_names = []
    
    for name in names:
        if name not in name_counts:
            name_counts[name] = 0 # Start count at 0 for the first instance
            unique_names.append(name)
        else:
            name_counts[name] += 1
            unique_name = f"{name}_{name_counts[name]}"
            # Ensure the newly generated name is also unique
            while unique_name in name_counts:
                 name_counts[name] += 1
                 unique_name = f"{name}_{name_counts[name]}"
            unique_names.append(unique_name)
            # Add the new unique name to counts to prevent future collisions
            name_counts[unique_name] = 0 
            
    return unique_names

# Modified load_geojson_gui to include scaling_factor
@magicgui(call_button='Load Annotations',
          scaling_factor={
              'label': 'GeoJSON Scaling Factor', 'min': 1, 'max': 256, 'step': 1, 'value': 1,
              'tooltip': 'Factor to divide GeoJSON coordinates by (auto-set to 4^level when loading SVS).'
          })
def load_geojson_gui(viewer: napari.Viewer, scaling_factor: int = 1): # Added scaling_factor parameter
    global global_scaling_factor, global_last_directory
    global_scaling_factor = scaling_factor

    start_dir = global_last_directory or os.path.expanduser("~")
    file_path, _ = QFileDialog.getOpenFileName(None, 'Select GeoJSON Annotations', start_dir, 'GeoJSON Files (*.geojson)')
    
    # Find the image layer to get metadata (path primarily)
    image_layer = None
    for layer in viewer.layers:
         if isinstance(layer, napari.layers.Image):
              image_layer = layer
              break # Use the first image layer found

    if file_path:
        global_last_directory = os.path.dirname(file_path)
        # Use the provided scaling_factor
        effective_scale = scaling_factor if scaling_factor > 0 else 1
        print(f"Loading GeoJSON with scaling factor: {effective_scale}")
        try:
             annotations, annotation_names = load_geojson(file_path, effective_scale)
             annotation_names = make_names_unique(annotation_names) # Ensure names are unique upon loading
        except Exception as e:
             print(f"Error loading or processing GeoJSON file {file_path}: {e}")
             return # Stop if loading fails

        # Remove any existing annotation layer
        if 'Annotations' in viewer.layers:
            viewer.layers.remove('Annotations')
        
        if not annotations:
             print("No valid annotations found or loaded from GeoJSON.")
             update_object_count(None) # Update count to 0
             return # Don't add layer if no annotations

        # Add the new annotation layer
        try:
             annotation_layer = viewer.add_shapes(
                 [np.array(poly.exterior.coords) for poly in annotations],
                 name='Annotations',
                 shape_type='polygon',
                 blending='additive', # Changed blending for better visibility
                 edge_color='cyan',    # Changed color
                 face_color=[0, 0, 0, 0], # Keep transparent faces
                 edge_width= 3 # Adjusted edge width
             )
             
             # Store the annotation names and potentially parent areas (initially None)
             annotation_layer.annotation_names = annotation_names
             annotation_layer.parent_areas = [0] * len(annotations) # Initialize parent areas

             # --- Connect selection and highlight events ---
             # Use a wrapper to handle potential errors in callbacks
             def safe_update_area(event):
                 try:
                     update_selected_area(annotation_layer)
                 except Exception as e:
                     print(f"Error in update_selected_area callback: {e}")

             # Connect highlight event (fired when hovering or selecting)
             annotation_layer.events.highlight.connect(safe_update_area)
             
             # Connect selection event (specifically for selection changes)
             # This seems redundant if highlight covers it, but can be useful
             # annotation_layer.events.selected_data.connect(safe_update_area) # Connect to selected_data changes

             # Connect data change event to update count
             def safe_update_count(event):
                  try:
                      update_object_count(annotation_layer)
                  except Exception as e:
                      print(f"Error in update_object_count callback: {e}")

             annotation_layer.events.data.connect(safe_update_count) # Update count when data changes (e.g., deletion)


             # --- Initial UI Update ---
             update_object_count(annotation_layer)
             update_selected_area(annotation_layer) # Update area display (should show None initially)

             print(f"Loaded {len(annotations)} annotations.")

        except Exception as e:
             print(f"Error adding shapes layer: {e}")

    else:
        print("No GeoJSON file selected.")


@magicgui(call_button='Load Settings')
def load_settings_gui():
    """Load settings from a previous session's JSON file."""
    global global_last_directory

    start_dir = global_last_directory or os.path.expanduser("~")
    file_path, _ = QFileDialog.getOpenFileName(
        None, 'Select Settings File', start_dir,
        'JSON Files (*.json);;All Files (*)'
    )

    if file_path:
        global_last_directory = os.path.dirname(file_path)
        settings = load_settings(file_path)

        if settings:
            # Apply settings to GUI widgets
            if 'image' in settings:
                img = settings['image']
                if 'extract_level' in img:
                    load_image_gui.level.value = img['extract_level']
                if 'pixel_size_um' in img:
                    apply_splitting.pixel_size.value = img['pixel_size_um']

            if 'tiling' in settings:
                tile = settings['tiling']
                if 'tile_type' in tile:
                    apply_splitting.tile_type.value = tile['tile_type']
                if 'tile_size_um' in tile:
                    apply_splitting.tile_size.value = tile['tile_size_um']
                if 'gap_size_um' in tile:
                    apply_splitting.gap_size.value = tile['gap_size_um']
                if 'num_points' in tile:
                    apply_splitting.num_points.value = tile['num_points']

            if 'filtering' in settings:
                filt = settings['filtering']
                if 'max_caliper_um' in filt:
                    apply_splitting.max_size.value = filt['max_caliper_um']
                if 'min_area_um2' in filt:
                    apply_splitting.min_area.value = filt['min_area_um2']
                if 'num_tiles_limit' in filt:
                    apply_splitting.num_tiles.value = filt['num_tiles_limit']

            if 'output' in settings:
                out = settings['output']
                if 'randomize_objects' in out:
                    apply_splitting.randomize_objects.value = out['randomize_objects']
                if 'bias_to_small' in out:
                    apply_splitting.bias_to_small.value = out['bias_to_small']
                if 'keep_names' in out:
                    apply_splitting.keep_names.value = out['keep_names']
                if 'scaling_factor' in out:
                    load_geojson_gui.scaling_factor.value = out['scaling_factor']
                if 'pad_minitiles' in out:
                    apply_splitting.pad_minitiles.value = out['pad_minitiles']

            print("Settings applied to GUI")


# Set up layer selection event handler to update count when layer changes
def on_layer_change(event, viewer):
    # Get the currently active layer from the selection model
    active_layer = viewer.layers.selection.active
    if active_layer is not None and active_layer.name == 'Annotations' and isinstance(active_layer, napari.layers.Shapes):
         # It's crucial that the active layer IS the annotation layer we care about
         try:
              # Update both count and selected area when the annotation layer becomes active
              update_object_count(active_layer)
              update_selected_area(active_layer)

              # Ensure the key binding is connected to the *currently active* annotation layer
              # Disconnect previous bindings if necessary to avoid duplicates? Careful with lambda context.
              # A simpler approach might be to always try connecting, Napari might handle duplicates.
              viewer.bind_key('Delete', lambda event: on_key_press(event, active_layer), overwrite=True) # Overwrite ensures only one binding

         except Exception as e:
              print(f"Error during layer change update for Annotations: {e}")
    else:
         # If a different layer is selected, potentially clear the labels or leave them as is
         global global_count_label, global_area_label
         if global_count_label: global_count_label.setText("Total objects: (select Annotations layer)")
         if global_area_label: global_area_label.setText("Selected area: (select Annotations layer)")
         # Optionally unbind delete key if no annotation layer is active
         # viewer.bind_key('Delete', None, overwrite=True) # Unbind Delete key


# Main Viewer
def main():
    global global_count_label, global_area_label, global_scaling_factor, global_extract_level
    
    viewer = napari.Viewer()

    # Create widget for displaying count and area labels
    info_widget = QWidget()
    info_layout = QVBoxLayout()
    global_count_label = QLabel("Total objects: 0")
    global_area_label = QLabel("Selected area: None")
    info_layout.addWidget(global_count_label)
    info_layout.addWidget(global_area_label)
    info_widget.setLayout(info_layout)
    viewer.window.add_dock_widget(info_widget, area='bottom', name='Info')

    # Connect layer selection change event
    # This lambda now correctly captures the viewer instance at definition time
    viewer.layers.selection.events.active.connect(lambda event: on_layer_change(event, viewer))

    # Create tabbed widget container
    tabs = QTabWidget()

    # Tab 1: Load (combine load widgets vertically)
    load_tab = QWidget()
    load_layout = QVBoxLayout()
    load_layout.addWidget(load_image_gui.native)
    load_layout.addWidget(load_geojson_gui.native)
    load_layout.addWidget(load_settings_gui.native)
    load_layout.addStretch()  # Push widgets to top
    load_tab.setLayout(load_layout)

    # Tab 2: Affine (warp matrix)
    affine_tab = QWidget()
    affine_layout = QVBoxLayout()
    affine_layout.addWidget(select_warp_matrix_gui.native)
    affine_layout.addStretch()
    affine_tab.setLayout(affine_layout)

    # Tab 3: Splitting
    split_tab = QWidget()
    split_layout = QVBoxLayout()
    split_layout.addWidget(apply_splitting.native)
    split_layout.addStretch()
    split_tab.setLayout(split_layout)

    # Add tabs
    tabs.addTab(load_tab, "Load")
    tabs.addTab(affine_tab, "Affine")
    tabs.addTab(split_tab, "Splitting")

    # Add single tabbed dock widget
    viewer.window.add_dock_widget(tabs, name='Controls')
    
    # Initial key binding setup (will be updated by on_layer_change)
    # Bind delete initially to a function that does nothing or checks for the layer
    def check_and_delete(event):
        active_layer = viewer.layers.selection.active
        if active_layer and active_layer.name == 'Annotations':
             on_key_press(event, active_layer)

    viewer.bind_key('Delete', check_and_delete, overwrite=True)

    napari.run()

if __name__ == '__main__':
    # Set multiprocessing start method for compatibility if needed (e.g., on Windows)
    # import multiprocessing
    # try:
    #      multiprocessing.set_start_method('spawn')
    # except RuntimeError:
    #      pass # Already set or not applicable
    main()