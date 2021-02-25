# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""provide information about this DataLad installation"""

__docformat__ = 'restructuredtext'

import logging
import os
import os.path as op
from functools import partial
from itertools import chain
from collections import OrderedDict


from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.utils import (
    ensure_unicode,
    getpwd,
    unlink,
    Path,
)
from datalad.dochelpers import exc_str
from datalad.support.external_versions import external_versions
from datalad.support.exceptions import (
    CommandError,
    InvalidGitRepositoryError,
)
from datalad.version import __version__, __full_version__

lgr = logging.getLogger('datalad.plugin.wtf')


# wording to use for items which were considered sensitive and thus not shown
_HIDDEN = "<SENSITIVE, report disabled by configuration>"


# formatting helper
def _t2s(t):
    res = []
    for e in t:
        if isinstance(e, tuple):
            es = _t2s(e)
            if es != '':
                res += ['(%s)' % es]
        elif e != '':
            res += [e]
    return '/'.join(res)


def get_max_path_length(top_path=None, maxl=1000):
    """Deduce the maximal length of the filename in a given path
    """
    if not top_path:
        top_path = getpwd()
    import random
    from datalad import lgr
    from datalad.dochelpers import exc_str
    from datalad.support import path
    prefix = path.join(top_path, "dl%d" % random.randint(1 ,100000))
    # some smart folks could implement binary search for this
    max_path_length = None
    for i in range(maxl-len(prefix)):
        filename = prefix + '_' * i
        path_length = len(filename)
        try:
            with open(filename, 'w') as f:
                max_path_length = path_length
        except Exception as exc:
            lgr.debug(
                "Failed to create sample file for length %d. Last succeeded was %s. Exception: %s",
                path_length, max_path_length, exc_str(exc))
            break
        unlink(filename)
    return max_path_length


def _describe_datalad():

    return {
        'version': ensure_unicode(__version__),
        'full_version': ensure_unicode(__full_version__),
    }


def _describe_annex():
    from datalad.cmd import (
        GitWitlessRunner,
        StdOutErrCapture,
    )

    runner = GitWitlessRunner()
    try:
        out = runner.run(
            ['git', 'annex', 'version'], protocol=StdOutErrCapture)
    except CommandError as e:
        return dict(
            version='not available',
            message=exc_str(e),
        )
    info = {}
    for line in out['stdout'].split(os.linesep):
        key = line.split(':')[0]
        if not key:
            continue
        value = line[len(key) + 2:].strip()
        key = key.replace('git-annex ', '')
        if key.endswith('s'):
            value = value.split()
        info[key] = value
    return info


def _describe_system():
    import platform as pl
    from datalad import get_encoding_info
    from datalad.utils import get_linux_distribution
    try:
        dist = get_linux_distribution()
    except Exception as exc:
        lgr.warning("Failed to get distribution information: %s", exc_str(exc))
        dist = tuple()

    return {
        'type': os.name,
        'name': pl.system(),
        'release': pl.release(),
        'version': pl.version(),
        'distribution': ' '.join([_t2s(dist),
                                  _t2s(pl.mac_ver()),
                                  _t2s(pl.win32_ver())]).rstrip(),
        'max_path_length': get_max_path_length(getpwd()),
        'encoding': get_encoding_info(),
    }


def _describe_environment():
    from datalad import get_envvars_info
    return get_envvars_info()


def _describe_python():
    import platform
    return {
        'version': platform.python_version(),
        'implementation': platform.python_implementation(),
    }


def _describe_configuration(cfg, sensitive):
    if not cfg:
        return _HIDDEN

    # make it into a dict to be able to reassign
    cfg = dict(cfg.items())

    if sensitive != 'all':
        # filter out some of the entries which known to be highly sensitive
        for k in cfg.keys():
            if 'user' in k or 'token' in k or 'passwd' in k:
                cfg[k] = _HIDDEN

    return cfg


def _describe_extensions():
    infos = {}
    from pkg_resources import iter_entry_points
    from importlib import import_module

    for e in iter_entry_points('datalad.extensions'):
        info = {}
        infos[e.name] = info
        try:
            ext = e.load()
            info['load_error'] = None
            info['description'] = ext[0]
            info['module'] = e.module_name
            mod = import_module(e.module_name, package='datalad')
            info['version'] = getattr(mod, '__version__', None)
        except Exception as e:
            info['load_error'] = exc_str(e)
            continue
        info['entrypoints'] = entry_points = {}
        for ep in ext[1]:
            ep_info = {
                'module': ep[0],
                'class': ep[1],
                'names': ep[2:],
            }
            entry_points['{}.{}'.format(*ep[:2])] = ep_info
            try:
                import_module(ep[0], package='datalad')
                ep_info['load_error'] = None
            except Exception as e:
                ep_info['load_error'] = exc_str(e)
                continue
    return infos


