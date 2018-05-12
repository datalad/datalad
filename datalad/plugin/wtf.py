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

from collections import OrderedDict
from datalad.interface.base import Interface
from datalad.interface.base import build_doc

# wording to use for items which were considered sensitive and thus not shown
_HIDDEN = "<Sensitive data, use -s=some or -s=all to show>"


@build_doc
class WTF(Interface):
    """Generate a report about the DataLad installation and configuration

    IMPORTANT: Sharing this report with untrusted parties (e.g. on the web)
    should be done with care, as it may include identifying information, and/or
    credentials or access tokens.
    """
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
            constraints=EnsureChoice('some', 'all') | EnsureNone(),
            doc="""if set to 'some' or 'all', it will display sections such as 
            config and metadata which could potentially contain sensitive 
            information (credentials, names, etc.).  If 'some', the fields
            which are known to be sensitive will still be masked out"""),
        clipboard=Parameter(
            args=("-c", "--clipboard",),
            action="store_true",
            doc="""if set, do not print but copy to clipboard (requires pyperclip
            module"""),
    )

    @staticmethod
    @datasetmethod(name='wtf')
    @eval_results
    def __call__(dataset=None, sensitive=None, clipboard=None):
        from datalad.distribution.dataset import require_dataset
        from datalad.support.exceptions import NoDatasetArgumentFound
        ds = None
        try:
            ds = require_dataset(dataset, check_installed=False, purpose='reporting')
        except NoDatasetArgumentFound:
            # failure is already logged
            pass
        if ds and not ds.is_installed():
            # we don't deal with absent datasets
            ds = None
        if sensitive:
            if ds is None:
                from datalad import cfg
            else:
                cfg = ds.config
        else:
            cfg = None

        from pkg_resources import iter_entry_points
        from datalad.ui import ui
        from datalad.api import metadata
        from datalad.support.external_versions import external_versions
        from datalad.dochelpers import exc_str
        from datalad.interface.results import success_status_map
        import os
        import platform as pl
        import json

        extractors={}
        for ep in iter_entry_points('datalad.metadata.extractors'):
            try:
                ep.load()
                status = 'OK'
            except Exception as e:
                status = 'BROKEN ({})'.format(exc_str(e))
            extractors[ep.name] = status

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


        report_template = """\
DataLad
=======
{datalad}

System
======
{system}

Environment
===========
{env}

Externals
=========
{externals}
Installed extensions
====================
{extensions}

Known metadata extractors
=========================
{metaextractors}

Configuration
=============
{cfg}
{dataset}
"""

        dataset_template = """\

Dataset information
===================
{basic}

Metadata
--------
{meta}
"""
        ds_meta = None
        if not sensitive:
            ds_meta = _HIDDEN
        elif ds and ds.is_installed() and ds.id:
            ds_meta = metadata(
                dataset=ds, reporton='datasets', return_type='list',
                result_filter=lambda x: x['action'] == 'metadata' and success_status_map[x['status']] == 'success',
                result_renderer='disabled', on_failure='ignore')
            if ds_meta:
                ds_meta = [dm['metadata'] for dm in ds_meta]
                if len(ds_meta) == 1:
                    ds_meta = ds_meta.pop()

        if cfg is not None:
            # make it into a dict to be able to reassign
            cfg = dict(cfg.items())

        if sensitive != 'all' and cfg:
            # filter out some of the entries which known to be highly sensitive
            for k in cfg.keys():
                if 'user' in k or 'token' in k or 'passwd' in k:
                    cfg[k] = _HIDDEN

        from datalad.version import __version__, __full_version__
        text = report_template.format(
            datalad=_format_dict([
                ('Version', __version__),
                ('Full version', __full_version__)
            ], indent=True),
            system=_format_dict([
                ('OS', ' '.join([
                    os.name,
                    pl.system(),
                    pl.release(),
                    pl.version()]).rstrip()),
                ('Distribution',
                 ' '.join([_t2s(pl.dist()),
                           _t2s(pl.mac_ver()),
                           _t2s(pl.win32_ver())]).rstrip())
            ], indent=True),
            env=_format_dict([
                (k, v) for k, v in os.environ.items()
                if k.startswith('PYTHON') or k.startswith('GIT') or k.startswith('DATALAD')
            ], fmt="{}={!r}"),
            dataset='' if not ds else dataset_template.format(
                basic=_format_dict([
                    ('path', ds.path),
                    ('repo', ds.repo.__class__.__name__ if ds.repo else '[NONE]'),
                ]),
                meta=_HIDDEN if not sensitive
                     else json.dumps(ds_meta, indent=1)
                     if ds_meta else '[no metadata]'
            ),
            externals=external_versions.dumps(preamble=None, indent='', query=True),
            extensions='\n'.join(ep.name for ep in iter_entry_points('datalad.extensions')),
            metaextractors=_format_dict(extractors),
            cfg=_format_dict(sorted(cfg.items(), key=lambda x: x[0]))
                if cfg else _HIDDEN,
        )
        if clipboard:
            from datalad.support.external_versions import external_versions
            external_versions.check(
                'pyperclip', msg="It is needed to be able to use clipboard")
            import pyperclip
            pyperclip.copy(text)
            ui.message("WTF information of length %s copied to clipboard"
                       % len(text))
        else:
            ui.message(text)
        yield


def _format_dict(d, indent=False, fmt=None):
    """A helper for uniform formatting of an OrderedDict output

    d could be of anything OrderedDict could be built from, e.g a list
    of tuples
    """
    od = OrderedDict(d)
    assert not (indent and fmt), "specify only indent of fmt"
    if not fmt:
        if indent:
            fmt = '{:%d}: {}' % max(map(len, od))
        else:
            fmt = '{}: {}'
    return '\n'.join(fmt.format(k, v) for k, v in od.items())


__datalad_plugin__ = WTF
