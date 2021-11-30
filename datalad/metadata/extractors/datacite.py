# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Extractor for datacite xml records, currently for CRCNS datasets
"""

import re
import os.path as op
from collections import OrderedDict
import logging
lgr = logging.getLogger('datalad.metadata.extractors.datacite')

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from datalad.metadata.extractors.base import BaseMetadataExtractor


def _merge(iterable):
    """Merge multiple items into a single one separating with a newline"""
    return "\n".join(iterable)


def _unwrap(text):
    """Basic unwrapping of text separated by newlines"""
    return re.sub(r'\n\s*', ' ', text)


def _process_tree(tree, nstag):
    """Process XML tree for a record and return a dictionary for our standard
    """
    rec = OrderedDict()
    for key, tag_, getall, trans1_, transall_ in [
        ('author', 'creatorName', True, None, None),
        ('name', "title[@titleType='AlternativeTitle']", False, None, None),
        # actually it seems we have no title but "ShortDescription"!!! TODO
        #('title', "title", False, _unwrap, None),
        ('shortdescription', "title", False, _unwrap, None),
        ('description', 'description', True, _unwrap, _merge),
        ('version', 'version', False, None, None),
        ('sameas', "identifier[@identifierType='DOI']", False, None, None),
        # conflicts with our notion for having a "type" to be internal and to demarkate a Dataset
        # here might include the field e.g. Dataset/Neurophysiology, so skipping for now
        # ('type', "resourceType[@resourceTypeGeneral='Dataset']", False, None, None),
        ('citation', "relatedIdentifier", True, None, None),
        ('tag', "subject", True, None, None),
        ('formats', "format", True, None, None),
    ]:
        trans1 = trans1_ or (lambda x: x)
        text = lambda x: trans1(x.text.strip())
        tag = nstag(tag_)
        try:
            if getall:
                value = list(map(text, tree.findall(tag)))
            else:
                value = text(tree.find(tag))
        except AttributeError:
            continue
        if not value or value == ['']:
            continue
        if transall_:
            value = transall_(value)
        rec[key] = value
    return rec


class MetadataExtractor(BaseMetadataExtractor):
    def _get_dataset_metadata(self):
        canonical = op.join(self.ds.path, '.datalad', 'meta.datacite.xml')

        # look for the first matching filename and go with it
        fname = [canonical] if op.lexists(canonical) else \
            [op.join(self.ds.path, f) for f in self.paths
             if op.basename(f) == 'meta.datacite.xml']
        if not fname or not op.lexists(fname[0]):
            return {}
        fname = fname[0]
        # those namespaces are a b.ch
        # TODO: avoid reading file twice
        namespaces = dict([
            node for _, node in ET.iterparse(
                open(fname), events=('start-ns',)
            )
        ])
        ns = namespaces['']

        def nstag(tag):
            return './/{%s}%s' % (ns, tag)

        tree = ET.ElementTree(file=fname)
        return _process_tree(tree, nstag)

    def _get_content_metadata(self):
        return []  # no content metadata provided
