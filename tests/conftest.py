import os
import time
import socket
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

# Set test environment variables before anything else
os.environ["DATABASE_URL"] = "sqlite:///./test_openticket.db"
os.environ["STRIPE_API_KEY"] = "sk_test_mock"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_mock_secret"
os.environ["TESTING"] = "True"

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="session")
def db_engine():
    """Session-scoped database engine setup with SQLite WAL mode enabled."""
    try:
        from sqlalchemy import create_engine, event
    except ImportError:
        yield None
        return
        
    TEST_DATABASE_URL = "sqlite:///./test_openticket.db"
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()
        
    yield engine
    
    engine.dispose()

@pytest.fixture(scope="session", autouse=True)
def setup_db(db_engine):
    """Session-scoped database initialization (creating and dropping tables)."""
    if db_engine is None:
        yield
        return
        
    try:
        from src.backend.models import Base
    except ImportError:
        yield
        return
        
    Base.metadata.create_all(bind=db_engine)
    yield
    Base.metadata.drop_all(bind=db_engine)
    
    # Dispose of engine to release file locks on Windows
    db_engine.dispose()
    
    import os
    for suffix in ["", "-wal", "-shm"]:
        path = f"./test_openticket.db{suffix}"
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

@pytest.fixture(scope="function")
def db_session(db_engine):
    """Function-scoped database session for querying or checking test database state."""
    if db_engine is None:
        yield None
        return
        
    try:
        from sqlalchemy.orm import sessionmaker
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        session = TestingSessionLocal()
        yield session
        session.close()
    except Exception:
        yield None

@pytest.fixture(scope="session")
def live_server():
    """Background Uvicorn live server process running on a free port."""
    # Check if backend application package is available
    try:
        import src.backend.main
        app_exists = True
    except ImportError:
        app_exists = False

    if not app_exists:
        yield "http://127.0.0.1:8000"
        return

    port = get_free_port()
    
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning"
    ]
    
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///./test_openticket.db"
    env["TESTING"] = "True"
    
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    import httpx
    url = f"http://127.0.0.1:{port}"
    success = False
    for _ in range(50):
        if proc.poll() is not None:
            break
        try:
            r = httpx.get(url + "/api/health", timeout=0.1)
            success = True
            break
        except Exception:
            try:
                r = httpx.get(url + "/docs", timeout=0.1)
                success = True
                break
            except Exception:
                time.sleep(0.1)
                
    yield url
    
    proc.terminate()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()

@pytest.fixture(scope="session", autouse=True)
def mock_stripe_checkout():
    """Session-scoped autouse fixture to mock Stripe checkout session creation."""
    mock_session = MagicMock()
    mock_session.id = "cs_test_mock_123"
    mock_session.url = "https://checkout.stripe.com/c/pay/cs_test_mock_123"
    
    with patch("stripe.checkout.Session.create", return_value=mock_session) as mocked:
        yield mocked

@pytest.fixture(scope="session", autouse=True)
def mock_stripe_refund():
    """Session-scoped autouse fixture to mock Stripe refund creation."""
    mock_refund = MagicMock()
    mock_refund.id = "re_test_mock_123"
    with patch("stripe.Refund.create", return_value=mock_refund) as mocked:
        yield mocked
