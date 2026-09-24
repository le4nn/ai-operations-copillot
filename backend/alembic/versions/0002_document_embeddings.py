"""Add document embeddings; SQLite remains relational-test-only."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(1536).with_variant(sa.JSON(), "sqlite"), nullable=True),
    )
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding")
    # The extension can be shared by other applications; do not drop it.
