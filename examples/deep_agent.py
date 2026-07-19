"""Deep Agents: build a minimal harness with one harmless tool."""

from deepagents import create_deep_agent
from langchain.tools import tool
from langchain_ollama import ChatOllama

from agent_learn.config import Settings


@tool
def glossary_lookup(term: str) -> str:
    """Look up one term in a tiny synthetic glossary."""

    glossary = {
        "agent": "A model-driven loop that can choose and call tools.",
        "tool": "A typed function exposed to an agent.",
    }
    return glossary.get(term.lower(), "Term not found in the synthetic glossary.")


def build_deep_agent():
    settings = Settings.from_env()
    model = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
    )
    return create_deep_agent(
        model=model,
        tools=[glossary_lookup],
        system_prompt=(
            "Always call glossary_lookup for glossary definitions. Do not answer from model memory."
        ),
        name="deep_agent_minimal",
    )


def run_deep_agent_demo() -> dict:
    return build_deep_agent().invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "You must call glossary_lookup with term='agent'. "
                        "Then return only the exact tool result."
                    ),
                }
            ]
        }
    )


def main() -> None:
    result = run_deep_agent_demo()
    tool_messages = [message for message in result["messages"] if message.type == "tool"]
    if not tool_messages:
        raise RuntimeError("deep agent did not call glossary_lookup")
    print(tool_messages[-1].content)


if __name__ == "__main__":
    main()
