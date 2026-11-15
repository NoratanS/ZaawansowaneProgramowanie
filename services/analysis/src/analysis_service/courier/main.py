"""Courier: delivers Analysis Results to the Results Service.

Run with ``python -m analysis_service.courier.main``.
"""

import asyncio
import logging
from uuid import UUID

import httpx
from faststream import FastStream

from analysis_service.auth import CourierToken
from analysis_service.courier.deliver import Outcome, deliver
from analysis_service.queues import (
    RESULTS,
    Action,
    Queue,
    QueueConfig,
    Received,
    confirming_broker,
)
from analysis_service.settings import CourierSettings


def build_courier(
    settings: CourierSettings, *, results: QueueConfig = RESULTS
) -> FastStream:
    base_url = settings.results_service_url
    timeout = settings.delivery_timeout_seconds
    token = CourierToken(settings.jwt_private_key.get_secret_value())
    broker = confirming_broker(settings.rabbitmq_url)
    results_queue = Queue(broker, results)
    # No per-operation timeout: deliver() enforces the total limit itself.
    http = httpx.AsyncClient(timeout=None)
    app = FastStream(broker)

    @app.on_startup
    async def declare_results_queue() -> None:
        # Declare before the subscriber starts consuming from analysis-results.
        await broker.connect()
        await results_queue.declare()

    @app.after_shutdown
    async def close_http() -> None:
        await http.aclose()

    async def put(job_id: UUID, body: bytes) -> Outcome:
        try:
            async with asyncio.timeout(timeout):
                response = await http.put(
                    f"{base_url}/results/{job_id}",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token.get()}",
                    },
                )
        except (httpx.TransportError, TimeoutError) as exc:
            return exc
        return response.status_code

    async def deliver_result(received: Received) -> Action:
        return await deliver(received, put, timeout=timeout)

    results_queue.consume(deliver_result, prefetch=settings.courier_prefetch)
    return app


def main() -> None:
    settings = CourierSettings()
    logging.basicConfig(level=settings.log_level)
    asyncio.run(build_courier(settings).run())


if __name__ == "__main__":
    main()
