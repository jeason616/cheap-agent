"""Backward-compatible launch shim.

This file exists so existing MCP client configs that point at
`/path/to/cheap-agent/server.py` keep working after the server logic moved
into the package. New installations should prefer the `cheap-agent` console
script or `python -m cheap_agent` instead.

    python server.py                 # legacy, still works
    python -m cheap_agent            # preferred
    cheap-agent                      # after pipx/pip install (console script)
"""

from cheap_agent.server import main

if __name__ == "__main__":
    main()
