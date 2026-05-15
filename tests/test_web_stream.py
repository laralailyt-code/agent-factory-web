import time

from fastapi.testclient import TestClient

import factory.web as web


class SlowGraph:
    def stream(self, initial, stream_mode):
        time.sleep(0.05)
        yield {
            **initial,
            "current_stage": "done",
            "log": ["slow pipeline finished"],
            "files": {},
        }


def test_stream_sends_keepalive_while_pipeline_is_busy(monkeypatch):
    monkeypatch.setattr(web, "SSE_KEEPALIVE_SECONDS", 0.01)
    monkeypatch.setattr(web, "build_graph", lambda: SlowGraph())

    client = TestClient(web.app)
    response = client.get(
        "/api/factory/stream",
        params={"req": "free key-in 任意需求，不一定是 Excel 比對"},
    )

    assert response.status_code == 200
    assert ": keepalive\n\n" in response.text
    assert '"type": "done"' in response.text
