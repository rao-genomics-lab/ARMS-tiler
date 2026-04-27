# Changelog

## [Unreleased]

### Added
- New 'Equal Area' tiling strategy using Monte Carlo Lloyd's algorithm to divide annotations into N roughly equal-area tiles; N is controlled by the existing 'N tiles (Voronoi / Equal Area)' parameter
- PALM preview now saves two PNG files: `_PALM_preview_parent.png` (colors by parent tile, glasbey palette) and `_PALM_preview_order.png` (colors by output index, viridis — blue=first, yellow=last); each image includes a legend note

### Fixed
- In 'Directly to minitiles' mode with 'Randomize objects' enabled, randomization now happens at the **tile** level (between Stage 1 square tiling and Stage 2 minitile subdivision), keeping all minitiles from the same parent tile consecutive in the output file; previously all minitiles were shuffled globally

### Changed
- Add `openslide-bin` as a pip dependency, eliminating the need for system-level OpenSlide installation (`apt install openslide-tools` / `brew install openslide`)
- Increase maximum tile size from 10,000 µm to 999,000 µm
- Rename 'Voronoi points' GUI parameter to 'N tiles (Voronoi / Equal Area)' to reflect dual use
