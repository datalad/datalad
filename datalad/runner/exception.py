# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Exception raise on a failed runner command execution
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from typing import (
    Any,
    Optional,
)

lgr = logging.getLogger('datalad.runner.exception')


class CommandError(RuntimeError):
    """Thrown if a command call fails.

    Note: Subclasses should override `to_str` rather than `__str__` because
    `to_str` is called directly in datalad.cli.main.
    """

    def __init__(
        self,
        cmd: str | list[str] = "",
        msg: str = "",
        code: Optional[int] = None,
        stdout: str | bytes = "",
        stderr: str | bytes = "",
        cwd: str | os.PathLike | None = None,
        **kwargs: Any,
    ) -> None:
        RuntimeError.__init__(self, msg)
        self.cmd = cmd
        self.msg = msg
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.cwd = cwd
        self.kwargs = kwargs

    def to_str(self, include_output: bool = True) -> str:
        from datalad.utils import (
            ensure_unicode,
            join_cmdline,
        )
        to_str = "{}: ".format(self.__class__.__name__)
        cmd = self.cmd
        if cmd:
            to_str += "'{}'".format(
                # go for a compact, normal looking, properly quoted
                # command rendering if the command is in list form
                join_cmdline(cmd) if isinstance(cmd, list) else cmd
            )
        if self.code:
            to_str += " failed with exitcode {}".format(self.code)
        if self.cwd:
            # only if not under standard PWD
            to_str += " under {}".format(self.cwd)
        if self.msg:
            # typically a command error has no specific idea
            to_str += " [{}]".format(ensure_unicode(self.msg))

        if self.kwargs:
            to_str += " [info keys: {}]".format(
                ', '.join(self.kwargs.keys()))

            if 'stdout_json' in self.kwargs:
                to_str += _format_json_error_messages(
                    self.kwargs['stdout_json'])

        if not include_output:
            return to_str

        if self.stdout:
            to_str += " [out: '{}']".format(ensure_unicode(self.stdout).strip())
        if self.stderr:
            to_str += " [err: '{}']".format(ensure_unicode(self.stderr).strip())

        return to_str

    def __str__(self) -> str:
        return self.to_str()


def _format_json_error_messages(recs: list[dict]) -> str:
    # there could be many, condense
    msgs: Counter[str] = Counter()
    for r in recs:
        if r.get('success'):
            continue
        msg = '{}{}'.format(
            ' {}\n'.format(r['note']) if r.get('note') else '',
            '\n'.join(r.get('error-messages', [])),
        )
        if 'file' in r or 'key' in r:
            msgs[msg] += 1

    if not msgs:
        return ''

    return '\n>{}'.format(
        '\n> '.join(
            '{}{}'.format(
                m,
                ' [{} times]'.format(n) if n > 1 else '',
            )
            for m, n in msgs.items()
        )
    )
