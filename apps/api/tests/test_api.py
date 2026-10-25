import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag import RetrievedChunk, build_user_message, get_answerer
from app.routers.ask import get_retriever

CHUNKS = [
    RetrievedChunk("Bring a PSA birth certificate.", "Passport", "https://a.gov.ph/p", "DFA"),
    RetrievedChunk("Appointments are online.", "Passport", "https://a.gov.ph/p", "DFA"),
]


class FakeAnswerer:
    def __init__(self):
        self.calls = []

    def answer(self, question, chunks, lang):
        self.calls.append((question, chunks, lang))
        return "Bring your PSA birth certificate [1]."


# Not entered as a context manager, so the lifespan (which needs Postgres) never runs.
client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_answerer():
    # FastAPI resolves dependencies even for invalid requests, so every test needs these stubs
    # to keep the real embedding model and Claude client from loading.
    fake = FakeAnswerer()
    app.dependency_overrides[get_retriever] = lambda: lambda q: CHUNKS
    app.dependency_overrides[get_answerer] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_ask_returns_answer_and_deduplicated_sources(fake_answerer):
    res = client.post("/ask", json={"question": "Paano kumuha ng passport?", "lang": "tl"})

    assert res.status_code == 200
    body = res.json()
    assert body["answer"] == "Bring your PSA birth certificate [1]."
    assert body["sources"] == [{"title": "Passport", "url": "https://a.gov.ph/p", "agency": "DFA"}]
    assert fake_answerer.calls[0][2] == "tl"


def test_ask_rejects_unknown_language():
    res = client.post("/ask", json={"question": "passport?", "lang": "fr"})
    assert res.status_code == 422


def test_user_message_numbers_sources_and_sets_language():
    msg = build_user_message("How?", CHUNKS, "ceb")
    assert "[1] DFA - Passport" in msg
    assert "[2] DFA - Passport" in msg
    assert msg.endswith("Answer in Bisaya (Cebuano).")
