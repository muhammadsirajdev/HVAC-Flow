"""Settings loaded from .env (pydantic-settings)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/  (the uv project root: holds .env, knowledge/, data/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Business ---
    business_name: str = "MD Cold Services"
    business_phone: str = "(786) 797-6193"
    business_tz: str = "America/New_York"       # Miami
    business_inbox: str = "mdcoldservices@gmail.com"

    # --- Database (app data + LangGraph checkpoints) ---
    database_url: str = ""

    # --- Chat LLM (classifier + answers). provider: openai | groq ---
    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1-mini"
    llm_timeout: float = 30.0
    groq_api_key: str = ""

    # --- OpenAI ---
    openai_api_key: str = ""

    # --- MCP: Gmail and Slack through Klavis ---
    klavis_gmail_mcp_url: str = ""
    klavis_slack_mcp_url: str = ""
    klavis_mcp_token: str = ""
    gmail_send_tool: str = "gmail_send_email"
    gmail_search_tool: str = "gmail_search_emails"
    gmail_read_tool: str = "gmail_read_email"
    gmail_modify_tool: str = "gmail_modify_email"
    slack_post_tool: str = "slack_user_post_message"
    slack_list_channels_tool: str = "slack_user_list_channels"
    slack_history_tool: str = "slack_get_channel_history"
    mcp_timeout: float = 30.0

    # --- Email agent (Run B) ---
    email_poll_enabled: bool = False          # start the inbox poller with the app
    email_poll_seconds: int = 90
    # Gmail search for candidate emails. Handled ones are skipped by message ID (messages table).
    email_poll_query: str = ("in:inbox -from:me newer_than:3d -category:promotions -category:social "
                             "-category:updates -category:forums")
    email_poll_max: int = 25
    # New conversations are only taken from mail sent TO this address (or a website form sender);
    # replies in a case's thread are always taken. Everything else in the mailbox is ignored.
    email_agent_address: str = ""             # e.g. you+hvac@gmail.com; empty -> business_inbox
    email_form_senders: str = ""              # comma-separated website enquiry-form sender addresses
    max_ai_replies_per_thread_per_hour: int = 5

    # --- Slack channels: a channel NAME (looked up with slack_user_list_channels) or an ID ---
    slack_urgent_channel: str = "slack_urgent_channel"
    slack_bookings_channel: str = ""          # empty -> everything goes to the urgent channel
    slack_status_channel: str = ""            # staff post "case 123 status done" here (Run C)

    # --- Job status (Run C): read the status channel, thank and close finished cases ---
    slack_status_enabled: bool = False        # run it on a timer inside the app
    slack_status_hours: float = 12

    # --- Day-before reminders (Run D) ---
    reminders_enabled: bool = False           # send them daily inside the app
    reminder_hour: int = 18                   # business time zone

    # --- Chat booking flow ---
    slot_offer_count: int = 3
    min_lead_hours: int = 2                   # earliest slot offered: now + this
    late_change_hours: int = 2                # changes closer than this to the visit -> a person
    chat_amend_minutes: int = 60              # a booking can be changed in the SAME chat for this long
    widget_allowed_origins: str = "http://localhost:8000"
    dev_ui: bool = True                       # test console at / and /dev/*; set False in production

    # --- RAG ---
    # The same embedding model MUST be used for ingestion and retrieval.
    rag_embedding_model: str = "text-embedding-3-large"
    rag_chunker_model: str = "gpt-4.1"
    rag_report_model: str = "gpt-4.1"
    kb_dir: Path = PROJECT_ROOT / "knowledge" / "mdcold"
    kb_build_dir: Path = PROJECT_ROOT / "knowledge" / "mdcold" / "build"
    chroma_dir: Path = PROJECT_ROOT / "data" / "chroma"
    chroma_collection: str = "mdcold_kb"
    kb_top_k: int = 6
    kb_max_per_source: int = 2                # at most this many chunks from one source file
    # Cosine similarity (1 - distance). text-embedding-3-large scores relevant
    # passages lower than older models; tune with `python -m backend.rag.evaluate_qa`.
    kb_min_score: float = 0.20                # only blocks off-topic (<0.19); see eval_qa_report.md


@lru_cache
def get_settings() -> Settings:
    return Settings()
