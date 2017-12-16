# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""add a README file to a dataset"""

__docformat__ = 'restructuredtext'


# PLUGIN API
def dlplugin(dataset, filename='README.md', existing='skip'):
    """Add basic information about DataLad datasets to a README file

    The README file is added to the dataset and the addition is saved
    in the dataset.

    Parameters
    ----------
    dataset : Dataset
      dataset to add information to
    filename : str, optional
      path of the README file within the dataset. Default: 'README.md'
    existing : {'skip', 'append', 'replace'}
      how to react if a file with the target name already exists:
      'skip': do nothing; 'append': append information to the existing
      file; 'replace': replace the existing file with new content.
      Default: 'skip'

    """

    from os.path import lexists
    from os.path import join as opj
    from io import open
    import logging
    lgr = logging.getLogger('datalad.plugin.add_readme')
    from datalad.utils import assure_list

    filename = opj(dataset.path, filename)
    res_kwargs = dict(action='add_readme', path=filename)

    if lexists(filename) and existing == 'skip':
        yield dict(
            res_kwargs,
            status='notneeded',
            message='file already exists, and not appending content')
        return

    # unlock, file could be annexed
    if lexists(filename):
        dataset.unlock(filename)

    # get any metadata on the dataset itself
    dsinfo = dataset.metadata('.', reporton='datasets', return_type='item-or-list')
    if not isinstance(dsinfo, dict) or dsinfo.get('status', None) != 'ok':
        lgr.warn("Could not obtain dataset metadata, proceeding without")
        dsinfo = {}
        meta = {}
    else:
        meta = dsinfo['metadata']

    metainfo = ''
    for label, content in (
            ('', meta.get('description', meta.get('shortdescription', ''))),
            ('Author{}'.format('s' if isinstance(meta.get('author', None), list) else ''),
                u'\n'.join([u'- {}'.format(a) for a in assure_list(meta.get('author', []))])),
            ('Homepage', meta.get('homepage', '')),
            ('Reference', meta.get('citation', '')),
            ('License', meta.get('license', '')),
            ('Keywords', u', '.join([u'`{}`'.format(k) for k in assure_list(meta.get('tag', []))])),
            ('Funding', meta.get('fundedby', '')),
            ):
        if label and content:
            metainfo += u'\n\n### {}\n\n{}'.format(label, content)
        elif content:
            metainfo += u'\n\n{}'.format(content)

    default_content=u"""\
# {title}{metainfo}

## General information

This is a DataLad dataset{id}.

For more information on DataLad and on how to work with its datasets,
see the DataLad documentation at: http://docs.datalad.org
""".format(
        title='Dataset "{}"'.format(meta['name']) if 'name' in meta else 'About this dataset',
        metainfo=metainfo,
        id=u' (id: {})'.format(dataset.id) if dataset.id else '',
        )

    with open(filename, 'a' if existing == 'append' else 'w', encoding='utf-8') as fp:
        fp.write(default_content)
        yield dict(
            status='ok',
            path=filename,
            type='file',
            action='add_readme')

    for r in dataset.add(
            filename,
            message='[DATALAD] added README',
            result_filter=None,
            result_xfm=None):
        yield r
