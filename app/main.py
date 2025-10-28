from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from integrations.MongoDB.router import router as mongo_router

app = FastAPI(title="Lacabrona API", version="0.1.0")


app.include_router(mongo_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Lacabrona API is running"}


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
