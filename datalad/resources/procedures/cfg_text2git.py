"""Procedure to configure Git annex to add text files directly to Git"""

import sys
import os.path as op
import platform

from datalad.distribution.dataset import require_dataset

ds = require_dataset(
    sys.argv[1],
    check_installed=True,
    purpose='configuration')

if platform.system().lower() == 'windows':
    # mimeencoding isn't functional under Windows yet (see #3360), this adds
    # common extensions of text files by hand
    force_in_git = [
        '*.txt',
        '*.json*',
        '*.log',
        '*.tsv',
        '*.csv',
        '*html',
        '*.css',
        '*.xml',
        '*.rss',
        '*.md',
        '*.markdown',
        '*.rmd',
        '*.rst',
        '*.rest',
        '*.yml',
        '*.toml',
        '*.adoc',
        '*.asc',
        '*.tex',
        '*.sty',
        '*.bib',
        '*.cls',
        '*.aux',
        '*.bst',
        '*.clo',
        '*.ini',
        '*.cfg',
        '*.cgi',
        '*.py',
        '*.pyx',
        '*.go',
        '*.java',
        '.*js',
        '*.sh',
        '*.bash',
        '*.zsh',
        '*.pl',
        '*.R',
        '*.jl',
        '*.ipynb'
        '*.m',
        '*.matlab',
        '*awk',
        '*.bat',
        '*.cmd',
        '*.cake',
        '*.cmake',
        'Makefile',
        '*.c++',
        '*.cpp',
        '*.h',
        '*.hh',
        '*.inc',
        '*.cp',
        '*.cu',
        '*.emacs',
        '*.emacs.desktop'
    ]
    ds.repo.set_gitattributes(
        [(p, {'annex.largefiles': 'nothing'}) for p in force_in_git])
else:
    annex_largefiles = '((mimeencoding=binary)and(largerthan=0))'

    attrs = ds.repo.get_gitattributes('*')
    if not attrs.get('*', {}).get(
            'annex.largefiles', None) == annex_largefiles:
        ds.repo.set_gitattributes([
            ('*', {'annex.largefiles': annex_largefiles})])

git_attributes_file = op.join(ds.path, '.gitattributes')
ds.save(
    git_attributes_file,
    message="Instruct annex to add text files to Git",
)
