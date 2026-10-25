import json
import uuid

import pika
import uvicorn
from fastapi import FastAPI, HTTPException, Query

from detector import detect_people, download_image
from rabbit import QUEUE, RESULTS_DIR, connect

app = FastAPI()


@app.get("/analyze_img_sync")
def analyze_img_sync(url: str) -> dict:
    """Original version (tasks 1-4): analyses the image inside the request."""
    try:
        image = download_image(url)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"people": len(detect_people(image))}


@app.get("/analyze_img")
def analyze_img(url: str) -> dict:
    """Producer: put the job on the queue and return its id straight away."""
    job_id = uuid.uuid4().hex
    connection, channel = connect()
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE,
        body=json.dumps({"id": job_id, "url": url}),
        properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent),
    )
    connection.close()
    return {"id": job_id}


@app.get("/check")
def check(id: str = Query(pattern="^[0-9a-f]{32}$")) -> dict:
    """Look for the consumer's result file: {id}-{number-of-people}.{extension}."""
    for path in RESULTS_DIR.glob(f"{id}-*"):
        people = int(path.stem.removeprefix(f"{id}-"))
        return {"id": id, "status": "done", "people": people, "file": path.name}
    return {"id": id, "status": "pending"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
