from factory import llm


class _Headers:
    def __init__(self, retry_after: str | None = None) -> None:
        self.retry_after = retry_after

    def get(self, name: str) -> str | None:
        if name.lower() == "retry-after":
            return self.retry_after
        return None


class _Response:
    status_code = 429

    def __init__(self, retry_after: str | None = None) -> None:
        self.headers = _Headers(retry_after)


class _RateLimitError(Exception):
    status_code = 429

    def __init__(self, message: str, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.response = _Response(retry_after)


def test_create_message_with_retry_waits_and_retries(monkeypatch):
    calls: list[dict] = []
    sleeps: list[float] = []

    class _Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise _RateLimitError("Rate limit exceeded", retry_after="2")
            return {"ok": True}

    class _Client:
        messages = _Messages()

    monkeypatch.setenv("ANTHROPIC_RATE_LIMIT_MAX_ATTEMPTS", "2")
    monkeypatch.setattr(llm, "_get_client", lambda: _Client())
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: sleeps.append(seconds))

    log: list[str] = []
    result = llm.create_message_with_retry(log=log, model="test-model", max_tokens=1)

    assert result == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [2.0]
    assert any("429" in line for line in log)
