"""Recognising transfers between the business and its own owners.

Paying yourself by Zelle looks identical to paying a supplier: same rail, same
description shape. Left alone it lands in operating expenses and understates
profit, which is wrong twice over — the P&L is misstated and an equity
withdrawal is claimed as a business cost.

These are balance-sheet movements:
  money out to an owner  -> Owner's Draw
  money in from an owner -> Owner's Contribution

Both are excluded from the P&L by services/pnl.py and shown in its excluded
section, so the cash stays visible without touching profit.

Matching is by name token against the org's own people list plus any aliases,
because the same person appears as "Bright Litandaze", "BRIGHT AMIBANG" and
"Bright Ambang" across statements. Aliases are needed for the cases a first
name cannot cover — "Kenny" never matches "Kenneth Manjo".
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

CATEGORY_DRAW = "Owner's Draw"
CATEGORY_CONTRIBUTION = "Owner's Contribution"

# Tokens too generic to identify anyone; matching on these would sweep in
# unrelated counterparties.
_STOPWORDS = {
    "the", "and", "llc", "inc", "corp", "ltd", "co", "mr", "mrs", "ms", "dr",
}
_MIN_TOKEN = 3


def _tokens(value: str) -> set[str]:
    """Lowercase word tokens worth matching on."""
    raw = re.split(r"[^A-Za-z]+", value or "")
    return {
        t.lower() for t in raw
        if len(t) >= _MIN_TOKEN and t.lower() not in _STOPWORDS
    }


def owner_tokens(people: Iterable) -> dict[str, set[str]]:
    """Map each person to the tokens that identify them.

    `people` may be OrgPerson rows or plain strings. Rows carry an optional
    comma-separated `aliases` field for the names a first name cannot reach.
    """
    out: dict[str, set[str]] = {}
    for person in people or ():
        if isinstance(person, str):
            name, aliases = person, ""
        else:
            name = getattr(person, "name", "") or ""
            aliases = getattr(person, "aliases", "") or ""
        if not name:
            continue
        toks = _tokens(name)
        for alias in aliases.split(","):
            toks |= _tokens(alias)
        if toks:
            out[name] = toks
    return out


def match_owner(counterparty: Optional[str], owners: dict[str, set[str]]) -> Optional[str]:
    """Return the owner this counterparty refers to, or None."""
    if not counterparty:
        return None
    party = _tokens(counterparty)
    if not party:
        return None
    for name, toks in owners.items():
        if party & toks:
            return name
    return None


def classify_owner_transfer(
    is_zelle: bool,
    counterparty: Optional[str],
    direction: Optional[str],
    transaction_type: str,
    owners: dict[str, set[str]],
) -> tuple[Optional[str], Optional[str]]:
    """Return (category, owner_name) for an owner transfer, else (None, None).

    Direction comes from the transaction type rather than `zelle_direction`,
    which is unreliable — the sign convention behind it is inverted.
    """
    if not is_zelle:
        return (None, None)
    owner = match_owner(counterparty, owners)
    if not owner:
        return (None, None)
    if transaction_type == "credit":
        return (CATEGORY_CONTRIBUTION, owner)
    return (CATEGORY_DRAW, owner)


def purpose_note(category: str, owner: str, org_name: str = "") -> str:
    """The business-purpose line for an owner transfer."""
    entity = f" of {org_name}" if org_name else ""
    if category == CATEGORY_CONTRIBUTION:
        return (
            f"Capital contributed by {owner}, a principal{entity}. "
            f"An equity contribution, not business income."
        )
    return (
        f"Owner's draw taken by {owner}, a principal{entity}. "
        f"An equity withdrawal, not a business expense."
    )
