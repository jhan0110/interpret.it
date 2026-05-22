"""Tests for domain_asr_prompt in app.vocab.seeds."""

from app.vocab.seeds import TOPIC_SEEDS, domain_asr_prompt


def test_known_domain_ko_returns_nonempty() -> None:
    result = domain_asr_prompt("logistics", "ko")
    assert result != ""


def test_known_domain_ko_contains_korean_terms() -> None:
    result = domain_asr_prompt("logistics", "ko")
    expected_definitions = [entry["definition"] for entry in TOPIC_SEEDS["logistics"]]
    result_terms = [t.strip() for t in result.split(",")]
    assert result_terms == expected_definitions


def test_known_domain_en_returns_english_terms() -> None:
    result = domain_asr_prompt("logistics", "en")
    expected_terms = [entry["term"] for entry in TOPIC_SEEDS["logistics"]]
    result_terms = [t.strip() for t in result.split(",")]
    assert result_terms == expected_terms


def test_known_domain_en_no_korean() -> None:
    result = domain_asr_prompt("logistics", "en")
    # English-only result should not contain any Hangul characters
    assert not any("가" <= ch <= "힣" for ch in result)


def test_unknown_domain_returns_empty_string() -> None:
    assert domain_asr_prompt("nonexistent_domain", "ko") == ""
    assert domain_asr_prompt("nonexistent_domain", "en") == ""


def test_all_known_domains_ko_nonempty() -> None:
    for domain in TOPIC_SEEDS:
        result = domain_asr_prompt(domain, "ko")
        assert result != "", f"Expected non-empty result for domain={domain!r}"


def test_all_known_domains_en_nonempty() -> None:
    for domain in TOPIC_SEEDS:
        result = domain_asr_prompt(domain, "en")
        assert result != "", f"Expected non-empty result for domain={domain!r}"
