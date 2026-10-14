"""search_kb tool wrapper around rag.retriever, ready to bind to a LangGraph agent."""

from langchain_core.tools import tool

from backend.rag import format_passages, search_kb as _search


@tool
def search_kb(query: str) -> str:
    """Search the MD Cold Services knowledge base (services, prices, maintenance plans,
    hours, service areas, contact details, policies, financing, FAQs).

    Answer ONLY from the returned passages. If the result is NO_RELEVANT_PASSAGES,
    say you don't know and offer to book a visit or give the phone number.
    """
    return format_passages(_search(query))
