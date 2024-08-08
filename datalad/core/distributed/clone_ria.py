""""""

__docformat__ = 'restructuredtext'

import logging
from typing import Dict

from datalad.distribution.dataset import Dataset

from . import clone as mod_clone
# For now kept in clone_utils, to avoid circular import (see datalad-next)
from .clone_utils import (
    postclone_preannex_cfg_ria,
    postclonecfg_ria,
)

# we need to preserve the original functions to be able to call them
# in the patch
orig_post_git_init_processing_ = mod_clone._post_git_init_processing_
orig_pre_final_processing_ = mod_clone._pre_final_processing_


lgr = logging.getLogger('datalad.core.distributed.clone')


def _post_git_init_processing_(
    *,
    destds: Dataset,
    gitclonerec: Dict,
    remote: str,
    **kwargs
):
    yield from orig_post_git_init_processing_(
        destds=destds, gitclonerec=gitclonerec, remote=remote,
        **kwargs)

    # In case of RIA stores we need to prepare *before* annex is called at all
    if gitclonerec['type'] == 'ria':
        postclone_preannex_cfg_ria(destds, remote=remote)


def _pre_final_processing_(
        *,
        destds: Dataset,
        gitclonerec: Dict,
        remote: str,
        **kwargs
):
    if gitclonerec['type'] == 'ria':
        yield from postclonecfg_ria(destds, gitclonerec,
                                    remote=remote)

    yield from orig_pre_final_processing_(
        destds=destds, gitclonerec=gitclonerec, remote=remote,
        **kwargs)


def _apply():
    # apply patch in a function, to be able to easily patch it out
    # and turn off the patch
    lgr.debug(
        'Apply RIA patch to clone.py:_post_git_init_processing_')
    mod_clone._post_git_init_processing_ = _post_git_init_processing_
    lgr.debug(
        'Apply RIA patch to clone.py:_pre_final_processing_')
    mod_clone._pre_final_processing_ = _pre_final_processing_


_apply()
