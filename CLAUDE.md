# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ARMS Napari Tiling Application - an interactive napari-based desktop application for preprocessing tissue annotations for laser capture microdissection (LCM). Divides large tissue region annotations into smaller tiles suitable for LCM workflows.

## Running the Application

```bash
# Install in development mode (preferred)
pip install -e .

# Or with dev dependencies (black, isort, flake8, pytest)
pip install -e ".[dev]"

# System dependency required: openslide-tools (apt), openslide (brew), or openslide.org (Windows)

# Run via entry point
ARMS-tiler

# Or as a module
python -m ARMS_tiler
```

**Do not run `python src/ARMS_tiler/app.py` directly** - it will fail due to relative imports.

**Note**: `requirements.txt` uses `opencv-python-headless` (preferred for headless/CI); `pyproject.toml` uses `opencv-python`. Use headless variant when not needing GUI from opencv.

## Code Formatting

Configured in `pyproject.toml`:
```bash
black src/        # line-length=120, target py39-py312
isort src/        # profile=black, line_length=120
flake8 src/
```

## Testing

```bash
pytest tests/     # No tests exist yet; test directory needs to be created
```

## Project Structure

The codebase has two parallel structures:

- **`src/ARMS_tiler/`** - Installable Python package (current, canonical code)
  - `app.py` - Main application (all GUI, algorithms, and logic in one file)
  - `qupath2palm.py` - PALM coordinate transformation functions
  - `__main__.py` / `__init__.py` - Module entry points
- **`arms_rao_gemini_*.py`** - Legacy standalone scripts (gitignored, kept for reference only)
- **`qupath2palm.py`** (root) - Standalone copy of PALM export module

All new development should target `src/ARMS_tiler/app.py`.

## Architecture

Single-file application (`app.py`) with a three-stage workflow controlled via magicgui-decorated functions organized in a tabbed Qt GUI:

1. **Load Image** (`load_image_gui`) - SVS/TIFF loading, SVS-to-TIFF conversion with pyramid level selection, TIFF caching
2. **Load Annotations** (`load_geojson_gui`) - GeoJSON import with coordinate scaling and (x,y)-to-(y,x) flip
3. **Apply Splitting** (`apply_splitting`) - Annotation filtering, tiling, GeoJSON + settings JSON output

Additional features: **Settings Management** (`load_settings_gui`) for reloading previous parameters, and **PALM Export** via `qupath2palm.py`.

### Key Tiling Algorithms

| Function | Description |
|----------|-------------|
| `split_polygon()` | Square grid tiling with gap spacing |
| `split_hexagonal()` | Honeycomb pattern |
| `split_voronoi()` | Voronoi tessellation from random seed points |
| `divide_into_four()` | Quadrant division |
| `divide_into_grid()` | NxM grid division for dynamic minitile sizing |

**Dynamic minitile mode** ("Directly to minitiles"): tiles <= 500um get 2x2 quadrants (4 minitiles); larger tiles get NxM grid where `N = ceil((tile_size + gap) / (300um + gap))`.

### GUI Pattern

```python
@magicgui(param={"widget_type": "Slider", "min": 0, "max": 100})
def my_function(param: int = 50):
    pass
```

## Critical Implementation Details

### Coordinate Systems
- **User Input**: Micrometers (um)
- **Internal Processing**: Pixels (`pixels = micrometers / pixel_size`)
- **GeoJSON Output**: Pixels x rescale_factor
- **GeoJSON uses (x,y), napari uses (y,x)** - conversion on load and save

### Key Global State
- `global_scaling_factor` - GeoJSON coordinate scaling (auto-set to 4^level)
- `global_extract_level` - SVS pyramid level (affects effective pixel size)
- `global_warp_matrix` - PALM coordinate transformation matrix (2x3)
- `global_last_directory` - persists across file dialogs within session

### Polygon Validation
Uses `polygon.buffer(0)` to repair invalid geometries. Always check `is_valid` and `is_empty` before processing.

### Scale Factor Management
Annotations scaled by division during load, multiplication during output. Default pixel size: 0.2627 um/px (40x objective).

Common pixel sizes by objective:
| Objective | Typical pixel size |
|-----------|-------------------|
| 10x | ~1.0 um/px |
| 20x | ~0.5 um/px |
| 40x | ~0.25 um/px |
| 60x | ~0.17 um/px |

### PALM Export
Exports via `qupath2palm.py` with warp matrix options (Default/Identity/Custom/Compute from points). Output formats: CenterRoboLPC.txt, RoboLPC.txt, preview PNG.

**Compute from points**: Calculates the affine warp matrix from two calibration files:
- **Source points TSV**: Tab-separated file with `x\ty` header and 3 rows of slide coordinates
- **PALM destination file**: Element file where coordinates appear on lines starting with `.\t` (format: `.\t97817.1,54024.0`)
- Computes the 2x3 affine matrix via `cv2.getAffineTransform` and auto-saves it as `.npy` and `.txt` alongside the source file

## Input/Output

**Inputs**: SVS/TIFF images + GeoJSON annotations (from QuPath or similar)
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

**Keyboard shortcuts**: `Delete` key removes selected shapes from the Annotations layer.
