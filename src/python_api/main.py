import uvicorn
from fastapi import FastAPI

from python_api.routes import router

app = FastAPI()
app.include_router(router)


@app.get("/")
def hello() -> dict:
    return {"hello": "world"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
