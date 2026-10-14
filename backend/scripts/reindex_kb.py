"""Rebuild the knowledge base: chunk changed documents and sync Chroma.

Same as `python -m backend.rag.ingest`; accepts the same flags.
"""

import sys

from backend.rag.ingest import main

if __name__ == "__main__":
    sys.exit(main())
