from io import StringIO
from pathlib import Path

from alembic.config import Config

from alembic import command


def test_migration_compiles_for_postgresql_without_server():
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "NUMERIC(12, 2)" in sql
    assert "CREATE TABLE orders" in sql
    assert "FOREIGN KEY(customer_id) REFERENCES customers (id)" in sql
    assert "COMMIT;" in sql
