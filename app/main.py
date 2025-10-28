from fastapi import FastAPI

app = FastAPI(title="Lacabrona API", version="0.1.0")


@app.get("/")
def read_root():
    return {"message": "Lacabrona API is running"}


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
