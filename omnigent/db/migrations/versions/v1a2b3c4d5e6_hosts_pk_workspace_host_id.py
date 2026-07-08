"""Change hosts primary key to (workspace_id, host_id).

Revision ID: v1a2b3c4d5e6
Revises: u1a2b3c4d5e6
Create Date: 2026-07-07 00:00:00.000000

Previously the ``hosts`` PK was ``(workspace_id, owner, name)`` with
``host_id`` carrying its own ``UNIQUE`` constraint (``uq_hosts_host_id``).
This migration promotes ``host_id`` into the PK alongside ``workspace_id``,
demotes ``owner`` and ``name`` to regular NOT NULL columns, drops the now-
redundant ``uq_hosts_host_id`` constraint, and adds a new
``uq_hosts_workspace_owner_name`` unique constraint so the upsert-on-connect
rotation logic (which looks up by ``(workspace_id, owner, name)`` to detect a
rotated ``host_id``) remains consistent.

SQLite cannot ALTER a primary key in place, so upgrade/downgrade both use
``batch_alter_table(recreate="always")`` with ``copy_from`` supplying an
explicit table definition that declares the desired PK — Alembic then
rebuilds the table from scratch against that spec.

Upgrade path:
  1. PRAGMA foreign_keys = OFF (SQLite only)
  2. Batch-recreate "hosts" with PK (workspace_id, host_id),
     drop uq_hosts_host_id, add uq_hosts_workspace_owner_name.
  3. PRAGMA foreign_keys = ON (SQLite only)

Downgrade path:
  Reverse — recreate with PK (workspace_id, owner, name),
  drop uq_hosts_workspace_owner_name, restore uq_hosts_host_id.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v1a2b3c4d5e6"
down_revision: str | None = "u1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


# Explicit table spec used as the ``copy_from`` reference for batch
# recreate. Alembic uses this definition (not the live schema) when
# building the replacement table, so the PK and constraints in the spec
# are the ones that end up in the recreated table.
_UPGRADED_TABLE = sa.Table(
    "hosts",
    sa.MetaData(),
    sa.Column("workspace_id", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("host_id", sa.String(64), nullable=False),
    sa.Column("owner", sa.String(256), nullable=False),
    sa.Column("name", sa.String(64), nullable=False),
    # status is SmallInteger after u1a2b3c4d5e6 (enums→int migration).
    sa.Column("status", sa.SmallInteger, nullable=False),
    sa.Column("created_at", sa.Integer),
    sa.Column("updated_at", sa.Integer),
    sa.Column("token_hash", sa.String(64), nullable=True),
    sa.Column("token_expires_at", sa.Integer, nullable=True),
    sa.Column("sandbox_provider", sa.String(32), nullable=True),
    sa.Column("sandbox_id", sa.String(256), nullable=True),
    sa.Column("configured_harnesses", sa.Text, nullable=True),
    sa.PrimaryKeyConstraint("workspace_id", "host_id", name="pk_hosts"),
    sa.UniqueConstraint("workspace_id", "owner", "name", name="uq_hosts_workspace_owner_name"),
    sa.UniqueConstraint("token_hash", name="uq_hosts_token_hash"),
    # u1a2b3c4d5e6 created this integer-coded check; preserve it through the
    # PK rebuild so it survives in both the upgraded and downgraded states.
    sa.CheckConstraint("status IN (1, 2)", name="ck_hosts_status"),
)

_DOWNGRADED_TABLE = sa.Table(
    "hosts",
    sa.MetaData(),
    sa.Column("workspace_id", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("host_id", sa.String(64), nullable=False),
    sa.Column("owner", sa.String(256), nullable=False),
    sa.Column("name", sa.String(64), nullable=False),
    # status is SmallInteger (u1a2b3c4d5e6 is still applied on downgrade).
    sa.Column("status", sa.SmallInteger, nullable=False),
    sa.Column("created_at", sa.Integer),
    sa.Column("updated_at", sa.Integer),
    sa.Column("token_hash", sa.String(64), nullable=True),
    sa.Column("token_expires_at", sa.Integer, nullable=True),
    sa.Column("sandbox_provider", sa.String(32), nullable=True),
    sa.Column("sandbox_id", sa.String(256), nullable=True),
    sa.Column("configured_harnesses", sa.Text, nullable=True),
    sa.PrimaryKeyConstraint("workspace_id", "owner", "name", name="pk_hosts"),
    sa.UniqueConstraint("host_id", name="uq_hosts_host_id"),
    sa.UniqueConstraint("token_hash", name="uq_hosts_token_hash"),
    # u1a2b3c4d5e6 renamed the string check to an integer one with the same
    # name. The downgrade of u1a2b3c4d5e6 will drop it; keep it here so the
    # table round-trips correctly through the enums downgrade.
    sa.CheckConstraint("status IN (1, 2)", name="ck_hosts_status"),
)


def upgrade() -> None:
    """Promote host_id to PK; demote owner+name; swap unique constraints."""
    if _is_sqlite():
        op.execute("PRAGMA foreign_keys = OFF")

    with op.batch_alter_table("hosts", copy_from=_UPGRADED_TABLE, recreate="always"):
        pass  # All structural changes are declared in _UPGRADED_TABLE.

    if _is_sqlite():
        op.execute("PRAGMA foreign_keys = ON")


def downgrade() -> None:
    """Restore (workspace_id, owner, name) PK; drop uq_hosts_workspace_owner_name."""
    if _is_sqlite():
        op.execute("PRAGMA foreign_keys = OFF")

    with op.batch_alter_table("hosts", copy_from=_DOWNGRADED_TABLE, recreate="always"):
        pass  # All structural changes are declared in _DOWNGRADED_TABLE.

    if _is_sqlite():
        op.execute("PRAGMA foreign_keys = ON")
