"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2025-01-24 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# Remove MySQL-specific import

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema for Prior Authorization Agent."""
    
    # Create authorization_requests table
    op.create_table(
        'authorization_requests',
        sa.Column('request_id', sa.String(36), nullable=False),
        sa.Column('provider_id', sa.String(50), nullable=False),
        sa.Column('patient_demographics_encrypted', sa.Text(), nullable=False),
        sa.Column('diagnosis_codes', sa.JSON(), nullable=False),
        sa.Column('procedure_codes', sa.JSON(), nullable=False),
        sa.Column('clinical_notes_encrypted', sa.Text(), nullable=True),
        sa.Column('procedure_type', sa.String(20), nullable=False),
        sa.Column('urgency_level', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('request_id')
    )
    
    # Create indexes for authorization_requests
    op.create_index('idx_provider_status', 'authorization_requests', ['provider_id', 'status'])
    op.create_index('idx_submitted_at', 'authorization_requests', ['submitted_at'])
    op.create_index('idx_status_updated', 'authorization_requests', ['status', 'updated_at'])
    op.create_index(op.f('ix_authorization_requests_request_id'), 'authorization_requests', ['request_id'])
    op.create_index(op.f('ix_authorization_requests_provider_id'), 'authorization_requests', ['provider_id'])
    op.create_index(op.f('ix_authorization_requests_status'), 'authorization_requests', ['status'])
    
    # Create authorization_decisions table
    op.create_table(
        'authorization_decisions',
        sa.Column('decision_id', sa.String(36), nullable=False),
        sa.Column('request_id', sa.String(36), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('reasoning', sa.JSON(), nullable=False),
        sa.Column('policy_references', sa.JSON(), nullable=True),
        sa.Column('additional_info_needed', sa.JSON(), nullable=True),
        sa.Column('alternative_procedures', sa.JSON(), nullable=True),
        sa.Column('authorization_number', sa.String(50), nullable=True),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.Column('confidence_score', sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['request_id'], ['authorization_requests.request_id'], ),
        sa.PrimaryKeyConstraint('decision_id'),
        sa.UniqueConstraint('authorization_number')
    )
    
    # Create indexes for authorization_decisions
    op.create_index('idx_request_decided', 'authorization_decisions', ['request_id', 'decided_at'])
    op.create_index('idx_status_decided', 'authorization_decisions', ['status', 'decided_at'])
    op.create_index('idx_auth_number', 'authorization_decisions', ['authorization_number'])
    op.create_index(op.f('ix_authorization_decisions_decision_id'), 'authorization_decisions', ['decision_id'])
    op.create_index(op.f('ix_authorization_decisions_request_id'), 'authorization_decisions', ['request_id'])
    op.create_index(op.f('ix_authorization_decisions_status'), 'authorization_decisions', ['status'])
    op.create_index(op.f('ix_authorization_decisions_decided_at'), 'authorization_decisions', ['decided_at'])
    
    # Create coverage_policies table
    op.create_table(
        'coverage_policies',
        sa.Column('policy_id', sa.String(36), nullable=False),
        sa.Column('payer_id', sa.String(50), nullable=False),
        sa.Column('procedure_code', sa.String(10), nullable=False),
        sa.Column('diagnosis_codes', sa.JSON(), nullable=True),
        sa.Column('coverage_criteria', sa.JSON(), nullable=False),
        sa.Column('policy_type', sa.String(20), nullable=False),
        sa.Column('policy_name', sa.String(200), nullable=False),
        sa.Column('policy_version', sa.String(20), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('expiration_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(50), nullable=False),
        sa.Column('updated_by', sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint('policy_id')
    )
    
    # Create indexes for coverage_policies
    op.create_index('idx_payer_procedure', 'coverage_policies', ['payer_id', 'procedure_code'])
    op.create_index('idx_effective_date', 'coverage_policies', ['effective_date'])
    op.create_index('idx_active_policies', 'coverage_policies', ['is_active', 'effective_date'])
    op.create_index('idx_policy_type_active', 'coverage_policies', ['policy_type', 'is_active'])
    op.create_index(op.f('ix_coverage_policies_policy_id'), 'coverage_policies', ['policy_id'])
    op.create_index(op.f('ix_coverage_policies_payer_id'), 'coverage_policies', ['payer_id'])
    op.create_index(op.f('ix_coverage_policies_procedure_code'), 'coverage_policies', ['procedure_code'])
    op.create_index(op.f('ix_coverage_policies_policy_type'), 'coverage_policies', ['policy_type'])
    op.create_index(op.f('ix_coverage_policies_expiration_date'), 'coverage_policies', ['expiration_date'])
    op.create_index(op.f('ix_coverage_policies_is_active'), 'coverage_policies', ['is_active'])


def downgrade() -> None:
    """Drop all tables and indexes."""
    
    # Drop coverage_policies table and its indexes
    op.drop_index(op.f('ix_coverage_policies_is_active'), table_name='coverage_policies')
    op.drop_index(op.f('ix_coverage_policies_expiration_date'), table_name='coverage_policies')
    op.drop_index(op.f('ix_coverage_policies_policy_type'), table_name='coverage_policies')
    op.drop_index(op.f('ix_coverage_policies_procedure_code'), table_name='coverage_policies')
    op.drop_index(op.f('ix_coverage_policies_payer_id'), table_name='coverage_policies')
    op.drop_index(op.f('ix_coverage_policies_policy_id'), table_name='coverage_policies')
    op.drop_index('idx_policy_type_active', table_name='coverage_policies')
    op.drop_index('idx_active_policies', table_name='coverage_policies')
    op.drop_index('idx_effective_date', table_name='coverage_policies')
    op.drop_index('idx_payer_procedure', table_name='coverage_policies')
    op.drop_table('coverage_policies')
    
    # Drop authorization_decisions table and its indexes
    op.drop_index(op.f('ix_authorization_decisions_decided_at'), table_name='authorization_decisions')
    op.drop_index(op.f('ix_authorization_decisions_status'), table_name='authorization_decisions')
    op.drop_index(op.f('ix_authorization_decisions_request_id'), table_name='authorization_decisions')
    op.drop_index(op.f('ix_authorization_decisions_decision_id'), table_name='authorization_decisions')
    op.drop_index('idx_auth_number', table_name='authorization_decisions')
    op.drop_index('idx_status_decided', table_name='authorization_decisions')
    op.drop_index('idx_request_decided', table_name='authorization_decisions')
    op.drop_table('authorization_decisions')
    
    # Drop authorization_requests table and its indexes
    op.drop_index(op.f('ix_authorization_requests_status'), table_name='authorization_requests')
    op.drop_index(op.f('ix_authorization_requests_provider_id'), table_name='authorization_requests')
    op.drop_index(op.f('ix_authorization_requests_request_id'), table_name='authorization_requests')
    op.drop_index('idx_status_updated', table_name='authorization_requests')
    op.drop_index('idx_submitted_at', table_name='authorization_requests')
    op.drop_index('idx_provider_status', table_name='authorization_requests')
    op.drop_table('authorization_requests')