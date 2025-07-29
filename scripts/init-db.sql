-- Initialize Prior Authorization Database
-- This script sets up the initial database structure and security

-- Create application user with limited privileges
CREATE USER prior_auth_app WITH PASSWORD 'app_password_change_in_production';

-- Create database if it doesn't exist
-- (This is typically handled by the POSTGRES_DB environment variable)

-- Connect to the prior_auth database
\c prior_auth;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS config;

-- Grant permissions to application user
GRANT USAGE ON SCHEMA app TO prior_auth_app;
GRANT USAGE ON SCHEMA audit TO prior_auth_app;
GRANT USAGE ON SCHEMA config TO prior_auth_app;

GRANT CREATE ON SCHEMA app TO prior_auth_app;
GRANT CREATE ON SCHEMA audit TO prior_auth_app;
GRANT CREATE ON SCHEMA config TO prior_auth_app;

-- Create audit trigger function
CREATE OR REPLACE FUNCTION audit.audit_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO audit.audit_log (
            table_name,
            operation,
            old_values,
            changed_by,
            changed_at
        ) VALUES (
            TG_TABLE_NAME,
            TG_OP,
            row_to_json(OLD),
            current_user,
            now()
        );
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit.audit_log (
            table_name,
            operation,
            old_values,
            new_values,
            changed_by,
            changed_at
        ) VALUES (
            TG_TABLE_NAME,
            TG_OP,
            row_to_json(OLD),
            row_to_json(NEW),
            current_user,
            now()
        );
        RETURN NEW;
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO audit.audit_log (
            table_name,
            operation,
            new_values,
            changed_by,
            changed_at
        ) VALUES (
            TG_TABLE_NAME,
            TG_OP,
            row_to_json(NEW),
            current_user,
            now()
        );
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Create audit log table
CREATE TABLE IF NOT EXISTS audit.audit_log (
    id SERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Create indexes for audit log
CREATE INDEX IF NOT EXISTS idx_audit_log_table_name ON audit.audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON audit.audit_log(changed_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_by ON audit.audit_log(changed_by);

-- Grant permissions on audit schema
GRANT SELECT, INSERT ON audit.audit_log TO prior_auth_app;
GRANT USAGE ON SEQUENCE audit.audit_log_id_seq TO prior_auth_app;

-- Create configuration table for application settings
CREATE TABLE IF NOT EXISTS config.app_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Insert default configuration
INSERT INTO config.app_settings (key, value, description) VALUES
    ('max_request_size', '10485760', 'Maximum request size in bytes (10MB)'),
    ('session_timeout', '3600', 'Session timeout in seconds (1 hour)'),
    ('rate_limit_requests', '1000', 'Rate limit requests per hour'),
    ('encryption_algorithm', 'AES-256-GCM', 'Encryption algorithm for PHI data'),
    ('audit_retention_days', '2555', 'Audit log retention period in days (7 years)'),
    ('backup_retention_days', '30', 'Database backup retention in days')
ON CONFLICT (key) DO NOTHING;

-- Grant permissions on config schema
GRANT SELECT, UPDATE ON config.app_settings TO prior_auth_app;

-- Create function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for app_settings
CREATE TRIGGER update_app_settings_updated_at
    BEFORE UPDATE ON config.app_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create performance monitoring views
CREATE OR REPLACE VIEW audit.performance_summary AS
SELECT 
    table_name,
    operation,
    COUNT(*) as operation_count,
    DATE_TRUNC('hour', changed_at) as hour
FROM audit.audit_log
WHERE changed_at >= now() - INTERVAL '24 hours'
GROUP BY table_name, operation, DATE_TRUNC('hour', changed_at)
ORDER BY hour DESC, operation_count DESC;

-- Grant permissions on views
GRANT SELECT ON audit.performance_summary TO prior_auth_app;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_app_settings_key ON config.app_settings(key);

-- Set up row level security (RLS) for sensitive tables
-- This will be configured by Alembic migrations for application tables

-- Create a function to check if current user is application user
CREATE OR REPLACE FUNCTION is_app_user()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN current_user = 'prior_auth_app';
END;
$$ LANGUAGE plpgsql;

-- Log successful initialization
INSERT INTO audit.audit_log (
    table_name,
    operation,
    new_values,
    changed_by,
    changed_at
) VALUES (
    'database_init',
    'INITIALIZE',
    '{"status": "success", "version": "1.0"}',
    current_user,
    now()
);

-- Display initialization summary
SELECT 
    'Database initialization completed successfully' as status,
    current_database() as database_name,
    current_user as initialized_by,
    now() as initialized_at;