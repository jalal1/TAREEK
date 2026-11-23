# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch the Config Wizard web application."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
