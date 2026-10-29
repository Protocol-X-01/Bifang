from __future__ import annotations

import math
from numbers import Real


def validate_embedding(vector) -> list[float]:
    if not isinstance(vector, list) or not vector or len(vector) > 65536:
        raise ValueError("Embedding must be a nonempty numeric vector")
    if any(isinstance(value, bool) or not isinstance(value, Real) for value in vector):
        raise ValueError("Embedding contains nonnumeric values")
    values = [float(value) for value in vector]
    norm = math.hypot(*values)
    if not all(math.isfinite(value) for value in values) or not math.isfinite(norm) or norm == 0:
        raise ValueError("Embedding must be finite and nonzero")
    return values


async def request_embedding(client, config, text: str, model: str,
                            input_type: str | None = None) -> list[float]:
    if not text.strip() or not model.strip():
        raise ValueError("Embedding text and model must be nonempty")
    payload = {"input": [text], "model": model, "encoding_format": "float"}
    if input_type is not None:
        if input_type not in ("query", "passage"):
            raise ValueError("Embedding input_type must be query or passage")
        payload["input_type"] = input_type
    response = await client.post("/embeddings", headers=config.get_headers(), json=payload)
    response.raise_for_status()
    try:
        data = response.json()["data"]
        if len(data) != 1:
            raise ValueError
        vector = data[0]["embedding"]
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise ValueError("Invalid embedding response structure") from error
    return validate_embedding(vector)
