# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for reporting changes in datasets"""

__docformat__ = 'restructuredtext'


import logging
import stat
from os.path import join as opj
from os.path import curdir
from os.path import isdir
from os.path import relpath
from os.path import normpath


from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureChoice
from datalad.support.exceptions import CommandError
from datalad.support.param import Parameter
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.cmd import GitRunner

from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod

from datalad.utils import with_pathsep as _with_sep
from datalad.utils import path_startswith

from datalad.consts import PRE_INIT_COMMIT_SHA


lgr = logging.getLogger('datalad.interface.diff')


# from Git docs
state_map = {
    'A': 'added',
    'C': 'copied',
    'D': 'deleted',
    'M': 'modified',
    'R': 'renamed',
    'T': 'typechange',
    'U': 'unmerged',
    'X': 'unknown_potentialbug',
}


def _translate_status(label, ap):
    if label[0] in ('C', 'R', 'M') and len(label) > 1:
        ap['perc_similarity'] = float(label[1:])
        label = label[0]
    ap['state'] = state_map[label]


def _translate_type(mode, ap, prop):
    if mode == 0:
        ap[prop] = None
    elif mode == stat.S_IFDIR | stat.S_IFLNK:
        ap[prop] = 'dataset'
    elif stat.S_ISDIR(mode):
        # not sure if this can happen at all, at least not in the tests...
        ap[prop] = 'directory'
    else:
        ap[prop] = 'file'


def _get_untracked_content(dspath, report_untracked, paths=None):
    cmd = ['git', '--work-tree=.', 'status', '--porcelain',
           # file names NULL terminated
           '-z',
           # we never want to touch submodules, they cannot be untracked
           '--ignore-submodules=all',
           # fully untracked dirs as such, the rest as files
           '--untracked={}'.format(report_untracked)]
    try:
        stdout, stderr = GitRunner(cwd=dspath).run(
            cmd,
            log_stderr=True,
            log_stdout=True,
            log_online=False,
            expect_stderr=False,
            shell=False,
            expect_fail=True)
    except CommandError as e:
        # TODO should we catch any and handle them in here?
        raise e

    if paths:
        paths = [r['path'] for r in paths]
        if len(paths) == 1 and paths[0] == dspath:
            # nothing to filter
            paths = None

    from datalad.utils import assure_unicode

    for line in stdout.split('\0'):
        if not line:
            continue
        line = assure_unicode(line)
        if not line.startswith('?? '):
            # nothing untracked, ignore, task of `diff`
            continue
        apath = opj(
            dspath,
            # strip state marker
            line[3:])
        norm_apath = normpath(apath)
        if paths and not any(norm_apath == p or path_startswith(apath, p)
                             for p in paths):
            # we got a whitelist for paths, don't report any other
            continue
        ap = dict(
            path=norm_apath,
            parentds=dspath,
            state='untracked',
            type='directory' if isdir(apath) else 'file')
        yield ap


def _parse_git_diff(dspath, diff_thingie=None, paths=None,
                    ignore_submodules='none', staged=False):
    # use '--work-tree=.' to get direct omde to cooperate
    cmd = ['git', '--work-tree=.', 'diff', '--raw',
           # file names NULL terminated
           '-z',
           # how to treat submodules (see git diff docs)
           '--ignore-submodules={}'.format(ignore_submodules),
           # never abbreviate sha sums
           '--abbrev=40']
    if staged:
        cmd.append('--staged')
    if diff_thingie:
        cmd.append(diff_thingie)
    if paths:
        cmd.append('--')
        cmd.extend(ap['path'] for ap in paths if ap.get('raw_input', False))

    try:
        stdout, stderr = GitRunner(cwd=dspath).run(
            cmd,
            log_stderr=True,
            log_stdout=True,
            log_online=False,
            expect_stderr=False,
            shell=False,
            expect_fail=True)
    except CommandError as e:
        if 'bad revision' in e.stderr:
            yield dict(
                path=dspath,
                type='dataset',
                status='impossible',
                message=e.stderr.strip())
            return
        raise

    ap = None
    for line in stdout.split('\0'):
        if not line:
            continue
        if line.startswith(':'):
            # a new path
            # yield any existing one
            if ap:
                yield ap
                ap = None
            # start new record
            m_src, m_dst, sha_src, sha_dst, status = \
                line[1:].split()
            ap = dict(
                mode_src=int(m_src, base=8),
                mode=int(m_dst, base=8),
                revision_src=sha_src if sha_src != '0' * 40 else None,
                revision=sha_dst if sha_dst != '0' * 40 else None,
                parentds=dspath)
            _translate_status(status, ap)
            _translate_type(ap['mode'], ap, 'type')
            _translate_type(ap['mode_src'], ap, 'type_src')
        else:
            # a filename
            if 'path' in ap:
                ap['path_src'] = ap['path']
            ap['path'] = opj(dspath, line)
    if ap:
        yield ap


