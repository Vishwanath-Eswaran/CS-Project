"""Get a molecule structure and start its 3D display."""

from vsepr.nameProcessing import main
from vsepr.rendering import render

# Get a molecule structure, then pass it to the 3D display.
if __name__ == "__main__":
    try:
        render(main())
    except AttributeError:
        print('Try Again')
    except IndexError:
        pass