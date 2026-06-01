"""
export/
-------
SQLite-Export-Paket für Zoo Guide.

Module:
    config  — PG_CONFIG, OUTPUT_DIR
    schema  — SCHEMA (SQLite DDL)
    fetch   — alle fetch_* Funktionen
    writer  — export_zoo, _do_export, _increment_data_version
"""

from .config import PG_CONFIG, OUTPUT_DIR
from .fetch  import get_zoo_ids
from .writer import export_zoo
