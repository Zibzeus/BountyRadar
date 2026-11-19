from alembic import op
from radar.db import meta

revision = "0001"
down_revision = None


def upgrade():
    meta.create_all(op.get_bind())


def downgrade():
    raise RuntimeError("Restore the pre-migration backup to roll back.")
