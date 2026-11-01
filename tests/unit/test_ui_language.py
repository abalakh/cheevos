import json
import logging
import time

import pytest

from cheevos.platform.desktop import translations
from cheevos.ui import format as fmt
from cheevos.ui import language, strings
from cheevos.ui.strings import Plural


def write_language(tmp_path, name, content):
    (tmp_path / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")
    return tmp_path


def problems(content):
    return language.parse(content)[1]


def test_english_strings_pass_their_own_checks():
    # Every English value is a valid template: a translation copied from the template works.
    parsed, found = language.parse(translations.template())
    assert found == []
    assert parsed == language.english()


def test_the_pseudo_language_is_a_complete_translation():
    parsed, found = language.parse(translations.pseudo())
    assert found == []
    assert parsed.keys() == language.english().keys()


@pytest.mark.parametrize(
    "path", sorted(language.LANG_DIR.glob("*.json")), ids=lambda path: path.stem
)
def test_shipped_translations_have_nothing_left_out(path):
    assert problems(json.loads(path.read_text(encoding="utf-8"))) == []


def test_a_translation_replaces_english_and_the_rest_stays(tmp_path, caplog):
    lang_dir = write_language(tmp_path, "Catalan", {"SYNC": "Sincronitza", "_note": "skipped"})
    with caplog.at_level(logging.INFO):
        language.use("Catalan", lang_dir)
    assert strings.SYNC == "Sincronitza"
    assert strings.SYNC_CANCEL == "Cancel"
    assert "Showing Catalan: 1 of" in caplog.text
    language.use(None, lang_dir)
    assert strings.SYNC == "Sync"


def test_no_translation_means_english(tmp_path, caplog):
    language.use("Catalan", write_language(tmp_path, "Catalan", {"SYNC": "Sincronitza"}))
    with caplog.at_level(logging.INFO):
        language.use("Klingon", tmp_path)
    assert strings.SYNC == "Sync"
    assert "No Klingon translation" in caplog.text


def test_an_unreadable_file_means_english(tmp_path, caplog):
    (tmp_path / "Catalan.json").write_text("{not json", encoding="utf-8")
    language.use("Catalan", tmp_path)
    assert strings.SYNC == "Sync"
    assert "Could not read Catalan.json" in caplog.text


def test_values_that_would_not_format_stay_english(tmp_path, caplog):
    content = {
        "SYNC_DONE_AGO": "Sincronitzat {when}",  # the code passes {ago}
        "MEMBER_SINCE": "Membre",  # leaves {date} out
        "RANK": ["#{rank}"],  # not text
        "LOADING": "Carregant {",  # a lone brace
        "NO_SUCH_STRING": "?",
    }
    language.use("Catalan", write_language(tmp_path, "Catalan", content))
    assert strings.SYNC_DONE_AGO == "Synced {ago}"
    assert strings.MEMBER_SINCE == "Member since {date}"
    assert strings.RANK == "#{rank}"
    assert strings.LOADING == "Loading…"
    assert "Catalan.json: SYNC_DONE_AGO: unknown field {when}" in caplog.text
    assert "MEMBER_SINCE: missing field {date}" in caplog.text
    assert "RANK: expected text" in caplog.text
    assert "LOADING: braces must hold a field name" in caplog.text
    assert "NO_SUCH_STRING: no such string" in caplog.text


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("{day} {month} {year}", None),
        ("{day:02d} de {month} de {year}", None),
        ("{{{day}}} {month} {year}", None),
        ("{day:d} {month} {year}", "DATE: write {day} or {day:02d}, not {day:d}"),
        ("{0} {month} {year}", "DATE: braces must hold a field name"),
        ("{day!r} {month} {year}", "DATE: braces must hold a field name"),
    ],
)
def test_format_specs_and_field_names(text, problem):
    found = problems({"DATE": text})
    if problem is None:
        assert found == []
    else:
        assert len(found) == 1
        assert found[0].startswith(problem)


