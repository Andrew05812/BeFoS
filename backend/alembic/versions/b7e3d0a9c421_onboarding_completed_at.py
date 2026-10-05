"""a profile somebody finished is the only profile worth showing

Revision ID: b7e3d0a9c421
Revises: 9c1f5b7d2a40
Create Date: 2026-10-05 12:10:04.552118

Registration creates a shell profile so downstream reads always have a row: the name is
the local part of the email, the birth date is a placeholder, and nothing else has been
answered. The deck predicate knew about deleted, inactive and hidden profiles but not
about that, so an abandoned sign-up was handed to other people as a card with an invented
age and a compatibility score computed from no data at all. Onboarding is the only writer
that fills the shell in, so it now leaves a timestamp and the deck asks for it. The
backfill reads the one field onboarding made mandatory and registration left empty.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e3d0a9c421"
down_revision: Union[str, None] = "9c1f5b7d2a40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE profiles SET onboarding_completed_at = updated_at WHERE city <> ''"
    )


def downgrade() -> None:
    op.drop_column("profiles", "onboarding_completed_at")
