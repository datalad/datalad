# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Report status of a dataset (hierarchy)'s work tree"""

__docformat__ = 'restructuredtext'


import logging
import os
import os.path as op
from six import (
    iteritems,
    text_type,
)
from collections import OrderedDict

from datalad.utils import (
    assure_list,
    assure_unicode,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    recursion_limit,
    recursion_flag,
)
from datalad.interface.utils import eval_results
import datalad.support.ansi_colors as ac
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
    rev_resolve_path,
    path_under_rev_dataset,
    rev_get_dataset_root,
)

import datalad.utils as ut

from datalad.dochelpers import single_or_plural

lgr = logging.getLogger('datalad.core.local.status')

_common_diffstatus_params = dict(
    dataset=Parameter(
        args=("-d", "--dataset"),
        doc="""specify the dataset to query.  If
        no dataset is given, an attempt is made to identify the dataset
        based on the current working directory""",
        constraints=EnsureDataset() | EnsureNone()),
    annex=Parameter(
        args=('--annex',),
        metavar='MODE',
        constraints=EnsureChoice(None, 'basic', 'availability', 'all'),
        doc="""Switch whether to include information on the annex
        content of individual files in the status report, such as
        recorded file size. By default no annex information is reported
        (faster). Three report modes are available: basic information
        like file size and key name ('basic'); additionally test whether
        file content is present in the local annex ('availability';
        requires one or two additional file system stat calls, but does
        not call git-annex), this will add the result properties
        'has_content' (boolean flag) and 'objloc' (absolute path to an
        existing annex object file); or 'all' which will report all
        available information (presently identical to 'availability').
        """),
    untracked=Parameter(
        args=('--untracked',),
        metavar='MODE',
        constraints=EnsureChoice('no', 'normal', 'all'),
        doc="""If and how untracked content is reported when comparing
        a revision to the state of the work tree. 'no': no untracked
        content is reported; 'normal': untracked files and entire
        untracked directories are reported as such; 'all': report
        individual files even in fully untracked directories."""),
    recursive=recursion_flag,
    recursion_limit=recursion_limit)


STATE_COLOR_MAP = {
    'untracked': ac.RED,
    'modified': ac.RED,
    'deleted': ac.RED,
    'added': ac.GREEN,
    'unknown': ac.YELLOW,
}


def _yield_status(ds, paths, annexinfo, untracked, recursion_limit, queried,
                  eval_submodule_state, cache):
    # take the datase that went in first
    repo_path = ds.repo.pathobj
    lgr.debug('query %s.diffstatus() for paths: %s', ds.repo, paths)
    status = ds.repo.diffstatus(
        fr='HEAD' if ds.repo.get_hexsha() else None,
        to=None,
        # recode paths with repo reference for low-level API
        paths=[repo_path / p.relative_to(ds.pathobj) for p in paths] if paths else None,
        untracked=untracked,
        eval_submodule_state=eval_submodule_state,
        _cache=cache)
    if annexinfo and hasattr(ds.repo, 'get_content_annexinfo'):
        lgr.debug('query %s.get_content_annexinfo() for paths: %s', ds.repo, paths)
        # this will amend `status`
        ds.repo.get_content_annexinfo(
            paths=paths if paths else None,
            init=status,
            eval_availability=annexinfo in ('availability', 'all'),
            ref=None)
    for path, props in iteritems(status):
        cpath = ds.pathobj / path.relative_to(repo_path)
        yield dict(
            props,
            path=text_type(cpath),
            # report the dataset path rather than the repo path to avoid
            # realpath/symlink issues
            parentds=ds.path,
        )
        queried.add(ds.pathobj)
        if recursion_limit and props.get('type', None) == 'dataset':
            subds = Dataset(text_type(cpath))
            if subds.is_installed():
                for r in _yield_status(
                        subds,
                        None,
                        annexinfo,
                        untracked,
                        recursion_limit - 1,
                        queried,
                        eval_submodule_state,
                        cache):
                    yield r


