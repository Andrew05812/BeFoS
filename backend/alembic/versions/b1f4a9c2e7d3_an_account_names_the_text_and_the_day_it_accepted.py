"""An account names the text it accepted, and the day it said yes.

Stage 131. Until this revision `users` had no consent column at all: registration was an email/lang
password pair and nothing else, so the product could not answer the one question a person is entitled
to ask about their own data — «what did I agree to, and when?». The audit filed that as P0-2
(`docs/PRODUCT_TECHNICAL_AUDIT.md` §11), together with the missing address confirmation.

Two columns, both nullable on purpose. `consent_version` is the product string of the document the
account accepted (`core/consent.py`), and `consent_accepted_at` is the moment. Null means «this row
was made before the product asked», which is the truth about every account that exists on the stand
today: a migration that stamped them with a version would be a backfill of a signature nobody gave,
and it is exactly the kind of invented fact this repository has refused before. The registration door
starts writing both in words once this revision lands; the `RootViewModel` gate asks accounts with no
version (or an old one) to read and accept the current text before they continue.

No index: the columns are read off the account row the session already loaded, and an index over a
column nobody filters by would only make every write pay for it.

revision: see `down_revision` — the chain runs `... -> c8f2b5d7a140 -> a7d4f0b2c318 -> this`.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1f4a9c2e7d3"
down_revision: Union[str, None] = "a7d4f0b2c318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("consent_version", sa.String(length=16), nullable=True))
    op.add_column(
        "users", sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "consent_accepted_at")
    op.drop_column("users", "consent_version")
