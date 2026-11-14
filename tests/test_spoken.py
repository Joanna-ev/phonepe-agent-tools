from datetime import date

import pytest

import spoken


@pytest.mark.parametrize("n, en, hi", [
    (0, "zero", "shunya"),
    (1, "one", "ek"),
    (9, "nine", "nau"),
    (11, "eleven", "gyarah"),
    (19, "nineteen", "unnees"),
    (20, "twenty", "bees"),
    (21, "twenty-one", "ikkees"),
    (25, "twenty-five", "pachchees"),
    (30, "thirty", "tees"),
    (48, "forty-eight", "artalees"),
    (50, "fifty", "pachaas"),
    (78, "seventy-eight", "athattar"),
    (99, "ninety-nine", "ninyanve"),
    (100, "one hundred", "ek sau"),
    (101, "one hundred one", "ek sau ek"),
    (125, "one hundred twenty-five", "ek sau pachchees"),
    (400, "four hundred", "chaar sau"),
    (550, "five hundred fifty", "paanch sau pachaas"),
    (999, "nine hundred ninety-nine", "nau sau ninyanve"),
    (1000, "one thousand", "ek hazaar"),
    (1042, "one thousand forty-two", "ek hazaar bayalees"),
    (2500, "two thousand five hundred", "do hazaar paanch sau"),
    (9999, "nine thousand nine hundred ninety-nine", "nau hazaar nau sau ninyanve"),
    (10000, "ten thousand", "das hazaar"),
    (150000, "one lakh fifty thousand", "ek lakh pachaas hazaar"),
    (12500000, "one crore twenty-five lakh", "ek karod pachchees lakh"),
])
def test_numbers(n, en, hi):
    assert spoken.number_en(n) == en
    assert spoken.number_hi(n) == hi


@pytest.mark.parametrize("bad", [-1, 10**9, 12.5, "999", None, True])
def test_numbers_reject_bad_input(bad):
    with pytest.raises(ValueError):
        spoken.number_en(bad)


def test_hindi_table_has_no_duplicates():
    assert len(set(spoken._HI)) == 100


def test_money_examples_from_spec():
    assert spoken.rupees_en(999) == "nine hundred ninety-nine rupees"
    assert spoken.rupees_hi(999) == "nau sau ninyanve rupaye"
    assert spoken.rupees_en(1) == "one rupee"
    assert spoken.rupees_hi(1) == "ek rupaya"


def test_paise_per_payment():
    assert spoken.paise_per_payment_en(30) == "about thirty paise per payment"
    assert spoken.paise_per_payment_hi(30) == "har payment par lagbhag tees paise"
    assert spoken.paise_per_payment_en(1) == "about one paisa per payment"


@pytest.mark.parametrize("n, word", [
    (1, "first"), (2, "second"), (3, "third"), (4, "fourth"), (5, "fifth"), (8, "eighth"),
    (9, "ninth"), (12, "twelfth"), (16, "sixteenth"), (20, "twentieth"), (21, "twenty-first"),
    (22, "twenty-second"), (30, "thirtieth"), (31, "thirty-first"),
])
def test_ordinals(n, word):
    assert spoken.ordinal_en(n) == word


def test_dates():
    assert spoken.date_en(date(2026, 11, 16)) == "the sixteenth of November"
    assert spoken.date_hi(date(2026, 11, 16)) == "solah November"
    assert spoken.date_en(date(2027, 1, 1)) == "the first of January"


@pytest.mark.parametrize("ref, out", [
    ("ZR-1042", "Z R, one zero four two"),
    ("CB-1042", "C B, one zero four two"),
    ("cn-1001", "C N, one zero zero one"),
    ("M1003", "M, one zero zero three"),
])
def test_reference(ref, out):
    assert spoken.reference(ref) == out


def test_plan_names():
    assert spoken.plan_name("zero_rental") == "zero rental plan"
    assert spoken.plan_name("monthly") == "monthly plan"
    assert spoken.plan_name("annual_pro") == "annual pro plan"


def test_add_spoken_is_recursive_and_ordered():
    out = spoken.add_spoken({"plan": "monthly", "offers": [{"fee_inr": 25}], "flag_inr": True, "x_inr": None})
    assert list(out) == ["plan", "plan_name_spoken", "offers", "flag_inr", "x_inr"]
    assert out["offers"] == [{"fee_inr": 25, "fee_inr_spoken_en": "twenty-five rupees", "fee_inr_spoken_hi": "pachchees rupaye"}]
