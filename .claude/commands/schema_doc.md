Regenerate `docs/database-schema.md` from SQLAlchemy models and show what changed.

Steps:
1. Run `python server/scripts/generate_schema_doc.py`
2. Run `git diff docs/database-schema.md` and summarize the changes (new tables, removed tables, column changes, FK changes)
3. If no changes, say so
