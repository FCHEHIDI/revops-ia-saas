from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg
from datetime import datetime

def upgrade():
    # 1. organizations
    op.create_table(
        'organizations',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), unique=True, nullable=False),
        sa.Column('plan', sa.String(50), default='free'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )
    # 2. users
    op.create_table(
        'users',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', pg.UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('roles', pg.ARRAY(sa.String), default=list),
        sa.Column('permissions', pg.ARRAY(sa.String), default=list),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    # 3. refresh_tokens
    op.create_table(
        'refresh_tokens',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    # 4. user_sessions
    op.create_table(
        'user_sessions',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('org_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('messages', pg.JSONB, nullable=False, default=list),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True)
    )
    # 5. documents
    op.create_table(
        'documents',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('storage_path', sa.String(500), nullable=False),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    # 6. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', pg.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource', sa.String(100), nullable=False),
        sa.Column('payload', pg.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.execute('ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;')
    op.execute("""
        CREATE POLICY tenant_isolation ON user_sessions
        USING (org_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (org_id::text = current_setting('app.current_tenant_id', true));
    """)
    op.execute('ALTER TABLE documents ENABLE ROW LEVEL SECURITY;')
    op.execute("""
        CREATE POLICY tenant_isolation ON documents
        USING (org_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (org_id::text = current_setting('app.current_tenant_id', true));
    """)
    op.execute('ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;')
    op.execute("""
        CREATE POLICY tenant_isolation ON audit_logs
        USING (org_id::text = current_setting('app.current_tenant_id', true));
    """)

def downgrade():
    op.drop_table('audit_logs')
    op.drop_table('documents')
    op.drop_table('user_sessions')
    op.drop_table('refresh_tokens')
    op.drop_table('users')
    op.drop_table('organizations')
