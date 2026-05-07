"""Route handler implementations.

Modules in this package contain the function bodies that the thin blueprints in
``routes/`` delegate to via ``register_route_handlers()``. They import shared
helpers and constants from ``app`` at module load time. Because ``app.py``
imports this package only AFTER all helpers/constants are defined, those
imports resolve cleanly without cycles.
"""
