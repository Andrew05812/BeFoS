"""The door that returns a lost word needs a deadline it can be proved to have.

Stage 131. `/auth` had eight verbs and none of them was recovery: the only way back into a lost
password was `POST /auth/change-password`, which asks for the old password — a door that needs the
thing it stands in place of. The audit filed that as P0-1 (`docs/PRODUCT_TECHNICAL_AUDIT.md` §11),
because losing a word there meant losing the profile, the pair and the correspondence, and support
had no lever either.

This revision adds one table, `auth_challenges`, and nothing else: no column on `users`, because the
question a recovery code answers is not a fact about a person but about a letter somebody asked for
and has maybe already read. Three decisions are carried by the shape of the table rather than by the
code above it:

* `token_hash` holds a SHA-256 hex digest and is UNIQUE, exactly as `refresh_tokens.token_hash` does
  (`models/token.py:22`). The plaintext code never reaches the database: a backup, a replica or a slow
  query log that leaks this table must not be a set of live doors into other people's accounts. The
  unique index doubles as the read path — redemption looks a code up by its digest and nothing else.
* `expires_at` and `consumed_at` are two columns, not one. An expired code and a spent code are
  refused with the same sentence at the door, and still have to be told apart by an operator
  answering «why did my letter not work»; a single column could hold only one of the two answers.
  `purpose` sits in the same predicate as both, so a code minted to return a word cannot be spent as
  proof of anything else.
* there is no check constraint on `expires_at > created_at`. That would make the expiry branch
  untestable — the only way a suite reaches «the letter was too late» is to move the deadline into the
  past — and an untestable branch is the one this door must not ship untested. The deadline is
  enforced where it is decided, in the ``WHERE`` clause of the redemption statement
  (`repositories/challenge_repo.py:redeem`).

The foreign key is CASCADE, so an erased account takes its unredeemed codes with it: a live code that
outlived the row it points at would be a door into nothing, and a purge that left it behind would
leave the address reusable while the person's own history is gone.

Two indexes, no more. `ix_auth_challenges_owner_purpose (user_id, purpose)` answers the one question
the request path asks of its own table — «does this account already hold a live code?» — which is
what keeps a script with one address from emitting a letter per request. A second index over
`user_id` alone would be a left prefix of it, and `test_schema_index_redundancy.py` exists to refuse
that.

revision: see `down_revision` — the chain runs `... -> f7c2a9d4e6b1 -> c8f2b5d7a140 -> this`.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7d4f0b2c318"
down_revision: Union[str, None] = "c8f2b5d7a140"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_auth_challenges_token_hash"), "auth_challenges", ["token_hash"], unique=True
    )
    op.create_index(
        "ix_auth_challenges_owner_purpose", "auth_challenges", ["user_id", "purpose"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_auth_challenges_owner_purpose", table_name="auth_challenges")
    op.drop_index(op.f("ix_auth_challenges_token_hash"), table_name="auth_challenges")
    op.drop_table("auth_challenges")
