import pytest

from app.services.parsing import CsvValidationError, parse_curve_csv

H = "Frequency [Hz],Magnitude [mm]\n"


def parse(s: str):
    return parse_curve_csv(s.encode())


def test_valid():
    c = parse(H + "5,1.0\n10,2.5\n")
    assert c.frequencies == [5, 10] and c.magnitudes == [1.0, 2.5] and not c.warnings


def test_bom_and_crlf_and_blank_lines():
    c = parse_curve_csv(("﻿" + H + "5,1\r\n\r\n10,2\r\n").encode("utf-8"))
    assert c.frequencies == [5, 10]
    assert any("Blank" in w for w in c.warnings)


def test_unsorted_is_sorted_with_warning():
    c = parse(H + "10,2\n5,1\n")
    assert c.frequencies == [5, 10] and c.magnitudes == [1, 2]
    assert any("sorted" in w for w in c.warnings)


@pytest.mark.parametrize("body,needle", [
    ("", "empty"),
    (H, "No data rows"),
    ("Frequency [Hz],Magnitude [m]\n5,1\n", "Incompatible magnitude unit"),
    ("Frequency [kHz],Magnitude [mm]\n5,1\n", "Incompatible frequency unit"),
    ("Freq,Mag\n5,1\n", "not recognised"),
    ("Frequency [Hz]\n5\n", "two columns"),
    (H + "5,abc\n", "non-numeric"),
    (H + "5,nan\n", "NaN"),
    (H + "5\n", "expected 2 values"),
    (H + "-1,2\n", "negative frequency"),
    (H + "5,-2\n", "negative magnitude"),
    (H + "5,1\n5,2\n", "Duplicate"),
])
def test_rejects(body, needle):
    with pytest.raises(CsvValidationError) as e:
        parse(body)
    assert needle.lower() in str(e.value).lower()


def test_bad_row_rejects_whole_file():
    # a dropped row might have been the peak, so partial import is refused
    with pytest.raises(CsvValidationError):
        parse(H + "5,1\n10,oops\n20,3\n")


def test_non_utf8():
    with pytest.raises(CsvValidationError):
        parse_curve_csv(b"\xff\xfe\x00\x01")
