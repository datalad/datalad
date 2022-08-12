# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset (component) installation

"""

import logging
from os import curdir

from datalad.interface.base import Interface
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
    location_description,
    jobs_opt,
    reckless_opt,
)
from datalad.interface.results import (
    get_status_dict,
    YieldDatasets,
    is_result_matching_pathsource_argument,
)
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import (
    CapturedException,
    InsufficientArgumentsError,
)
from datalad.support.param import Parameter
from datalad.support.network import (
    RI,
    PathRI,
)
from datalad.utils import ensure_list

from datalad.distribution.dataset import (
    datasetmethod,
    resolve_path,
    require_dataset,
    EnsureDataset,
)
from datalad.distribution.get import Get
from datalad.core.distributed.clone import Clone

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.install')


@build_doc
class Install(Interface):
    """Install a dataset from a (remote) source.

    This command creates a local :term:`sibling` of an existing dataset from a
    (remote) location identified via a URL or path. Optional recursion into
    potential subdatasets, and download of all referenced data is supported.
    The new dataset can be optionally registered in an existing
    :term:`superdataset` by identifying it via the `dataset` argument (the new
    dataset's path needs to be located within the superdataset for that).

    It is recommended to provide a brief description to label the dataset's
    nature *and* location, e.g. "Michael's music on black laptop". This helps
    humans to identify data locations in distributed scenarios.  By default an
    identifier comprised of user and machine name, plus path will be generated.

    When only partial dataset content shall be obtained, it is recommended to
    use this command without the `get-data` flag, followed by a
    :func:`~datalad.api.get` operation to obtain the desired data.

    .. note::
      Power-user info: This command uses :command:`git clone`, and
      :command:`git annex init` to prepare the dataset. Registering to a
      superdataset is performed via a :command:`git submodule add` operation
      in the discovered superdataset.
    """

    # very frequently this command will yield exactly one installed dataset
    # spare people the pain of going through a list by default
    return_type = 'item-or-list'
    # as discussed in #1409 and #1470, we want to return dataset instances
    # matching what is actually available after command completion (and
    # None for any failed dataset installation)
    # TODO actually need success(containing)dataset-or-none
    result_xfm = 'successdatasets-or-none'
    # we also want to limit the returned result to explicit input arguments
    # (paths/source) and not report any implicit action, like intermediate
    # datasets
    result_filter = is_result_matching_pathsource_argument

    _examples_ = [
        dict(text="Install a dataset from GitHub into the current directory",
             code_py="install("
             "source='https://github.com/datalad-datasets/longnow"
             "-podcasts.git')",
             code_cmd="datalad install "
             "https://github.com/datalad-datasets/longnow-podcasts.git"),
        dict(text="Install a dataset as a subdataset into the current dataset",
             code_py="""\
             install(dataset='.',
                     source='https://github.com/datalad-datasets/longnow-podcasts.git')""",
             code_cmd="""\
             datalad install -d . \\
             --source='https://github.com/datalad-datasets/longnow-podcasts.git'"""),
        dict(text="Install a dataset, and get all content right away",
             code_py="""\
             install(source='https://github.com/datalad-datasets/longnow-podcasts.git',
                     get_data=True)""",
             code_cmd="""\
             datalad install --get-data \\
             -s https://github.com/datalad-datasets/longnow-podcasts.git"""),
        dict(text="Install a dataset with all its subdatasets",
             code_py="""\
             install(source='https://github.com/datalad-datasets/longnow-podcasts.git',
                     recursive=True)""",
             code_cmd="""\
             datalad install -r \\
             https://github.com/datalad-datasets/longnow-podcasts.git"""),
    ]

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            # TODO: this probably changes to install into the dataset (add_to_super)
            # and to install the thing 'just there' without operating 'on' a dataset.
            # Adapt doc.
            # MIH: `shouldn't this be the job of `add`?
            doc="""specify the dataset to perform the install operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            in a parent directory of the current working directory and/or the
            `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            nargs="*",
            # doc: TODO
            doc="""path/name of the installation target.  If no `path` is
            provided a destination path will be derived from a source URL
            similar to :command:`git clone`"""),
        source=Parameter(
            args=("-s", "--source"),
            metavar='SOURCE',
            doc="URL or local path of the installation source",
            constraints=EnsureStr() | EnsureNone()),
        branch=Parameter(
            args=("--branch",),
            doc="""Clone source at this branch or tag. This option applies only
            to the top-level dataset not any subdatasets that may be cloned
            when installing recursively. Note that if the source is a RIA URL
            with a version, it takes precedence over this option.""",
            constraints=EnsureStr() | EnsureNone()),
        get_data=Parameter(
            args=("-g", "--get-data",),
            doc="""if given, obtain all data content too""",
            action="store_true"),
        description=location_description,
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        reckless=reckless_opt,
        jobs=jobs_opt,
    )

    @staticmethod
    @datasetmethod(name='install')
    @eval_results
    def __call__(
            path=None,
            *,
            source=None,
            dataset=None,
            get_data=False,
            description=None,
            recursive=False,
            recursion_limit=None,
            reckless=None,
            jobs="auto",
            branch=None):

        # normalize path argument to be equal when called from cmdline and
        # python and nothing was passed into `path`
        path = ensure_list(path)

        if not source and not path:
            raise InsufficientArgumentsError(
                "Please provide at least a source or a path")

        #  Common kwargs to pass to underlying git/install calls.
        #  They might need adjustments (e.g. for recursion_limit, but
        #  otherwise would be applicable throughout
        #
        # There should have been more of common options!
        # since underneath get could do similar installs
        common_kwargs = dict(
            get_data=get_data,
            recursive=recursive,
            recursion_limit=recursion_limit,
            # git_opts=git_opts,
            # annex_opts=annex_opts,
            reckless=reckless,
            jobs=jobs,
        )

        # did we explicitly get a dataset to install into?
        # if we got a dataset, path will be resolved against it.
        # Otherwise path will be resolved first.
        ds = None
        if dataset is not None:
            ds = require_dataset(dataset, check_installed=True,
                                 purpose='install')
            common_kwargs['dataset'] = dataset
        # pre-compute for results below
        refds_path = ds if ds is None else ds.path

        # switch into the two scenarios without --source:
        # 1. list of URLs
        # 2. list of (sub)dataset content
        if source is None:
            # we need to collect URLs and paths
            to_install = []
            to_get = []
            # TODO: this approach is problematic, it disrupts the order of input args.
            # consequently results will be returned in an unexpected order when a
            # mixture of source URL and paths is given. Reordering is only possible when
            # everything in here is fully processed before any results can be yielded.
            # moreover, I think the semantics of the status quo implementation are a
            # bit complicated: in a mixture list a source URL will lead to a new dataset
            # at a generated default location, but a path will lead to a subdataset
            # at that exact location
            for urlpath in path:
                ri = RI(urlpath)
                (to_get if isinstance(ri, PathRI) else to_install).append(urlpath)

            # 1. multiple source URLs
            for s in to_install:
                lgr.debug("Install passes into install source=%s", s)
                for r in Install.__call__(
                        source=s,
                        description=description,
                        # we need to disable error handling in order to have it done at
                        # the very top, otherwise we are not able to order a global
                        # "ignore-and-keep-going"
                        on_failure='ignore',
                        return_type='generator',
                        result_renderer='disabled',
                        result_xfm=None,
                        result_filter=None,
                        **common_kwargs):
                    # no post-processing of the installed content on disk
                    # should be necessary here, all done by code further
                    # down that deals with an install from an actual `source`
                    # any necessary fixes should go there too!
                    r['refds'] = refds_path
                    yield r

            # 2. one or more dataset content paths
            if to_get:
                lgr.debug("Install passes into get %d items", len(to_get))
                # all commented out hint on inability to pass those options
                # into underlying install-related calls.
                # Also need to pass from get:
                #  annex_get_opts

                for r in Get.__call__(
                        to_get,
                        # TODO should pass-through description, not sure why disabled
                        # description=description,
                        # we need to disable error handling in order to have it done at
                        # the very top, otherwise we are not able to order a global
                        # "ignore-and-keep-going"
                        on_failure='ignore',
                        return_type='generator',
                        result_xfm=None,
                        result_renderer='disabled',
                        result_filter=None,
                        **common_kwargs):
                    # no post-processing of get'ed content on disk should be
                    # necessary here, this is the responsibility of `get`
                    # (incl. adjusting parent's gitmodules when submodules end
                    # up in an "updated" state (done in get helpers)
                    # any required fixes should go there!
                    r['refds'] = refds_path
                    yield r

            # we are done here
            # the rest is about install from a `source`
            return

        # an actual `source` was given
        if source and path and len(path) > 1:
            # exception is ok here, if this fails it is either direct user error
            # or we fucked up one of our internal calls
            raise ValueError(
                "install needs a single PATH when source is provided.  "
                "Was given multiple PATHs: %s" % str(path))

        # parameter constraints:
        if not source:
            # exception is ok here, if this fails it is either direct user error
            # or we fucked up one of our internal calls
            raise InsufficientArgumentsError(
                "a `source` is required for installation")

        # code below deals with a single path only
        path = path[0] if path else None

        if source == path:
            # even if they turn out to be identical after resolving symlinks
            # and more sophisticated witchcraft, it would still happily say
            # "it appears to be already installed", so we just catch an
            # obviously pointless input combination
            yield get_status_dict(
                'install', path=path, status='impossible', logger=lgr,
                source_url=source, refds=refds_path,
                message="installation `source` and destination `path` are identical. "
                "If you are trying to add a subdataset simply use the `save` command")
            return

        # resolve the target location (if local) against the provided dataset
        # or CWD:
        if path is not None:
            # MIH everything in here is highly similar to what common
            # interface helpers do (or should/could do), but at the same
            # is very much tailored to just apply to `install` -- I guess
            # it has to stay special

            # Should work out just fine for regular paths, so no additional
            # conditioning is necessary
            try:
                path_ri = RI(path)
            except Exception as e:
                ce = CapturedException(e)
                raise ValueError(
                    "invalid path argument {}: ({})".format(path, ce))
            try:
                # Wouldn't work for SSHRI ATM, see TODO within SSHRI
                # yoh: path should be a local path, and mapping note within
                #      SSHRI about mapping localhost:path to path is kinda
                #      a peculiar use-case IMHO
                # TODO Stringification can be removed once PY35 is no longer
                # supported
                path = str(resolve_path(path_ri.localpath, dataset))
                # any `path` argument that point to something local now
                # resolved and is no longer a URL
            except ValueError:
                # `path` is neither a valid source nor a local path.
                # TODO: The only thing left is a known subdataset with a
                # name, that is not a path; Once we correctly distinguish
                # between path and name of a submodule, we need to consider
                # this.
                # For now: Just raise
                raise ValueError("Invalid path argument {0}".format(path))
        # `path` resolved, if there was any.

        # clone dataset, will also take care of adding to superdataset, if one
        # is given
        res = Clone.__call__(
            source, path, dataset=ds, description=description,
            reckless=reckless,
            git_clone_opts=["--branch=" + branch] if branch else None,
            # we need to disable error handling in order to have it done at
            # the very top, otherwise we are not able to order a global
            # "ignore-and-keep-going"
            result_xfm=None,
            return_type='generator',
            result_renderer='disabled',
            result_filter=None,
            on_failure='ignore')
        # helper
        as_ds = YieldDatasets()
        destination_dataset = None
        for r in res:
            if r['action'] == 'install' and r['type'] == 'dataset':
                # make sure logic below is valid, only one dataset result is
                # coming back
                assert(destination_dataset is None)
                destination_dataset = as_ds(r)
            r['refds'] = refds_path
            yield r
        assert(destination_dataset)

        # Now, recursive calls:
        if recursive or get_data:
            # dataset argument must not be passed inside since we use bound .get
            # It is ok to do "inplace" as long as we still return right
            # after the loop ends
            common_kwargs.pop('dataset', '')
            for r in destination_dataset.get(
                    curdir,
                    description=description,
                    # we need to disable error handling in order to have it done at
                    # the very top, otherwise we are not able to order a global
                    # "ignore-and-keep-going"
                    on_failure='ignore',
                    return_type='generator',
                    result_xfm=None,
                    result_renderer='disabled',
                    **common_kwargs):
                r['refds'] = refds_path
                yield r
        # at this point no further post-processing should be necessary,
        # `clone` and `get` must have done that (incl. parent handling)
        # if not, bugs should be fixed in those commands
        return
