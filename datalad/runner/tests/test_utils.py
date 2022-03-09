from typing import (
    List,
    Optional,
)
from unittest.mock import (
    call,
    patch,
)

from datalad.tests.utils import (
    assert_equal,
    assert_in,
    assert_is_none,
)

from ..utils import (
    AssemblingDecoderMixIn,
    LineSplitter,
)


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


def test_assembling_decoder_mix_in_basic():

    encoding = "utf-8"
    unicode_str = "These are not ASCII: ä, ö, ü. These can be ASCII: a, o, u."
    data_bytes = unicode_str.encode(encoding)

    adm = AssemblingDecoderMixIn()

    single_result = "".join([
        adm.decode(1, bytes([data_byte]), encoding)
        for data_byte in data_bytes
    ])
    assert_equal(single_result, unicode_str)


def _decode_multiple(adm: AssemblingDecoderMixIn,
                     encoded_strings: List[bytes],
                     encoding: str,
                     fixed_index: Optional[int] = None) -> List[str]:

    # Interleave decoding of multiple strings
    decoded_chars = [list() for _ in range(len(encoded_strings))]
    for data_index in range(max([len(es) for es in encoded_strings])):
        for string_index in range(len(encoded_strings)):
            if data_index < len(encoded_strings[string_index]):
                decoded_char = adm.decode(
                    string_index if fixed_index is None else fixed_index,
                    bytes([encoded_strings[string_index][data_index]]),
                    encoding)
                decoded_chars[string_index].append(decoded_char)
    return ["".join(decoded_list) for decoded_list in decoded_chars]


def test_assembling_decoder_mix_in_multiple():
    encoding = "utf-8"
    unicode_strings = [
        "These are not ASCII: ä, ö, ü. These can be ASCII: a, o, u.",
        "Some other weird stuff: öäöß.",
        "Even weirder: 🐷🐶.",
    ]
    encoded_strings = [
        unicode_string.encode(encoding)
        for unicode_string in unicode_strings
    ]

    adm = AssemblingDecoderMixIn()
    decoded_strings = _decode_multiple(adm, encoded_strings, encoding)
    assert_equal(unicode_strings, decoded_strings)


def test_assembling_decoder_mix_in_multiple_fail():
    encoding = "utf-8"
    unicode_strings = [
        "A: ä, ö, ü.",
        "B: öäöß.",
        "C: 🐷🐶.",
    ]
    encoded_strings = [
        unicode_string.encode(encoding)
        for unicode_string in unicode_strings
    ]

    adm = AssemblingDecoderMixIn()
    decoded_strings = _decode_multiple(adm, encoded_strings, encoding, 0)
    # Because the strings are not separated, we do not expect any proper
    # output after single-byte encoded chars.
    assert_equal(decoded_strings, ["A: ", "B: ", "C: "])


def test_assembling_decoder_mix_in_warning():
    encoding = "utf-8"
    data_bytes = "🐷🐶.".encode(encoding)

    adm = AssemblingDecoderMixIn()

    with patch("datalad.runner.utils.logger") as logger_mock:
        result = adm.decode(1, data_bytes[0:1], encoding)
        assert_equal(result, '')
        del adm
        assert_in(
            call.warning("unprocessed data in AssemblingDecoderMixIn"),
            logger_mock.mock_calls)
        assert_in(
            call.debug(
                "unprocessed data in AssemblingDecoderMixIn:\n"
                "fd: 1, data: b'\\xf0'\n"),
            logger_mock.mock_calls)
