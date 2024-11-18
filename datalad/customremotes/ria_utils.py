# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper for RIA stores

"""
import logging
from pathlib import Path

lgr = logging.getLogger('datalad.customremotes.ria_utils')


class UnknownLayoutVersion(Exception):
    pass


# TODO: Make versions a tuple of (label, description)?
# Object tree versions we introduced so far. This is about the layout within a
# dataset in a RIA store
known_versions_objt = ['1', '2']
# Dataset tree versions we introduced so far. This is about the layout of
# datasets in a RIA store
known_versions_dst = ['1']


# TODO: This is wrong and should consider both versions (store+dataset)
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
        raise ValueError("Unknown layout version: {}. Supported: {}"
                         "".format(version, known_versions_dst))


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
      (host, base-path, rewritten url)
      `host` is not just a hostname, but is a stub URL that may also contain
      username, password, and port, if specified in a given URL.
      `base-path` is the unquoted path component of the url
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
    if protocol not in ['ssh', 'file', 'http', 'https']:
        raise ValueError("Unsupported protocol: %s. "
                         "Supported: ssh, file, http(s)" %
                         protocol)

    host = '{proto}://{user}{pdlm}{passwd}{udlm}{host}{portdlm}{port}'.format(
        proto=protocol,
        user=url_ri.username or '',
        pdlm=':' if url_ri.password else '',
        passwd=url_ri.password or '',
        udlm='@' if url_ri.username else '',
        host=url_ri.hostname or '',
        portdlm=':' if url_ri.port else '',
        port=url_ri.port or '',
    )
    # this ``!= 'file'´´ is critical behavior, if removed, it will ruin the IO
    # selection in ORARemote!!
    return host if protocol != 'file' else None, url_ri.path or '/', url


def _ensure_version(io, base_path, version):
    """Check a store or dataset version and make sure it is declared

    Parameters
    ----------
    io: SSHRemoteIO or LocalIO
    base_path: Path
      root path of a store or dataset
    version: str
      target layout version of the store (dataset tree)
    """
    version_file = base_path / 'ria-layout-version'
    if io.exists(version_file):
        existing_version = io.read_file(version_file).split('|')[0].strip()
        if existing_version != version.split('|')[0]:
            # We have an already existing location with a conflicting version on
            # record.
            # Note, that a config flag after pipe symbol is fine.
            raise ValueError("Conflicting version found at target: {}"
                             .format(existing_version))
        else:
            # already exists, recorded version fits - nothing to do
            return
    # Note, that the following does create the base-path dir as well, since
    # mkdir has parents=True:
    io.mkdir(base_path)
    io.write_file(version_file, version)


def create_store(io, base_path, version):
    """Helper to create a RIA store

    Note, that this is meant as an internal helper and part of intermediate
    RF'ing. Ultimately should lead to dedicated command or option for
    create-sibling-ria.

    Parameters
    ----------
    io: SSHRemoteIO or LocalIO
      Respective execution instance.
      Note: To be replaced by proper command abstraction
    base_path: Path
      root path of the store
    version: str
      layout version of the store (dataset tree)
    """

    # At store level the only version we know as of now is 1.
    if version not in known_versions_dst:
        raise UnknownLayoutVersion("RIA store layout version unknown: {}."
                                   "Supported versions: {}"
                                   .format(version, known_versions_dst))
    _ensure_version(io, base_path, version)
    error_logs = base_path / 'error_logs'
    io.mkdir(error_logs)


def create_ds_in_store(io, base_path, dsid, obj_version, store_version,
                       alias=None, init_obj_tree=True):
    """Helper to create a dataset in a RIA store

    Note, that this is meant as an internal helper and part of intermediate
    RF'ing. Ultimately should lead to a version option for create-sibling-ria
    in conjunction with a store creation command/option.

    Parameters
    ----------
    io: SSHRemoteIO or LocalIO
      Respective execution instance.
      Note: To be replaced by proper command abstraction
    base_path: Path
      root path of the store
    dsid: str
      dataset id
    store_version: str
      layout version of the store (dataset tree)
    obj_version: str
      layout version of the dataset itself (object tree)
    alias: str, optional
      alias for the dataset in the store
    init_obj_tree: bool
      whether or not to create the base directory for an annex objects tree (
      'annex/objects')
    """

    # TODO: Note for RF'ing, that this is about setting up a valid target
    #       for the special remote not a replacement for create-sibling-ria.
    #       There's currently no git (bare) repo created.

    try:
        # TODO: This is currently store layout version!
        #       Too entangled by current get_layout_locations.
        dsgit_dir, archive_dir, dsobj_dir = \
            get_layout_locations(int(store_version), base_path, dsid)
    except ValueError as e:
        raise UnknownLayoutVersion(str(e))

    if obj_version not in known_versions_objt:
        raise UnknownLayoutVersion("Dataset layout version unknown: {}. "
                                   "Supported: {}"
                                   .format(obj_version, known_versions_objt))

    _ensure_version(io, dsgit_dir, obj_version)

    io.mkdir(archive_dir)
    if init_obj_tree:
        io.mkdir(dsobj_dir)
    if alias:
        alias_dir = base_path / "alias"
        io.mkdir(alias_dir)
        try:
            # go for a relative path to keep the alias links valid
            # when moving a store
            io.symlink(
                Path('..') / dsgit_dir.relative_to(base_path),
                alias_dir / alias)
        except FileExistsError:
            lgr.warning("Alias %r already exists in the RIA store, not adding an "
                        "alias.", alias)
