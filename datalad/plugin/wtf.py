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


# PLUGIN API
def dlplugin(dataset=None):
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
    from datalad.support.external_versions import external_versions
    import os
    import platform as pl

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
{dataset}
Externals
=========
{externals}
Configuration
=============
{cfg}

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
            dataset=ds, dataset_global=True, return_type='item-or-list',
            result_filter=lambda x: x['action'] == 'metadata')
    if ds_meta:
        ds_meta = ds_meta['metadata']
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
            meta='\n'.join(
                '{}: {}'.format(k, v) for k, v in ds_meta)
            if ds_meta else '[no metadata]'
        ),
        externals=external_versions.dumps(preamble=None, indent='', query=True),
        cfg='\n'.join(
            '{}: {}'.format(
                k,
                '<HIDDEN>'
                if k.startswith('user.') or 'token' in k or 'user' in k else v)
            for k, v in sorted(cfg.items(), key=lambda x: x[0])),
    ))
    yield