@build_doc
class Status(Interface):
    """Report on the state of dataset content.

    This is an analog to `git status` that is simultaneously crippled and more
    powerful. It is crippled, because it only supports a fraction of the
    functionality of its counter part and only distinguishes a subset of the
    states that Git knows about. But it is also more powerful as it can handle
    status reports for a whole hierarchy of datasets, with the ability to
    report on a subset of the content (selection of paths) across any number
    of datasets in the hierarchy.

    *Path conventions*

    All reports are guaranteed to use absolute paths that are underneath the
    given or detected reference dataset, regardless of whether query paths are
    given as absolute or relative paths (with respect to the working directory,
    or to the reference dataset, when such a dataset is given explicitly).
    Moreover, so-called "explicit relative paths" (i.e. paths that start with
    '.' or '..') are also supported, and are interpreted as relative paths with
    respect to the current working directory regardless of whether a reference
    dataset with specified.

    When it is necessary to address a subdataset record in a superdataset
    without causing a status query for the state _within_ the subdataset
    itself, this can be achieved by explicitly providing a reference dataset
    and the path to the root of the subdataset like so::

      datalad status --dataset . subdspath

    In contrast, when the state of the subdataset within the superdataset is
    not relevant, a status query for the content of the subdataset can be
    obtained by adding a trailing path separator to the query path (rsync-like
    syntax)::

      datalad status --dataset . subdspath/

    When both aspects are relevant (the state of the subdataset content
    and the state of the subdataset within the superdataset), both queries
    can be combined::

      datalad status --dataset . subdspath subdspath/

    When performing a recursive status query, both status aspects of subdataset
    are always included in the report.


    *Content types*

    The following content types are distinguished:

    - 'dataset' -- any top-level dataset, or any subdataset that is properly
      registered in superdataset
    - 'directory' -- any directory that does not qualify for type 'dataset'
    - 'file' -- any file, or any symlink that is placeholder to an annexed
      file
    - 'symlink' -- any symlink that is not used as a placeholder for an annexed
      file

    *Content states*

    The following content states are distinguished:

    - 'clean'
    - 'added'
    - 'modified'
    - 'deleted'
    - 'untracked'
    """
    # make the custom renderer the default one, as the global default renderer
    # does not yield meaningful output for this command
    result_renderer = 'tailored'

    _params_ = dict(
        _common_diffstatus_params,
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path to be evaluated""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        eval_subdataset_state=Parameter(
            args=("-e", "--eval-subdataset-state",),
            constraints=EnsureChoice('no', 'commit', 'full'),
            doc="""Evaluation of subdataset state (clean vs.
            modified) can be expensive for deep dataset hierarchies
            as subdataset have to be tested recursively for
            uncommitted modifications. Setting this option to
            'no' or 'commit' can substantially boost performance
            by limiting what is being tested. With 'no' no state
            is evaluated and subdataset result records typically do
            not contain a 'state' property.
            With 'commit' only a discrepancy of the HEAD commit
            shasum of a subdataset and the shasum recorded in the
            superdataset's record is evaluated,
            and the 'state' result property only reflects this
            aspect. With 'full' any other modification is considered
            too (see the 'untracked' option for further tailoring
            modification testing).
            """),
    )

    @staticmethod
    @datasetmethod(name='status')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            annex=None,
            untracked='normal',
            recursive=False,
            recursion_limit=None,
            eval_subdataset_state='full'):
        # To the next white knight that comes in to re-implement `status` as a
        # special case of `diff`. There is one fundamental difference between
        # the two commands: `status` can always use the worktree as evident on
        # disk as a contraint (e.g. to figure out which subdataset a path is in)
        # `diff` cannot do that (everything need to be handled based on a
        # "virtual" representation of a dataset hierarchy).
        # MIH concludes that while `status` can be implemented as a special case
        # of `diff` doing so would complicate and slow down both `diff` and
        # `status`. So while the apparent almost code-duplication between the
        # two commands feels wrong, the benefit is speed. Any future RF should
        # come with evidence that speed does not suffer, and complexity stays
        # on a manageable level
        ds = require_dataset(
            dataset, check_installed=True, purpose='status reporting')

        paths_by_ds = OrderedDict()
        if path:
            # sort any path argument into the respective subdatasets
            for p in sorted(assure_list(path)):
                # it is important to capture the exact form of the
                # given path argument, before any normalization happens
                # for further decision logic below
                orig_path = text_type(p)
                p = rev_resolve_path(p, dataset)
                root = rev_get_dataset_root(text_type(p))
                if root is None:
                    # no root, not possibly underneath the refds
                    yield dict(
                        action='status',
                        path=p,
                        refds=ds.path,
                        status='error',
                        message='path not underneath this dataset',
                        logger=lgr)
                    continue
                else:
                    if dataset and root == text_type(p) and \
                            not (orig_path.endswith(op.sep) or
                                 orig_path == "."):
                        # the given path is pointing to a dataset
                        # distinguish rsync-link syntax to identify
                        # the dataset as whole (e.g. 'ds') vs its
                        # content (e.g. 'ds/')
                        super_root = rev_get_dataset_root(op.dirname(root))
                        if super_root:
                            # the dataset identified by the path argument
                            # is contained in a superdataset, and no
                            # trailing path separator was found in the
                            # argument -> user wants to address the dataset
                            # as a whole (in the superdataset)
                            root = super_root

                root = ut.Path(root)
                ps = paths_by_ds.get(root, [])
                ps.append(p)
                paths_by_ds[root] = ps
        else:
            paths_by_ds[ds.pathobj] = None

        queried = set()
        content_info_cache = {}
        while paths_by_ds:
            qdspath, qpaths = paths_by_ds.popitem(last=False)
            if qpaths and qdspath in qpaths:
                # this is supposed to be a full query, save some
                # cycles sifting through the actual path arguments
                qpaths = []
            # try to recode the dataset path wrt to the reference
            # dataset
            # the path that it might have been located by could
            # have been a resolved path or another funky thing
            qds_inrefds = path_under_rev_dataset(ds, qdspath)
            if qds_inrefds is None:
                # nothing we support handling any further
                # there is only a single refds
                yield dict(
                    path=text_type(qdspath),
                    refds=ds.path,
                    action='status',
                    status='error',
                    message=(
                        "dataset containing given paths is not underneath "
                        "the reference dataset %s: %s",
                        ds, qpaths),
                    logger=lgr,
                )
                continue
            elif qds_inrefds != qdspath:
                # the path this dataset was located by is not how it would
                # be referenced underneath the refds (possibly resolved
                # realpath) -> recode all paths to be underneath the refds
                qpaths = [qds_inrefds / p.relative_to(qdspath) for p in qpaths]
                qdspath = qds_inrefds
            if qdspath in queried:
                # do not report on a single dataset twice
                continue
            qds = Dataset(text_type(qdspath))
            for r in _yield_status(
                    qds,
                    qpaths,
                    annex,
                    untracked,
                    recursion_limit
                    if recursion_limit is not None else -1
                    if recursive else 0,
                    queried,
                    eval_subdataset_state,
                    content_info_cache):
                yield dict(
                    r,
                    refds=ds.path,
                    action='status',
                    status='ok',
                )

    @staticmethod
    def custom_result_renderer(res, **kwargs):  # pragma: no cover
        if not (res['status'] == 'ok' \
                and res['action'] in ('status', 'diff') \
                and res.get('state', None) != 'clean'):
            # logging reported already
            return
        from datalad.ui import ui
        # when to render relative paths:
        #  1) if a dataset arg was given
        #  2) if CWD is the refds
        refds = res.get('refds', None)
        refds = refds if kwargs.get('dataset', None) is not None \
            or refds == os.getcwd() else None
        # Note: We have to force unicode for res['path'] because
        # interface.utils encodes it on py2 before passing it to
        # custom_result_renderer().
        path = assure_unicode(res['path']) if refds is None \
            else text_type(ut.Path(res['path']).relative_to(refds))
        type_ = res.get('type', res.get('type_src', ''))
        max_len = len('untracked')
        state = res.get('state', 'unknown')
        ui.message(u'{fill}{state}: {path}{type_}'.format(
            fill=' ' * max(0, max_len - len(state)),
            state=ac.color_word(
                state,
                STATE_COLOR_MAP.get(res.get('state', 'unknown'))),
            path=path,
            type_=' ({})'.format(
                ac.color_word(type_, ac.MAGENTA) if type_ else '')))

    @staticmethod
    def custom_result_summary_renderer(results):  # pragma: no cover
        # fish out sizes of annexed files. those will only be present
        # with --annex ...
        annexed = [
            (int(r['bytesize']), r.get('has_content', None))
            for r in results
            if r.get('action', None) == 'status' \
            and 'key' in r and 'bytesize' in r]
        if annexed:
            have_availability = any(a[1] is not None for a in annexed)
            total_size = bytes2human(sum(a[0] for a in annexed))
            # we have availability info encoded in the results
            from datalad.ui import ui
            if have_availability:
                ui.message(
                    "{} annex'd {} ({}/{} present/total size)".format(
                        len(annexed),
                        single_or_plural('file', 'files', len(annexed)),
                        bytes2human(sum(a[0] for a in annexed if a[1])),
                        total_size))
            else:
                ui.message(
                    "{} annex'd {} ({} recorded total size)".format(
                        len(annexed),
                        single_or_plural('file', 'files', len(annexed)),
                        total_size))


