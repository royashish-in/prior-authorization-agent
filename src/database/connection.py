"""
Database connection management for the Prior Authorization Agent.

Provides connection pooling, session management, and database configuration
with support for encrypted PHI data storage.
"""

import os
import logging
from typing import Generator, Optional
from contextlib import contextmanager
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import get_settings
from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages database connections, sessions, and configuration.
    
    Provides connection pooling, health checks, and encrypted storage support.
    """
    
    def __init__(self):
        """Initialize database manager with configuration."""
        self.settings = get_settings()
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        
    @property
    def engine(self) -> Engine:
        """Get or create database engine with connection pooling."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine
    
    @property
    def session_factory(self) -> sessionmaker:
        """Get or create session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False
            )
        return self._session_factory
    
    def _create_engine(self) -> Engine:
        """Create SQLAlchemy engine with optimized configuration."""
        database_url = self._get_database_url()
        
        # Engine configuration for production use
        engine_config = {
            "poolclass": QueuePool,
            "pool_size": self.settings.db_pool_size,
            "max_overflow": self.settings.db_max_overflow,
            "pool_pre_ping": True,  # Validate connections before use
            "pool_recycle": 3600,   # Recycle connections every hour
            "echo": self.settings.db_echo,  # Log SQL queries in debug mode
            "future": True,  # Use SQLAlchemy 2.0 style
        }
        
        # Add MySQL-specific configuration if using MySQL
        if database_url.startswith("mysql"):
            engine_config.update({
                "connect_args": {
                    "charset": "utf8mb4",
                    "use_unicode": True,
                    "autocommit": False,
                }
            })
        
        engine = create_engine(database_url, **engine_config)
        
        # Add event listeners for connection management
        self._setup_engine_events(engine)
        
        logger.info(f"Database engine created with pool_size={self.settings.db_pool_size}")
        return engine
    
    def _get_database_url(self) -> str:
        """Construct database URL from configuration."""
        if hasattr(self.settings, 'database_url') and self.settings.database_url:
            return self.settings.database_url
        
        # Construct URL from components
        db_config = {
            'driver': getattr(self.settings, 'db_driver', 'mysql+pymysql'),
            'username': getattr(self.settings, 'db_username', 'root'),
            'password': getattr(self.settings, 'db_password', ''),
            'host': getattr(self.settings, 'db_host', 'localhost'),
            'port': getattr(self.settings, 'db_port', 3306),
            'database': getattr(self.settings, 'db_name', 'prior_auth'),
        }
        
        if db_config['password']:
            return f"{db_config['driver']}://{db_config['username']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        else:
            return f"{db_config['driver']}://{db_config['username']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
    
    def _setup_engine_events(self, engine: Engine) -> None:
        """Set up engine event listeners for connection management."""
        
        @event.listens_for(engine, "connect")
        def set_mysql_mode(dbapi_connection, connection_record):
            """Set MySQL session variables for optimal performance."""
            if engine.dialect.name == "mysql":
                with dbapi_connection.cursor() as cursor:
                    # Set session variables for better performance and security
                    cursor.execute("SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO'")
                    cursor.execute("SET SESSION innodb_lock_wait_timeout = 50")
                    cursor.execute("SET SESSION wait_timeout = 28800")
        
        @event.listens_for(engine, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            """Log connection checkout for monitoring."""
            logger.debug("Database connection checked out from pool")
        
        @event.listens_for(engine, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            """Log connection checkin for monitoring."""
            logger.debug("Database connection returned to pool")
    
    def create_tables(self) -> None:
        """Create all database tables."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except SQLAlchemyError as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    def drop_tables(self) -> None:
        """Drop all database tables (use with caution)."""
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.warning("All database tables dropped")
        except SQLAlchemyError as e:
            logger.error(f"Failed to drop database tables: {e}")
            raise
    
    def health_check(self) -> bool:
        """Perform database health check."""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get database session with automatic cleanup."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def close(self) -> None:
        """Close database connections and cleanup resources."""
        if self._engine:
            self._engine.dispose()
            logger.info("Database connections closed")


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """Get or create global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def get_session() -> Generator[Session, None, None]:
    """Get database session for dependency injection."""
    db_manager = get_database_manager()
    with db_manager.get_session() as session:
        yield session


def get_db_session() -> Generator[Session, None, None]:
    """Get database session for dependency injection (alias for get_session)."""
    return get_session()


def init_database() -> None:
    """Initialize database with tables and configuration."""
    db_manager = get_database_manager()
    db_manager.create_tables()
    logger.info("Database initialized successfully")


def close_database() -> None:
    """Close database connections and cleanup."""
    global _db_manager
    if _db_manager:
        _db_manager.close()
        _db_manager = None