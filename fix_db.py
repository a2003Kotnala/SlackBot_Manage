from sqlalchemy import create_engine, text
from app.config import settings

def fix_alembic():
    engine = create_engine(settings.resolved_database_url)
    with engine.connect() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '20260323_0002'"))
        conn.commit()
    print("Fixed!")

if __name__ == "__main__":
    fix_alembic()