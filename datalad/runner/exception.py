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

from datasalad.runners import CommandError as _CommandError

lgr = logging.getLogger('datalad.runner.exception')


class CommandError(_CommandError):
    """Thrown if a command call fails.

    This class is derived from ``datasalad``'s exception, which in turn is the
    successor of this implementation. The main difference is improved
    messaging, and alignment with ``subprocess``'s ``CalledProcessError``.

    However, for backward compatibility reasons, the behavior when converting
    to ``str`` is overwritten here, and held constant with respect to prior
    DataLad versions.

    In order to ease a future transition, the class supports the ``returncode``
    attribute and constructor argument (as done by ``subprocess``) in addition
    to ``code``.
    """
    # Basic alias idea taken from here:
    # <https://stackoverflow.com/questions/4017572/how-can-i-make-an-alias-to-a-non-function-member-attribute-in-a-python-class>
    _aliases = {
        'returncode': 'code',
    }

    def __init__(
        self,
        cmd: str | list[str] = "",
        msg: str = "",
        code: Optional[int] = None,
        returncode: Optional[int] = None,
        stdout: str | bytes = "",
        stderr: str | bytes = "",
        cwd: str | os.PathLike | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            cmd=cmd,
            msg=msg,
            returncode=returncode or code,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
        )
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

    # override to support alias lookup
    def __getattr__(self, item):
        return object.__getattribute__(
            self, self._aliases.get(item, item))

    # override to support alias lookup
    def __setattr__(self, key, value):
        if key == '_aliases':
            raise AttributeError('Cannot set `_aliases`')
        return object.__setattr__(
            self, self._aliases.get(key, key), value)


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
