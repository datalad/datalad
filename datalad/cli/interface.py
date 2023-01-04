"""Utilities and definitions for DataLad command interfaces"""

# TODO this should be a dochelper
from datalad.interface.base import dedent_docstring

# Some known extensions and their commands to suggest whenever lookup fails
_known_extension_commands = {
    'datalad-container': (
        'containers-list', 'containers-remove', 'containers-add',
        'containers-run'),
    'datalad-crawler': ('crawl', 'crawl-init'),
    'datalad-deprecated': (
        'ls',
        'metadata',
        'search',
        'aggregate-metadata',
        'extract-metadata',
    ),
    'datalad-neuroimaging': ('bids2scidata',)
}

_deprecated_commands = {
    'add': "save",
    'uninstall': 'drop',
}


def get_cmd_ex(interface):
    """Return the examples for the command defined by 'interface'.

    Parameters
    ----------
    interface : subclass of Interface
    """
    from datalad.interface.base import build_example
    intf_ex = "\n\n*Examples*\n\n"
    for example in interface._examples_:
        intf_ex += build_example(example, api='cmdline')
    return intf_ex


def get_cmdline_command_name(intfspec):
    """Given an interface specification return a cmdline command name"""
    if len(intfspec) > 2:
        name = intfspec[2]
    else:
        name = intfspec[0].split('.')[-1].replace('_', '-')
    return name


def alter_interface_docs_for_cmdline(docs):
    """Apply modifications to interface docstrings for cmdline doc use."""
    # central place to alter the impression of docstrings,
    # like removing Python API specific sections, and argument markup
    if not docs:
        return docs
    import re
    import textwrap

    docs = dedent_docstring(docs)
    # clean cmdline sections
    docs = re.sub(
        r'\|\| PYTHON \>\>.*?\<\< PYTHON \|\|',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # clean cmdline in-line bits
    docs = re.sub(
        r'\[PY:\s.*?\sPY\]',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    docs = re.sub(
        r'\[CMD:\s(.*?)\sCMD\]',
        lambda match: match.group(1),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    docs = re.sub(
        r'\|\| CMDLINE \>\>(.*?)\<\< CMDLINE \|\|',
        lambda match: match.group(1),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # remove :role:`...` RST markup for cmdline docs
    docs = re.sub(
        r':\S+:`[^`]*`[\\]*',
        lambda match: ':'.join(match.group(0).split(':')[2:]).strip('`\\'),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # make the handbook doc references more accessible
    # the URL is a redirect configured at readthedocs
    docs = re.sub(
        r'(handbook:[0-9]-[0-9]*)',
        '\\1 (http://handbook.datalad.org/symbols)',
        docs)
    # remove None constraint. In general, `None` on the cmdline means don't
    # give option at all, but specifying `None` explicitly is practically
    # impossible
    docs = re.sub(
        r',\sor\svalue\smust\sbe\s`None`',
        '',
        docs,
        flags=re.MULTILINE | re.DOTALL)
    # capitalize variables and remove backticks to uniformize with
    # argparse output
    docs = re.sub(
        r'([^`]+)`([a-zA-Z0-9_]+)`([^`]+)',
        lambda match: f'{match.group(1)}{match.group(2).upper()}{match.group(3)}',
        docs)
    # select only the cmdline alternative from argument specifications
    docs = re.sub(
        r'``([a-zA-Z0-9_,.]+)\|\|([a-zA-Z0-9-,.]+)``',
        lambda match: f'``{match.group(2)}``',
        docs)
    # clean up sphinx API refs
    docs = re.sub(
        r'\~datalad\.api\.\S*',
        lambda match: "`{0}`".format(match.group(0)[13:]),
        docs)
    # dedicated support for version markup
    docs = docs.replace('.. versionadded::', 'New in version')
    docs = docs.replace('.. versionchanged::', 'Changed in version')
    docs = docs.replace('.. deprecated::', 'Deprecated in version')
    # Remove RST paragraph markup
    docs = re.sub(
        r'^.. \S+::',
        lambda match: match.group(0)[3:-2].upper(),
        docs,
        flags=re.MULTILINE)
    docs = re.sub(
        r'^([ ]*)\|\| REFLOW \>\>\n(.*?)\<\< REFLOW \|\|',
        lambda match: textwrap.fill(match.group(2), subsequent_indent=match.group(1)),
        docs,
        flags=re.MULTILINE | re.DOTALL)
    return docs
