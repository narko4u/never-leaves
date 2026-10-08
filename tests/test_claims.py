"""Claim checking tests.

These are the tests that protect a tradie from sending a client a number
that the model made up. The two that matter most are the invented price
and the corrupted sign.
"""

from never_leaves import claims


def test_numbers_are_extracted_by_value():
    found = claims.numbers_in("6 downlights, 90mm cutouts, 2 flickering")
    assert {"6", "90", "2"} <= found


def test_thousands_and_decimals_normalise():
    assert claims.numbers_in("about 1,200 dollars") == {"1200"}
    assert claims.numbers_in("$1,200.50") == {"1200.5"}
    # A trailing zero is not a difference in value, so these must compare equal.
    assert claims.numbers_in("$340.50") == claims.numbers_in("$340.5")


def test_money_is_found_with_and_without_a_space():
    assert claims.money_in("total $1,200") == {"1200"}
    assert claims.money_in("total $ 340.50") == {"340.5"}


def test_an_invented_price_is_flagged():
    """The headline behaviour. The notes have no price, the draft does."""
    note = "replace 6 downlights, 3 gpos in the shed, about 18m of cable"
    draft = "Price\n\n| Item | Rate | Total |\n|---|---|---|\n| Downlights | $95 | $570 |"
    result = claims.check(draft, note)
    assert not result.clean
    assert "570" in result.unsourced_money
    assert "95" in result.unsourced_money
    assert any("MONEY TO CHECK" in line for line in result.lines())


def test_a_figure_that_is_in_the_notes_is_not_flagged():
    note = "about 18m of cable and 6 downlights"
    draft = "Cable run 18m. Six downlights replaced."
    result = claims.check(draft, note)
    assert result.unsourced_money == []
    assert "18" not in result.unsourced_numbers


def test_a_flipped_sign_is_caught():
    """The model wrote 'about -400mm' where the notes said 'about 400mm'."""
    note = "access under the house is tight, about 400mm"
    draft = "Access under house is tight, about -400mm"
    result = claims.check(draft, note)
    assert "-400" in result.unsourced_numbers


def test_placeholders_are_listed_for_the_operator():
    draft = "Price: [RATE] and [TOTAL], deposit [DEPOSIT]"
    result = claims.check(draft, "no figures here")
    assert result.placeholders == ["DEPOSIT", "RATE", "TOTAL"]
    assert any("FILL THESE IN" in line for line in result.lines())


def test_headings_are_recorded_so_the_shape_can_be_checked():
    draft = "## Scope of work\ntext\n## Price\nmore"
    result = claims.check(draft, "source")
    assert result.headings == ["Scope of work", "Price"]


def test_a_clean_draft_says_so():
    result = claims.check("All good, no figures.", "All good, no figures.")
    assert result.clean
    assert result.unsourced_money == []
    assert result.placeholders == []


def test_check_survives_empty_input():
    result = claims.check("", "")
    assert result.word_count == 0
    assert result.lines()