# TODO move to datalad.utils eventually
def bytes2human(n, format='%(value).1f %(symbol)sB'):
    """
    Convert n bytes into a human readable string based on format.
    symbols can be either "customary", "customary_ext", "iec" or "iec_ext",
    see: http://goo.gl/kTQMs

      >>> bytes2human(1)
      '1.0 B'
      >>> bytes2human(1024)
      '1.0 KB'
      >>> bytes2human(1048576)
      '1.0 MB'
      >>> bytes2human(1099511627776127398123789121)
      '909.5 YB'

      >>> bytes2human(10000, "%(value).1f %(symbol)s/sec")
      '9.8 K/sec'

      >>> # precision can be adjusted by playing with %f operator
      >>> bytes2human(10000, format="%(value).5f %(symbol)s")
      '9.76562 K'

    Taken from: http://goo.gl/kTQMs and subsequently simplified
    Original Author: Giampaolo Rodola' <g.rodola [AT] gmail [DOT] com>
    License: MIT
    """
    n = int(n)
    if n < 0:
        raise ValueError("n < 0")
    symbols = ('', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')
    prefix = {}
    for i, s in enumerate(symbols[1:]):
        prefix[s] = 1 << (i + 1) * 10
    for symbol in reversed(symbols[1:]):
        if n >= prefix[symbol]:
            value = float(n) / prefix[symbol]
            return format % locals()
    return format % dict(symbol=symbols[0], value=n)
