"""日晷 FastAPI 入口"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import HOST, PORT
from .db import init_db

app = FastAPI(title="日晷 Sundial", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok", "name": "sundial"}


def main():
    uvicorn.run("sundial.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
