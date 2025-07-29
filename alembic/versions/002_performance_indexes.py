"""Add performance optimization indexes

Revision ID: 002_performance_indexes
Revises: 001_initial_schema
Create Date: 2025-01-24 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '002_performance_indexes'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    """Add performance optimization indexes."""
    
    # Authorization Requests Performance Indexes
    
    # Composite index for provider dashboard queries
    op.create_index(
        'idx_provider_status_submitted',
        'authorization_requests',
        ['provider_id', 'status', 'submitted_at'],
        unique=False
    )
    
    # Index for urgency-based queries
    op.create_index(
        'idx_urgency_submitted',
        'authorization_requests',
        ['urgency_level', 'submitted_at'],
        unique=False
    )
    
    # Index for status transitions and updates
    op.create_index(
        'idx_status_updated_submitted',
        'authorization_requests',
        ['status', 'updated_at', 'submitted_at'],
        unique=False
    )
    
    # Index for procedure type filtering
    op.create_index(
        'idx_procedure_type_status',
        'authorization_requests',
        ['procedure_type', 'status'],
        unique=False
    )
    
    # Authorization Decisions Performance Indexes
    
    # Composite index for decision analytics
    op.create_index(
        'idx_status_decided_confidence',
        'authorization_decisions',
        ['status', 'decided_at', 'confidence_score'],
        unique=False
    )
    
    # Index for authorization number lookups
    op.create_index(
        'idx_auth_number_valid_until',
        'authorization_decisions',
        ['authorization_number', 'valid_until'],
        unique=False
    )
    
    # Index for decision time analysis
    op.create_index(
        'idx_decided_at_status',
        'authorization_decisions',
        ['decided_at', 'status'],
        unique=False
    )
    
    # Coverage Policies Performance Indexes
    
    # Composite index for policy lookup optimization
    op.create_index(
        'idx_payer_procedure_active_effective',
        'coverage_policies',
        ['payer_id', 'procedure_code', 'is_active', 'effective_date'],
        unique=False
    )
    
    # Index for policy type and status queries
    op.create_index(
        'idx_policy_type_active_effective',
        'coverage_policies',
        ['policy_type', 'is_active', 'effective_date'],
        unique=False
    )
    
    # Index for expiration date queries
    op.create_index(
        'idx_expiration_active',
        'coverage_policies',
        ['expiration_date', 'is_active'],
        unique=False
    )
    
    # Index for policy versioning
    op.create_index(
        'idx_policy_name_version',
        'coverage_policies',
        ['policy_name', 'policy_version'],
        unique=False
    )
    
    # Index for audit queries
    op.create_index(
        'idx_created_updated_by',
        'coverage_policies',
        ['created_by', 'updated_by', 'updated_at'],
        unique=False
    )
    
    # MySQL-specific optimizations
    if op.get_bind().dialect.name == 'mysql':
        # Add MySQL-specific index hints and optimizations
        
        # Optimize for JSON column queries (MySQL 5.7+)
        op.execute("""
            ALTER TABLE authorization_requests 
            ADD INDEX idx_diagnosis_codes_json ((CAST(diagnosis_codes AS CHAR(255) ARRAY)))
        """)
        
        op.execute("""
            ALTER TABLE authorization_requests 
            ADD INDEX idx_procedure_codes_json ((CAST(procedure_codes AS CHAR(255) ARRAY)))
        """)
        
        # Optimize coverage criteria JSON queries
        op.execute("""
            ALTER TABLE coverage_policies 
            ADD INDEX idx_coverage_criteria_json ((CAST(coverage_criteria AS CHAR(1000))))
        """)


def downgrade():
    """Remove performance optimization indexes."""
    
    # Drop Authorization Requests indexes
    op.drop_index('idx_provider_status_submitted', table_name='authorization_requests')
    op.drop_index('idx_urgency_submitted', table_name='authorization_requests')
    op.drop_index('idx_status_updated_submitted', table_name='authorization_requests')
    op.drop_index('idx_procedure_type_status', table_name='authorization_requests')
    
    # Drop Authorization Decisions indexes
    op.drop_index('idx_status_decided_confidence', table_name='authorization_decisions')
    op.drop_index('idx_auth_number_valid_until', table_name='authorization_decisions')
    op.drop_index('idx_decided_at_status', table_name='authorization_decisions')
    
    # Drop Coverage Policies indexes
    op.drop_index('idx_payer_procedure_active_effective', table_name='coverage_policies')
    op.drop_index('idx_policy_type_active_effective', table_name='coverage_policies')
    op.drop_index('idx_expiration_active', table_name='coverage_policies')
    op.drop_index('idx_policy_name_version', table_name='coverage_policies')
    op.drop_index('idx_created_updated_by', table_name='coverage_policies')
    
    # Drop MySQL-specific indexes
    if op.get_bind().dialect.name == 'mysql':
        op.drop_index('idx_diagnosis_codes_json', table_name='authorization_requests')
        op.drop_index('idx_procedure_codes_json', table_name='authorization_requests')
        op.drop_index('idx_coverage_criteria_json', table_name='coverage_policies')