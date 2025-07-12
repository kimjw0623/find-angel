from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import threading
from abc import ABC, abstractmethod

class BaseDatabaseManager(ABC):
    _instances = {}
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__new__(cls)
                    instance._initialize_db()
                    cls._instances[cls] = instance
        return cls._instances[cls]
    
    def _initialize_db(self):
        """Initialize database connection and configuration"""
        self.engine = create_engine(self.get_database_url())
        self._configure_sqlite()
        self.Session = sessionmaker(bind=self.engine)
        self.get_base_metadata().create_all(self.engine)
    
    def _configure_sqlite(self):
        """Configure SQLite with WAL mode"""
        with self.engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
    
    @abstractmethod
    def get_database_url(self) -> str:
        """Return the database URL for this manager"""
        pass
    
    @abstractmethod
    def get_base_metadata(self):
        """Return the metadata for this database"""
        pass
    
    @contextmanager
    def get_session(self):
        """General session with auto-commit/rollback"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    @contextmanager
    def get_read_session(self):
        """Read-only session for concurrent reads"""
        session = self.Session()
        try:
            session.execute(text("BEGIN"))
            yield session
        finally:
            session.rollback()
            session.close()
    
    @contextmanager
    def get_write_session(self):
        """Write session with exclusive locking"""
        with self._lock:
            session = self.Session()
            try:
                session.execute(text("BEGIN EXCLUSIVE"))
                yield session
                session.commit()
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()