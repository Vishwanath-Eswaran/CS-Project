"""Launch the VPython renderer for a molecule saved in the local cache."""

import sys

try:
    from .nameProcessing import load_molecule_map
except ImportError:  # pragma: no cover - direct script execution fallback
    from nameProcessing import load_molecule_map


def main():
    identifier = sys.argv[1]
    scene_width = int(sys.argv[2])
    scene_height = int(sys.argv[3])
    molecules = load_molecule_map()
    try:
        molecular_map = molecules[identifier.lower()]
    except KeyError as error:
        raise ValueError("Molecule is not in the saved structure cache.") from error

    try:
        from .rendering import render
    except ImportError:  # pragma: no cover - direct script execution fallback
        from rendering import render
    import vpython

    render(
        molecular_map,
        width=scene_width,
        height=scene_height,
        background=vpython.color.gray(0.5),
    )


if __name__ == "__main__":
    main()
