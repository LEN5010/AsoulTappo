from fastapi.testclient import TestClient

import app.main as main
from app.releases import FRESH_SECONDS, RETRY_SECONDS, STALE_SECONDS, ReleaseFeed, newest

URL = "https://main.test/api/tappo/release"
FEED = {"releases": [{"version": "0.1.0-beta.7", "notes": "新版本"}, {"version": "0.1.0-beta.6", "notes": ""}],
        "checkedAt": "2026-11-07T00:00:00Z"}


class FakeMain:
    def __init__(self):
        self.calls = 0
        self.feed = FEED
        self.down = False
        self.error = None  # raised by the next call only

    def __call__(self, url):
        assert url == URL
        self.calls += 1
        if self.error:
            error, self.error = self.error, None
            raise error
        if self.down:
            raise OSError("unreachable")
        return self.feed


def feed_with(fake):
    clock = [0.0]
    return ReleaseFeed(URL, fake, lambda: clock[0]), clock


def test_newest_takes_the_first_release():
    assert newest(FEED) == {"version": "0.1.0-beta.7", "notes": "新版本"}
    assert newest({"releases": []}) is None
    assert newest({"releases": [{"version": "latest"}]}) is None
    assert newest([]) is None


def test_feed_caches_and_retries():
    fake = FakeMain()
    feed, clock = feed_with(fake)
    assert feed.latest()["version"] == "0.1.0-beta.7"
    clock[0] = FRESH_SECONDS - 1
    feed.latest()
    assert fake.calls == 1

    fake.down = True
    clock[0] = FRESH_SECONDS
    assert feed.latest()["version"] == "0.1.0-beta.7"  # last good answer while the main site fails
    clock[0] = FRESH_SECONDS + RETRY_SECONDS - 1
    feed.latest()
    assert fake.calls == 2

    clock[0] = STALE_SECONDS + 1
    assert feed.latest() is None


def test_a_broken_response_is_retried_like_any_failure():
    import http.client

    fake = FakeMain()
    feed, clock = feed_with(fake)
    feed.latest()
    clock[0] = FRESH_SECONDS
    fake.error = http.client.IncompleteRead(b"{")  # a truncated body, which is not an OSError
    assert feed.latest()["version"] == "0.1.0-beta.7"  # the cached answer, not an exception
    clock[0] = FRESH_SECONDS + RETRY_SECONDS - 1
    feed.latest()
    assert fake.calls == 2
    clock[0] = FRESH_SECONDS + RETRY_SECONDS
    fake.feed = {"releases": [{"version": "0.1.0-beta.8", "notes": ""}]}
    assert feed.latest()["version"] == "0.1.0-beta.8"
    assert fake.calls == 3


def test_feed_without_a_first_answer():
    fake = FakeMain()
    fake.down = True
    feed, _ = feed_with(fake)
    assert feed.latest() is None


def test_release_endpoint(monkeypatch):
    fake = FakeMain()
    feed, _ = feed_with(fake)
    monkeypatch.setattr(main, "releases", feed)
    monkeypatch.setattr(main, "notice", main.Notice())
    client = TestClient(main.app)
    assert client.get("/api/client/release").json() == {
        "version": "0.1.0-beta.7", "notes": "新版本", "minVersion": None, "announcements": []}

    fake.down = True
    monkeypatch.setattr(main, "releases", feed_with(fake)[0])
    res = client.get("/api/client/release")
    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "release_unavailable"


def test_a_slow_main_site_does_not_block_other_callers():
    import threading
    from app.releases import ReleaseFeed

    started, release = threading.Event(), threading.Event()
    calls = []

    def slow(url):
        calls.append(url)
        started.set()
        release.wait(5)
        return {"releases": [{"version": "0.1.0", "notes": ""}]}

    feed = ReleaseFeed("u", fetch=slow)
    t = threading.Thread(target=feed.latest)
    t.start()
    assert started.wait(5)
    # while the first caller waits on the main site, others answer at once from the (empty) cache
    assert feed.latest() is None
    release.set()
    t.join(5)
    assert feed.latest() == {"version": "0.1.0", "notes": ""}
    assert len(calls) == 1


def test_newest_accepts_tag_forms_the_client_accepts():
    for raw, want in [("v1.2.3", "1.2.3"), ("1.2.3+b5", "1.2.3"), ("v0.1.0-beta.7+ci", "0.1.0-beta.7")]:
        assert newest({"releases": [{"version": raw}]})["version"] == want
    for bad in ["1.2", "1.2.3/x", "vv1.2.3"]:
        assert newest({"releases": [{"version": bad}]}) is None
