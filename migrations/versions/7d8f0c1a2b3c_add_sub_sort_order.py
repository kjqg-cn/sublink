"""add subscription sort order

Revision ID: 7d8f0c1a2b3c
Revises: 4e76f839124e
"""
from alembic import op
import sqlalchemy as sa


revision = '7d8f0c1a2b3c'
down_revision = '4e76f839124e'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {column['name'] for column in sa.inspect(connection).get_columns('sub')}
    if 'sort_order' not in columns:
        with op.batch_alter_table('sub', schema=None) as batch_op:
            batch_op.add_column(sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))

    groups = connection.execute(sa.text(
        'SELECT name, MIN(id), COUNT(DISTINCT sort_order), MIN(sort_order), '
        'SUM(CASE WHEN sort_order IS NULL THEN 1 ELSE 0 END) '
        'FROM sub GROUP BY name ORDER BY MIN(id)'
    )).fetchall()
    orders = [row[3] for row in groups]
    valid = all(row[2] == 1 and row[3] is not None and row[4] == 0 for row in groups)
    valid = valid and sorted(orders) == list(range(len(groups)))
    if valid:
        return
    groups.sort(key=lambda row: (
        row[3] is None,
        row[3] if row[3] is not None else 0,
        row[1]
    ))
    for index, row in enumerate(groups):
        connection.execute(
            sa.text(
                'UPDATE sub SET sort_order = :sort_order '
                'WHERE (name = :name) OR (name IS NULL AND :name IS NULL)'
            ),
            {'sort_order': index, 'name': row[0]}
        )


def downgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('sub')}
    if 'sort_order' in columns:
        with op.batch_alter_table('sub', schema=None) as batch_op:
            batch_op.drop_column('sort_order')
