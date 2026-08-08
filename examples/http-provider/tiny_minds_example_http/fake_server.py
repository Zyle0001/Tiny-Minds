from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def _overlap(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def _vector(text: str) -> list[float]:
    raw = hashlib.sha256(text.encode()).digest()[:8]
    values = [(byte - 127.5) / 127.5 for byte in raw]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_POST(self) -> None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            if self.path == "/embeddings":
                result = {"vectors": [_vector(text) for text in payload["texts"]], "model": {"model_id": "fake-embedding"}}
            elif self.path == "/rerank":
                result = {"scores": [_overlap(payload["query"], item) for item in payload["documents"]], "model": {"model_id": "fake-reranker"}}
            elif self.path == "/nli":
                rows = []
                for pair in payload["pairs"]:
                    overlap = _overlap(pair["premise"], pair["hypothesis"])
                    negated = bool(re.search(r"\b(no|not|never)\b", pair["premise"], re.I)) != bool(re.search(r"\b(no|not|never)\b", pair["hypothesis"], re.I))
                    rows.append({"contradiction": 0.8 if negated else 0.05, "entailment": overlap if not negated else 0.05,
                                 "neutral": max(0.0, 1.0 - overlap) if not negated else 0.15})
                result = {"scores": rows, "model": {"model_id": "fake-nli"}}
            elif self.path == "/classify":
                result = {"scores": [{label: _overlap(text, label) for label in payload["labels"]} for text in payload["texts"]],
                          "model": {"model_id": "fake-classifier"}}
            else:
                self.send_error(404)
                return
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_error(400, str(exc))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