@build_doc
class Diff(Interface):
    """Report changes of dataset components.

    Reports can be generated for changes between recorded revisions, or
    between a revision and the state of a dataset's work tree.

    Unlike 'git diff', this command also reports untracked content when
    comparing a revision to the state of the work tree. Such content is
    marked with the property `state='untracked'` in the command results.

    The following types of changes are distinguished and reported via the
    `state` result property:

    - added
    - copied
    - deleted
    - modified
    - renamed
    - typechange
    - unmerged
    - untracked

    Whenever applicable, source and/or destination revisions are reported
    to indicate when exactly within the requested revision range a particular
    component changed its status.

    Optionally, the reported changes can be limited to a subset of paths
    within a dataset.
    """

    # make the custom renderer the default one, as the global default renderer
    # does not yield meaningful output for this command
    result_renderer = 'tailored'

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to query.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path to be evaluated""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        revision=Parameter(
            args=('--revision',),
            metavar='REVISION EXPRESSION',
            nargs='?',
            doc="""comparison reference specification. Three modes are
            supported: 1) <revision> changes you have in your working tree
            relative to the named revision (this can also be a branch name,
            tag, commit or any label Git can understand). 2) <revision>..<revision>
            changes between two arbitrary revisions. 3) <revision>...<revision>
            changes on the branch containing and up to the second <revision>,
            starting at a common ancestor of both revisions."""),
        staged=Parameter(
            args=("--staged",),
            action="store_true",
            doc="""get the changes already staged for a commit relative
            to an optionally given revision (by default the most recent one)"""),
        ignore_subdatasets=Parameter(
            args=('--ignore-subdatasets',),
            constraints=EnsureChoice('none', 'untracked', 'dirty', 'all'),
            doc="""speed up execution by (partially) not evaluating the state of
            subdatasets in a parent dataset. With "none" a subdataset is
            considered modified when it either contains untracked or modified
            content or its last saved state differs from that recorded in the
            parent dataset. When "untracked" is used subdatasets are not
            considered modified when they only contain untracked content (but
            they are still scanned for modified content). Using "dirty" ignores
            all changes to the work tree of subdatasets, only changes to the
            revisions stored in the parent dataset are shown. Using "all" hides
            all changes to subdatasets. Note, even with "all" recursive
            execution will still report other changes in any existing
            subdataset, only the subdataset record in a parent dataset
            is not  evaluated."""),
        report_untracked=Parameter(
            args=('--report-untracked',),
            constraints=EnsureChoice('no', 'normal', 'all'),
            doc="""If and how untracked content is reported when comparing
            a revision to the state of the work tree. 'no': no untracked files
            are reported; 'normal': untracked files and entire untracked
            directories are reported as such; 'all': report individual files
            even in fully untracked directories."""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit)

    @staticmethod
    @datasetmethod(name='diff')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            revision=None,
            staged=False,
            ignore_subdatasets='none',
            report_untracked='normal',
            recursive=False,
            recursion_limit=None):
        if not dataset and not path:
            # act on the whole dataset if nothing else was specified
            dataset = curdir
        refds_path = Interface.get_refds_path(dataset)

        to_process = []
        # tracked what commit ranges we want to diff per dataset
        ds_diffies = {}
        for ap in AnnotatePaths.__call__(
                path=path,
                dataset=refds_path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='diff',
                # unavailable is OK, because we might query for a deleted file
                unavailable_path_status='',
                nondataset_path_status='impossible',
                # must not use `modified`, infinite loop otherwise
                modified=None,
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # we know what to report already
                yield ap
                continue
            if ap.get('type', None) == 'dataset':
                ap['process_content'] = True
            if ap.get('raw_input', False) or ap['path'] == refds_path:
                # prepopulate the revision specs for all input paths
                ds_diffies[ap['path']
                           if ap.get('type', None) == 'dataset'
                           else ap['parentds']] = revision
            to_process.append(ap)

        # sort into datasets
        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                to_process,
                refds_path=refds_path)
        assert(not completed)

        for ds_path in sorted(content_by_ds.keys()):
            if ds_path not in ds_diffies:
                # we don't know how to diff
                # this was not neither an input path, not did we see it
                # when diffing its parent
                continue
            content_paths = content_by_ds[ds_path]
            revision = ds_diffies[ds_path]
            for r in _parse_git_diff(
                    ds_path,
                    diff_thingie=ds_diffies[ds_path],
                    paths=content_paths,
                    ignore_submodules=ignore_subdatasets,
                    staged=staged):
                r.update(dict(
                    action='diff',
                    logger=lgr))
                if refds_path:
                    r['refds'] = refds_path
                if 'status' not in r:
                    r['status'] = 'ok'
                if r.get('type', None) == 'dataset':
                    # this is a subdataset report
                    # we need to use the reported commit range to properly adjust the
                    # query once we hit that subdataset
                    from_rev = r.get('revision_src', '')
                    to_rev = r.get('revision', '')
                    subrev = '{}..{}'.format(
                        from_rev if from_rev else PRE_INIT_COMMIT_SHA,
                        to_rev if to_rev else '',
                    )
                    if from_rev and from_rev == to_rev:
                        # this is a special case, where subdataset reported changes without
                        # a change in state/commit -- this is code for uncommited changes
                        # in the subdataset (including staged ones). In such a case, we
                        # must not provide a diff range, but only the source commit we want
                        # to diff against
                        # XXX if this is changed, likely the same logic in annotate_paths needs
                        # changing too!
                        subrev = from_rev
                    ds_diffies[r['path']] = subrev
                yield r
            if (revision and '..' in revision) or report_untracked == 'no':
                # don't look for untracked content, we got a revision range
                continue
            for r in _get_untracked_content(
                    ds_path,
                    report_untracked,
                    paths=content_paths):
                r.update(dict(
                    action='diff',
                    logger=lgr))
                if refds_path:
                    r['refds'] = refds_path
                if 'status' not in r:
                    r['status'] = 'ok'
                yield r

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui
        if not res['status'] == 'ok':
            # logging reported already
            return
        path = relpath(res['path'], start=res['refds']) \
            if res.get('refds', None) else res['path']
        type_ = res.get('type', res.get('type_src', ''))
        max_len = len('untracked(directory)')
        state_msg = '{}{}'.format(
            res['state'],
            '({})'.format(type_ if type_ else ''))
        ui.message('{fill}{state_msg}: {path}'.format(
            fill=' ' * max(0, max_len - len(state_msg)),
            state_msg=state_msg,
            path=path))
