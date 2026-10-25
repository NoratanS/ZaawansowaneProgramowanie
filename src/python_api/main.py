import uvicorn
from fastapi import Depends, FastAPI

from python_api import user_routes
from python_api.auth import get_token_payload
from python_api.routes import router

app = FastAPI()
# /login is public; /users and /user_details check the token themselves.
app.include_router(user_routes.router)
app.include_router(router, dependencies=[Depends(get_token_payload)])


@app.get("/", dependencies=[Depends(get_token_payload)])
def hello() -> dict:
    return {"hello": "world"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
