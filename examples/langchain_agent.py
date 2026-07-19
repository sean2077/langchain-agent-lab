"""LangChain v1: a minimal create_agent + tool example."""

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_ollama import ChatOllama

from agent_learn.config import Settings


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers. Always use this tool for multiplication."""

    return a * b


def build_langchain_agent():
    settings = Settings.from_env()
    model = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
    )
    return create_agent(
        model,
        tools=[multiply],
        system_prompt="Use the multiply tool for multiplication, then answer concisely.",
        name="langchain_minimal_agent",
    )


def main() -> None:
    result = build_langchain_agent().invoke(
        {"messages": [{"role": "user", "content": "What is 17 times 23?"}]}
    )
    print(result["messages"][-1].text)


if __name__ == "__main__":
    main()
