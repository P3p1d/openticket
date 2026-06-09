import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./openticket.db")

connect_args = {}
engine_kwargs = {}

if "sqlite" in DATABASE_URL:
    connect_args["check_same_thread"] = False
    engine_kwargs["connect_args"] = connect_args
else:
    # PostgreSQL configuration options
    engine_kwargs["pool_size"] = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    engine_kwargs["max_overflow"] = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
    engine_kwargs["pool_timeout"] = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
    engine_kwargs["pool_recycle"] = int(os.getenv("DATABASE_POOL_RECYCLE", "1800"))
    engine_kwargs["poolclass"] = QueuePool

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Configure SQLite specific settings if using SQLite
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000") # 30 seconds timeout
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def do_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
