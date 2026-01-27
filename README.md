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

### Prerequisites

**System Dependencies** (OpenSlide library):

```bash
# Ubuntu/Debian
sudo apt-get install openslide-tools

# macOS
brew install openslide

# Windows
# Download from https://openslide.org/download/
```

### Install from PyPI (when published)

```bash
pip install ARMS-tiler
```

### Install from source

```bash
# Clone the repository
git clone https://github.com/yourusername/ARMS-tiler.git
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

### Command Line

After installation, run the application from anywhere:

```bash
ARMS-tiler
```

### Python

```python
from ARMS_tiler import main
main()
```

### Direct Script Execution

```bash
cd src/ARMS_tiler
python app.py
```

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
https://github.com/yourusername/ARMS-tiler
```
