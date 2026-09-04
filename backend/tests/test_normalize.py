"""Shared normalisers: batch years, district suffixes, gov-order links."""
from __future__ import annotations

from app.services.normalize import (
    looks_like_gov_order, norm_batch, norm_name, strip_state_suffix,
)


def test_batch_is_reduced_to_a_four_digit_year():
    assert norm_batch("2009 batch") == "2009"
    assert norm_batch("2023 बैच") == "2023"
    assert norm_batch("IAS (2015)") == "2015"
    assert norm_batch("2009") == "2009"
    assert norm_batch("batch not stated") is None
    assert norm_batch("") is None
    assert norm_batch(None) is None
    # A phone number or an order number must not be mistaken for a batch year.
    assert norm_batch("No. 20250912") is None


def test_state_suffix_is_stripped_from_districts():
    assert strip_state_suffix("Imphal, Manipur") == "Imphal"
    assert strip_state_suffix("Imphal, Manipur, India") == "Imphal, Manipur, India"  # 'India' is not a state
    assert strip_state_suffix("Imphal") == "Imphal"
    assert strip_state_suffix("Manipur") == "Manipur"          # a lone state is left to the state check
    assert strip_state_suffix("Gurugram, Haryana") == "Gurugram"
    assert strip_state_suffix("") is None
    assert strip_state_suffix(None) is None


def test_name_key_ignores_case_punctuation_and_spacing():
    assert norm_name("A.S.P.S. Ravi Prakash") == norm_name("ASPS Ravi  Prakash")
    assert norm_name("Rajeev Singh Thakur") == norm_name("rajeev singh thakur")
    assert norm_name("रितु वर्मा") == norm_name("रितु  वर्मा")
    assert norm_name("Anita Sharma") != norm_name("Anita Sharmaa")


def test_gov_order_links_reject_substring_false_positives():
    # The three real cases that produced junk links in production.
    assert not looks_like_gov_order("https://apacnewsnetwork.com/tag/enterprise-ai-adoption/")
    assert not looks_like_gov_order(
        "https://www.bhaskar.com/local/bihar/sitamarhi/news/sitamarhi-nepal-border-trade-138911821.html"
    )
    assert not looks_like_gov_order("https://newsonair.gov.in/")          # bare homepage


def test_gov_order_links_accept_real_orders():
    assert looks_like_gov_order("https://up.gov.in/orders/1147.pdf")
    assert looks_like_gov_order("https://dopt.gov.in/sites/default/files/order_2026.pdf")
    assert looks_like_gov_order("https://gad.bihar.gov.in/notifications/2026/09/transfer")
    assert looks_like_gov_order("https://cdn.example.com/files/transfer-order-sept.pdf")
    assert looks_like_gov_order("https://someportal.in/documents/notification/2026-09-01")


def test_publishers_own_pages_are_never_orders():
    host = "www.thehindu.com"
    assert not looks_like_gov_order("https://www.thehindu.com/news/national/order-of-the-day/", host)
    # ...but the same path on another host still counts.
    assert looks_like_gov_order("https://www.other.org/news/order-of-the-day/", host)


def test_name_key_collides_spelling_variants_of_one_officer():
    from app.services.normalize import name_key, names_match

    # The two real pairs the merge missed in production.
    assert name_key("Mohd. Aijaz") == name_key("Mohammad Aijaz")
    assert name_key("Aniruddh Yadav") == name_key("Anirudh Yadav")
    assert names_match("Md Aijaz", "Mohammed Aijaz")
    assert names_match("Dr. Anita Sharma IAS", "Anita Sharma")
    assert names_match("A.S.P.S. Ravi Prakash", "ASPS Ravi Prakash")
    # One-letter romanisation differences still match...
    assert names_match("Sudhansh Pant", "Sudhanshu Pant")
    # ...but different people do not.
    assert not names_match("Rajeev Singh Thakur", "Rajeev Kumar")
    assert not names_match("Anita Sharma", "Anita Verma")
    assert not names_match("", "Anita Sharma")
    assert not names_match("Ram", "Rama")           # too short to trust a ratio
