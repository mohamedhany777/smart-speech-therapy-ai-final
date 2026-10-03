from app.services.web_search import UnavailableWebSearchProvider, _score_domain_trust, get_web_search_provider


def test_gov_and_edu_domains_score_highest():
    assert _score_domain_trust("https://www.nih.gov/some-article") == 1.0
    assert _score_domain_trust("https://stanford.edu/research/speech") == 1.0


def test_known_trusted_health_orgs_score_highest():
    assert _score_domain_trust("https://www.asha.org/practice-portal/") == 1.0
    assert _score_domain_trust("https://www.who.int/news") == 1.0
    assert _score_domain_trust("https://pubmed.ncbi.nlm.nih.gov/12345") == 1.0


def test_generic_org_scores_moderately():
    score = _score_domain_trust("https://somecharity.org/article")
    assert 0.5 <= score < 1.0


def test_blogs_and_forums_score_lowest():
    assert _score_domain_trust("https://random.blogspot.com/post") < 0.3
    assert _score_domain_trust("https://reddit.com/r/speech") < 0.3


def test_unknown_generic_domain_scores_low_moderate():
    score = _score_domain_trust("https://randomsite.com/page")
    assert 0.0 < score < 0.7


def test_unavailable_provider_returns_empty_without_crashing():
    provider = UnavailableWebSearchProvider()
    results = provider.search("stuttering treatment")
    assert results == []


def test_get_provider_returns_unavailable_when_no_key_configured():
    # In tests, TAVILY_API_KEY is not set, so this should gracefully
    # degrade rather than attempt a network call.
    provider = get_web_search_provider()
    assert provider.name == "unavailable"
    assert provider.search("anything") == []
