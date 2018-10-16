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

import io
import os
import logging

from datalad.distribution.dataset import resolve_path
from datalad.distribution.dataset import datasetmethod
from datalad.utils import assure_list


lgr = logging.getLogger('datalad.interface.open')


@datasetmethod(name='open')
def open(
        paths,
        mode=None,
        dataset=None,
        save=True,
        message=None,
        callable=io.open,
        **open_kwargs
    ):
    """A git-annex aware io.open() (or another open-like callable) context manager

    This function provides a context manager around io.open() (or regular `open`
    if provided as `callable`) to do 'annex' operations (get, unlock, etc) on
    the paths as appropriate depending on the `mode` parameter.
    For "w"rite and "a"ppend operations introduced changes will be datalad saved
    (see `save` and `message` arguments).  In case of "w"rite mode, we simply
    remove file without bothering unlocking it to avoid unnecessary traffic and
    file copying (just to have it rewritten from scratch).
    Permissions and authorship are (attempted) to be transfered to the new file
    (TODO).

    In "a" and "r" mode file first gets `get`'ed and then `unlock`ed in "a" mode.

    Notes:
    - unlike `io.open` this context manager can take multiple paths as input
    - we introduced addnitional keyword parameters, so any `io.open` argument
      besides `mode` should be provided as the keyword argument

    Parameters
    ----------
    paths: str or list of str
      A single or multiple paths to be opene'ed
    mode: str, optional
      Passed to the callable as the first argument
    dataset: dataset, optional
      If specified, non-explicit relative paths will be taken from the top of
      the dataset, and an explicit against current directory.  See `resolve_path`
      for more information.
    save: bool, optional
      Either to save the changes introduced by "a" or "w" mode of operation
    message: str, optional
      Message for `save`
    callable: callable, optional
      An "open" function (like `io.open` or regular `open` in PY2) or any other
      which takes standard's open `mode` as the first argument, and returns an
      object with `.name` and `.closed` properties and `.close()` method.
    **open_kwargs:
      Passed to the callable as is
    """
    # Pre-treat open parameters first
    if mode is not None:
        if mode[0] not in 'rwa':
            raise ValueError("Mode must be either None or start with r, w, or a")

    open_args = []
    if mode is not None:
        open_args.append(mode)

    # Probably will be useless in Python mode since we cannot return a
    # context manager an yield all the result records at the same time.
    # But if we make it into a class, we could store them in the instance
    # so they could be inspected later on if desired?
    paths = assure_list(paths)
    resolved_paths = [resolve_path(p, dataset) for p in paths] \
        if dataset is not None else paths

    import datalad.api as dl  # heavy import so delayed

    class OpenBase(object):
        """The base class to provide context handler for open

        It will also be used to store .all_results collected from running
        all the DataLad commands for possible introspection and yielding.
        To avoid passing all those wonderful arguments, it is defined within
        the closure of the `open` function, to access its variables.
        Derived classes should overload `pre_open` and `post_close` methods
        with corresponding logic
        """
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
                self.files.append(callable(p, *open_args, **open_kwargs))
                self.all_results.append({
                    'status': 'ok',
                    'action': 'open',
                    'mode': mode,
                    'path': p,
                    'type': 'file'
                })
            return self.files if len(self.files) > 1 else self.files[0]

        def __exit__(self, exc_type, exc_val, exc_tb):
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
            if exc_type:
                self.all_results.append(
                    {
                        'status': 'error',
                        'action': 'open',
                        'path': None,
                        # TODO: "proper" way to channel exeption into results
                        'exception': (exc_type, exc_val, exc_tb)
                    }
                )
            else:
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
