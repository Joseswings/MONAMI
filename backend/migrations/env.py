from alembic import context

from app.config import Settings
from app.database import build_engine
from app.models import Base

settings = Settings()
database_url = settings.migration_database_url or settings.database_url
if database_url is None:
    raise RuntimeError("Configurar DATABASE_URL o MIGRATION_DATABASE_URL en el backend")

options = {
    "target_metadata": Base.metadata,
    "include_schemas": True,
    "version_table": "monami_schema_version",
    "version_table_schema": "public",
}

if context.is_offline_mode():
    context.configure(url=database_url.get_secret_value(), literal_binds=True, **options)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = build_engine(database_url)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, **options)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
