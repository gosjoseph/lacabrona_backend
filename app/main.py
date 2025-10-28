from fastapi import FastAPI
from integrations.MongoDB.router import router as mongo_router

app = FastAPI(title="Lacabrona API", version="0.1.0")


app.include_router(mongo_router)


@app.get("/")
def read_root():
    return {"message": "Lacabrona API is running"}


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
