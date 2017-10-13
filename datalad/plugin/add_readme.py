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
def dlplugin(dataset, filename='README.rst', existing='skip'):
    """Add basic information about DataLad datasets to a README file

    The README file is added to the dataset and the addition is saved
    in the dataset.

    Parameters
    ----------
    dataset : Dataset
      dataset to add information to
    filename : str, optional
      path of the README file within the dataset. Default: 'README.rst'
    existing : {'skip', 'append', 'replace'}
      how to react if a file with the target name already exists:
      'skip': do nothing; 'append': append information to the existing
      file; 'replace': replace the existing file with new content.
      Default: 'skip'

    """

    from os.path import lexists
    from os.path import join as opj

    default_content="""\
About this dataset
==================

This is a DataLad dataset{id}.

For more information on DataLad and on how to work with its datasets,
see the DataLad documentation at: http://docs.datalad.org
""".format(
        id=' (id: {})'.format(dataset.id) if dataset.id else '')
    filename = opj(dataset.path, filename)
    res_kwargs = dict(action='add_readme', path=filename)

    if lexists(filename) and existing == 'skip':
        yield dict(
            res_kwargs,
            status='notneeded',
            message='file already exists, and not appending content')
        return

    # unlock, file could be annexed
    # TODO yield
    if lexists(filename):
        dataset.unlock(filename)

    with open(filename, 'a' if existing == 'append' else 'w') as fp:
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
