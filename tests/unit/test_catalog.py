from agent_learn.catalog import official_sources_for


def test_catalog_returns_relevant_first_party_sources_without_duplicates() -> None:
    sources = official_sources_for("Deep Agents、LangGraph 和 LangSmith evaluation 有什么区别？")

    urls = [source.url for source in sources]
    assert "https://docs.langchain.com/oss/python/langgraph/overview" in urls
    assert "https://docs.langchain.com/oss/python/deepagents/overview" in urls
    assert "https://docs.langchain.com/langsmith/evaluation" in urls
    assert len(urls) == len(set(urls))


def test_catalog_includes_both_first_party_sides_for_dify_comparison() -> None:
    sources = official_sources_for("Dify 与 LangChain 的定位差异是什么？")

    urls = {source.url for source in sources}
    assert "https://docs.dify.ai/en/home" in urls
    assert "https://dify.ai/blog/dify-vs-langchain" in urls
    assert "https://docs.langchain.com/oss/python/releases/langchain-v1" in urls


def test_catalog_does_not_seed_unrelated_questions() -> None:
    assert official_sources_for("新加坡今天适合散步吗？") == []
