# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Parser for datacite xml records, currently for CRCNS datasets
"""

import re
from os.path import join as opj
from collections import OrderedDict

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from datalad.metadata.parsers.base import BaseMetadataParser
from datalad.interface.base import dedent_docstring


def _split_list_field(content):
    return [i.strip() for i in content.split(',') if i.strip()]


def _beautify_multiline_field(content):
    content = dedent_docstring(content)
    lines = content.split('\n')
    title = ''
    if len(lines):
        title = lines[0]
    if len(lines) > 1:
        content = ''
        for l in lines[1:]:
            l = l.strip()
            content = '{}{}{}'.format(
                content,
                ' ' if len(content) and l != '.' and content[-1] != '\n' else '',
                l if l != '.' else '\n')
    return title, content


def _merge(iterable):
    "Helper: merge multiple items into a single one separating with a newline"
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
        ('title', "title", False, _unwrap, None),
        # actually it seems we have no title but "ShortDescription"!!! TODO
        ('doap:shortdesc', "title", False, _unwrap, None),  # duplicate for now
        ('description', 'description', True, _unwrap, _merge),
        ('doap:Version', 'version', False, None, None),
        ('sameAs', "identifier[@identifierType='DOI']", False, None, None),
		# conflicts with our notion for having a "type" to be internal and to demarkate a Dataset
		# here might include the field e.g. Dataset/Neurophysiology, so skipping for now
        # ('type', "resourceType[@resourceTypeGeneral='Dataset']", False, None, None),
        ('citation', "relatedIdentifier", True, None, None),
        ('keywords', "subject", True, None, None),
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


class MetadataParser(BaseMetadataParser):
    _metadata_compliance = "http://docs.datalad.org/metadata.html#v0-1"
    _core_metadata_filenames = [opj('.datalad', 'meta.datacite.xml')]

    def _get_metadata(self, ds_identifier, meta, full):

        fname = self.get_core_metadata_filenames()[0]
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
        meta.update(_process_tree(tree, nstag))
        meta['dcterms:conformsTo'] = self._metadata_compliance
        return meta
