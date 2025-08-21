"""AI Configuration Schema

Revision ID: 005_ai_configuration_schema
Revises: 003_medical_codes_schema
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005_ai_configuration_schema'
down_revision = '003_medical_codes_schema'
branch_labels = None
depends_on = None


def upgrade():
    """Create AI configuration tables."""
    
    # Create ai_configurations table
    op.create_table(
        'ai_configurations',
        sa.Column('config_id', sa.String(36), primary_key=True, index=True),
        sa.Column('configuration_type', sa.String(50), nullable=False, index=True),
        sa.Column('configuration_name', sa.String(200), nullable=False),
        sa.Column('configuration_version', sa.String(20), nullable=False, default='1.0'),
        sa.Column('configuration_data', sa.JSON, nullable=False),
        sa.Column('effective_date', sa.Date, nullable=False, index=True),
        sa.Column('expiration_date', sa.Date, nullable=True, index=True),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True, index=True),
        sa.Column('parent_config_id', sa.String(36), nullable=True, index=True),
        sa.Column('change_summary', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_by', sa.String(50), nullable=False),
        sa.Column('updated_by', sa.String(50), nullable=False)
    )
    
    # Create indexes for ai_configurations
    op.create_index('idx_config_type_active', 'ai_configurations', ['configuration_type', 'is_active'])
    op.create_index('idx_config_version', 'ai_configurations', ['config_id', 'configuration_version'])
    op.create_index('idx_parent_config', 'ai_configurations', ['parent_config_id'])
    
    # Create model_performance_metrics table
    op.create_table(
        'model_performance_metrics',
        sa.Column('metric_id', sa.String(36), primary_key=True, index=True),
        sa.Column('model_id', sa.String(100), nullable=False, index=True),
        sa.Column('model_name', sa.String(200), nullable=False),
        sa.Column('accuracy_score', sa.Numeric(5, 4), nullable=False, default=0.0),
        sa.Column('precision_score', sa.Numeric(5, 4), nullable=False, default=0.0),
        sa.Column('recall_score', sa.Numeric(5, 4), nullable=False, default=0.0),
        sa.Column('f1_score', sa.Numeric(5, 4), nullable=False, default=0.0),
        sa.Column('average_response_time_ms', sa.Numeric(10, 2), nullable=False, default=0.0),
        sa.Column('success_rate', sa.Numeric(5, 4), nullable=False, default=0.0),
        sa.Column('error_rate', sa.Numeric(5, 4), nullable=False, default=0.0),
        sa.Column('total_requests', sa.Integer, nullable=False, default=0),
        sa.Column('successful_requests', sa.Integer, nullable=False, default=0),
        sa.Column('failed_requests', sa.Integer, nullable=False, default=0),
        sa.Column('total_cost', sa.Numeric(10, 4), nullable=False, default=0.0),
        sa.Column('cost_per_request', sa.Numeric(8, 6), nullable=False, default=0.0),
        sa.Column('measurement_start', sa.DateTime, nullable=False, index=True),
        sa.Column('measurement_end', sa.DateTime, nullable=False, index=True),
        sa.Column('last_updated', sa.DateTime, nullable=False, default=sa.func.now(), onupdate=sa.func.now())
    )
    
    # Create indexes for model_performance_metrics
    op.create_index('idx_model_time_range', 'model_performance_metrics', ['model_id', 'measurement_start', 'measurement_end'])
    op.create_index('idx_performance_ranking', 'model_performance_metrics', ['accuracy_score', 'average_response_time_ms'])
    op.create_index('idx_cost_efficiency', 'model_performance_metrics', ['cost_per_request', 'success_rate'])
    
    # Create configuration_audit_logs table
    op.create_table(
        'configuration_audit_logs',
        sa.Column('audit_id', sa.String(36), primary_key=True, index=True),
        sa.Column('configuration_type', sa.String(50), nullable=False, index=True),
        sa.Column('config_id', sa.String(36), nullable=False, index=True),
        sa.Column('action', sa.String(20), nullable=False, index=True),
        sa.Column('old_values', sa.JSON, nullable=True),
        sa.Column('new_values', sa.JSON, nullable=True),
        sa.Column('change_summary', sa.Text, nullable=True),
        sa.Column('user_id', sa.String(50), nullable=False, index=True),
        sa.Column('user_role', sa.String(50), nullable=False),
        sa.Column('timestamp', sa.DateTime, nullable=False, default=sa.func.now(), index=True),
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('approval_required', sa.Boolean, nullable=False, default=False),
        sa.Column('approved_by', sa.String(50), nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True)
    )
    
    # Create indexes for configuration_audit_logs
    op.create_index('idx_config_audit', 'configuration_audit_logs', ['config_id', 'timestamp'])
    op.create_index('idx_user_audit', 'configuration_audit_logs', ['user_id', 'timestamp'])
    op.create_index('idx_action_audit', 'configuration_audit_logs', ['action', 'timestamp'])
    op.create_index('idx_approval_audit', 'configuration_audit_logs', ['approval_required', 'approved_at'])
    
    # Create ai_feedback table
    op.create_table(
        'ai_feedback',
        sa.Column('feedback_id', sa.String(36), primary_key=True, index=True),
        sa.Column('decision_id', sa.String(36), sa.ForeignKey('authorization_decisions.decision_id'), nullable=False, index=True),
        sa.Column('request_id', sa.String(36), sa.ForeignKey('authorization_requests.request_id'), nullable=False, index=True),
        sa.Column('feedback_type', sa.String(50), nullable=False, index=True),
        sa.Column('feedback_score', sa.Numeric(3, 2), nullable=False),
        sa.Column('feedback_text', sa.Text, nullable=True),
        sa.Column('feedback_source', sa.String(50), nullable=False, index=True),
        sa.Column('source_user_id', sa.String(50), nullable=True, index=True),
        sa.Column('source_role', sa.String(50), nullable=True),
        sa.Column('model_id', sa.String(100), nullable=False, index=True),
        sa.Column('model_version', sa.String(20), nullable=True),
        sa.Column('original_confidence', sa.Numeric(3, 2), nullable=False),
        sa.Column('processed', sa.Boolean, nullable=False, default=False, index=True),
        sa.Column('processed_at', sa.DateTime, nullable=True),
        sa.Column('processing_notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, default=sa.func.now(), index=True)
    )
    
    # Create indexes for ai_feedback
    op.create_index('idx_feedback_model', 'ai_feedback', ['model_id', 'feedback_type'])
    op.create_index('idx_feedback_processing', 'ai_feedback', ['processed', 'created_at'])
    op.create_index('idx_feedback_source', 'ai_feedback', ['feedback_source', 'created_at'])
    op.create_index('idx_decision_feedback', 'ai_feedback', ['decision_id', 'feedback_type'])
    
    # Add check constraints
    op.create_check_constraint(
        'ck_ai_configurations_config_type',
        'ai_configurations',
        "configuration_type IN ('llm_model', 'decision_threshold', 'escalation_rule', 'clinical_guideline', 'feedback_rule')"
    )
    
    op.create_check_constraint(
        'ck_model_performance_scores',
        'model_performance_metrics',
        "accuracy_score >= 0.0 AND accuracy_score <= 1.0 AND "
        "precision_score >= 0.0 AND precision_score <= 1.0 AND "
        "recall_score >= 0.0 AND recall_score <= 1.0 AND "
        "f1_score >= 0.0 AND f1_score <= 1.0 AND "
        "success_rate >= 0.0 AND success_rate <= 1.0 AND "
        "error_rate >= 0.0 AND error_rate <= 1.0"
    )
    
    op.create_check_constraint(
        'ck_model_performance_counts',
        'model_performance_metrics',
        "total_requests >= 0 AND successful_requests >= 0 AND failed_requests >= 0 AND "
        "total_cost >= 0.0 AND cost_per_request >= 0.0"
    )
    
    op.create_check_constraint(
        'ck_audit_action',
        'configuration_audit_logs',
        "action IN ('CREATE', 'UPDATE', 'DELETE', 'ACTIVATE', 'DEACTIVATE', 'APPROVE', 'REJECT')"
    )
    
    op.create_check_constraint(
        'ck_feedback_score',
        'ai_feedback',
        "feedback_score >= -1.0 AND feedback_score <= 1.0"
    )
    
    op.create_check_constraint(
        'ck_feedback_type',
        'ai_feedback',
        "feedback_type IN ('decision_accuracy', 'reasoning_quality', 'policy_compliance', 'clinical_appropriateness')"
    )
    
    op.create_check_constraint(
        'ck_feedback_source',
        'ai_feedback',
        "feedback_source IN ('PROVIDER', 'PAYER', 'EXPERT', 'SYSTEM', 'PATIENT')"
    )
    
    op.create_check_constraint(
        'ck_original_confidence',
        'ai_feedback',
        "original_confidence >= 0.0 AND original_confidence <= 1.0"
    )


def downgrade():
    """Drop AI configuration tables."""
    
    # Drop check constraints
    op.drop_constraint('ck_original_confidence', 'ai_feedback')
    op.drop_constraint('ck_feedback_source', 'ai_feedback')
    op.drop_constraint('ck_feedback_type', 'ai_feedback')
    op.drop_constraint('ck_feedback_score', 'ai_feedback')
    op.drop_constraint('ck_audit_action', 'configuration_audit_logs')
    op.drop_constraint('ck_model_performance_counts', 'model_performance_metrics')
    op.drop_constraint('ck_model_performance_scores', 'model_performance_metrics')
    op.drop_constraint('ck_ai_configurations_config_type', 'ai_configurations')
    
    # Drop indexes
    op.drop_index('idx_decision_feedback', 'ai_feedback')
    op.drop_index('idx_feedback_source', 'ai_feedback')
    op.drop_index('idx_feedback_processing', 'ai_feedback')
    op.drop_index('idx_feedback_model', 'ai_feedback')
    
    op.drop_index('idx_approval_audit', 'configuration_audit_logs')
    op.drop_index('idx_action_audit', 'configuration_audit_logs')
    op.drop_index('idx_user_audit', 'configuration_audit_logs')
    op.drop_index('idx_config_audit', 'configuration_audit_logs')
    
    op.drop_index('idx_cost_efficiency', 'model_performance_metrics')
    op.drop_index('idx_performance_ranking', 'model_performance_metrics')
    op.drop_index('idx_model_time_range', 'model_performance_metrics')
    
    op.drop_index('idx_parent_config', 'ai_configurations')
    op.drop_index('idx_config_version', 'ai_configurations')
    op.drop_index('idx_config_type_active', 'ai_configurations')
    
    # Drop tables
    op.drop_table('ai_feedback')
    op.drop_table('configuration_audit_logs')
    op.drop_table('model_performance_metrics')
    op.drop_table('ai_configurations')