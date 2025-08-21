"""Add medical codes database schema

Revision ID: 003_medical_codes_schema
Revises: 002_performance_indexes
Create Date: 2025-01-29 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_medical_codes_schema'
down_revision: Union[str, None] = '002_performance_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create medical codes database schema."""
    
    # Create icd10_codes table
    op.create_table(
        'icd10_codes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('short_description', sa.String(255), nullable=True),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('subcategory', sa.String(100), nullable=True),
        sa.Column('chapter', sa.String(100), nullable=True),
        sa.Column('billable', sa.Boolean(), nullable=False, default=True),
        sa.Column('gender_specific', sa.String(1), nullable=True),
        sa.Column('age_restrictions', sa.JSON(), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('version', sa.String(20), nullable=False, default='2024'),
        sa.Column('search_terms', sa.Text(), nullable=True),
        sa.Column('synonyms', sa.JSON(), nullable=True),
        sa.Column('severity_level', sa.String(20), nullable=True),
        sa.Column('chronic_condition', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('created_by', sa.String(50), nullable=False, default='system'),
        sa.Column('updated_by', sa.String(50), nullable=False, default='system'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    
    # Create indexes for icd10_codes
    op.create_index('idx_icd10_code_billable', 'icd10_codes', ['code', 'billable'])
    op.create_index('idx_icd10_category_valid', 'icd10_codes', ['category', 'valid_from', 'valid_to'])
    op.create_index('idx_icd10_chapter_category', 'icd10_codes', ['chapter', 'category'])
    op.create_index('idx_icd10_gender_age', 'icd10_codes', ['gender_specific', 'billable'])
    op.create_index('idx_icd10_version_valid', 'icd10_codes', ['version', 'valid_from'])
    op.create_index('idx_icd10_chronic_severity', 'icd10_codes', ['chronic_condition', 'severity_level'])
    op.create_index(op.f('ix_icd10_codes_code'), 'icd10_codes', ['code'])
    op.create_index(op.f('ix_icd10_codes_category'), 'icd10_codes', ['category'])
    op.create_index(op.f('ix_icd10_codes_subcategory'), 'icd10_codes', ['subcategory'])
    op.create_index(op.f('ix_icd10_codes_chapter'), 'icd10_codes', ['chapter'])
    op.create_index(op.f('ix_icd10_codes_billable'), 'icd10_codes', ['billable'])
    op.create_index(op.f('ix_icd10_codes_valid_from'), 'icd10_codes', ['valid_from'])
    op.create_index(op.f('ix_icd10_codes_valid_to'), 'icd10_codes', ['valid_to'])
    
    # Create cpt_codes table
    op.create_table(
        'cpt_codes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('short_description', sa.String(255), nullable=True),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('subcategory', sa.String(100), nullable=True),
        sa.Column('section', sa.String(100), nullable=True),
        sa.Column('code_type', sa.String(20), nullable=False, default='CPT'),
        sa.Column('modifier_allowed', sa.Boolean(), nullable=False, default=True),
        sa.Column('bilateral_surgery', sa.Boolean(), nullable=False, default=False),
        sa.Column('assistant_surgery', sa.Boolean(), nullable=False, default=False),
        sa.Column('multiple_procedure', sa.Boolean(), nullable=False, default=True),
        sa.Column('work_rvu', sa.DECIMAL(6, 2), nullable=True),
        sa.Column('practice_expense_rvu', sa.DECIMAL(6, 2), nullable=True),
        sa.Column('malpractice_rvu', sa.DECIMAL(6, 2), nullable=True),
        sa.Column('total_rvu', sa.DECIMAL(6, 2), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('version', sa.String(20), nullable=False, default='2024'),
        sa.Column('search_terms', sa.Text(), nullable=True),
        sa.Column('synonyms', sa.JSON(), nullable=True),
        sa.Column('procedure_type', sa.String(50), nullable=True),
        sa.Column('body_system', sa.String(50), nullable=True),
        sa.Column('imaging_required', sa.Boolean(), nullable=False, default=False),
        sa.Column('anesthesia_required', sa.Boolean(), nullable=False, default=False),
        sa.Column('prior_auth_required', sa.Boolean(), nullable=False, default=False),
        sa.Column('medical_necessity_level', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('created_by', sa.String(50), nullable=False, default='system'),
        sa.Column('updated_by', sa.String(50), nullable=False, default='system'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    
    # Create indexes for cpt_codes
    op.create_index('idx_cpt_code_type', 'cpt_codes', ['code', 'code_type'])
    op.create_index('idx_cpt_category_valid', 'cpt_codes', ['category', 'valid_from', 'valid_to'])
    op.create_index('idx_cpt_procedure_type', 'cpt_codes', ['procedure_type', 'body_system'])
    op.create_index('idx_cpt_prior_auth', 'cpt_codes', ['prior_auth_required', 'medical_necessity_level'])
    op.create_index('idx_cpt_billing_props', 'cpt_codes', ['bilateral_surgery', 'assistant_surgery'])
    op.create_index('idx_cpt_version_valid', 'cpt_codes', ['version', 'valid_from'])
    op.create_index('idx_cpt_rvu_total', 'cpt_codes', ['total_rvu'])
    op.create_index(op.f('ix_cpt_codes_code'), 'cpt_codes', ['code'])
    op.create_index(op.f('ix_cpt_codes_category'), 'cpt_codes', ['category'])
    op.create_index(op.f('ix_cpt_codes_subcategory'), 'cpt_codes', ['subcategory'])
    op.create_index(op.f('ix_cpt_codes_section'), 'cpt_codes', ['section'])
    op.create_index(op.f('ix_cpt_codes_code_type'), 'cpt_codes', ['code_type'])
    op.create_index(op.f('ix_cpt_codes_procedure_type'), 'cpt_codes', ['procedure_type'])
    op.create_index(op.f('ix_cpt_codes_body_system'), 'cpt_codes', ['body_system'])
    op.create_index(op.f('ix_cpt_codes_prior_auth_required'), 'cpt_codes', ['prior_auth_required'])
    op.create_index(op.f('ix_cpt_codes_valid_from'), 'cpt_codes', ['valid_from'])
    op.create_index(op.f('ix_cpt_codes_valid_to'), 'cpt_codes', ['valid_to'])
    
    # Create code_relationships table
    op.create_table(
        'code_relationships',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('primary_code_id', sa.Integer(), nullable=False),
        sa.Column('primary_code_type', sa.String(10), nullable=False),
        sa.Column('related_code_id', sa.Integer(), nullable=False),
        sa.Column('related_code_type', sa.String(10), nullable=False),
        sa.Column('relationship_type', sa.String(50), nullable=False),
        sa.Column('strength', sa.DECIMAL(3, 2), nullable=False, default=1.0),
        sa.Column('confidence', sa.DECIMAL(3, 2), nullable=False, default=1.0),
        sa.Column('clinical_rationale', sa.Text(), nullable=True),
        sa.Column('evidence_level', sa.String(20), nullable=True),
        sa.Column('guideline_reference', sa.String(255), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=False, default=sa.func.current_date()),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('created_by', sa.String(50), nullable=False, default='system'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for code_relationships
    op.create_index('idx_relationship_primary', 'code_relationships', ['primary_code_id', 'primary_code_type'])
    op.create_index('idx_relationship_related', 'code_relationships', ['related_code_id', 'related_code_type'])
    op.create_index('idx_relationship_type_active', 'code_relationships', ['relationship_type', 'is_active'])
    op.create_index('idx_relationship_strength', 'code_relationships', ['strength', 'confidence'])
    op.create_index('idx_relationship_valid', 'code_relationships', ['valid_from', 'valid_to', 'is_active'])
    op.create_index(op.f('ix_code_relationships_primary_code_id'), 'code_relationships', ['primary_code_id'])
    op.create_index(op.f('ix_code_relationships_related_code_id'), 'code_relationships', ['related_code_id'])
    op.create_index(op.f('ix_code_relationships_relationship_type'), 'code_relationships', ['relationship_type'])
    op.create_index(op.f('ix_code_relationships_is_active'), 'code_relationships', ['is_active'])
    
    # Create full-text search indexes for PostgreSQL
    if op.get_bind().dialect.name == 'postgresql':
        # Create GIN indexes for full-text search on ICD-10 codes
        op.execute("""
            CREATE INDEX idx_icd10_description_fts 
            ON icd10_codes 
            USING gin(to_tsvector('english', description))
        """)
        
        op.execute("""
            CREATE INDEX idx_icd10_search_terms_fts 
            ON icd10_codes 
            USING gin(to_tsvector('english', coalesce(search_terms, '')))
        """)
        
        # Create GIN indexes for full-text search on CPT codes
        op.execute("""
            CREATE INDEX idx_cpt_description_fts 
            ON cpt_codes 
            USING gin(to_tsvector('english', description))
        """)
        
        op.execute("""
            CREATE INDEX idx_cpt_search_terms_fts 
            ON cpt_codes 
            USING gin(to_tsvector('english', coalesce(search_terms, '')))
        """)
        
        # Create composite indexes for common query patterns
        op.execute("""
            CREATE INDEX idx_icd10_valid_billable_category 
            ON icd10_codes (valid_from, valid_to, billable, category) 
            WHERE billable = true
        """)
        
        op.execute("""
            CREATE INDEX idx_cpt_valid_prior_auth_category 
            ON cpt_codes (valid_from, valid_to, prior_auth_required, category) 
            WHERE prior_auth_required = true
        """)
        
        # Create partial indexes for active relationships
        op.execute("""
            CREATE INDEX idx_active_relationships_by_primary 
            ON code_relationships (primary_code_id, primary_code_type, relationship_type) 
            WHERE is_active = true AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
        """)
        
        op.execute("""
            CREATE INDEX idx_active_relationships_by_related 
            ON code_relationships (related_code_id, related_code_type, relationship_type) 
            WHERE is_active = true AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
        """)


def downgrade() -> None:
    """Drop medical codes database schema."""
    
    # Drop PostgreSQL-specific indexes first
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP INDEX IF EXISTS idx_active_relationships_by_related")
        op.execute("DROP INDEX IF EXISTS idx_active_relationships_by_primary")
        op.execute("DROP INDEX IF EXISTS idx_cpt_valid_prior_auth_category")
        op.execute("DROP INDEX IF EXISTS idx_icd10_valid_billable_category")
        op.execute("DROP INDEX IF EXISTS idx_cpt_search_terms_fts")
        op.execute("DROP INDEX IF EXISTS idx_cpt_description_fts")
        op.execute("DROP INDEX IF EXISTS idx_icd10_search_terms_fts")
        op.execute("DROP INDEX IF EXISTS idx_icd10_description_fts")
    
    # Drop code_relationships table and its indexes
    op.drop_index(op.f('ix_code_relationships_is_active'), table_name='code_relationships')
    op.drop_index(op.f('ix_code_relationships_relationship_type'), table_name='code_relationships')
    op.drop_index(op.f('ix_code_relationships_related_code_id'), table_name='code_relationships')
    op.drop_index(op.f('ix_code_relationships_primary_code_id'), table_name='code_relationships')
    op.drop_index('idx_relationship_valid', table_name='code_relationships')
    op.drop_index('idx_relationship_strength', table_name='code_relationships')
    op.drop_index('idx_relationship_type_active', table_name='code_relationships')
    op.drop_index('idx_relationship_related', table_name='code_relationships')
    op.drop_index('idx_relationship_primary', table_name='code_relationships')
    op.drop_table('code_relationships')
    
    # Drop cpt_codes table and its indexes
    op.drop_index(op.f('ix_cpt_codes_valid_to'), table_name='cpt_codes')
    op.drop_index(op.f('ix_cpt_codes_valid_from'), table_name='cpt_codes')
    op.drop_index(op.f('ix_cpt_codes_prior_auth_required'), table_name='cpt_codes')
    op.drop_index(op.f('ix_cpt_codes_body_system'), table_name='cpt_codes')
    op.drop_index(op.f('ix_cpt_codes_procedure_type'), table_name='cpt_codes')
    op.drop_index(op.f('ix_cpt_codes_code_type'), table_name='cpt_codes')
    op.drop_index(op.f('ix_cpt_codes_section'), table_name='cpt_codes')
    op.drop_index(op.f('ix_cpt_codes_subcategory'), table_name='cpt_codes')
    op.drop_index(op.f('ix_cpt_codes_category'), table_name='cpt_codes')
    op.drop_index(op.f('ix_cpt_codes_code'), table_name='cpt_codes')
    op.drop_index('idx_cpt_rvu_total', table_name='cpt_codes')
    op.drop_index('idx_cpt_version_valid', table_name='cpt_codes')
    op.drop_index('idx_cpt_billing_props', table_name='cpt_codes')
    op.drop_index('idx_cpt_prior_auth', table_name='cpt_codes')
    op.drop_index('idx_cpt_procedure_type', table_name='cpt_codes')
    op.drop_index('idx_cpt_category_valid', table_name='cpt_codes')
    op.drop_index('idx_cpt_code_type', table_name='cpt_codes')
    op.drop_table('cpt_codes')
    
    # Drop icd10_codes table and its indexes
    op.drop_index(op.f('ix_icd10_codes_valid_to'), table_name='icd10_codes')
    op.drop_index(op.f('ix_icd10_codes_valid_from'), table_name='icd10_codes')
    op.drop_index(op.f('ix_icd10_codes_billable'), table_name='icd10_codes')
    op.drop_index(op.f('ix_icd10_codes_chapter'), table_name='icd10_codes')
    op.drop_index(op.f('ix_icd10_codes_subcategory'), table_name='icd10_codes')
    op.drop_index(op.f('ix_icd10_codes_category'), table_name='icd10_codes')
    op.drop_index(op.f('ix_icd10_codes_code'), table_name='icd10_codes')
    op.drop_index('idx_icd10_chronic_severity', table_name='icd10_codes')
    op.drop_index('idx_icd10_version_valid', table_name='icd10_codes')
    op.drop_index('idx_icd10_gender_age', table_name='icd10_codes')
    op.drop_index('idx_icd10_chapter_category', table_name='icd10_codes')
    op.drop_index('idx_icd10_category_valid', table_name='icd10_codes')
    op.drop_index('idx_icd10_code_billable', table_name='icd10_codes')
    op.drop_table('icd10_codes')