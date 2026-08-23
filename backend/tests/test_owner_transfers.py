import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.owner_transfers import (
    owner_tokens,
    match_owner,
    classify_owner_transfer,
    purpose_note,
    CATEGORY_DRAW,
    CATEGORY_CONTRIBUTION,
)
from app.services.pnl import classify, build_pnl, EXCLUDED_CATEGORIES


class _Person:
    def __init__(self, name, aliases=None):
        self.name = name
        self.aliases = aliases


BRIGHT = owner_tokens([_Person("Bright")])
BOTH = owner_tokens([_Person("Bright"), _Person("Kenny", "Kenneth Manjo")])


# --- the real name variants from the statements ---

def test_matches_every_spelling_of_the_owner():
    for variant in ("Bright Litandaze", "BRIGHT AMIBANG", "Bright Amibang",
                    "Bright Ambang", "Bright-Litanda Amibang"):
        assert match_owner(variant, BRIGHT) == "Bright", variant


def test_alias_covers_a_name_the_first_name_cannot_reach():
    # "Kenny" shares no token with "Kenneth Manjo".
    assert match_owner("Kenneth Manjo", owner_tokens([_Person("Kenny")])) is None
    assert match_owner("Kenneth Manjo", BOTH) == "Kenny"


# --- false positives are the real risk here ---

def test_a_different_person_sharing_a_surname_is_not_the_owner():
    # "Bee Amibang" and "Bright Amibang" share a surname but are not the same
    # person; matching on the surname would sweep $15,471 out of expenses.
    assert match_owner("Bee Amibang", BRIGHT) is None


def test_unrelated_payees_do_not_match():
    for other in ("Mimi S", "Ba Hunnington", "Folabi Mojibola", "Gio",
                  "Yasmine Yvonne", "Tech4 Logistics", "Kya Tax Lady"):
        assert match_owner(other, BOTH) is None, other


def test_generic_tokens_never_match():
    owners = owner_tokens([_Person("Bright", "The LLC Inc")])
    assert match_owner("Some Company LLC", owners) is None


def test_short_tokens_are_ignored():
    # A two-letter name must not match everything containing those letters.
    assert match_owner("BA Huntington", owner_tokens([_Person("Bo")])) is None


def test_empty_counterparty_is_safe():
    assert match_owner(None, BRIGHT) is None
    assert match_owner("", BRIGHT) is None


# --- direction ---

def test_money_out_to_an_owner_is_a_draw():
    cat, owner = classify_owner_transfer(True, "Bright Litandaze", "sent", "debit", BRIGHT)
    assert cat == CATEGORY_DRAW
    assert owner == "Bright"


def test_money_in_from_an_owner_is_a_contribution():
    cat, owner = classify_owner_transfer(True, "BRIGHT AMIBANG", "received", "credit", BRIGHT)
    assert cat == CATEGORY_CONTRIBUTION


def test_direction_follows_transaction_type_not_zelle_direction():
    # zelle_direction is derived from an inverted sign convention; the
    # transaction type is authoritative.
    cat, _ = classify_owner_transfer(True, "Bright Litandaze", "received", "debit", BRIGHT)
    assert cat == CATEGORY_DRAW


def test_non_zelle_rows_are_untouched():
    cat, owner = classify_owner_transfer(False, "Bright Litandaze", None, "debit", BRIGHT)
    assert cat is None and owner is None


# --- effect on the statement ---

def test_owner_categories_are_excluded_from_the_pnl():
    assert CATEGORY_DRAW in EXCLUDED_CATEGORIES
    assert CATEGORY_CONTRIBUTION in EXCLUDED_CATEGORIES
    assert classify(CATEGORY_DRAW, "debit")[0] == "excluded"
    assert classify(CATEGORY_CONTRIBUTION, "credit")[0] == "excluded"


def test_reclassifying_a_draw_raises_profit_by_that_amount():
    from datetime import datetime

    class _Type:
        def __init__(self, v): self.value = v

    class _Tx:
        def __init__(self, amount, category, ttype):
            self.date = datetime(2025, 3, 5)
            self.amount = amount
            self.category = category
            self.transaction_type = _Type(ttype)

    revenue = _Tx(10000.0, "Deposit", "credit")
    before = build_pnl([revenue, _Tx(2000.0, "Zelle", "debit")],
                       datetime(2025, 3, 1), datetime(2025, 3, 31))
    after = build_pnl([revenue, _Tx(2000.0, CATEGORY_DRAW, "debit")],
                      datetime(2025, 3, 1), datetime(2025, 3, 31))

    assert before["total_expenses"] == 2000.0
    assert after["total_expenses"] == 0.0
    assert after["net_profit"] - before["net_profit"] == 2000.0
    assert after["total_excluded"] == 2000.0      # still visible, just not an expense


# --- the note that lands on the receipt ---

def test_draw_note_says_it_is_not_an_expense():
    note = purpose_note(CATEGORY_DRAW, "Bright", "LITANRYAN TECHNOLOGIES")
    assert "Owner's draw" in note
    assert "not a business expense" in note
    assert "LITANRYAN" in note


