"""Agents package for GLPI AI Gateway.

Export agent builder functions for use in crew_orchestrator.
See agent_factory.py for IT Support agent definition.
"""

from .agent_factory import build_it_support

__all__ = ["build_it_support"]
