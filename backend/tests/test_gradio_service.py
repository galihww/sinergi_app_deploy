from __future__ import annotations

from unittest import mock

import pytest

from app.services import gradio_service


class FakeJob:
    def __init__(self, outputs=(), *, result=None, error=None):
        self._outputs = list(outputs)
        self._result = result
        self._error = error

    def __iter__(self):
        return iter(self._outputs)

    def exception(self):
        return self._error

    def result(self):
        return self._result


class FakeClient:
    def __init__(self, *, jobs=(), predictions=()):
        self.jobs = list(jobs)
        self.predictions = list(predictions)
        self.payloads = []

    def submit(self, **payload):
        self.payloads.append(payload)
        return self.jobs.pop(0)

    def predict(self, **payload):
        self.payloads.append(payload)
        value = self.predictions.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def test_normalize_payload_converts_gradio_slider_values() -> None:
    original = {
        "max_new_tokens": "4096",
        "temperature": "0.2",
        "top_p": "0.95",
        "top_k": "64",
    }

    normalized = gradio_service._normalize_payload(original)

    assert normalized == {
        "max_new_tokens": 4096,
        "temperature": 0.2,
        "top_p": 0.95,
        "top_k": 64,
    }
    assert original["max_new_tokens"] == "4096"


def test_gradio_stream_preserves_successful_generator_updates(monkeypatch) -> None:
    client = FakeClient(jobs=[FakeJob(["Halo", "Halo dunia"], result="Halo dunia")])
    monkeypatch.setattr(gradio_service, "_client", lambda _space: client)

    assert list(gradio_service.gradio_stream("owner/space", {})) == [
        "Halo",
        "Halo dunia",
    ]


def test_gradio_stream_propagates_job_exception(monkeypatch) -> None:
    error = RuntimeError("ZeroGPU quota exceeded (120 requested vs 30 left)")
    client = FakeClient(jobs=[FakeJob(error=error)])
    monkeypatch.setattr(gradio_service, "_client", lambda _space: client)

    with pytest.raises(RuntimeError, match="quota is insufficient"):
        list(gradio_service.gradio_stream("owner/space", {}))


def test_gradio_stream_retries_empty_job_once(monkeypatch) -> None:
    client = FakeClient(
        jobs=[
            FakeJob(result=""),
            FakeJob(result="Jawaban setelah retry"),
        ]
    )
    monkeypatch.setattr(gradio_service, "_client", lambda _space: client)

    assert list(gradio_service.gradio_stream("owner/space", {})) == [
        "Jawaban setelah retry"
    ]
    assert len(client.payloads) == 2


def test_gradio_respond_retries_transient_failure(monkeypatch) -> None:
    client = FakeClient(
        predictions=[RuntimeError("temporarily unavailable"), "Jawaban sinkron"]
    )
    monkeypatch.setattr(gradio_service, "_client", lambda _space: client)

    assert gradio_service.gradio_respond("owner/space", {}) == "Jawaban sinkron"


def test_gradio_respond_reports_repeated_empty_output(monkeypatch) -> None:
    client = FakeClient(predictions=[None, ""])
    monkeypatch.setattr(gradio_service, "_client", lambda _space: client)

    with pytest.raises(RuntimeError, match="without generating text after one retry"):
        gradio_service.gradio_respond("owner/space", {})
