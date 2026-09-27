"""add_composite_tenant_foreign_keys

Revision ID: 7c5c02e406e5
Revises: 6040860e7e48
Create Date: 2026-09-26 18:13:08.931955

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c5c02e406e5'
down_revision: Union[str, Sequence[str], None] = '6040860e7e48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to enforce composite multi-tenant foreign keys."""
    # 1. Create composite unique constraints on parent tables first
    op.create_unique_constraint('uq_trackers_id_org', 'trackers', ['id', 'organization_id'])
    op.create_unique_constraint('uq_shipments_id_org', 'shipments', ['id', 'organization_id'])

    # 2. Drop old single-column foreign keys
    op.drop_constraint('shipments_tracker_id_fkey', 'shipments', type_='foreignkey')
    op.drop_constraint('telemetry_tracker_id_fkey', 'telemetry', type_='foreignkey')
    op.drop_constraint('telemetry_shipment_id_fkey', 'telemetry', type_='foreignkey')
    op.drop_constraint('alerts_tracker_id_fkey', 'alerts', type_='foreignkey')
    op.drop_constraint('alerts_shipment_id_fkey', 'alerts', type_='foreignkey')

    # 3. Create composite foreign keys ensuring cross-tenant isolation
    op.create_foreign_key(
        'fk_shipments_tracker_org',
        'shipments', 'trackers',
        ['tracker_id', 'organization_id'], ['id', 'organization_id'],
        ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'fk_telemetry_tracker_org',
        'telemetry', 'trackers',
        ['tracker_id', 'organization_id'], ['id', 'organization_id'],
        ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'fk_telemetry_shipment_org',
        'telemetry', 'shipments',
        ['shipment_id', 'organization_id'], ['id', 'organization_id'],
        ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'fk_alerts_tracker_org',
        'alerts', 'trackers',
        ['tracker_id', 'organization_id'], ['id', 'organization_id'],
        ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'fk_alerts_shipment_org',
        'alerts', 'shipments',
        ['shipment_id', 'organization_id'], ['id', 'organization_id'],
        ondelete='RESTRICT',
    )


def downgrade() -> None:
    """Downgrade schema to revert composite foreign keys."""
    # 1. Drop composite foreign keys
    op.drop_constraint('fk_alerts_shipment_org', 'alerts', type_='foreignkey')
    op.drop_constraint('fk_alerts_tracker_org', 'alerts', type_='foreignkey')
    op.drop_constraint('fk_telemetry_shipment_org', 'telemetry', type_='foreignkey')
    op.drop_constraint('fk_telemetry_tracker_org', 'telemetry', type_='foreignkey')
    op.drop_constraint('fk_shipments_tracker_org', 'shipments', type_='foreignkey')

    # 2. Restore single-column foreign keys
    op.create_foreign_key('alerts_tracker_id_fkey', 'alerts', 'trackers', ['tracker_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('alerts_shipment_id_fkey', 'alerts', 'shipments', ['shipment_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('telemetry_tracker_id_fkey', 'telemetry', 'trackers', ['tracker_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('telemetry_shipment_id_fkey', 'telemetry', 'shipments', ['shipment_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('shipments_tracker_id_fkey', 'shipments', 'trackers', ['tracker_id'], ['id'], ondelete='RESTRICT')

    # 3. Drop composite unique constraints
    op.drop_constraint('uq_shipments_id_org', 'shipments', type_='unique')
    op.drop_constraint('uq_trackers_id_org', 'trackers', type_='unique')
