from alembic import context

from app import models  # Registra as tabelas de destino.
from app.database import Base, engine


def run_migrations(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is None:
    with engine.connect() as connection:
        run_migrations(connection)
else:
    run_migrations(connection)
