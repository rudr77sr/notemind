"""add description to document

Revision ID: 93742b5eb07b
Revises: 
Create Date: 2026-10-05 20:18:02.575166

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '93742b5eb07b'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # remove chunks whose document no longer exists
    op.execute(
        "DELETE FROM chunk WHERE document_id NOT IN (SELECT file_id FROM document)"
    )
    op.create_foreign_key('chunk_document_id_fkey', 'chunk', 'document', ['document_id'], ['file_id'])
    op.add_column('document', sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('document', 'description')
    op.drop_constraint('chunk_document_id_fkey', 'chunk', type_='foreignkey')


def downgrade() -> None:
    op.drop_column('document', 'description')
    op.drop_constraint('chunk_document_id_fkey', 'chunk', type_='foreignkey')