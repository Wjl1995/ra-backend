"""structure navigation: document structure_json

Revision ID: 3a1b2c4d5e6f
Revises: 2bb813c0723d
Create Date: 2026-08-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a1b2c4d5e6f'
down_revision: Union[str, Sequence[str], None] = '2bb813c0723d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'documents',
        sa.Column('structure_status', sa.String(length=16), nullable=False, server_default='pending'),
    )
    op.add_column(
        'documents',
        sa.Column('structure_json', sa.Text(), nullable=False, server_default='{}'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'structure_json')
    op.drop_column('documents', 'structure_status')
