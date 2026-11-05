from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request

from .normalization import normalize_tag, score_text_similarity


@dataclass
class LlmConfig:
    llama_server_path: str | None
    model_path: str | None
    host: str = "127.0.0.1"
    port: int = 8766


class LocalReconciler:
    """Small adapter around llama.cpp with deterministic fallback.

    The production path uses JSON-schema constrained output from llama.cpp. The
    deterministic fallback keeps the extractor useful when the model bundle is
    intentionally absent in development.
    """

    def __init__(self, config: LlmConfig) -> None:
        self.config = config
        self.process: subprocess.Popen[str] | None = None

    def reconcile_tags(self, left: str, right: str) -> dict[str, Any]:
        fallback = {
            "left": normalize_tag(left),
            "right": normalize_tag(right),
            "match": score_text_similarity(left, right) >= 0.72,
            "confidence": score_text_similarity(left, right),
            "reason": "deterministic normalization fallback",
        }
        if not self._available():
            return fallback
        try:
            self._ensure_server()
            payload = {
                "model": "recreation-local",
                "messages": [
                    {
                        "role": "system",
                        "content": "Normalize engineering tags and decide if they refer to the same item. Return only JSON.",
                    },
                    {"role": "user", "content": json.dumps({"left": left, "right": right})},
                ],
                "temperature": 0.0,
                "max_tokens": 128,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "tag_match",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "left": {"type": "string"},
                                "right": {"type": "string"},
                                "match": {"type": "boolean"},
                                "confidence": {"type": "number"},
                                "reason": {"type": "string"},
                            },
                            "required": ["left", "right", "match", "confidence", "reason"],
                        },
                    },
                },
            }
            req = request.Request(
                f"http://{self.config.host}:{self.config.port}/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode())
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            return fallback

    def _available(self) -> bool:
        return bool(
            self.config.llama_server_path
            and self.config.model_path
            and Path(self.config.llama_server_path).exists()
            and Path(self.config.model_path).exists()
        )

    def _ensure_server(self) -> None:
        if self.process and self.process.poll() is None:
            return
        assert self.config.llama_server_path and self.config.model_path
        self.process = subprocess.Popen(
            [
                self.config.llama_server_path,
                "--host",
                self.config.host,
                "--port",
                str(self.config.port),
                "--model",
                self.config.model_path,
                "--ctx-size",
                "4096",
                "--parallel",
                "1",
                "--cache-type-k",
                "q8_0",
                "--cache-type-v",
                "q8_0",
                "--no-webui",
                "--offline",
                "--alias",
                "recreation-local",
            ],
            text=True,
        )
        time.sleep(1.0)
