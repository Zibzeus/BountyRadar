import pytest
from radar import official, research
from radar.sources import SourceError


@pytest.mark.parametrize(
    "kind,listing,detail",
    [
        (
            "yeswehack",
            {
                "items": [{"public": False}, {"public": True, "slug": "project"}],
                "pagination": {"nb_pages": 1},
            },
            {
                "public": True,
                "title": "Project",
                "type": "bug-bounty",
                "rules": "Policy",
                "scopes": [{"scope": "Product A", "scope_type": "other"}],
            },
        ),
        (
            "intigriti",
            {
                "records": [
                    {"confidentialityLevel": {"value": "Private"}},
                    {"id": "abc", "confidentialityLevel": {"value": "Public"}},
                ],
                "maxCount": 2,
            },
            {
                "id": "abc",
                "name": "Project",
                "confidentialityLevel": {"value": "Public"},
                "webLinks": {"detail": "https://example.org/program"},
                "domains": {
                    "content": [
                        {
                            "endpoint": "Product A",
                            "type": {"value": "Product"},
                            "tier": {"value": "Out of scope"},
                        }
                    ]
                },
            },
        ),
        (
            "hackerone",
            {
                "data": [
                    {"attributes": {"state": "private_mode"}},
                    {
                        "attributes": {
                            "state": "public_mode",
                            "handle": "project",
                            "name": "Project",
                            "offers_bounties": True,
                        }
                    },
                ],
                "links": {"next": None},
            },
            {
                "data": [
                    {
                        "attributes": {
                            "asset_identifier": "Product A",
                            "asset_type": "OTHER",
                            "eligible_for_submission": True,
                            "eligible_for_bounty": False,
                        }
                    }
                ],
                "links": {"next": None},
            },
        ),
    ],
)
def test_auth_sources_only_return_public(monkeypatch, kind, listing, detail):
    pages = iter([listing, detail, {"data": [], "links": {}}])
    monkeypatch.setattr(
        official, "_get", lambda url, headers: (next(pages), {}, "hash")
    )
    monkeypatch.setattr(official.time, "sleep", lambda _: None)
    records = official.fetch("api:" + kind, {"key": "test", "username": "reader"})
    assert len(records) == 1
    assert records[0]["scope"][0]["raw"] == "Product A"
    assert records[0]["provenance"]["authority"] == "official"


def test_bugcrowd_requires_verified_visibility():
    with pytest.raises(SourceError):
        official.fetch("api:bugcrowd", {"key": "test", "username": "reader"})


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_review_and_provenance(monkeypatch, provider):
    def request(conn, path, payload, timeout):
        if provider == "openai":
            assert path == "/chat/completions"
            return {"choices": [{"message": {"content": "Published policy [S1]"}}]}
        assert path == "/messages"
        return {"content": [{"type": "text", "text": "Published policy [S1]"}]}

    monkeypatch.setattr(research, "_request", request)
    result = research.research_program(
        {
            "name": "Project",
            "url": "https://example.org/policy",
            "policy": "Original terms",
            "snapshot_id": "1",
        },
        {"kind": provider, "model": "test"},
    )
    assert result["status"] == "needs_review" and result["citations"][0]["id"] == "S1"
    assert "Original terms" in result["citations"][0]["excerpt"]


def test_model_cannot_invent_citations(monkeypatch):
    monkeypatch.setattr(research, "_answer", lambda *args: ("Policy [S999]", [], 4, 4))
    with pytest.raises(research.ResearchError, match="citations"):
        research.research_program(
            {"name": "Test", "url": "https://example.org"},
            {"kind": "openai", "model": "test"},
        )


@pytest.mark.parametrize("kind", ["firecrawl", "agent_reach"])
def test_browse_uses_only_approved_policy(monkeypatch, kind):
    url = "https://example.org/policy"
    replies = iter([("", [("read_policy", {})], 1, 1), ("Read [S2]", [], 1, 1)])
    monkeypatch.setattr(research, "_answer", lambda *args: next(replies))
    monkeypatch.setattr(research, "_preflight", lambda u: None)
    monkeypatch.setattr(
        research,
        "validated_target",
        lambda u: (
            __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(u),
            "8.8.8.8",
        ),
    )

    def request(conn, path, payload, timeout):
        assert payload["url"] == url
        return (
            {"text": "Policy page"}
            if kind == "agent_reach"
            else {"success": True, "data": {"markdown": "Policy page"}}
        )

    monkeypatch.setattr(research, "_request", request)
    with pytest.raises(research.ResearchError, match="approved"):
        research.research_program({"name": "test", "url": url}, {}, {"kind": kind})
    result = research.research_program(
        {"name": "test", "url": url}, {}, {"kind": kind}, (url,)
    )
    assert result["usage"]["pages"] == 1 and result["citations"][0]["url"] == url
