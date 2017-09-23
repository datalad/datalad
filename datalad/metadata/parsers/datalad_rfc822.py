# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Parser for RFC822-based metadata specifications

This is inspired by (and very similiar to) Debian's package meta data format.
The main difference is that information spread across multiple files in Debian
packages, is concentrated in one file.

The main advantage of this format is that it is proven to be hand-editable,
i.e. can be composed from scratch, by hand, in an editor -- with a good
chance of producing syntax-compliant content with the first attempt.
"""

from os.path import exists
import email
import email.parser  # necessary on Python 2.7.6 (trusty)
from os.path import join as opj
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


class MetadataParser(BaseMetadataParser):
    _metadata_compliance = "http://docs.datalad.org/metadata.html#v0-1"
    _core_metadata_filename = opj('.datalad', 'meta.rfc822')

    _key2stdkey = {
        'name': 'name',
        'license': 'license',
        'author': 'author',
        'maintainer': 'maintainer',
        'audience': 'audience',
        'homepage': 'homepage',
        'version': 'version',
        'funding': 'fundedby',
        'issue-tracker': 'issuetracker',
        'cite-as': 'citation',
        'doi': 'sameas',
        'description': None,
    }

    def has_metadata(self):
        return exists(opj(self.ds.path, self._core_metadata_filename))

    def get_dataset_metadata(self):
        meta = {}
        if not self.has_metadata():
            return meta
        spec = email.parser.Parser().parse(
            open(opj(self.ds.path, self._core_metadata_filename)),
            headersonly=True)

        for term in self._key2stdkey:
            if term not in spec:
                continue
            hkey = self.get_homogenized_key(term)
            content = spec[term]
            if term == 'description':
                short, long = _beautify_multiline_field(content)
                meta['shortdescription'] = short
                meta['description'] = long
            elif term == 'license':
                # TODO if title looks like a URL, use it as @id
                label, desc = _beautify_multiline_field(content)
                if label:
                    meta[hkey] = [label, desc]
                else:
                    meta[hkey] = desc
            elif term in ('maintainer', 'author'):
                meta[hkey] = _split_list_field(content)
            elif term == 'doi':
                meta[hkey] = 'http://dx.doi.org/{}'.format(content)
            else:
                meta[hkey] = content

        meta['conformsto'] = self._metadata_compliance
        return meta
