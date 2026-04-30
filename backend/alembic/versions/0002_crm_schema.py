from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade():
    # accounts
    op.create_table(
        'accounts',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', pg.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255)),
        sa.Column('industry', sa.String(100)),
        sa.Column('size', sa.String(50)),
        sa.Column('arr', sa.Numeric(14, 2)),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('created_by', pg.UUID(as_uuid=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_accounts_org_name', 'org_id', 'name'),
    )
    # contacts
    op.create_table(
        'contacts',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', pg.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('account_id', pg.UUID(as_uuid=True), sa.ForeignKey('accounts.id'), nullable=True),
        sa.Column('first_name', sa.String(255), nullable=False),
        sa.Column('last_name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(50)),
        sa.Column('job_title', sa.String(150)),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('created_by', pg.UUID(as_uuid=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.UniqueConstraint('org_id', 'email', name='uq_contacts_org_email'),
        sa.PrimaryKeyConstraint('id'),
    )
    # deals
    op.create_table(
        'deals',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', pg.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('account_id', pg.UUID(as_uuid=True), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('contact_id', pg.UUID(as_uuid=True), sa.ForeignKey('contacts.id'), nullable=True),
        sa.Column('owner_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('stage', sa.String(50), nullable=False),
        sa.Column('amount', sa.Numeric(14, 2)),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),
        sa.Column('close_date', sa.Date()),
        sa.Column('probability', sa.SmallInteger()),
        sa.Column('notes', sa.Text()),
        sa.Column('created_by', pg.UUID(as_uuid=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_deals_org_stage', 'org_id', 'stage'),
        sa.Index('ix_deals_org_owner', 'org_id', 'owner_id'),
    )
    # RLS : Enable + Policy
    for table in ["accounts", "contacts", "deals"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""
        CREATE POLICY tenant_isolation ON {table} \
        USING (org_id::text = current_setting('app.current_tenant_id', true)) \
        WITH CHECK (org_id::text = current_setting('app.current_tenant_id', true));
        """)

def downgrade():
    for table in ["deals", "contacts", "accounts"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        op.drop_table(table)
