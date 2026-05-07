"""Compatibility surface for handler-level shared helpers/constants.

Handlers import from this module instead of importing directly from ``app``.
This removes the direct handler -> app dependency edge that triggered circular
imports during the migration.
"""

from importlib import import_module


def __getattr__(name: str):
    app_module = import_module("app")
    return getattr(app_module, name)
