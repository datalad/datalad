# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for creating a publication target on a GitLab instance
"""

__docformat__ = 'restructuredtext'


import logging
import warnings

from datalad.support.exceptions import CapturedException

from ..distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    require_dataset,
    resolve_path,
)
# bound methods
from ..distribution.siblings import Siblings
from ..dochelpers import exc_str
from ..interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from ..interface.common_opts import (
    publish_depends,
    recursion_flag,
    recursion_limit,
)
from ..local.subdatasets import Subdatasets
from ..support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from ..support.param import Parameter
from ..utils import ensure_list

lgr = logging.getLogger('datalad.distributed.create_sibling_gitlab')

known_layout_labels = ('collection', 'flat')
known_access_labels = ('http', 'ssh', 'ssh+http')


@build_doc
class CreateSiblingGitlab(Interface):
    """Create dataset sibling at a GitLab site

    An existing GitLab project, or a project created via the GitLab web
    interface can be configured as a sibling with the :command:`siblings`
    command. Alternatively, this command can create a GitLab project at any
    location/path a given user has appropriate permissions for. This is
    particularly helpful for recursive sibling creation for subdatasets. API
    access and authentication are implemented via python-gitlab, and all its
    features are supported. A particular GitLab site must be configured in a
    named section of a python-gitlab.cfg file (see
    https://python-gitlab.readthedocs.io/en/stable/cli-usage.html#configuration-file-format
    for details), such as::

      [mygit]
      url = https://git.example.com
      api_version = 4
      private_token = abcdefghijklmnopqrst

    Subsequently, this site is identified by its name ('mygit' in the example
    above).

    (Recursive) sibling creation for all, or a selected subset of subdatasets
    is supported with two different project layouts (see --layout):

    "flat"
      All datasets are placed as GitLab projects in the same group. The project name
      of the top-level dataset follows the configured
      datalad.gitlab-SITENAME-project configuration. The project names of
      contained subdatasets extend the configured name with the subdatasets'
      s relative path within the root dataset, with all path separator
      characters replaced by '-'. This path separator is configurable
      (see Configuration).
    "collection"
      A new group is created for the dataset hierarchy, following the
      datalad.gitlab-SITENAME-project configuration. The root dataset is placed
      in a "project" project inside this group, and all nested subdatasets are
      represented inside the group using a "flat" layout. The root datasets
      project name is configurable (see Configuration).

    GitLab cannot host dataset content. However, in combination with
    other data sources (and siblings), publishing a dataset to GitLab can
    facilitate distribution and exchange, while still allowing any dataset
    consumer to obtain actual data content from alternative sources.

    *Configuration*

    Many configuration switches and options for GitLab sibling creation can
    be provided as arguments to the command. However, it is also possible to
    specify a particular setup in a dataset's configuration. This is
    particularly important when managing large collections of datasets.
    Configuration options are:

    "datalad.gitlab-default-site"
        Name of the default GitLab site (see --site)
    "datalad.gitlab-SITENAME-siblingname"
        Name of the sibling configured for the local dataset that points
        to the GitLab instance SITENAME (see --name)
    "datalad.gitlab-SITENAME-layout"
        Project layout used at the GitLab instance SITENAME (see --layout)
    "datalad.gitlab-SITENAME-access"
        Access method used for the GitLab instance SITENAME (see --access)
    "datalad.gitlab-SITENAME-project"
        Project "location/path" used for a datasets at GitLab instance
        SITENAME (see --project). Configuring this is useful for deriving
        project paths for subdatasets, relative to superdataset.
        The root-level group ("location") needs to be created beforehand via
        GitLab's web interface.
    "datalad.gitlab-default-projectname"
        The collection layout publishes (sub)datasets as projects
        with a custom name. The default name "project" can be overridden with
        this configuration.
    "datalad.gitlab-default-pathseparator"
        The flat and collection layout represent subdatasets with project names
        that correspond to their path within the superdataset, with the regular path separator replaced
        with a "-": superdataset-subdataset. This configuration can be used to override
        this default separator.

    This command can be configured with
    "datalad.create-sibling-ghlike.extra-remote-settings.NETLOC.KEY=VALUE" in
    order to add any local KEY = VALUE configuration to the created sibling in
    the local `.git/config` file. NETLOC is the domain of the Gitlab instance to
    apply the configuration for.
    This leads to a behavior that is equivalent to calling datalad's
    ``siblings('configure', ...)``||``siblings configure`` command with the
    respective KEY-VALUE pair after creating the sibling.
    The configuration, like any other, could be set at user- or system level, so
    users do not need to add this configuration to every sibling created with
    the service at NETLOC themselves.

    """
    _params_ = dict(
        path=Parameter(
            args=('path',),
            metavar='PATH',
            nargs='*',
            doc="""selectively create siblings for any datasets underneath a given
            path. By default only the root dataset is considered."""),
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""reference or root dataset. If no path constraints are given,
            a sibling for this dataset will be created. In this and all other
            cases, the reference dataset is also consulted for the GitLab
            configuration, and desired project layout. If no dataset is given,
            an attempt is made to identify the dataset based on the current
            working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        site=Parameter(
            args=('--site',),
            metavar='SITENAME',
            doc="""name of the GitLab site to create a sibling at. Must match an
            existing python-gitlab configuration section with location and
            authentication settings (see
            https://python-gitlab.readthedocs.io/en/stable/cli-usage.html#configuration).
            By default the dataset configuration is consulted.
            """,
            constraints=EnsureNone() | EnsureStr()),
        project=Parameter(
            args=('--project',),
            metavar='NAME/LOCATION',
            doc="""project name/location at the GitLab site. If a subdataset of the
            reference dataset is processed, its project path is automatically
            determined by the `layout` configuration, by default. Users need to
            create the root-level GitLab group (NAME) via the webinterface
            before running the command.
            """,
            constraints=EnsureNone() | EnsureStr()),
        layout=Parameter(
            args=('--layout',),
            constraints=EnsureChoice(None, *known_layout_labels),
            doc="""layout of projects at the GitLab site, if a collection, or
            a hierarchy of datasets and subdatasets is to be created.
            By default the dataset configuration is consulted.
            """),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        name=Parameter(
            args=('-s', '--name',),
            metavar='NAME',
            doc="""name to represent the GitLab sibling remote in the local
            dataset installation. If not specified a name is looked up in the
            dataset configuration, or defaults to the `site` name""",
            constraints=EnsureStr() | EnsureNone()),
        existing=Parameter(
            args=("--existing",),
            constraints=EnsureChoice('skip', 'error', 'reconfigure'),
            doc="""desired behavior when already existing or configured
            siblings are discovered. 'skip': ignore; 'error': fail, if access
            URLs differ; 'reconfigure': use the existing repository and
            reconfigure the local dataset to use it as a sibling""",),
        access=Parameter(
            args=("--access",),
            constraints=EnsureChoice(None, *known_access_labels),
            doc="""access method used for data transfer to and from the sibling.
            'ssh': read and write access used the SSH protocol; 'http': read and
            write access use HTTP requests; 'ssh+http': read access is done via
            HTTP and write access performed with SSH. Dataset configuration is
            consulted for a default, 'http' is used otherwise.""",),
        description=Parameter(
            args=("--description",),
            doc="""brief description for the GitLab project (displayed on the
            site)""",
            constraints=EnsureStr() | EnsureNone()),
        publish_depends=publish_depends,
        dry_run=Parameter(
            args=("--dry-run",),
            action="store_true",
            doc="""if set, no repository will be created, only tests for
            name collisions will be performed, and would-be repository names
            are reported for all relevant datasets"""),
        dryrun=Parameter(
            args=("--dryrun",),
            action="store_true",
            doc="""Deprecated. Use the renamed
            ``dry_run||--dry-run`` parameter""")
    )

    @staticmethod
    @datasetmethod(name='create_sibling_gitlab')
    @eval_results
    def __call__(
            path=None,
            *,
            site=None,
            project=None,
            layout=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            name=None,
            existing='error',
            access=None,
            publish_depends=None,
            description=None,
            dryrun=False,
            dry_run=False):
        if dryrun and not dry_run:
            # the old one is used, and not in agreement with the new one
            warnings.warn(
                "datalad-create-sibling-github's `dryrun` option is "
                "deprecated and will be removed in a future release, "
                "use the renamed `dry_run/--dry-run` option instead.",
                DeprecationWarning)
            dry_run = dryrun
        path = resolve_path(ensure_list(path), ds=dataset) \
            if path else None

        if project and (recursive or (path and len(path) > 1)):
            raise ValueError(
                'Providing a GitLab project name/location cannot be combined '
                'with recursive operation or multiple paths, as each dataset '
                'needs to be mapped onto its own individual project.')
        # what to operate on
        ds = require_dataset(
            dataset, check_installed=True, purpose='create GitLab sibling(s)')

        # cache for objects of gitlab sites (we could face different ones
        # in a single hierarchy, cache them to avoid duplicate initialization
        # while still being able to process each dataset individually
        siteobjs = dict()

        # which datasets to process?
        if path is None or ds.pathobj in path:
            for r in _proc_dataset(
                    ds, ds,
                    site, project, name, layout, existing, access,
                    dry_run, siteobjs, publish_depends, description):
                yield r
        # we need to find a subdataset when recursing, or when there is a path that
        # could point to one, we have to exclude the parent dataset in this test
        # to avoid undesired level-1 recursion into subdatasets
        if any(p != ds.pathobj for p in (path or [])) or recursive:
            # also include any matching subdatasets
            subds = ds.subdatasets(
                    path=path,
                    # we can only operate on present datasets
                    state='present',
                    recursive=recursive,
                    recursion_limit=recursion_limit,
                    contains=None,
                    bottomup=False,
                    result_xfm='datasets',
                    result_renderer='disabled',
                    return_type='list')
            if not subds:
                # we didn't find anything to operate on, let the user know
                res_kwargs = {'status': 'impossible', 'refds': ds.path,
                              'type':'dataset', 'logger': lgr,
                              'action': 'create_sibling_gitlab'}
                if path is not None:
                    for p in path:
                        yield dict(
                              path=p,
                              message=('No installed dataset found under %s, forgot to "get" it?' % p),
                              **res_kwargs
                        )
                else:
                    yield dict(
                        path=ds.path,
                        message=('No installed subdatasets found underneath %s, forgot to "get" any?' % ds.path),
                        **res_kwargs)
            else:
                for sub in subds:
                    for r in _proc_dataset(
                            ds, sub,
                            site, project, name, layout, existing, access,
                            dry_run, siteobjs, publish_depends, description):
                        yield r

        return


def _proc_dataset(refds, ds, site, project, remotename, layout, existing,
                  access, dry_run, siteobjs, depends, description):
    # basic result setup
    res_kwargs = dict(
        action='create_sibling_gitlab',
        refds=refds.path,
        path=ds.path,
        type='dataset',
        logger=lgr,
    )
    if description:
        res_kwargs['description'] = description

    if site is None:
        # always try pulling the base config from a parent dataset
        # even if paths were given (may be overwritten later)
        basecfgsite = ds.config.get('datalad.gitlab-default-site', None)

    # let the dataset config overwrite the target site, if none
    # was given
    site = refds.config.get(
        'datalad.gitlab-default-site', basecfgsite) \
        if site is None else site
    if site is None:
        # this means the most top-level dataset has no idea about
        # gitlab, and no site was specified as an argument
        # fail rather then give an error result, as this is very
        # unlikely to be intentional
        raise ValueError(
            'No GitLab site was specified (--site) or configured '
            'in {} (datalad.gitlab.default-site)'.format(ds))
    res_kwargs['site'] = site

    # determine target remote name, unless given
    if remotename is None:
        remotename_var = 'datalad.gitlab-{}-siblingname'.format(site)
        remotename = ds.config.get(
            remotename_var,
            # use config from parent, if needed
            refds.config.get(
                remotename_var,
                # fall back on site name, if nothing else can be used
                site))
    res_kwargs['sibling'] = remotename
    # check against existing remotes
    dremotes = {
        r['name']: r
        for r in ds.siblings(
            action='query',
            # fastest possible
            get_annex_info=False,
            recursive=False,
            return_type='generator',
            result_renderer='disabled')
    }
    if remotename in dremotes and existing not in ['replace', 'reconfigure']:
        # we already know a sibling with this name
        yield dict(
            res_kwargs,
            status='error' if existing == 'error' else 'notneeded',
            message=('already has a configured sibling "%s"', remotename),
        )
        return

    if layout is None:
        # figure out the layout of projects on the site
        # use the reference dataset as default, and fall back
        # on 'collection' as the most generic method of representing
        # the filesystem in a group/subproject structure
        layout_var = 'datalad.gitlab-{}-layout'.format(site)
        layout = ds.config.get(
            layout_var, refds.config.get(
                layout_var, 'collection'))
    if layout not in known_layout_labels:
        raise ValueError(
            "Unknown site layout '{}' given or configured, "
            "known ones are: {}".format(layout, known_layout_labels))

    if access is None:
        access_var = 'datalad.gitlab-{}-access'.format(site)
        access = ds.config.get(
            access_var, refds.config.get(
                access_var, 'http'))
    if access not in known_access_labels:
        raise ValueError(
            "Unknown site access '{}' given or configured, "
            "known ones are: {}".format(access, known_access_labels))

    pathsep = ds.config.get("datalad.gitlab-default-pathseparator", "-")
    project_stub = \
        ds.config.get("datalad.gitlab-default-projectname", "project")
    project_var = 'datalad.gitlab-{}-project'.format(site)
    process_root = refds == ds
    if project is None:
        # look for a specific config in the dataset
        project = ds.config.get(project_var, None)

    if project and process_root and layout != 'flat':
        # the root of a collection
        project = f'{project}/{project_stub}'
    elif project is None and not process_root:
        # check if we can build one from the refds config
        ref_project = refds.config.get(project_var, None)
        if ref_project:
            # layout-specific derivation of a path from
            # the reference dataset configuration
            rproject = ds.pathobj.relative_to(refds.pathobj).as_posix()
            if layout == 'collection':
                project = '{}/{}'.format(
                    ref_project,
                    rproject.replace('/', pathsep))
            else:
                project = '{}{}{}'.format(
                    ref_project,
                    pathsep,
                    rproject.replace('/', pathsep))

    if project is None:
        yield dict(
            res_kwargs,
            status='error',
            message='No project name/location specified, and no configuration '
                    'to derive one',
        )
        return

    res_kwargs['project'] = project

    if dry_run:
        # this is as far as we can get without talking to GitLab
        yield dict(
            res_kwargs,
            status='ok',
            dryrun=True,
        )
        return

    # and now talk to GitLab for real
    site_api = siteobjs[site] if site in siteobjs else GitLabSite(site)

    site_project = site_api.get_project(project)
    if site_project is None:
        try:
            site_project = site_api.create_project(project, description)
            # report success
            message = "sibling repository '%s' created at %s",\
                      remotename, site_project.get('web_url', None)
            yield dict(
                res_kwargs,
                # relay all attributes
                project_attributes=site_project,
                message=message,
                status='ok',
            )
        except Exception as e:
            ce = CapturedException(e)
            yield dict(
                res_kwargs,
                # relay all attributes
                status='error',
                message=('Failed to create GitLab project: %s', ce),
                exception=ce
            )
            return
    else:
        # there already is a project
        if existing == 'error':
            # be nice and only actually error if there is a real mismatch
            if remotename not in dremotes:
                yield dict(
                    res_kwargs,
                    project_attributes=site_project,
                    status='error',
                    message=(
                        "There is already a project at '%s' on site '%s', "
                        "but no sibling with name '%s' is configured, "
                        "maybe use --existing=reconfigure",
                        project, site, remotename,
                    )
                )
                return
            elif access in ('ssh', 'ssh+http') \
                    and dremotes[remotename].get(
                        'url', None) != site_project.get(
                            # use False as a default so that there is a
                            # mismatch, complain if both are missing
                            'ssh_url_to_repo', False):
                yield dict(
                    res_kwargs,
                    project_attributes=site_project,
                    status='error',
                    message=(
                        "There is already a project at '%s' on site '%s', "
                        "but SSH access URL '%s' does not match '%s', "
                        "maybe use --existing=reconfigure",
                        project, site,
                        dremotes[remotename].get('url', None),
                        site_project.get('ssh_url_to_repo', None)
                    )
                )
                return
            elif access == 'http' \
                    and dremotes[remotename].get(
                        'url', None) != site_project.get(
                            # use False as a default so that there is a
                            # mismatch, veen if both are missing
                            'http_url_to_repo', False):
                yield dict(
                    res_kwargs,
                    project_attributes=site_project,
                    status='error',
                    message=(
                        "There is already a project at '%s' on site '%s', "
                        "but HTTP access URL '%s' does not match '%s', "
                        "maybe use --existing=reconfigure",
                        project, site,
                        dremotes[remotename].get('url', None),
                        site_project.get('http_url_to_repo', None)
                    )
                )
                return
        yield dict(
            res_kwargs,
            project_attributes=site_project,
            status='notneeded',
            message=(
                "There is already a project at '%s' on site '%s'",
                project, site,
            )
        )

    # first make sure that annex doesn't touch this one
    # but respect any existing config
    ignore_var = 'remote.{}.annex-ignore'.format(remotename)
    if ignore_var not in ds.config:
        ds.config.add(ignore_var, 'true', scope='local')

    for res in ds.siblings(
            'configure',
            name=remotename,
            url=site_project['http_url_to_repo']
            if access in ('http', 'ssh+http')
            else site_project['ssh_url_to_repo'],
            pushurl=site_project['ssh_url_to_repo']
            if access in ('ssh', 'ssh+http')
            else None,
            recursive=False,
            publish_depends=depends,
            result_renderer='disabled',
            return_type='generator'):
        yield res


class GitLabSite(object):
    def __init__(self, site):
        import gitlab
        self.gitlab = gitlab
        try:
            self.site = gitlab.Gitlab.from_config(site)
        except gitlab.config.GitlabDataError as e:
            raise ValueError(
                '{}, please configure access to this GitLab instance'.format(
                    str(e)))

    def get_project(self, path):
        try:
            return self.site.projects.get(path).attributes
        except self.gitlab.GitlabGetError as e:
            lgr.debug("Project with path '%s' does not yet exist at site '%s'",
                      path, self.site.url)
            return None

    def create_project(self, path, description=None):
        path_l = path.split('/')
        namespace_id = self._obtain_namespace(path_l)
        # check for options:
        # https://gitlab.com/help/api/projects.md#create-project
        props = dict(
            name=path_l[-1],
            namespace_id=namespace_id,
        )
        if description:
            props['description'] = description
        project = self.site.projects.create(props)
        return project.attributes

    def _obtain_namespace(self, path_l):

        if len(path_l) == 1:
            # no nesting whatsoever
            return None

        try:
            namespace_id = self.site.groups.get(
                '/'.join(path_l[:-1])).get_id()
            lgr.debug("Found existing parent group '%s' with ID %s",
                      '/'.join(path_l[:-1]), namespace_id)
        except self.gitlab.GitlabGetError as e:
            try:
                if len(path_l) > 2:
                    parent_group = self.site.groups.get(
                        '/'.join(path_l[:-2]))
                else:
                    parent_group = None
            except self.gitlab.GitlabGetError as e:
                raise ValueError(
                    "No parent group {} for project {} found, "
                    "and a group {} also does not exist. At most one "
                    "parent group would be created.".format(
                        '/'.join(path_l[:-1]),
                        '/'.join(path_l),
                        '/'.join(path_l[:-2]),
                    ))
            # create the group for the target project
            try:
                # prevent failure due to specification of a users personal
                # group, always exists, cannot and must not be created
                self.site.auth()
                if len(path_l) == 2 \
                        and path_l[0] == self.site.user.attributes.get(
                            'username', None):
                    # attempt to create a personal project in the users
                    # top-level personal group-- this is the same as
                    # having no parent namespace, don't attempt to
                    # create the group
                    return None
                namespace_id = self.site.groups.create(dict(
                    name=path_l[-2],
                    path=path_l[-2],
                    parent_id=parent_group.get_id() if parent_group else None)
                ).get_id()
            except self.gitlab.GitlabCreateError as e:
                raise RuntimeError(
                    "Failed to create parent group '{}' under {}: {}".format(
                        path_l[-2],
                        repr(parent_group.attributes['full_path'])
                        if parent_group else 'the account root',
                        str(e)),
                )
        return namespace_id
