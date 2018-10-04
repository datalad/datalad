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


import logging


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
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.unlock import Unlock

from datalad.utils import assure_bytes
from datalad.utils import chpwd
# Rename get_dataset_pwds for the benefit of containers_run.
from datalad.utils import get_dataset_pwds as get_command_pwds
from datalad.utils import getpwd
from datalad.utils import partition
from datalad.utils import SequenceFormatter

lgr = logging.getLogger('datalad.interface.open')


@build_doc
class Open(Interface):
    """Open files for reading or writing performing necessary git-annex actions.

    TODO
    """
    _params_ = dict(
        dataset=dataset_argument,
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path to the file to be opened",
            nargs="+",
            constraints=EnsureStr() | EnsureNone(),
        ),
        mode=Parameter(
            default=None,
            doc="Mode as passed (if specified) to `open` call",
            constraints=EnsureStr() | EnsureNone(),
        ),
        buffering=Parameter(
            default=None,
            doc="Buffering argument as passed (if specified) to `open` call",
            constraints=EnsureInt() | EnsureNone(),
        ),
        save=nosave_opt,
        message=save_message_opt,
        # TODO: should we worry/bother eg checking dirtiness for those
        # specified files
        # if_dirty=if_dirty_opt,
    )

    @staticmethod
    @datasetmethod(name='open')
    @eval_results
    def __call__(
            path=None,
            mode=None,
            buffering=None,
            dataset=None,
            save=True,
            message=None
            # , if_dirty='save-before'
        ):
        if mode is not None:
            if mode[0] not in 'rwa':
                raise ValueError("Mode must be either None or start with r, w, or a")
        # refds_path = Interface.get_refds_path(dataset)
        # to_process = []
        # for ap in AnnotatePaths.__call__(
        #         path=path,
        #         dataset=refds_path,
        #         action='open',
        #         unavailable_path_status='unavailable',
        #         nondataset_path_status='',
        #         return_type='generator',
        #         on_failure='error'):
        #     # if ap.get('status', None):
        #     #     # this is done
        #     #     yield ap
        #     #     continue
        #     # if ap.get('state', None) == 'absent' and \
        #     #         ap.get('parentds', None) is None:
        #     #     # nothing exists at location, and there is no parent to
        #     #     # remove from
        #     #     ap['status'] = 'notneeded'
        #     #     ap['message'] = "path does not exist and is not in a dataset"
        #     #     yield ap
        #     #     continue
        #     # if ap.get('raw_input', False) and ap.get('type', None) == 'dataset':
        #     #     # make sure dataset sorting yields a dedicted entry for this one
        #     #     ap['process_content'] = True
        #     to_process.append(ap)
        #
        # if not to_process:
        #     # nothing left to do, potentially all errored before
        #     raise RuntimeError(
        #         "There should have been something to do for paths %s" % (path,))

        open_args = []
        if mode is not None:
            open_args.append(mode)
            if buffering is not None:
                open_args.append(buffering)
        elif buffering is not None:
            # Do not bother messing with it
            raise ValueError("When specifying buffering, provide mode for open")

        # Probably will be useless in Python mode since we cannot return a
        # context manager an yield all the result records at the same time
        all_results = []

        from contextlib import contextmanager
        import datalad.api as dl
        @contextmanager
        def open_read():
            # TODO cannot yield all those wonderful reports here since it would
            # be a context manager... nothing to be yielded into the Python code
            res = dl.get(path, dataset=dataset
                         # TODO: what should we do with files not under git at all?
                         # here on_failure is not effective - fails during "rendering"
                         # , on_failure='continue'
            )
            all_results.extend(res)
            files = []
            for p in path:
                # TODO: actually do all that full path deduction here probably
                # since we allow for ds.open
                files.append(open(p, *open_args))
                all_results.append({
                    'status': 'ok',
                    'action': 'open',
                    'path': p,
                    'type': 'file'
                })

            yield files

            # Nothing more to do for reading operation besides closing those
            for f in files:
                if not f.closed:
                    f.close()
                    all_results.append({
                        'status': 'ok',
                        'action': 'close',
                        'path': f.name,
                        'type': 'file'
                    })


        mode_base = mode[0] if mode is not None else 'r'
        res = {
            'r': open_read,
            #'w': open_write(),
        }[mode_base]()

        cmdline_mode = True
        return res
        # TODO: in cmdline mode we should use it as a context manager here.
        # In Python - we just need to return it I guess?
        # with res as files:
        #   # TODO: cmdline - start a shell?
        #   print("files are: %s" % str(files))
        # Since we are to use it as an actual context manager, and not as a
        # generator of result records
        #for r in all_results:
        #    yield r