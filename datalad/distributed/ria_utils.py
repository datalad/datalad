def get_layout_locations(version, base_path, dsid):
    """Return dataset-related path in a RIA store

    Parameters
    ----------
    version : int
      Layout version of the store.
    base_path : Path
      Base path of the store.
    dsid : str
      Dataset ID

    Returns
    -------
    Path, Path, Path
      The location of the bare dataset repository in the store,
      the directory with archive files for the dataset, and the
      annex object directory are return in that order.
    """
    if version == 1:
        dsgit_dir = base_path / dsid[:3] / dsid[3:]
        archive_dir = dsgit_dir / 'archives'
        dsobj_dir = dsgit_dir / 'annex' / 'objects'
        return dsgit_dir, archive_dir, dsobj_dir
    else:
        raise ValueError("Unknown layout version: {}".format(version))


def verify_ria_url(url, cfg):
    """Verify and decode ria url

    Expects a ria-URL pointing to a RIA store, applies rewrites and tries to
    decode potential host and base path for the store from it. Additionally
    raises if `url` is considered invalid.

    ria+ssh://somehost:/path/to/store
    ria+file:///path/to/store

    Parameters
    ----------
    url : str
      URL to verify an decode.
    cfg : dict-like
      Configuration settings for rewrite_url()

    Raises
    ------
    ValueError

    Returns
    -------
    tuple
      (host, base-path)
    """
    from datalad.config import rewrite_url
    from datalad.support.network import URL

    if not url:
        raise ValueError("Got no URL")

    url = rewrite_url(cfg, url)
    url_ri = URL(url)
    if not url_ri.scheme.startswith('ria+'):
        raise ValueError("Missing ria+ prefix in final URL: %s" % url)
    if url_ri.fragment:
        raise ValueError(
            "Unexpected fragment in RIA-store URL: %s" % url_ri.fragment)
    protocol = url_ri.scheme[4:]
    if protocol not in ['ssh', 'file']:
        raise ValueError("Unsupported protocol: %s" % protocol)

    return url_ri.hostname if protocol == 'ssh' else None, url_ri.path
