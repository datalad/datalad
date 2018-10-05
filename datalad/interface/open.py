# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A context manager to assist with annexed files access (i.e. read/write)"""

__docformat__ = 'restructuredtext'

import os
import logging
from contextlib import contextmanager

import json

from argparse import REMAINDER
import glob
import os.path as op
from os.path import join as opj
from os.path import normpath
from os.path import relpath
from os.path import isabs

from six.moves import shlex_quote

from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import save_message_opt
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import nosave_opt
# TODO should be moved to common_opts may be?
from datalad.distribution.drop import dataset_argument

from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureInt
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureBool
from datalad.support.exceptions import CommandError
from datalad.support.param import Parameter
from datalad.support.json_py import dump2stream

from datalad.distribution.add import Add
from datalad.distribution.get import Get
from datalad.distribution.install import Install
from datalad.distribution.remove import Remove
from datalad.distribution.dataset import resolve_path
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.unlock import Unlock

from datalad.utils import assure_list
from datalad.utils import chpwd
# Rename get_dataset_pwds for the benefit of containers_run.
from datalad.utils import get_dataset_pwds as get_command_pwds
from datalad.utils import getpwd
from datalad.utils import partition
from datalad.utils import SequenceFormatter

lgr = logging.getLogger('datalad.interface.open')


# @build_doc
# class Open(Interface):
#     """Open files for reading or writing performing necessary git-annex actions.
#
#     TODO
#     """
#     _params_ = dict(
#         dataset=dataset_argument,
#         path=Parameter(
#             args=("path",),
#             metavar="PATH",
#             doc="path to the file to be opened",
#             nargs="+",
#             constraints=EnsureStr() | EnsureNone(),
#         ),
#         mode=Parameter(
#             default=None,
#             doc="Mode as passed (if specified) to `open` call",
#             constraints=EnsureStr() | EnsureNone(),
#         ),
#         buffering=Parameter(
#             default=None,
#             doc="Buffering argument as passed (if specified) to `open` call",
#             constraints=EnsureInt() | EnsureNone(),
#         ),
#         save=nosave_opt,
#         message=save_message_opt,
#         # TODO: should we worry/bother eg checking dirtiness for those
#         # specified files
#         # if_dirty=if_dirty_opt,
#     )

_builtin_open = open

@datasetmethod(name='open')
def open(
        path,
        mode=None,
        buffering=None,
        dataset=None,
        save=True,
        message=None
        # , if_dirty='save-before'
    ):
    """TODO"""
    # Pre-treat open parameters first
    if mode is not None:
        if mode[0] not in 'rwa':
            raise ValueError("Mode must be either None or start with r, w, or a")

    open_args = []
    if mode is not None:
        open_args.append(mode)
        if buffering is not None:
            open_args.append(buffering)
    elif buffering is not None:
        # Do not bother messing with it
        raise ValueError("When specifying buffering, provide mode for open")

    # Probably will be useless in Python mode since we cannot return a
    # context manager an yield all the result records at the same time.
    # But if we make it into a class, we could store them in the instance
    # so they could be inspected later on if desired?
    path = assure_list(path)
    resolved_paths = [resolve_path(p, dataset) for p in path] \
        if dataset is not None else path

    import datalad.api as dl  # heavy import so delayed

    class OpenBase(object):
        def __init__(self):
            self.all_results = []
            self.files = None

        def __enter__(self):
            pre_open = self.pre_open()
            if pre_open:
                self.all_results.extend(pre_open)

            self.files = []
            for p in resolved_paths:
                # TODO: actually do all that full path deduction here probably
                # since we allow for ds.open
                self.files.append(_builtin_open(p, *open_args))
                self.all_results.append({
                    'status': 'ok',
                    'action': 'open',
                    'mode': mode,
                    'path': p,
                    'type': 'file'
                })
            return self.files if len(self.files) > 1 else self.files[0]

        def __exit__(self, exc_type, exc_val, exc_tb):
            # TODO: handle if exception happened - I think we should "abort"
            for f in self.files:
                if not f.closed:
                    f.close()
                    self.all_results.append(
                        {
                            'status': 'ok',
                            'action': 'close',
                            'path': f.name,
                            'type': 'file'
                        }
                    )

            post_close = self.post_close()
            if post_close:
                self.all_results.extend(post_close)

        def pre_open(self):
            raise NotImplementedError

        def post_close(self):
            raise NotImplementedError

    class OpenRead(OpenBase):
        def pre_open(self):
            return dl.get(resolved_paths,
                 # TODO: what should we do with files not under git at all?
                 # here on_failure is not effective - fails during "rendering"
                 # , on_failure='continue'
            )

        def post_close(self):
            pass


    class OpenRewrite(OpenBase):
        def pre_open(self):
            for p in resolved_paths:
                # TODO: do we need to store/apply to the new files anything?
                # If file is under git - the only thing we could (re)store is
                # executable bit
                # If file is outside of git/annex control - we might better even
                # not remove it at all
                os.unlink(p)

        def post_close(self):
            # add would crash in case file jumps between git and annex
            # due to .gitattributes settings.
            # .save seems to be more resilient BUT! retains git/annex so
            # there would be no auto migrations
            # self.all_results.extend(
            #     dl.add(path=resolved_paths, save=save, message=message)
            # )
            # TODO, see https://github.com/datalad/datalad/issues/1651
            if save:
                # mneh -- even this one (may be due to paths specification?)
                # doesn't work if file jumps between git and annex
                self.all_results.extend(
                    dl.save(path=resolved_paths, message=message)
                )


    class OpenAppend(OpenRewrite):
        def pre_open(self):
            # Copy from OpenRead,
            res = dl.get(resolved_paths,
                 # TODO: what should we do with files not under git at all?
                 # here on_failure is not effective - fails during "rendering"
                 # , on_failure='continue'
            )
            res.extend(dl.unlock(resolved_paths))
            return res

        # TODO: might need to track what was actually unlocked (v6) and do more
        # in post_close here

    mode_base = mode[0] if mode is not None else 'r'
    res = {
        'r': OpenRead,
        'w': OpenRewrite,
        'a': OpenAppend,
    }[mode_base]()

    return res
