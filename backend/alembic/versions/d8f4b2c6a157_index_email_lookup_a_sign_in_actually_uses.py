"""the address a sign-in is looked up by needs an index it can actually use

Revision ID: d8f4b2c6a157
Revises: c5a7d1e0b342
Create Date: 2026-10-06 04:22:41.903772

Both auth reads — `get_by_email` and `email_exists` — ask `lower(email) = :value`. The write
path normalises the address before storing it, and the predicate has to stay case-insensitive
or a person typing their address the way they read it gets "no such account". A btree over the
raw column cannot serve that predicate, so Postgres answered the hottest query in the product
with a full sequential scan of `users`; measured on the running database, `EXPLAIN` printed
`Seq Scan on users` for a login lookup.

The expression index serves the query and, being unique, also closes the gap the column
constraint leaves open: `unique` over the raw value treats `A@x` and `a@x` as two addresses, so
two accounts could have claimed one mailbox. Nothing in the application writes a mixed-case
address today, which is why the constraint below is a no-op on a healthy database — it fails
loudly rather than picking a winner, because choosing between two accounts that share a mailbox
is not a decision a migration gets to make.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8f4b2c6a157"
down_revision: Union[str, None] = "c5a7d1e0b342"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
