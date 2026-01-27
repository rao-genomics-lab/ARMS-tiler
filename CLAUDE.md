# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ARMS Napari Tiling Application - an interactive napari-based desktop application for preprocessing tissue annotations for laser capture microdissection (LCM). The tool divides large tissue region annotations into smaller, manageable tiles suitable for LCM workflows.

**Primary use case**: Taking whole slide images (WSIs) with annotated regions and splitting oversized annotations into regular or irregular tile patterns for precise specimen collection.

## Running the Application

```bash
# Install dependencies
pip install napari[all] openslide-python tifffile scikit-image shapely geojson scipy magicgui qtpy opencv-python matplotlib

# System dependency
# Ubuntu/Debian:
sudo apt-get install openslide-tools
# macOS:
brew install openslide
# Windows: Download from openslide.org

# Run the application (use the most recent dated version)
python arms_rao_gemini_20260124.py
```

No build step required - this is a standalone Python GUI application.

**Keyboard shortcuts**: `Delete` key removes selected shapes from the Annotations layer.

## Architecture

The application follows a three-stage workflow:

### Stage 1: Image Loading (`load_image_gui`)
- Supports SVS (Aperio) and TIFF formats
- Converts SVS to TIFF at specified pyramid level (0-16)
- Caches converted TIFFs for faster subsequent loads
- Stores scale factor for coordinate transformation
- Remembers last used directory during session

### Stage 2: Annotation Loading (`load_geojson_gui`)
- Loads GeoJSON FeatureCollections with Polygon/MultiPolygon geometries
- Auto-scales annotations based on image's scale factor
- Flips coordinates from GeoJSON (x,y) to napari (y,x) format
- Remembers last used directory during session

### Stage 3: Annotation Splitting (`apply_splitting`)
- Filters annotations by maximum caliper size
- Splits oversized annotations using selected tiling method
- Filters output tiles by minimum area threshold
- Saves results as GeoJSON + JSON settings file (in same output folder)

### Settings Management (`load_settings_gui`)
- Load previous session settings from JSON file
- Automatically populates all GUI parameters
- Remembers last used directory during session

## Key Tiling Algorithms

| Function | Description |
|----------|-------------|
| `split_polygon()` | Square grid tiling with gap spacing |
| `split_hexagonal()` | Honeycomb pattern, more efficient packing |
| `split_voronoi()` | Voronoi tessellation from random seed points |
| `divide_into_four()` | Quadrant division for technical replicates |
| `divide_into_grid()` | NxM grid division for dynamic minitile sizing |

### Dynamic Minitile Division ("Directly to minitiles" mode)
- For tile sizes <= 500µm: divides into 2x2 quadrants (4 minitiles)
- For tile sizes > 500µm: dynamically calculates grid dimensions so no minitile exceeds 300µm
- Uses formula: `N = ceil((tile_size + gap) / (300µm + gap))` for each dimension

## Critical Implementation Details

### Coordinate Systems
- **User Input**: Micrometers (µm)
- **Internal Processing**: Pixels
- **GeoJSON Output**: Pixels × rescale_factor
- **GeoJSON uses (x,y), napari uses (y,x)** - consistently handled during load/save

### Polygon Validation
Uses `polygon.buffer(0)` to repair invalid geometries. Always check `is_valid` and `is_empty` before processing.

### Scale Factor Management
The app tracks image downsample factors. Annotations must be scaled accordingly:
- Division during load
- Multiplication during output

### Unit Conversion
```python
pixels = micrometers / pixel_size
```
Pixel size (µm/px) is critical and instrument-specific (default: 0.2627).

Common pixel sizes by objective:
| Objective | Typical pixel size |
|-----------|-------------------|
| 10× | ~1.0 µm/px |
| 20× | ~0.5 µm/px |
| 40× | ~0.25 µm/px |
| 60× | ~0.17 µm/px |

### PALM Export
The application exports coordinates for PALM laser microdissection systems via `qupath2palm.py`:
- **Warp Matrix Options**: Default (standard slide-to-PALM transform), Identity (no transform), or Custom (load from .npy/.txt file)
- **Output formats**: CenterRoboLPC.txt (irregular), RoboLPC.txt (new format)
- **Preview**: PNG visualization with color-coded parent regions

### Directory Memory
Global variable `global_last_directory` tracks the last used folder across all file dialogs during a session, improving workflow efficiency.

## File Versions

- `arms_rao_gemini_20260124.py` - **Current version**. Dynamic minitile division, JSON settings, PALM export with warp matrices.
- `qupath2palm.py` - Required dependency for PALM coordinate transformation (provides `qupath2palm_affine_irregular` and `qupath2palm_affine_new` functions).
- Earlier versions (`20250406`, `20250410`, `20250425`) - Legacy, kept for reference.

## Input/Output

**Inputs**: SVS/TIFF images + GeoJSON annotations
**Outputs**:
- GeoJSON tiles
- JSON settings file (`settings_YYYY-MM-DD_HH-MM-SS.json`) - saved in same folder as GeoJSON
- PALM coordinate files (CenterRoboLPC.txt, RoboLPC.txt)
- PALM preview PNG

### Settings JSON Structure
```json
{
  "version": "1.0",
  "timestamp": "2026-01-24T10:30:00",
  "image": {
    "extract_level": 2,
    "pixel_size_um": 0.2627,
    "effective_pixel_size_um": 4.2032
  },
  "tiling": {
    "tile_type": "Directly to minitiles",
    "tile_size_um": 500.0,
    "gap_size_um": 50.0,
    "num_points": 700
  },
  "filtering": {
    "max_caliper_um": 130.0,
    "min_area_um2": 50000.0,
    "num_tiles_limit": 0
  },
  "output": {
    "randomize_objects": false,
    "bias_to_small": false,
    "keep_names": true,
    "scaling_factor": 16
  }
}
```

## GUI Pattern

Uses magicgui decorators to auto-generate Qt widgets from Python function signatures:
```python
@magicgui(param={"widget_type": "Slider", "min": 0, "max": 100})
def my_function(param: int = 50):
    pass
```

Key global state variables:
- `global_scaling_factor` - GeoJSON coordinate scaling (auto-set to 4^level)
- `global_extract_level` - SVS pyramid level (affects effective pixel size)
- `global_warp_matrix` - PALM coordinate transformation matrix (2x3)
- `global_last_directory` - persists across file dialogs within session
