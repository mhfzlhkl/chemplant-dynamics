"""tools — developer-facing scripts that live next to ``app/``.

Kept separate from the runtime package so production imports stay
clean. Currently houses:

- :mod:`tools.export_static` — renders the home page to a static
  ``docs/index.html`` for GitHub Pages.
"""
