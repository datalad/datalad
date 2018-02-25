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

from datalad.interface.base import Interface
from datalad.interface.base import build_doc


@build_doc
class WTF(Interface):
    from datalad.support.param import Parameter
    from datalad.distribution.dataset import datasetmethod
    from datalad.interface.utils import eval_results
    from datalad.distribution.dataset import EnsureDataset
    from datalad.support.constraints import EnsureNone

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to unlock files in. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory. If the latter fails, an
            attempt is made to identify the dataset based on `path` """,
            constraints=EnsureDataset() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='unlock')
    @eval_results
    def __call__(dataset=None):
        """Generate a report about the DataLad installation and configuration

        IMPORTANT: Sharing this report with untrusted parties (e.g. on the web)
        should be done with care, as it may include identifying information, and/or
        credentials or access tokens.

        Parameters
        ----------
        dataset : Dataset, optional
          If a dataset is given or found, information on this dataset is provided
          (if it exists), and its active configuration is reported.
        """
        ds = dataset
        if ds and not ds.is_installed():
            # we don't deal with absent datasets
            ds = None
        if ds is None:
            from datalad import cfg
        else:
            cfg = ds.config
        from datalad.ui import ui
        from datalad.api import metadata
        from datalad.metadata import extractors as metaextractors
        from datalad.support.external_versions import external_versions
        import os
        import platform as pl
        import json

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
System
======
{system}

Environment
===========
{env}

Externals
=========
{externals}
Available metadata extractors
=============================
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
        if ds and ds.is_installed():
            ds_meta = metadata(
                dataset=ds, reporton='datasets', return_type='list',
                result_filter=lambda x: x['action'] == 'metadata')
        if ds_meta:
            ds_meta = [dm['metadata'] for dm in ds_meta]
            if len(ds_meta) == 1:
                ds_meta = ds_meta.pop()
        ui.message(report_template.format(
            system='\n'.join(
                '{}: {}'.format(*i) for i in (
                    ('OS          ', ' '.join([
                        os.name,
                        pl.system(),
                        pl.release(),
                        pl.version()]).rstrip()),
                    ('Distribution',
                     ' '.join([_t2s(pl.dist()),
                               _t2s(pl.mac_ver()),
                               _t2s(pl.win32_ver())]).rstrip()))),
            env='\n'.join(
                '{}: {}'.format(k, v) for k, v in os.environ.items()
                if k.startswith('PYTHON') or k.startswith('GIT') or k.startswith('DATALAD')),
            dataset='' if not ds else dataset_template.format(
                basic='\n'.join(
                    '{}: {}'.format(k, v) for k, v in (
                        ('path', ds.path),
                        ('repo', ds.repo.__class__.__name__ if ds.repo else '[NONE]'),
                    )),
                meta=json.dumps(ds_meta, indent=1)
                if ds_meta else '[no metadata]'
            ),
            externals=external_versions.dumps(preamble=None, indent='', query=True),
            metaextractors='\n'.join(p for p in dir(metaextractors) if not p.startswith('_')),
            cfg='\n'.join(
                '{}: {}'.format(
                    k,
                    '<HIDDEN>' if 'user' in k or 'token' in k or 'passwd' in k else v)
                for k, v in sorted(cfg.items(), key=lambda x: x[0])),
        ))
        yield


DLPlugin = WTF