def test_contribution_note_says_it_is_not_income():
    note = purpose_note(CATEGORY_CONTRIBUTION, "Bright")
    assert "not business income" in note


# --- personal payees: money out for family is still a draw ---

def _people(*specs):
    return owner_tokens([_Person(n, a) if k == "owner" else _PersonalPerson(n, a)
                         for n, a, k in specs])


class _PersonalPerson:
    def __init__(self, name, aliases=None):
        self.name = name
        self.aliases = aliases
        self.kind = "personal"


PERSONAL = owner_tokens([_Person("Bright"), _PersonalPerson("Mimi S")])


def test_paying_a_personal_payee_is_a_draw():
    # Childcare for the owner's own children is not a business cost; the money
    # left the business for personal use regardless of who received it.
    cat, who = classify_owner_transfer(True, "Mimi S", "sent", "debit", PERSONAL)
    assert cat == CATEGORY_DRAW
    assert who == "Mimi S"


def test_money_back_from_a_personal_payee_is_not_income():
    # The business never earned it — it is the return of a draw, so it belongs
    # outside the statement rather than in revenue.
    cat, who = classify_owner_transfer(True, "Mimi S", "received", "credit", PERSONAL)
    assert cat == CATEGORY_CONTRIBUTION
    assert who == "Mimi S"


def test_owners_still_contribute_capital():
    cat, _ = classify_owner_transfer(True, "Bright Litandaze", "received", "credit", PERSONAL)
    assert cat == CATEGORY_CONTRIBUTION


def test_personal_draw_note_says_why():
    from app.services.owner_transfers import kind_of
    note = purpose_note(CATEGORY_DRAW, "Mimi S", "LITANRYAN", kind_of(PERSONAL, "Mimi S"))
    assert "personal and family" in note
    assert "not a business expense" in note


def test_owner_draw_note_is_unchanged():
    from app.services.owner_transfers import kind_of
    note = purpose_note(CATEGORY_DRAW, "Bright", "LITANRYAN", kind_of(PERSONAL, "Bright"))
    assert "a principal" in note


def test_kinds_do_not_leak_between_orgs():
    # Two orgs classified in the same process must not see each other's people.
    org_a = owner_tokens([_PersonalPerson("Sam")])
    org_b = owner_tokens([_Person("Sam")])
    from app.services.owner_transfers import kind_of
    assert kind_of(org_a, "Sam") == "personal"
    assert kind_of(org_b, "Sam") == "owner"


def test_org_person_model_has_the_kind_column():
    # The classification depends on this field existing on the ORM model, not
    # just in the database — a silently-skipped edit once left it missing.
    from app.models import OrgPerson
    assert hasattr(OrgPerson, "kind")
    person = OrgPerson(org_id=None, name="Someone", kind="personal")
    assert person.kind == "personal"


def test_money_back_from_a_personal_payee_is_not_called_capital():
    # Calling a returned payment "capital contributed by a principal" would be
    # wrong on the face of the receipt.
    note = purpose_note(CATEGORY_CONTRIBUTION, "Marilyn Sheriff", "LITANRYAN", "personal")
    assert "a principal" not in note
    assert "not business income" in note


# --- splitting the draw into its own lines ---

class _LabelledPerson:
    def __init__(self, name, kind="personal", draw_label=None, aliases=None):
        self.name = name
        self.kind = kind
        self.aliases = aliases
        self.draw_label = draw_label


def test_a_draw_label_gives_the_withdrawal_its_own_line():
    owners = owner_tokens([_LabelledPerson("Mimi S", draw_label="Childcare")])
    cat, who = classify_owner_transfer(True, "Mimi S", "sent", "debit", owners)
    assert cat == "Owner's Draw — Childcare"
    assert who == "Mimi S"


def test_an_unlabelled_person_keeps_the_plain_draw_line():
    owners = owner_tokens([_LabelledPerson("Bright", kind="owner")])
    cat, _ = classify_owner_transfer(True, "Bright Litandaze", "sent", "debit", owners)
    assert cat == CATEGORY_DRAW


def test_every_split_draw_is_still_excluded():
    for label in ("Owner's Draw — Childcare", "Owner's Draw — Gifts & Other",
                  "Owner's Draw — Self", CATEGORY_DRAW):
        assert classify(label, "debit")[0] == "excluded", label
        assert classify(label, "debit")[1] == label


def test_split_draws_do_not_reach_expenses():
    from datetime import datetime

    class _Type:
        def __init__(self, v): self.value = v

    class _Tx:
        def __init__(self, amount, category):
            self.date = datetime(2025, 3, 5)
            self.amount = amount
            self.category = category
            self.transaction_type = _Type("debit")

    pnl = build_pnl(
        [_Tx(16450.0, "Owner's Draw — Childcare"), _Tx(500.0, "Office Supplies")],
        datetime(2025, 3, 1), datetime(2025, 3, 31),
    )
    assert pnl["total_expenses"] == 500.0
    labels = {l["label"] for l in pnl["excluded_lines"]}
    assert "Owner's Draw — Childcare" in labels
