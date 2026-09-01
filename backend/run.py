import uvicorn
import os
from app.api.main import app

if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
        workers=1,  # Single worker — models are loaded in-process
    )
