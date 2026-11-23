"""Registra o esquema inicial"""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def _create_table(name, *columns):
    if not sa.inspect(op.get_bind()).has_table(name):
        op.create_table(name, *columns)


def _create_index(name, table, columns, *, unique=False):
    existing = sa.inspect(op.get_bind()).get_indexes(table)
    if not any(index["name"] == name for index in existing):
        op.create_index(name, table, columns, unique=unique)


def _upgrade_legacy_readings():
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("readings")}
    additions = (
        sa.Column("received_at", sa.DateTime()),
        sa.Column("measured_ts", sa.BigInteger()),
        sa.Column("rssi", sa.Integer()),
        sa.Column("uptime_s", sa.Integer()),
        sa.Column("send_failures", sa.Integer()),
        sa.Column("reasons", sa.Text()),
        sa.Column("feedback", sa.String(16)),
        sa.Column("anomaly_types", sa.String(120)),
    )
    for column in additions:
        if column.name not in existing:
            op.add_column("readings", column)


def upgrade():
    _create_table('alert_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=True),
        sa.Column('device_id', sa.String(length=64), nullable=False),
        sa.Column('metric', sa.String(length=32), nullable=True),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('threshold', sa.Float(), nullable=True),
        sa.Column('message', sa.String(length=255), nullable=False),
        sa.Column('notified', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_alert_events_created_at'), 'alert_events', ['created_at'], unique=False)
    _create_table('alert_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('metric', sa.String(length=32), nullable=False),
        sa.Column('operator', sa.String(length=2), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('cooldown_s', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('device_id', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_table('app_settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    _create_table('readings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('device_id', sa.String(length=64), nullable=False),
        sa.Column('voltage', sa.Float(), nullable=False),
        sa.Column('current', sa.Float(), nullable=False),
        sa.Column('power', sa.Float(), nullable=False),
        sa.Column('energy', sa.Float(), nullable=False),
        sa.Column('frequency', sa.Float(), nullable=False),
        sa.Column('power_factor', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('measured_ts', sa.BigInteger(), nullable=True),
        sa.Column('is_anomaly', sa.Boolean(), nullable=False),
        sa.Column('anomaly_score', sa.Float(), nullable=True),
        sa.Column('rssi', sa.Integer(), nullable=True),
        sa.Column('uptime_s', sa.Integer(), nullable=True),
        sa.Column('send_failures', sa.Integer(), nullable=True),
        sa.Column('reasons', sa.Text(), nullable=True),
        sa.Column('feedback', sa.String(length=16), nullable=True),
        sa.Column('anomaly_types', sa.String(length=120), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _upgrade_legacy_readings()
    _create_index('ix_readings_device_created', 'readings', ['device_id', 'created_at'], unique=False)
    _create_index('ux_readings_device_measured', 'readings', ['device_id', 'measured_ts'], unique=True)
    _create_table('validations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('device_id', sa.String(length=64), nullable=False),
        sa.Column('quantity', sa.String(length=16), nullable=False),
        sa.Column('reference', sa.Float(), nullable=False),
        sa.Column('measured', sa.Float(), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_table('alert_deliveries',
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['alert_events.id'], ),
        sa.PrimaryKeyConstraint('event_id', 'channel'),
    )
    _create_index(op.f('ix_alert_deliveries_next_attempt_at'), 'alert_deliveries', ['next_attempt_at'], unique=False)


def downgrade():
    raise RuntimeError("A revisão inicial pode incorporar dados existentes. Restaure um backup para revertê-la.")
