# ARMS Tiler

An interactive napari-based desktop application for preprocessing tissue annotations for laser capture microdissection (LCM). The tool divides large tissue region annotations into smaller, manageable tiles suitable for LCM workflows.

## Features

- **Image Loading**: Supports SVS (Aperio) and TIFF whole slide image formats
- **Annotation Loading**: Imports GeoJSON annotations from QuPath or other tools
- **Multiple Tiling Methods**:
  - Square grid tiling
  - Hexagonal (honeycomb) tiling
  - Voronoi tessellation
  - Quadrant division (divide into 4)
  - Dynamic minitile division
- **PALM Export**: Generates coordinate files for PALM laser microdissection systems
- **Settings Management**: Save and load session settings for reproducibility

## Installation

### Install from PyPI (when published)

```bash
pip install ARMS-tiler
```

### Install from source

```bash
# Clone the repository
git clone https://github.com/sraorao/ARMS-tiler.git
cd ARMS-tiler

# Install in development mode
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### Install from requirements.txt

```bash
pip install -r requirements.txt
```

## Usage

### Command Line (after `pip install -e .`)

```bash
ARMS-tiler
```

### As a Python Module

```bash
# From the repository root:
python -m ARMS_tiler

# Or from the src directory:
cd src && python -m ARMS_tiler
```

### From Python

```python
from ARMS_tiler import main
main()
```

**Note**: Do not run `python app.py` directly - it will fail due to relative imports. Use one of the methods above.

## Workflow

The application follows a three-stage workflow:

### 1. Load Image
- Open SVS or TIFF whole slide images
- SVS files are converted to TIFF at the specified pyramid level
- Converted TIFFs are cached for faster subsequent loads

### 2. Load Annotations
- Import GeoJSON FeatureCollections with Polygon/MultiPolygon geometries
- Coordinates are automatically scaled based on the image's scale factor

### 3. Apply Splitting
- Filter annotations by maximum caliper size
- Split oversized annotations using the selected tiling method
- Filter output tiles by minimum area threshold
- Save results as GeoJSON + JSON settings file
- Export PALM coordinate files

## Tiling Methods

| Method | Description |
|--------|-------------|
| **Square** | Regular grid tiling with configurable gap spacing |
| **Hexagonal** | Honeycomb pattern for more efficient packing |
| **Voronoi** | Random tessellation from seed points |
| **Divide into 4** | Quadrant division for technical replicates |
| **Directly to minitiles** | Dynamic grid division based on tile size |

### Dynamic Minitile Division

- For tile sizes ≤ 500µm: divides into 2x2 quadrants (4 minitiles)
- For tile sizes > 500µm: dynamically calculates grid so no minitile exceeds 300µm

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| Tile size | Size of each tile in micrometers | 500 µm |
| Gap size | Space between tiles | 50 µm |
| Max caliper | Polygons larger than this are split | 130 µm |
| Min area | Tiles smaller than this are discarded | 50,000 µm² |
| Pixel size | Micrometers per pixel (instrument-specific) | 0.2627 µm/px |

## Keyboard Shortcuts

- `Delete`: Remove selected shapes from the Annotations layer

## Output Files

- **GeoJSON**: Tiled annotations with coordinates
- **Settings JSON**: All parameters used for the session
- **PALM files**: CenterRoboLPC.txt and RoboLPC.txt for PALM systems
- **Preview PNG**: Visualization of transformed PALM coordinates

## Settings JSON Structure

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

## Common Pixel Sizes by Objective

| Objective | Typical pixel size |
|-----------|-------------------|
| 10× | ~1.0 µm/px |
| 20× | ~0.5 µm/px |
| 40× | ~0.25 µm/px |
| 60× | ~0.17 µm/px |

## Troubleshooting

### Qt platform plugin error on Linux

If you see errors like:

```
Could not load the Qt platform plugin "xcb" even though it was found.
```
or:
```
This application failed to start because no Qt platform plugin could be initialized.
```

This is usually caused by `opencv-python` bundling its own Qt libraries which conflict with napari's Qt. Try these fixes in order:

1. **Replace `opencv-python` with `opencv-python-headless`** (most common fix):
   ```bash
   pip uninstall opencv-python && pip install opencv-python-headless
   ```

2. **Install missing system XCB libraries**:
   ```bash
   sudo apt install libxcb-xinerama0 libxcb-cursor0
   ```

3. **Force Qt to use the system XCB plugin** (if the above don't help):
   ```bash
   export QT_QPA_PLATFORM_PLUGIN_PATH=/usr/lib/x86_64-linux-gnu/qt5/plugins/platforms
   ```

You can run `QT_DEBUG_PLUGINS=1 ARMS-tiler` to get detailed diagnostics if the issue persists.

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/
isort src/
flake8 src/
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Citation

If you use this tool in your research, please cite:

```
ARMS Tiler
https://github.com/sraorao/ARMS-tiler
```
