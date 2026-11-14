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
    assert spoken.paise_per_payment_en(30) == "about thirty paisay per payment"
    assert spoken.paise_per_payment_hi(30) == "har payment par lagbhag tees paise"
    assert spoken.paise_per_payment_en(1) == "about one paisa per payment"


def test_months_and_payments():
    assert spoken.months_en(10) == "ten months"
    assert spoken.months_hi(10) == "das mahine"
    assert spoken.months_en(1) == "one month"
    assert spoken.months_hi(1) == "ek mahina"
    assert spoken.payments_en(410) == "four hundred ten payments"
    assert spoken.payments_hi(410) == "chaar sau das payments"
    assert spoken.payments_en(1) == "one payment"
    assert spoken.payments_hi(1) == "ek payment"


def test_add_spoken_months_and_payments():
    out = spoken.add_spoken({"tenure_months": 14, "payments_last_month": 150, "break_even_months": 1})
    assert out["tenure_months_spoken_en"] == "fourteen months"
    assert out["tenure_months_spoken_hi"] == "chaudah mahine"
    assert out["payments_last_month_spoken_en"] == "one hundred fifty payments"
    assert out["payments_last_month_spoken_hi"] == "ek sau pachaas payments"
    assert out["break_even_months_spoken_en"] == "one month"
    assert out["break_even_months_spoken_hi"] == "ek mahina"


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


@pytest.mark.parametrize("ref, kind, out", [
    ("CB-1001", "callback ticket", "callback ticket one, zero, zero, one"),
    ("CB-1042", "callback ticket", "callback ticket one, zero, four, two"),
    ("cn-1001", "cancellation reference", "cancellation reference one, zero, zero, one"),
    ("M1003", "merchant number", "merchant number one, zero, zero, three"),
])
def test_reference(ref, kind, out):
    assert spoken.reference(ref, kind) == out


def test_reference_default_kind():
    assert spoken.reference("ZR-1042") == "reference number one, zero, four, two"


@pytest.mark.parametrize("key, value, out", [
    ("ticket_id", "CB-1001", "callback ticket one, zero, zero, one"),
    ("cancellation_id", "CN-1001", "cancellation reference one, zero, zero, one"),
    ("merchant_id", "M1001", "merchant number one, zero, zero, one"),
    ("order_id", "OR-77", "reference number seven, seven"),
])
def test_add_spoken_reference_kinds(key, value, out):
    assert spoken.add_spoken({key: value})[f"{key}_spoken"] == out


def test_paise_spelled_paisay_only_in_english():
    out = spoken.add_spoken({"cost_per_payment_paise": 17})
    assert out["cost_per_payment_paise_spoken_en"] == "about seventeen paisay per payment"
    assert out["cost_per_payment_paise_spoken_hi"] == "har payment par lagbhag satrah paise"


def test_plan_names():
    assert spoken.plan_name("zero_rental") == "zero rental plan"
    assert spoken.plan_name("monthly") == "monthly plan"
    assert spoken.plan_name("annual_pro") == "annual pro plan"


def test_add_spoken_is_recursive_and_ordered():
    out = spoken.add_spoken({"plan": "monthly", "offers": [{"fee_inr": 25}], "flag_inr": True, "x_inr": None})
    assert list(out) == ["plan", "plan_name_spoken", "offers", "flag_inr", "x_inr"]
    assert out["offers"] == [{"fee_inr": 25, "fee_inr_spoken_en": "twenty-five rupees", "fee_inr_spoken_hi": "pachchees rupaye"}]
