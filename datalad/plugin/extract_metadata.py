# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""run one or more metadata extractors on a dataset or file(s)"""

__docformat__ = 'restructuredtext'


# PLUGIN API
def dlplugin(type, file=None, dataset=None):
    """Run one or more of DataLad's metadata extractors on a dataset or file.

    The result(s) are structured like the metadata,DataLad would extract
    during metadata aggregation. There is one result per dataset/file.

    Parameters
    ----------
    type : str
      Name of the metadata extractor to be executed.
    file : path, optional
      Path of a file to extract metadata from.
    dataset : Dataset or path, optional
      Dataset to extract metadata from. If no `file` is given, metadata
      is extracted from all files of the dataset.

    Examples
    --------

    Extract metadata with two extractors from a dataset in the current directory
    and also from all its files::

      $ datalad plugin -d . extract_metadata type=frictionless_datapackage type=datalad_core

    Extract XMP metadata from a single PDF that is not part of any dataset::

      $ datalad plugin extract_metadata type=xmp file=Downloads/freshfromtheweb.pdf
    """
    from os.path import join as opj
    from datalad.interface.results import get_status_dict
    from datalad.distribution.dataset import require_dataset
    from datalad.metadata.metadata import _get_metadata
    from datalad.metadata.metadata import _get_metadatarelevant_paths

    if file is None:
        ds = require_dataset(dataset, check_installed=True)
        subds = ds.subdatasets(recursive=False, result_xfm='relpaths')
        file = list(_get_metadatarelevant_paths(ds, subds))

    dsmeta, contentmeta, error = _get_metadata(
        dataset,
        type if isinstance(type, list) else [type],
        global_meta=dataset is not None,
        content_meta=file is not None,
        paths=file if isinstance(file, list) else [file])

    if dataset is not None and dataset.is_installed():
        res = get_status_dict(
            action='metadata',
            ds=dataset,
            refds=dataset,
            metadata=dsmeta,
            status='error' if error else 'ok')
        yield res

    for p in contentmeta:
        res = get_status_dict(
            action='metadata',
            path=opj(dataset.path, p) if dataset else p,
            refds=dataset,
            metadata=contentmeta[p],
            type='file',
            status='error' if error else 'ok')
        if dataset:
            res['parentds'] = dataset.path
        yield res
