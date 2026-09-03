"""Canonical Indian states / UTs + IAS cadres, for validating extracted data.

IAS officers belong to an Indian state cadre (or AGMUT). A `state` value that
isn't a recognised Indian state/UT (e.g. "Sylhet", which is in Bangladesh) is a
strong signal the record isn't a genuine Indian IAS transfer.
"""
from __future__ import annotations

# Canonical name -> set of accepted variants/aliases (all matched lowercased).
_CANON: dict[str, set[str]] = {
    "Andhra Pradesh": {"andhra pradesh", "andhra", "ap"},
    "Arunachal Pradesh": {"arunachal pradesh", "arunachal"},
    "Assam": {"assam"},
    "Bihar": {"bihar"},
    "Chhattisgarh": {"chhattisgarh", "chattisgarh", "cg"},
    "Goa": {"goa"},
    "Gujarat": {"gujarat"},
    "Haryana": {"haryana"},
    "Himachal Pradesh": {"himachal pradesh", "himachal", "hp"},
    "Jharkhand": {"jharkhand"},
    "Karnataka": {"karnataka"},
    "Kerala": {"kerala"},
    "Madhya Pradesh": {"madhya pradesh", "mp"},
    "Maharashtra": {"maharashtra"},
    "Manipur": {"manipur"},
    "Meghalaya": {"meghalaya"},
    "Mizoram": {"mizoram"},
    "Nagaland": {"nagaland"},
    "Odisha": {"odisha", "orissa"},
    "Punjab": {"punjab"},
    "Rajasthan": {"rajasthan"},
    "Sikkim": {"sikkim"},
    "Tamil Nadu": {"tamil nadu", "tamilnadu", "tn"},
    "Telangana": {"telangana"},
    "Tripura": {"tripura"},
    "Uttar Pradesh": {"uttar pradesh", "up"},
    "Uttarakhand": {"uttarakhand", "uttaranchal"},
    "West Bengal": {"west bengal", "bengal", "wb"},
    # Union Territories
    "Andaman and Nicobar Islands": {"andaman and nicobar islands", "andaman and nicobar", "andaman"},
    "Chandigarh": {"chandigarh"},
    "Dadra and Nagar Haveli and Daman and Diu": {"dadra and nagar haveli and daman and diu", "daman and diu", "dadra and nagar haveli"},
    "Delhi": {"delhi", "new delhi", "nct of delhi", "national capital territory of delhi"},
    "Jammu and Kashmir": {"jammu and kashmir", "j&k", "jammu & kashmir", "jk"},
    "Ladakh": {"ladakh"},
    "Lakshadweep": {"lakshadweep"},
    "Puducherry": {"puducherry", "pondicherry"},
    # Common IAS cadre grouping
    "AGMUT": {"agmut"},
}

_ALIAS_TO_CANON = {alias: canon for canon, aliases in _CANON.items() for alias in aliases}


def canonical_state(value: str | None) -> str | None:
    """Return the canonical Indian state/UT/cadre name, or None if unrecognised."""
    if not value:
        return None
    return _ALIAS_TO_CANON.get(value.strip().lower())


def is_indian_state(value: str | None) -> bool:
    return canonical_state(value) is not None
