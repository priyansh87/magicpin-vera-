"""
main.py — ASGI Entrypoint for Vera Assistant Deployment
Aliases bot:app so default container commands (uvicorn main:app) succeed out of the box.
"""

import os
import uvicorn
from bot import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
