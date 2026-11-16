"""Start the local VSEPR Flask application."""

from vsepr.app import app, main

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
