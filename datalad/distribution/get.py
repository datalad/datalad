# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for getting dataset content

"""

import logging
import os.path as op
import re

from datalad.config import ConfigManager
from datalad.core.distributed.clone import clone_dataset
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.distribution.utils import _get_flexible_source_candidates
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.common_opts import (
    jobs_opt,
    location_description,
    reckless_opt,
    recursion_flag,
)
from datalad.interface.results import (
    annexjson2result,
    get_status_dict,
    is_ok_dataset,
    results_from_annex_noinfo,
    results_from_paths,
    success_status_map,
)
from datalad.local.subdatasets import Subdatasets
from datalad.support.annexrepo import AnnexRepo
from datalad.support.collections import ReadOnlyDict
from datalad.support.constraints import (
    EnsureChoice,
    EnsureInt,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
    InsufficientArgumentsError,
)
from datalad.support.gitrepo import (
    GitRepo,
    _fixup_submodule_dotgit_setup,
)
from datalad.support.network import (
    RI,
    URL,
    urlquote,
)
from datalad.support.parallel import ProducerConsumerProgressLog
from datalad.support.param import Parameter
from datalad.utils import (
    Path,
    get_dataset_root,
    shortened_repr,
    unique,
)

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.get')


def _get_remotes_having_commit(repo, commit_hexsha, with_urls_only=True):
    """Traverse all branches of the remote and check if commit in any of their ancestry

    It is a generator yielding names of the remotes
    """
    remote_branches = [
        b['refname:strip=2']
        for b in repo.for_each_ref_(
            fields='refname:strip=2',
            pattern='refs/remotes',
            contains=commit_hexsha)]
    return [
        remote
        for remote in repo.get_remotes(with_urls_only=with_urls_only)
        if any(rb.startswith(remote + '/') for rb in remote_branches)
    ]


def _get_flexible_source_candidates_for_submodule(ds, sm):
    """Assemble candidate locations from where to clone a submodule

    The following location candidates are considered. For each candidate a
    cost is given in parenthesis, higher values indicate higher cost, and
    thus lower priority:

    - A datalad URL recorded in `.gitmodules` (cost 590). This allows for
      datalad URLs that require additional handling/resolution by datalad, like
      ria-schemes (ria+http, ria+ssh, etc.)

    - A URL or absolute path recorded for git in `.gitmodules` (cost 600).

    - URL of any configured superdataset remote that is known to have the
      desired submodule commit, with the submodule path appended to it.
      There can be more than one candidate (cost 650).

    - In case `.gitmodules` contains a relative path instead of a URL,
      the URL of any configured superdataset remote that is known to have the
      desired submodule commit, with this relative path appended to it.
      There can be more than one candidate (cost 650).

    - In case `.gitmodules` contains a relative path as a URL, the absolute
      path of the superdataset, appended with this relative path (cost 900).

    Additional candidate URLs can be generated based on templates specified as
    configuration variables with the pattern

      `datalad.get.subdataset-source-candidate-<name>`

    where `name` is an arbitrary identifier. If name starts with three digits
    (e.g. '400myserver') these will be interpreted as a cost, and the
    respective candidate will be sorted into the generated candidate list
    according to this cost. If no cost is given, a default of 700
    is used.

    A template string assigned to such a variable can utilize the Python format
    mini language and may reference a number of properties that are inferred
    from the parent dataset's knowledge about the target subdataset. Properties
    include any submodule property specified in the respective `.gitmodules`
    record. For convenience, an existing `datalad-id` record is made available
    under the shortened name `id`.

    Additionally, the URL of any configured remote that contains the respective
    submodule commit is available as `remoteurl-<name>` property, where `name`
    is the configured remote name.

    Lastly, all candidates are sorted according to their cost (lower values
    first), and duplicate URLs are stripped, while preserving the first item in the
    candidate list.

    More information on this feature can be found at
    http://handbook.datalad.org/r.html?clone-priority

    Parameters
    ----------
    ds : Dataset
      Parent dataset of to-be-installed subdataset.
    sm : dict
      Submodule record as produced by `subdatasets()`.

    Returns
    -------
    list of dict
      Where each dict has keys 'cost' (int), 'name' (str), 'url' (str).
      Names are not unique and either derived from the name of the respective
      remote, template configuration variable, or 'local'.
    """

    # short cuts
    ds_repo = ds.repo
    sm_url = sm.get('gitmodule_url', None)
    sm_datalad_url = sm.get('gitmodule_datalad-url', None)
    sm_path = op.relpath(sm['path'], start=sm['parentds'])

    clone_urls = []

    # CANDIDATE: tracking remote of the current branch
    tracking_remote, tracking_branch = ds_repo.get_tracking_branch()
    candidate_remotes = [tracking_remote] if tracking_remote else []

    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule
    last_commit = ds_repo.get_last_commit_hexsha(sm_path)
    if last_commit:
        # CANDIDATE: any remote that has the commit when the submodule was
        # last modified

        # ideally should also give preference to the remotes which have
        # the same branch checked out I guess
        candidate_remotes += list(_get_remotes_having_commit(ds_repo, last_commit))

    # prepare a dict to generate URL candidates from templates
    sm_candidate_props = {
        k[10:].replace('datalad-id', 'id'): v
        for k, v in sm.items()
        if k.startswith('gitmodule_')
    }

    for remote in unique(candidate_remotes):
        remote_url = ds_repo.get_remote_url(remote, push=False)

        # Directly on parent's ds url
        if remote_url:
            # make remotes and their URLs available to template rendering
            sm_candidate_props['remoteurl-{}'.format(remote)] = remote_url
            # attempt: submodule checkout at parent remote URL
            # We might need to quote sm_path portion, e.g. for spaces etc
            if isinstance(RI(remote_url), URL):
                sm_path_url = urlquote(sm_path)
            else:
                sm_path_url = sm_path

            clone_urls.extend(
                dict(cost=650, name=remote, url=url)
                for url in _get_flexible_source_candidates(
                    # alternate suffixes are tested by `clone` anyways
                    sm_path_url, remote_url, alternate_suffix=False)
            )

            # attempt: provided (configured?) submodule URL
            # TODO: consider supporting DataLadRI here?  or would confuse
            #  git and we wouldn't want that (i.e. not allow pure git clone
            #  --recursive)
            if sm_url:
                clone_urls.extend(
                    dict(cost=600, name=remote, url=url)
                    for url in _get_flexible_source_candidates(
                        sm_url,
                        remote_url,
                        alternate_suffix=False)
                )

    cost_candidate_expr = re.compile('[0-9][0-9][0-9].*')
    candcfg_prefix = 'datalad.get.subdataset-source-candidate-'
    for name, tmpl in [(c[len(candcfg_prefix):],
                        ds_repo.config[c])
                       for c in ds_repo.config.keys()
                       if c.startswith(candcfg_prefix)]:
        # ensure that there is only one template of the same name
        if type(tmpl) == tuple and len(tmpl) > 1:
            raise ValueError(
                f"There are multiple URL templates for submodule clone "
                f"candidate '{name}', but only one is allowed. "
                f"Check datalad.get.subdataset-source-candidate-* configuration!"
            )
        try:
            url = tmpl.format(**sm_candidate_props)
        except KeyError as e:
            ce = CapturedException(e)
            lgr.warning(
                "Failed to format template %r for a submodule clone. "
                "Error: %s", tmpl, ce
            )
            continue
        # we don't want "flexible_source_candidates" here, this is
        # configuration that can be made arbitrarily precise from the
        # outside. Additional guesswork can only make it slower
        has_cost = cost_candidate_expr.match(name) is not None
        clone_urls.append(
            # assign a default cost, if a config doesn't have one
            dict(
                cost=int(name[:3]) if has_cost else 700,
                name=name[3:] if has_cost else name,
                url=url,
                from_config=True,
            ))

    # CANDIDATE: the actual configured gitmodule URL
    if sm_url:
        clone_urls.extend(
            dict(cost=900, name='local', url=url)
            for url in _get_flexible_source_candidates(
                sm_url,
                ds.path,
                alternate_suffix=False)
            # avoid inclusion of submodule location itself
            if url != sm['path']
        )

    # Consider original datalad URL in .gitmodules before any URL that is meant
    # to be consumed by git:
    if sm_datalad_url:
        clone_urls.append(
            dict(cost=590, name='dl-url', url=sm_datalad_url)
        )

    # sort all candidates by their label, thereby allowing a
    # candidate provided by configuration to purposefully
    # sort before or after automatically generated configuration
    clone_urls = sorted(clone_urls, key=lambda x: x['cost'])
    # take out any duplicate source candidates
    # unique() takes out the duplicated at the tail end
    clone_urls = unique(clone_urls, lambda x: x['url'])
    lgr.debug('Assembled %i clone candidates for %s: %s',
              len(clone_urls), sm_path, [cand['url'] for cand in clone_urls])

    return clone_urls


def _install_subds_from_flexible_source(ds, sm, **kwargs):
    """Tries to obtain a given subdataset from several meaningful locations

    Parameters
    ----------
    ds : Dataset
      Parent dataset of to-be-installed subdataset.
    sm : dict
      Submodule record as produced by `subdatasets()`.
    **kwargs
      Passed onto clone()
    """
    sm_path = op.relpath(sm['path'], start=sm['parentds'])
    # compose a list of candidate clone URLs
    clone_urls = _get_flexible_source_candidates_for_submodule(ds, sm)

    # prevent inevitable exception from `clone`
    dest_path = op.join(ds.path, sm_path)
    clone_urls_ = [src['url'] for src in clone_urls if src['url'] != dest_path]

    if not clone_urls:
        # yield error
        yield get_status_dict(
            action='install',
            ds=ds,
            status='error',
            message=(
                "Have got no candidates to install subdataset %s from.",
                sm_path),
            logger=lgr,
        )
        return

    for res in clone_dataset(
            clone_urls_,
            Dataset(dest_path),
            cfg=ds.config,
            checkout_gitsha=sm['gitshasum'],
            **kwargs):
        if res.get('action', None) == 'install' and \
                res.get('status', None) == 'ok' and \
                res.get('type', None) == 'dataset' and \
                res.get('path', None) == dest_path:
            _fixup_submodule_dotgit_setup(ds, sm_path)

            section_name = 'submodule.{}'.format(sm['gitmodule_name'])
            # register the submodule as "active" in the superdataset
            ds.config.set(
                '{}.active'.format(section_name),
                'true',
                reload=False, force=True, scope='local',
            )
            ds.config.set(
                '{}.url'.format(section_name),
                # record the actual source URL of the successful clone
                # and not a funky prediction based on the parent ds
                # like ds.repo.update_submodule() would do (does not
                # accept a URL)
                res['source']['giturl'],
                reload=True, force=True, scope='local',
            )
        yield res

    subds = Dataset(dest_path)
    if not subds.is_installed():
        lgr.debug('Desired subdataset %s did not materialize, stopping', subds)
        return

    # check whether clone URL generators were involved
    cand_cfg = [rec for rec in clone_urls if rec.get('from_config', False)]
    if cand_cfg:
        # get a handle on the configuration that is specified in the
        # dataset itself (local and dataset)
        super_cfg = ConfigManager(dataset=ds, source='branch-local')
        need_reload = False
        for rec in cand_cfg:
            # check whether any of this configuration originated from the
            # superdataset. if so, inherit the config in the new subdataset
            # clone unless that config is already specified in the new
            # subdataset which can happen during postclone_cfg routines.
            # if not, keep things clean in order to be able to move with any
            # outside configuration change
            for c in ('datalad.get.subdataset-source-candidate-{}{}'.format(
                          rec['cost'], rec['name']),
                      'datalad.get.subdataset-source-candidate-{}'.format(
                          rec['name'])):
                if c in super_cfg.keys() and c not in subds.config.keys():
                    subds.config.set(c, super_cfg.get(c), scope='local',
                                     reload=False)
                    need_reload = True
                    break
        if need_reload:
            subds.config.reload(force=True)


def _install_necessary_subdatasets(
        ds, path, reckless, refds_path, description=None):
    """Installs subdatasets of `ds`, that are necessary to obtain in order
    to have access to `path`.

    Gets the subdataset containing `path` regardless of whether or not it was
    already installed. While doing so, installs everything necessary in between
    the uppermost installed one and `path`.

    Note: `ds` itself has to be installed.

    Parameters
    ----------
    ds: Dataset
    path: str
    reckless: bool
    """
    # figuring out what dataset to start with, --contains limits --recursive
    # to visit only subdataset on the trajectory to the target path
    subds_trail = ds.subdatasets(contains=path, recursive=True,
                                 on_failure="ignore",
                                 result_filter=is_ok_dataset,
                                 result_renderer='disabled')
    if not subds_trail:
        # there is not a single known subdataset (installed or not)
        # for this path -- job done
        return
    # otherwise we start with the one deepest down
    cur_subds = subds_trail[-1]

    while not GitRepo.is_valid_repo(cur_subds['path']):
        # install using helper that give some flexibility regarding where to
        # get the module from
        for res in _install_subds_from_flexible_source(
                Dataset(cur_subds['parentds']),
                cur_subds,
                reckless=reckless,
                description=description):
            if res.get('action', None) == 'install':
                if res['status'] == 'ok':
                    # report installation, whether it helped or not
                    res['message'] = (
                        "Installed subdataset in order to get %s",
                        str(path))
                    # next subdataset candidate
                    sd = Dataset(res['path'])
                    yield res
                elif res['status'] in ('impossible', 'error'):
                    yield res
                    # we cannot go deeper, we need to stop
                    return
                else:
                    # report unconditionally to caller
                    yield res
        if sd.pathobj == path:
            # we've just got the target subdataset, we're done
            return
        # now check whether the just installed subds brought us any closer to
        # the target path
        subds_trail = sd.subdatasets(contains=path, recursive=False,
                                     on_failure='ignore',
                                     result_filter=is_ok_dataset,
                                     result_renderer='disabled')
        if not subds_trail:
            # no (newly available) subdataset gets us any closer
            return
        # next round
        cur_subds = subds_trail[-1]


def _recursive_install_subds_underneath(ds, recursion_limit, reckless, start=None,
                 refds_path=None, description=None, jobs=None, producer_only=False):
    if isinstance(recursion_limit, int) and recursion_limit <= 0:
        return
    # install using helper that give some flexibility regarding where to
    # get the module from

    # Keep only paths, to not drag full instances of Datasets along,
    # they are cheap to instantiate
    sub_paths_considered = []
    subs_notneeded = []

    def gen_subs_to_install():  # producer
        for sub in ds.subdatasets(
                path=start,
                return_type='generator',
                result_renderer='disabled'):
            sub_path = sub['path']
            sub_paths_considered.append(sub_path)
            if sub.get('gitmodule_datalad-recursiveinstall', '') == 'skip':
                lgr.debug(
                    "subdataset %s is configured to be skipped on recursive installation",
                    sub_path)
                continue
            # TODO: Yarik is lost among all parentds, ds, start, refds_path so is not brave enough to
            # assume any from the record, thus will pass "ds.path" around to consumer
            yield ds.path, ReadOnlyDict(sub), recursion_limit

    def consumer(ds_path__sub__limit):
        ds_path, sub, recursion_limit = ds_path__sub__limit
        subds = Dataset(sub['path'])
        if sub.get('state', None) != 'absent':
            rec = get_status_dict('install', ds=subds, status='notneeded', logger=lgr, refds=refds_path)
            subs_notneeded.append(rec)
            yield rec
            # do not continue, even if an intermediate dataset exists it
            # does not imply that everything below it does too
        else:
            # TODO: here we need another "ds"!  is it within "sub"?
            yield from _install_subds_from_flexible_source(
                Dataset(ds_path), sub, reckless=reckless, description=description)

        if not subds.is_installed():
            # an error result was emitted, and the external consumer can decide
            # what to do with it, but there is no point in recursing into
            # something that should be there, but isn't
            lgr.debug('Subdataset %s could not be installed, skipped', subds)
            return

        # recurse
        # we can skip the start expression, we know we are within
        for res in _recursive_install_subds_underneath(
                subds,
                recursion_limit=recursion_limit - 1 if isinstance(recursion_limit, int) else recursion_limit,
                reckless=reckless,
                refds_path=refds_path,
                jobs=jobs,
                producer_only=True  # we will be adding to producer queue
        ):
            producer_consumer.add_to_producer_queue(res)

    producer = gen_subs_to_install()
    if producer_only:
        yield from producer
    else:
        producer_consumer = ProducerConsumerProgressLog(
            producer,
            consumer,
            # no safe_to_consume= is needed since we are doing only at a single level ATM
            label="Installing",
            unit="datasets",
            jobs=jobs,
            lgr=lgr
        )
        yield from producer_consumer


def _install_targetpath(
        ds,
        target_path,
        recursive,
        recursion_limit,
        reckless,
        refds_path,
        description,
        jobs=None,
):
    """Helper to install as many subdatasets as needed to verify existence
    of a target path

    Parameters
    ==========
    ds : Dataset
      Locally available dataset that contains the target path
    target_path : Path
    """
    # if it is an empty dir, it could still be a subdataset that is missing
    if (target_path.is_dir() and any(target_path.iterdir())) or \
            (not target_path.is_dir()
             and (target_path.is_symlink() or target_path.exists())):
        yield dict(
            action='get',
            type='dataset',
            # this cannot just be the dataset path, as the original
            # situation of datasets avail on disk can have changed due
            # to subdataset installation. It has to be actual subdataset
            # it resides in, because this value is used to determine which
            # dataset to call `annex-get` on
            # TODO stringification is a PY35 compatibility kludge
            path=get_dataset_root(str(target_path)),
            status='notneeded',
            contains=[target_path],
            refds=refds_path,
        )
    else:
        # we don't have it yet. is it in a subdataset?
        for res in _install_necessary_subdatasets(
                ds, target_path, reckless, refds_path, description=description):
            if (target_path.is_symlink() or target_path.exists()):
                # this dataset brought the path, mark for annex
                # processing outside
                res['contains'] = [target_path]
            # just spit it out
            yield res
        if not (target_path.is_symlink() or target_path.exists()):
            # looking for subdatasets did not help -> all hope is lost
            yield dict(
                action='get',
                path=str(target_path),
                status='impossible',
                refds=refds_path,
                message='path does not exist',
            )
            return
    # we have the target path
    if not (recursive
            #and not recursion_limit == 'existing' \
            and target_path.is_dir()):
        # obtain any subdatasets underneath the paths given
        # a non-directory cannot have content underneath
        return
    if recursion_limit == 'existing':
        for res in ds.subdatasets(
                state='present',
                path=target_path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                return_type='generator',
                result_renderer='disabled'):
            res.update(
                contains=[Path(res['path'])],
                action='get',
                status='notneeded',
            )
            yield res
        return
    lgr.info(
        "Ensuring presence of %s%s",
        ds,
        (" to get %s" % target_path
         if ds.path != target_path
         else ""))
    for res in _recursive_install_subds_underneath(
            ds,
            # target_path was explicitly given as input
            # we count recursions from the input, hence we
            # can start with the full number
            recursion_limit,
            reckless,
            # TODO keep Path when RF is done
            start=str(target_path),
            refds_path=refds_path,
            description=description,
            jobs=jobs,
    ):
        # yield immediately so errors could be acted upon
        # outside, before we continue
        res.update(
            # do not override reported action, could be anything
            #action='get',
            contains=[Path(res['path'])],
        )
        yield res


def _get_targetpaths(ds, content, refds_path, source, jobs):
    # not ready for Path instances...
    content = [str(c) for c in content]
    # hand over to git-annex, get files content,
    # report files in git as 'notneeded' to get
    ds_repo = ds.repo
    # needs to be an annex to get content
    if not isinstance(ds_repo, AnnexRepo):
        for r in results_from_paths(
                content, status='notneeded',
                message="no dataset annex, content already present",
                action='get',
                type='file',
                logger=lgr,
                refds=refds_path):
            yield r
        return
    respath_by_status = {}
    try:
        results = ds_repo.get(
            content,
            options=['--from=%s' % source] if source else [],
            jobs=jobs)
    except CommandError as exc:
        results = exc.kwargs.get("stdout_json")
        if not results:
            raise

    for res in results:
        res = annexjson2result(res, ds, type='file', logger=lgr,
                               refds=refds_path)
        success = success_status_map[res['status']]
        # TODO: in case of some failed commands (e.g. get) there might
        # be no path in the record.  yoh has only vague idea of logic
        # here so just checks for having 'path', but according to
        # results_from_annex_noinfo, then it would be assumed that
        # `content` was acquired successfully, which is not the case
        if 'path' in res:
            respath_by_status[success] = \
                respath_by_status.get(success, []) + [res['path']]
        yield res

    for r in results_from_annex_noinfo(
            ds,
            content,
            respath_by_status,
            dir_fail_msg='could not get some content in %s %s',
            noinfo_dir_msg='nothing to get from %s',
            noinfo_file_msg='already present',
            action='get',
            logger=lgr,
            refds=refds_path):
        yield r


def _check_error_reported_before(res: dict, error_dict: dict):
    # Helper to check if an impossible result for a path that does
    # not exist has already been yielded before. If not, add path
    # to the error_dict.
    if res.get('action', None) == 'get' and \
        res.get('status', None) == 'impossible' and \
        res.get('message', None) == 'path does not exist':
            non_existing_path = res.get('path', None)
            if non_existing_path not in error_dict.keys():
                # if path not in dict, add it
                error_dict[non_existing_path] = True
                return False
            else:
                return True
    return False


@build_doc
class Get(Interface):
    """Get any dataset content (files/directories/subdatasets).

    This command only operates on dataset content. To obtain a new independent
    dataset from some source use the `clone` command.

    By default this command operates recursively within a dataset, but not
    across potential subdatasets, i.e. if a directory is provided, all files in
    the directory are obtained. Recursion into subdatasets is supported too. If
    enabled, relevant subdatasets are detected and installed in order to
    fulfill a request.

    Known data locations for each requested file are evaluated and data are
    obtained from some available location (according to git-annex configuration
    and possibly assigned remote priorities), unless a specific source is
    specified.

    *Getting subdatasets*

    Just as DataLad supports getting file content from more than one location,
    the same is supported for subdatasets, including a ranking of individual
    sources for prioritization.

    The following location candidates are considered. For each candidate a
    cost is given in parenthesis, higher values indicate higher cost, and thus
    lower priority:

    - A datalad URL recorded in `.gitmodules` (cost 590). This allows for
      datalad URLs that require additional handling/resolution by datalad, like
      ria-schemes (ria+http, ria+ssh, etc.)

    - A URL or absolute path recorded for git in `.gitmodules` (cost 600).

    - URL of any configured superdataset remote that is known to have the
      desired submodule commit, with the submodule path appended to it.
      There can be more than one candidate (cost 650).

    - In case `.gitmodules` contains a relative path instead of a URL,
      the URL of any configured superdataset remote that is known to have the
      desired submodule commit, with this relative path appended to it.
      There can be more than one candidate (cost 650).

    - In case `.gitmodules` contains a relative path as a URL, the absolute
      path of the superdataset, appended with this relative path (cost 900).

    Additional candidate URLs can be generated based on templates specified as
    configuration variables with the pattern

      `datalad.get.subdataset-source-candidate-<name>`

    where `name` is an arbitrary identifier. If `name` starts with three digits
    (e.g. '400myserver') these will be interpreted as a cost, and the
    respective candidate will be sorted into the generated candidate list
    according to this cost. If no cost is given, a default of 700 is used.

    A template string assigned to such a variable can utilize the Python format
    mini language and may reference a number of properties that are inferred
    from the parent dataset's knowledge about the target subdataset. Properties
    include any submodule property specified in the respective `.gitmodules`
    record. For convenience, an existing `datalad-id` record is made available
    under the shortened name `id`.

    Additionally, the URL of any configured remote that contains the respective
    submodule commit is available as `remoteurl-<name>` property, where `name`
    is the configured remote name.

    Hence, such a template could be `http://example.org/datasets/{id}` or
    `http://example.org/datasets/{path}`, where `{id}` and `{path}` would be
    replaced by the `datalad-id` or `path` entry in the `.gitmodules` record.

    If this config is committed in `.datalad/config`, a clone of a dataset can
    look up any subdataset's URL according to such scheme(s) irrespective of
    what URL is recorded in `.gitmodules`.

    Lastly, all candidates are sorted according to their cost (lower values
    first), and duplicate URLs are stripped, while preserving the first item in the
    candidate list.

    .. note::
      Power-user info: This command uses :command:`git annex get` to fulfill
      file handles.
    """
    _examples_ = [
        dict(text="Get a single file",
             code_py="get('path/to/file')",
             code_cmd="datalad get <path/to/file>"),
        dict(text="Get contents of a directory",
             code_py="get('path/to/dir/')",
             code_cmd="datalad get <path/to/dir/>"),
        dict(text="Get all contents of the current dataset and its subdatasets",
             code_py="get(dataset='.', recursive=True)",
             code_cmd="datalad get . -r"),
        dict(text="Get (clone) a registered subdataset, but don't retrieve data",
             code_py="get('path/to/subds', get_data=False)",
             code_cmd="datalad get -n <path/to/subds>"),
    ]

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="PATH",
            doc="""specify the dataset to perform the add operation on, in
            which case `path` arguments are interpreted as being relative
            to this dataset.  If no dataset is given, an attempt is made to
            identify a dataset for each input `path`""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path/name of the requested dataset component. The component
            must already be known to a dataset. To add new components to a
            dataset use the `add` command""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        source=Parameter(
            args=("-s", "--source",),
            metavar="LABEL",
            doc="""label of the data source to be used to fulfill requests.
            This can be the name of a dataset :term:`sibling` or another known
            source""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=Parameter(
            args=("-R", "--recursion-limit",),
            metavar="LEVELS",
            constraints=EnsureInt() | EnsureChoice('existing') | EnsureNone(),
            doc="""limit recursion into subdataset to the given number of levels.
            Alternatively, 'existing' will limit recursion to subdatasets that already
            existed on the filesystem at the start of processing, and prevent new
            subdatasets from being obtained recursively."""),
        get_data=Parameter(
            args=("-n", "--no-data",),
            dest='get_data',
            action='store_false',
            doc="""whether to obtain data for all file handles. If disabled, `get`
            operations are limited to dataset handles.[CMD:  This option prevents data
            for file handles from being obtained CMD]"""),
        description=location_description,
        reckless=reckless_opt,
        jobs=jobs_opt)

    @staticmethod
    @datasetmethod(name='get')
    @eval_results
    def __call__(
            path=None,
            *,
            source=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            get_data=True,
            description=None,
            reckless=None,
            jobs='auto',
    ):

        if not (dataset or path):
            raise InsufficientArgumentsError(
                "Neither dataset nor target path(s) provided")
        # we have to have a single dataset to operate on
        refds = require_dataset(
            dataset, check_installed=True, purpose='get content of %s' % shortened_repr(path))
        # some functions downstream expect a str
        refds_path = refds.path
        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = refds_path

        # keep track of error results for paths that do not exist
        error_reported = {}
        content_by_ds = {}
        # use subdatasets() to discover any relevant content that is not
        # already present in the root dataset (refds)
        for sdsres in Subdatasets.__call__(
                contains=path,
                # maintain path argument semantics and pass in dataset arg
                # as is
                dataset=dataset,
                # always come from the top to get sensible generator behavior
                bottomup=False,
                # when paths are given, they will constrain the recursion
                # automatically, and we need to enable recursion so we can
                # location path in subdatasets several levels down
                recursive=True if path else recursive,
                recursion_limit=None if path else recursion_limit,
                return_type='generator',
                on_failure='ignore',
                result_renderer='disabled'):
            if sdsres.get('type', None) != 'dataset':
                # if it is not about a 'dataset' it is likely content in
                # the root dataset
                if sdsres.get('status', None) == 'impossible' and \
                        sdsres.get('message', None) == \
                        'path not contained in any matching subdataset':
                    target_path = Path(sdsres['path'])
                    if refds.pathobj != target_path and \
                            refds.pathobj not in target_path.parents:
                        yield dict(
                            action='get',
                            path=str(target_path),
                            status='error',
                            message=('path not associated with dataset %s',
                                     refds),
                        )
                        continue
                    # check if we need to obtain anything underneath this path
                    # the subdataset() call above will only look _until_ it
                    # hits the targetpath
                    for res in _install_targetpath(
                            refds,
                            Path(sdsres['path']),
                            recursive,
                            recursion_limit,
                            reckless,
                            refds_path,
                            description,
                            jobs=jobs,
                    ):
                        # fish out the datasets that 'contains' a targetpath
                        # and store them for later
                        if res.get('status', None) in ('ok', 'notneeded') and \
                                'contains' in res:
                            dsrec = content_by_ds.get(res['path'], set())
                            dsrec.update(res['contains'])
                            content_by_ds[res['path']] = dsrec
                        if res.get('status', None) != 'notneeded':
                            # all those messages on not having installed anything
                            # are a bit pointless
                            # "notneeded" for annex get comes below
                            # prevent double yielding of impossible result
                            if _check_error_reported_before(res, error_reported):
                                continue
                            yield res
                else:
                    # dunno what this is, send upstairs
                    yield sdsres
                # must continue for both conditional branches above
                # the rest is about stuff in real subdatasets
                continue
            # instance of the closest existing dataset for this result
            ds = Dataset(sdsres['parentds']
                         if sdsres.get('state', None) == 'absent'
                         else sdsres['path'])
            assert 'contains' in sdsres
            # explore the unknown
            for target_path in sdsres.get('contains', []):
                # essentially the same as done above for paths in the root
                # dataset, but here we are starting from the closest
                # discovered subdataset
                for res in _install_targetpath(
                        ds,
                        Path(target_path),
                        recursive,
                        recursion_limit,
                        reckless,
                        refds_path,
                        description,
                        jobs=jobs,
                ):
                    known_ds = res['path'] in content_by_ds
                    if res.get('status', None) in ('ok', 'notneeded') and \
                            'contains' in res:
                        dsrec = content_by_ds.get(res['path'], set())
                        dsrec.update(res['contains'])
                        content_by_ds[res['path']] = dsrec
                    # prevent double-reporting of datasets that have been
                    # installed by explorative installation to get to target
                    # paths, prior in this loop
                    if res.get('status', None) != 'notneeded' or not known_ds:
                        # prevent double yielding of impossible result
                        if _check_error_reported_before(res, error_reported):
                            continue
                        yield res

        if not get_data:
            # done already
            return

        # and now annex-get, this could all be done in parallel now
        for ds, content in content_by_ds.items():
            for res in _get_targetpaths(
                    Dataset(ds),
                    content,
                    refds.path,
                    source,
                    jobs):
                if 'path' not in res or res['path'] not in content_by_ds:
                    # we had reports on datasets and subdatasets already
                    # before the annex stage
                    yield res
