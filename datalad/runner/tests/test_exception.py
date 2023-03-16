from __future__ import annotations

from datalad.tests.utils_pytest import assert_equal

from ..exception import (
    CommandError,
    _format_json_error_messages,
)


def get_json_objects(object_count: int, message_count: int) -> list[dict]:
    return [
        {
            "success": index % 2 == 0,
            "file": f"file-{index}",
            "note": f"note-{index}",
            "error-messages": [
                f"error-message-{index}-{j}"
                for j in range(message_count)
            ]
        }
        for index in range(object_count)
    ]


def test_format_error_with_duplicates() -> None:

    object_count = 10
    message_count = 3

    json_objects = get_json_objects(object_count, message_count)
    failed_object_indices = [
        index
        for index in range(object_count)
        if json_objects[index]["success"] is False
    ]

    # Check single appearance
    result = _format_json_error_messages(json_objects)
    lines = result.splitlines()
    del lines[0]
    assert_equal(len(lines), len(failed_object_indices) * 4)
    for i, failed_index in enumerate(failed_object_indices):
        # Accommodate for non-consistent message formatting, I don't
        # want to change the formatting because external tools might
        # depend on it.
        if i == 0:
            assert_equal(lines[4 * i], f"> note-{failed_index}")
        else:
            assert_equal(lines[4 * i], f">  note-{failed_index}")
        for j in range(message_count):
            assert_equal(
                lines[4 * i + 1 + j],
                f"error-message-{failed_index}-{j}")

    # Check double appearance
    result = _format_json_error_messages(json_objects + json_objects)
    lines = result.splitlines()
    del lines[0]
    assert_equal(len(lines), len(failed_object_indices) * 4)

    for i, failed_index in enumerate(failed_object_indices):
        if i == 0:
            assert_equal(lines[4 * i], f"> note-{failed_index}")
        else:
            assert_equal(lines[4 * i], f">  note-{failed_index}")
        for j in range(message_count - 1):
            assert_equal(
                lines[4 * i + 1 + j],
                f"error-message-{failed_index}-{j}")
        j = message_count - 1
        assert_equal(
            lines[4 * i + 1 + j],
            f"error-message-{failed_index}-{j} [2 times]")


def test_format_no_errors() -> None:
    json_objects = get_json_objects(1, 3)

    result = _format_json_error_messages(json_objects)
    assert_equal(result, "")

    result = _format_json_error_messages(json_objects + json_objects)
    assert_equal(result, "")


def test_command_error_rendering() -> None:
    command_error = CommandError(
        cmd="<cmd>",
        msg="<msg>",
        code=1,
        stdout="<stdout>",
        stderr="<stderr>",
        cwd="<cwd>",
        kwarg1="<kwarg1>",
        kwarg2="<kwarg2>")

    result = command_error.to_str()
    assert_equal(
        result,
        "CommandError: '<cmd>' failed with exitcode 1 under <cwd> [<msg>] "
        "[info keys: kwarg1, kwarg2] [out: '<stdout>'] [err: '<stderr>']"
    )

    result = command_error.to_str(False)
    assert_equal(
        result,
        "CommandError: '<cmd>' failed with exitcode 1 under <cwd> [<msg>] "
        "[info keys: kwarg1, kwarg2]"
    )
