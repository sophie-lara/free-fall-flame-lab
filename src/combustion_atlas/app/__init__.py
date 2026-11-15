"""Combustion Atlas web app: FastAPI back end serving the React front end."""

from .api import Settings, create_app

__all__ = ["Settings", "create_app"]