def test_plural_forms():
    parsed, found = language.parse(
        {
            "POINTS": {"one": "{count} punt", "other": "{count} punts", "two": "?"},
            "MINUTES_AGO": "fa {count} min",
            "DAYS_AGO": {"one": "ahir", "other": "fa {count} dies"},  # one may drop {count}
            "HOURS_AGO": {"one": "fa {count} hora"},  # no "other"
            "EVENT_POINTS": {"one": "{count} {points}", "other": "almenys {count} punts"},
            "SYNC_RATE_LIMITED": {"other": "espera {minutes} min"},
        }
    )
    assert parsed["POINTS"] == Plural(one="{count} punt", other="{count} punts")
    assert parsed["MINUTES_AGO"] == Plural(other="fa {count} min")
    assert parsed["DAYS_AGO"] == Plural(one="ahir", other="fa {count} dies")
    assert parsed["EVENT_POINTS"] == Plural(other="almenys {count} punts")
    assert "HOURS_AGO" not in parsed
    assert "SYNC_RATE_LIMITED" not in parsed
    assert found == [
        "POINTS: no plural form 'two'",
        'HOURS_AGO: expected text, or forms like {"one": ..., "other": ...}',
        "EVENT_POINTS: one: unknown field {points}",
        "SYNC_RATE_LIMITED: other: unknown field {minutes}",
    ]


def test_labels_and_lists_translate_entry_by_entry():
    parsed, found = language.parse(
        {
            "VIEWS": {"grid": "Graella", "carousel": "?", "list": ""},
            "MONTHS": ["gen.", "febr.", "", *(["?"] * 9)],
            "ABOUT_TEXT": ["just one line"],
        }
    )
    assert parsed["VIEWS"] == {"list": "List", "grid": "Graella"}
    assert parsed["MONTHS"] == ("gen.", "febr.", "Mar", *(["?"] * 9))
    assert "ABOUT_TEXT" not in parsed
    assert found == ["VIEWS: carousel: no such entry", "ABOUT_TEXT: expected a list of 4"]


def test_untranslated_and_notes_are_skipped():
    assert language.parse({"SYNC": "", "_translators": ["Someone"]}) == ({}, [])
    assert language.parse(["SYNC"]) == ({}, ["expected a JSON object of names and translations"])


def test_the_language_picks_its_plural_forms(tmp_path):
    content = {"POINTS": {"one": "{count} punkt", "few": "{count} punkty", "many": "{count} pkt"}}
    content["POINTS"]["other"] = "{count} punktu"
    language.use("Polish", write_language(tmp_path, "Polish", content))
    assert [fmt.points(n) for n in (1, 2, 5, 22, 1_000)] == [
        "1 punkt",
        "2 punkty",
        "5 pkt",
        "22 punkty",
        "1,000 pkt",
    ]
    language.reset()
    assert fmt.points(2) == "2 pts"


def test_numbers_and_dates_follow_the_language(tmp_path):
    content = {
        "THOUSANDS_SEPARATOR": ".",
        "DECIMAL_SEPARATOR": ",",
        "PERCENT": "{percent} %",
        "MONTHS": ["gen.", "febr.", "març", "abr.", "maig", "juny"] + ["?"] * 6,
        "DATE": "{day} {month} {year}",
        "SIZE_UNITS": ["o", "Ko", "Mo", "Go"],
    }
    language.use("Catalan", write_language(tmp_path, "Catalan", content))
    assert fmt.number(12_843) == "12.843"
    assert fmt.percent(0.035) == "3,5 %"
    assert fmt.size(1_887_437) == "1,8 Mo"
    assert fmt.decimal(1.25, 2) == "1,25"
    march = 1_773_576_000  # 15 March 2026, noon UTC: the 15th in any time zone
    local = time.localtime(march)
    assert fmt.local_date(march) == "15 març 2026"
    assert fmt.local_datetime(march) == f"15 març 2026 {local.tm_hour:02d}:{local.tm_min:02d}"


@pytest.mark.parametrize(
    ("english", "pseudo"),
    [
        ("Sync", "[Sýñç]"),
        ("Synced {ago}", "[Sýñçééd {ago}]"),
        ("{day:02d} {month} {year}", "{day:02d} {month} {year}"),
        ("{percent}%", "{percent}%"),
        ("—", "—"),
    ],
)
def test_pseudo_text_marks_words_and_keeps_fields(english, pseudo):
    assert translations.pseudo_text(english) == pseudo
