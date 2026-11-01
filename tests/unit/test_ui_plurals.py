import pytest

from cheevos.ui import plurals

COUNTS = (0, 1, 2, 4, 5, 11, 12, 21, 22, 25, 101, 102, 111, 112, 1_000)
INITIALS = {"one": "o", "few": "f", "many": "m", "other": "-"}


@pytest.mark.parametrize(
    ("languages", "expected"),
    [
        # Categories for COUNTS: o = one, f = few, m = many, - = other.
        (("English", "Catalan", "Spanish", "German", "Klingon"), "-o-------------"),
        (("French", "Portuguese (BR)", "Hindi"), "oo-------------"),
        (("Chinese (S)", "Japanese", "Korean", "Thai", "Vietnamese"), "---------------"),
        (("Russian", "Ukrainian"), "moffmmmofmofmmm"),
        (("Polish",), "moffmmmmfmmfmmm"),
        (("Bosnian", "Croatian", "Serbian"), "-off---of-of---"),
        (("Romanian",), "fofffff----fff-"),
        (("Tagalog",), "ooo-ooooooooooo"),
    ],
)
def test_rules(languages, expected):
    for language in languages:
        categories = [plurals.rule(language)(count) for count in COUNTS]
        assert "".join(INITIALS[category] for category in categories) == expected, language


def test_every_category_is_a_plural_form():
    assert set(plurals.CATEGORIES) == set(INITIALS)
