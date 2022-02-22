# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""add a README file to a dataset"""

__docformat__ = 'restructuredtext'


from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.support.annexrepo import AnnexRepo


@build_doc
class AddReadme(Interface):
    """Add basic information about DataLad datasets to a README file

    The README file is added to the dataset and the addition is saved
    in the dataset.
    Note: Make sure that no unsaved modifications to your dataset's
    .gitattributes file exist.

    """
    from datalad.support.param import Parameter
    from datalad.distribution.dataset import datasetmethod
    from datalad.interface.utils import eval_results
    from datalad.distribution.dataset import EnsureDataset
    from datalad.support.constraints import (
        EnsureChoice,
        EnsureNone,
        EnsureStr,
    )

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""Dataset to add information to. If no dataset is given, an
            attempt is made to identify the dataset based on the current
            working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        filename=Parameter(
            args=("filename",),
            metavar="PATH",
            nargs='?',
            doc="""Path of the README file within the dataset.""",
            constraints=EnsureStr()),
        existing=Parameter(
            args=("--existing",),
            doc="""How to react if a file with the target name already exists:
            'skip': do nothing; 'append': append information to the existing
            file; 'replace': replace the existing file with new content.""",
            constraints=EnsureChoice("skip", "append", "replace")),
    )

    @staticmethod
    @datasetmethod(name='add_readme')
    @eval_results
    def __call__(filename='README.md',
                 *,
                 dataset=None,
                 existing='skip'):
        from os.path import lexists
        from os.path import join as opj
        from io import open
        import logging
        lgr = logging.getLogger('datalad.local.add_readme')

        from datalad.distribution.dataset import require_dataset
        from datalad.utils import ensure_list

        dataset = require_dataset(dataset, check_installed=True,
                                  purpose='add README')

        fpath = opj(dataset.path, filename)
        res_kwargs = dict(action='add_readme', path=fpath)

        if lexists(fpath) and existing == 'skip':
            yield dict(
                res_kwargs,
                status='notneeded',
                message='file already exists, and not appending content')
            return

        # unlock, file could be annexed
        if lexists(fpath):
            yield from dataset.unlock(
                fpath,
                return_type='generator',
                result_renderer='disabled'
            )
        if not lexists(fpath):
            # if we have an annex repo, shall the README go to Git or annex?

            if isinstance(dataset.repo, AnnexRepo) \
                and 'annex.largefiles' not in \
                    dataset.repo.get_gitattributes(filename).get(filename, {}):
                # configure the README to go into Git
                dataset.repo.set_gitattributes(
                    [(filename, {'annex.largefiles': 'nothing'})])
                yield from dataset.save(
                    path='.gitattributes',
                    message="[DATALAD] Configure README to be in Git",
                    to_git=True,
                    return_type='generator',
                    result_renderer='disabled'
                )

        # get any metadata on the dataset itself
        dsinfo = dataset.metadata(
            '.',
            reporton='datasets',
            return_type='item-or-list',
            result_renderer='disabled',
            on_failure='ignore')
        meta = {}
        if not isinstance(dsinfo, dict) or dsinfo.get('status', None) != 'ok':
            lgr.warning("Could not obtain dataset metadata, proceeding without")
            dsinfo = {}
        else:
            # flatten possibly existing multiple metadata sources
            for src in dsinfo['metadata']:
                if src.startswith('@'):
                    # not a source
                    continue
                meta.update(dsinfo['metadata'][src])

        metainfo = ''
        for label, content in (
                ('', meta.get('description', meta.get('shortdescription', ''))),
                ('Author{}'.format('s' if isinstance(meta.get('author', None), list) else ''),
                    u'\n'.join([u'- {}'.format(a) for a in ensure_list(meta.get('author', []))])),
                ('Homepage', meta.get('homepage', '')),
                ('Reference', meta.get('citation', '')),
                ('License', meta.get('license', '')),
                ('Keywords', u', '.join([u'`{}`'.format(k) for k in ensure_list(meta.get('tag', []))])),
                ('Funding', meta.get('fundedby', '')),
                ):
            if label and content:
                metainfo += u'\n\n### {}\n\n{}'.format(label, content)
            elif content:
                metainfo += u'\n\n{}'.format(content)

        for key in 'title', 'name', 'shortdescription':
            if 'title' in meta:
                break
            if key in meta:
                meta['title'] = meta[key]

        default_content=u"""\
# {title}{metainfo}

## General information

This is a DataLad dataset{id}.

## DataLad datasets and how to use them

This repository is a [DataLad](https://www.datalad.org/) dataset. It provides
fine-grained data access down to the level of individual files, and allows for
tracking future updates. In order to use this repository for data retrieval,
[DataLad](https://www.datalad.org/) is required. It is a free and open source
command line tool, available for all major operating systems, and builds up on
Git and [git-annex](https://git-annex.branchable.com/) to allow sharing,
synchronizing, and version controlling collections of large files.

More information on how to install DataLad and [how to install](http://handbook.datalad.org/en/latest/intro/installation.html)
it can be found in the [DataLad Handbook](https://handbook.datalad.org/en/latest/index.html).

### Get the dataset

A DataLad dataset can be `cloned` by running

```
datalad clone <url>
```

Once a dataset is cloned, it is a light-weight directory on your local machine.
At this point, it contains only small metadata and information on the identity
of the files in the dataset, but not actual *content* of the (sometimes large)
data files.

### Retrieve dataset content

After cloning a dataset, you can retrieve file contents by running

```
datalad get <path/to/directory/or/file>
```

This command will trigger a download of the files, directories, or subdatasets
you have specified.

DataLad datasets can contain other datasets, so called *subdatasets*.  If you
clone the top-level dataset, subdatasets do not yet contain metadata and
information on the identity of files, but appear to be empty directories. In
order to retrieve file availability metadata in subdatasets, run

```
datalad get -n <path/to/subdataset>
```

Afterwards, you can browse the retrieved metadata to find out about subdataset
contents, and retrieve individual files with `datalad get`.  If you use
`datalad get <path/to/subdataset>`, all contents of the subdataset will be
downloaded at once.

### Stay up-to-date

DataLad datasets can be updated. The command `datalad update` will *fetch*
updates and store them on a different branch (by default
`remotes/origin/master`). Running

```
datalad update --merge
```

will *pull* available updates and integrate them in one go.

### Find out what has been done

DataLad datasets contain their history in the ``git log``.  By running ``git
log`` (or a tool that displays Git history) in the dataset or on specific
files, you can find out what has been done to the dataset or to individual
files by whom, and when.
""".format(
            title='Dataset "{}"'.format(meta['title']) if 'title' in meta else 'About this dataset',
            metainfo=metainfo,
            id=u' (id: {})'.format(dataset.id) if dataset.id else '',
            )

        with open(fpath, 'a' if existing == 'append' else 'w', encoding='utf-8') as fp:
            fp.write(default_content)
            yield dict(
                status='ok',
                path=fpath,
                type='file',
                action='add_readme')

        yield from dataset.save(
                fpath,
                message='[DATALAD] added README',
                result_filter=None,
                result_xfm=None,
                return_type='generator',
                result_renderer='disabled'
        )
