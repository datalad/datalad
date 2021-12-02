from datalad.tests.utils import (
    assert_equal,
    assert_is_none,
)

from ..utils import LineSplitter


def test_line_splitter_basic():
    line_splitter = LineSplitter()
    lines = line_splitter.process(
        "first line\n"
        "second line\r\n"
        "third line\n"
        "\n"
    )

    assert_equal(
        lines,
        [
            "first line",
            "second line",
            "third line",
            ""
        ])

    assert_is_none(line_splitter.finish_processing())


def test_line_splitter_unterminated():
    # Expect two lines split at "x", after the second process-call
    line_splitter = LineSplitter("x")
    lines = line_splitter.process("first line")
    assert_equal(lines, [])
    lines = line_splitter.process("xsecond linex")
    assert_equal(lines, ["first line", "second line"])
    assert_is_none(line_splitter.finish_processing())


def test_line_splitter_separator():
    line_splitter = LineSplitter("X")
    lines = line_splitter.process(
        "first line\nX"
        "second line\r\nX"
        "third line\nX"
        "\nX"
    )

    assert_equal(lines, [
        "first line\n",
        "second line\r\n",
        "third line\n",
        "\n"
    ])

    assert_is_none(line_splitter.finish_processing())


def test_line_splitter_continue():
    line_splitter = LineSplitter()
    lines = line_splitter.process(
        "first line\n"
        "second line\r\n"
        "third line\n"
        "fourth "
    )

    assert_equal(lines, [
        "first line",
        "second line",
        "third line"
    ])

    assert_equal(line_splitter.remaining_data, "fourth ")

    lines = line_splitter.process("line\n")
    assert_equal(lines, ["fourth line"])
    assert_is_none(line_splitter.finish_processing())


def test_line_splitter_corner_cases():
    line_splitter = LineSplitter()
    lines = line_splitter.process("")
    assert_equal(lines, [])
    assert_equal(line_splitter.remaining_data, None)

    line_splitter = LineSplitter()
    lines = line_splitter.process("")
    assert_equal(lines, [])
    lines = line_splitter.process("\n")
    assert_equal(lines, [""])
    assert_equal(line_splitter.remaining_data, None)

    line_splitter = LineSplitter()
    lines = line_splitter.process("  a   \f \r\n")
    assert_equal(lines, ["  a   ", " "])
