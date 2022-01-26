# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" Metadata indexer base class """
import abc
from typing import Any, Dict, List, Union


class MetadataIndexer(metaclass=abc.ABCMeta):
    """ Defines the indexer interface """
    def __init__(self, metadata_format_name: str):
        """
        Create a metadata indexer

        The format name is passed to the constructor to allow
        a single indexer to process multiple extractor results
        """
        self.metadata_format_name = metadata_format_name

    @abc.abstractmethod
    def create_index(self, metadata: Union[Dict, List]) -> Dict[str, Any]:
        """
        Create an index from metadata.

        The input is a list or dictionary that contains metadata
        in the format identified by metadata_format_name.

        The output should be a set of key-value pairs that represent
        the information stored in `metadata´.

        Parameters
        ----------
        metadata : Dict or List
          Metadata created by an extractor.

        Returns
        -------
        dict:
           key-value pairs representing the information in metadata.
           values can be literals or lists of literals
        """
        raise NotImplementedError
