"""Agents package for GLPI AI Gateway.

Export agent builder functions for use in crew_services.
See it_support.py for IT Support agent definition.
"""

from app.legacy.it_support import build_it_support

__all__ = ["build_it_support"]