def _describe_metadata_elements(group):
    infos = {}
    from pkg_resources import iter_entry_points
    from importlib import import_module

    for e in iter_entry_points(group):
        info = {}
        infos['%s (%s)' % (e.name, str(e.dist))] = info
        try:
            info['module'] = e.module_name
            info['distribution'] = str(e.dist)
            mod = import_module(e.module_name, package='datalad')
            info['version'] = getattr(mod, '__version__', None)
            e.load()
            info['load_error'] = None
        except Exception as e:
            info['load_error'] = exc_str(e)
            continue
    return infos


def _describe_dependencies():
    return {
        k: str(external_versions[k]) for k in external_versions.keys(query=True)
    }


def _describe_dataset(ds, sensitive):
    from datalad.interface.results import success_status_map
    from datalad.api import metadata

    try:
        infos = {
            'path': ds.path,
            'repo': ds.repo.__class__.__name__ if ds.repo else None,
            'id': ds.id,
        }
        if not sensitive:
            infos['metadata'] = _HIDDEN
        elif ds.id:
            ds_meta = metadata(
                dataset=ds, reporton='datasets', return_type='list',
                result_filter=lambda x: x['action'] == 'metadata' and success_status_map[x['status']] == 'success',
                result_renderer='disabled', on_failure='ignore')
            if ds_meta:
                ds_meta = [dm['metadata'] for dm in ds_meta]
                if len(ds_meta) == 1:
                    ds_meta = ds_meta.pop()
                infos['metadata'] = ds_meta
            else:
                infos['metadata'] = None
        return infos
    except InvalidGitRepositoryError as e:
        return {"invalid": exc_str(e)}


def _describe_location(res):
    return {
        'path': res['path'],
        'type': res['type'],
    }


def _describe_credentials():
    import keyring
    from keyring.util import platform_

    def describe_keyring_backend(be):
        be_repr = repr(be)
        return be.name if 'object at 0' in be_repr else be_repr.strip('<>')

    # might later add information on non-keyring credentials gh-4981
    props = {}

    active_keyring = keyring.get_keyring()
    krp = {
        'config_file': Path(platform_.config_root(), 'keyringrc.cfg'),
        'data_root': platform_.data_root(),
        'active_backends': [
            describe_keyring_backend(be)
            for be in getattr(active_keyring, 'backends', [active_keyring])
        ],
    }
    props.update(
        keyring=krp,
    )
    return props


# Actuall callables for WTF. If None -- should be bound later since depend on
# the context
SECTION_CALLABLES = {
    'datalad': _describe_datalad,
    'python': _describe_python,
    'git-annex': _describe_annex,
    'system': _describe_system,
    'environment': _describe_environment,
    'configuration': None,
    'location': None,
    'extensions': _describe_extensions,
    'metadata_extractors': lambda: _describe_metadata_elements('datalad.metadata.extractors'),
    'metadata_indexers': lambda: _describe_metadata_elements('datalad.metadata.indexers'),
    'dependencies': _describe_dependencies,
    'dataset': None,
    'credentials': _describe_credentials,
}


