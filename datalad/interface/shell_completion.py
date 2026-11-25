# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A helper command to enable shell (bash, zsh) completion for DataLad

"""
__docformat__ = 'restructuredtext'


from logging import getLogger

from datalad.interface.base import (
    build_doc,
    eval_results,
)
from datalad.interface.results import get_status_dict
from datalad.support.exceptions import CapturedException

from .base import Interface

lgr = getLogger("datalad.interface.shell_completion")

# argcomplete registers the completion in zsh with compdef, which is not
# available until the completion system of zsh is initialized
_ZSH_COMPINIT = """\
if [ -n "${ZSH_VERSION:-}" ] && ! command -v compdef >/dev/null 2>&1; then
  autoload -U compinit && compinit
fi
"""


@build_doc
class ShellCompletion(Interface):
    """Display shell script for enabling shell completion for DataLad.

    Output of this command should be "sourced" by the bash or zsh to enable
    shell completions provided by argcomplete.

    Example:

        $ source <(datalad shell-completion)
        $ datalad --<PRESS TAB to display available option>

    """
    # XXX prevent common args from being added to the docstring
    _no_eval_results = True
    result_renderer = 'tailored'
    _params_ = {}

    @staticmethod
    @eval_results
    def __call__():
        """
        """
        try:
            import argcomplete
        except Exception as exc:
            ce = CapturedException(exc)
            yield get_status_dict(
                action='shell_completion',
                status='error',
                message=("argcomplete failed to import - no shell completion. "
                         "Check if it is installed: %s", ce),
                exception=ce,
            )
            return
        # The shell code is entirely argcomplete's, the same as of
        #   eval "$(register-python-argcomplete datalad)"
        # so it is in sync with the installed argcomplete, and supports bash
        # and (natively, since argcomplete 3.0.0) zsh.
        content = _ZSH_COMPINIT + argcomplete.shellcode(['datalad'])
        yield get_status_dict(
            action='shell_completion',
            status='ok',
            content=content
        )

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui
        if 'content' in res:
            ui.message(res['content'])
