# Changelog

## [Unreleased]

### Added
- New 'Equal Area' tiling strategy using Lloyd's algorithm (centroidal Voronoi tessellation) to divide annotations into N roughly equal-area tiles; N is controlled by the existing 'N tiles (Voronoi / Equal Area)' parameter

### Changed
- Add `openslide-bin` as a pip dependency, eliminating the need for system-level OpenSlide installation (`apt install openslide-tools` / `brew install openslide`)
- Increase maximum tile size from 10,000 µm to 999,000 µm
- Rename 'Voronoi points' GUI parameter to 'N tiles (Voronoi / Equal Area)' to reflect dual use