@build_doc
class WTF(Interface):
    """Generate a report about the DataLad installation and configuration

    IMPORTANT: Sharing this report with untrusted parties (e.g. on the web)
    should be done with care, as it may include identifying information, and/or
    credentials or access tokens.
    """
    result_renderer = 'tailored'

    from datalad.support.param import Parameter
    from datalad.distribution.dataset import datasetmethod
    from datalad.interface.utils import eval_results
    from datalad.distribution.dataset import EnsureDataset
    from datalad.support.constraints import EnsureNone, EnsureChoice

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to report on.
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        sensitive=Parameter(
            args=("-s", "--sensitive",),
            constraints=EnsureChoice(None, 'some', 'all'),
            doc="""if set to 'some' or 'all', it will display sections such as 
            config and metadata which could potentially contain sensitive 
            information (credentials, names, etc.).  If 'some', the fields
            which are known to be sensitive will still be masked out"""),
        sections=Parameter(
            args=("-S", "--section"),
            action='append',
            dest='sections',
            metavar="SECTION",
            constraints=EnsureChoice(*sorted(SECTION_CALLABLES) + ['*']) | EnsureNone(),
            doc="""section to include.  If not set - depends on flavor.
            '*' could be used to force all sections.
            [CMD: This option can be given multiple times. CMD]"""),
        flavor=Parameter(
            args=("--flavor",),
            constraints=EnsureChoice('full', 'short'),
            doc="""Flavor of WTF. 'full' would produce markdown with exhaustive list of sections.
            'short' will provide a condensed summary only of datalad and dependencies by default.
            Use [CMD: --section CMD][PY: `section` PY] to list other sections"""),
        decor=Parameter(
            args=("-D", "--decor"),
            constraints=EnsureChoice('html_details') | EnsureNone(),
            doc="""decoration around the rendering to facilitate embedding into
            issues etc, e.g. use 'html_details' for posting collapsable entry
            to GitHub issues."""),
        clipboard=Parameter(
            args=("-c", "--clipboard",),
            action="store_true",
            doc="""if set, do not print but copy to clipboard (requires pyperclip
            module)"""),
    )

    @staticmethod
    @datasetmethod(name='wtf')
    @eval_results
    def __call__(dataset=None, sensitive=None, sections=None, flavor="full", decor=None, clipboard=None):
        from datalad.distribution.dataset import require_dataset
        from datalad.support.exceptions import NoDatasetFound
        from datalad.interface.results import get_status_dict

        ds = None
        try:
            ds = require_dataset(dataset, check_installed=False, purpose='reporting')
        except NoDatasetFound:
            # failure is already logged
            pass
        if ds and not ds.is_installed():
            # warn that the dataset is bogus
            yield dict(
                action='wtf',
                path=ds.path,
                status='impossible',
                message=(
                    'No dataset found at %s. Reporting on the dataset is '
                    'not attempted.', ds.path),
                logger=lgr
            )
            # we don't deal with absent datasets
            ds = None
        if sensitive:
            if ds is None:
                from datalad import cfg
            else:
                cfg = ds.config
        else:
            cfg = None

        from datalad.ui import ui
        from datalad.support.external_versions import external_versions

        infos = OrderedDict()
        res = get_status_dict(
            action='wtf',
            path=ds.path if ds else ensure_unicode(op.abspath(op.curdir)),
            type='dataset' if ds else 'directory',
            status='ok',
            logger=lgr,
            decor=decor,
            infos=infos,
            flavor=flavor,
        )

        # Define section callables which require variables.
        # so there is no side-effect on module level original
        section_callables = SECTION_CALLABLES.copy()
        section_callables['location'] = partial(_describe_location, res)
        section_callables['configuration'] = \
            partial(_describe_configuration, cfg, sensitive)
        if ds:
            section_callables['dataset'] = \
                partial(_describe_dataset, ds, sensitive)
        else:
            section_callables.pop('dataset')
        assert all(section_callables.values())  # check if none was missed

        asked_for_all_sections = sections is not None and any(s == '*' for s in sections)
        if sections is None or asked_for_all_sections:
            if flavor == 'full' or asked_for_all_sections:
                sections = sorted(list(section_callables))
            elif flavor == 'short':
                sections = ['datalad', 'dependencies']
            else:
                raise ValueError(flavor)

        for s in sections:
            infos[s] = section_callables[s]()

        if clipboard:
            external_versions.check(
                'pyperclip', msg="It is needed to be able to use clipboard")
            import pyperclip
            report = _render_report(res)
            pyperclip.copy(report)
            ui.message("WTF information of length %s copied to clipboard"
                       % len(report))
        yield res
        return

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui
        out = _render_report(res)
        ui.message(out)


def _render_report(res):
    report = u'# WTF'

    def _unwind(text, val, top):
        if isinstance(val, dict):
            for k in sorted(val):
                text += u'\n{}{} {}{} '.format(
                    '##' if not top else top,
                    '-' if top else '',
                    k,
                    ':' if top else '')
                text = _unwind(text, val[k], u'{}  '.format(top))
        elif isinstance(val, (list, tuple)):
            for i, v in enumerate(val):
                text += u'\n{}{} '.format(top, '-')
                text = _unwind(text, v, u'{}  '.format(top))
        else:
            text += u'{}'.format(val)
        return text

    def _unwind_short(text, val, top):
        if isinstance(val, dict):
            if not top:
                text += '\n'
                for k, v in val.items():
                    text += "- " + _unwind_short(k, v, top + ' ') + '\n'
            else:
                text += ": " + ' '.join('%s=%s' % i for i in val.items())
        elif isinstance(val, (list, tuple)):
            text += (' ' if not top else '\n').join(map(str, val))
        else:
            text += u'{}'.format(val)
        return text

    unwinder = {'full': _unwind, 'short': _unwind_short}[res.get('flavor', 'full')]
    report = unwinder(report, res.get('infos', {}), '')
    decor = res.get('decor', None)

    if not decor:
        return report

    if decor == 'html_details':
        report = """\
<details><summary>DataLad %s WTF (%s)</summary>

%s
</details>
        """ % (__version__, ', '.join(res.get('infos', {})), report)
    else:
        raise ValueError("Unknown value of decor=%s" % decor)
    return report
