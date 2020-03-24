# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import argparse
import datetime
import re


class ManPageFormatter(argparse.HelpFormatter):
    # This code was originally distributed
    # under the same License of Python
    # Copyright (c) 2014 Oz Nahum Tiram  <nahumoz@gmail.com>
    def __init__(self,
                 prog,
                 indent_increment=2,
                 max_help_position=4,
                 width=1000000,
                 section=1,
                 ext_sections=None,
                 authors=None,
                 version=None
                 ):

        super(ManPageFormatter, self).__init__(
            prog,
            indent_increment=indent_increment,
            max_help_position=max_help_position,
            width=width)

        self._prog = prog
        self._section = 1
        self._today = datetime.date.today().strftime('%Y\\-%m\\-%d')
        self._ext_sections = ext_sections
        self._version = version

    def _get_formatter(self, **kwargs):
        return self.formatter_class(prog=self.prog, **kwargs)

    def _markup(self, txt):
        return txt.replace('-', '\\-')

    def _underline(self, string):
        return "\\fI\\s-1" + string + "\\s0\\fR"

    def _bold(self, string):
        if not string.strip().startswith('\\fB'):
            string = '\\fB' + string
        if not string.strip().endswith('\\fR'):
            string = string + '\\fR'
        return string

    def _mk_synopsis(self, parser):
        self.add_usage(parser.usage, parser._actions,
                       parser._mutually_exclusive_groups, prefix='')
        usage = self._format_usage(None, parser._actions,
                                   parser._mutually_exclusive_groups, '')
        # replace too long list of commands with a single placeholder
        usage = re.sub(r'{[^]]*?create,.*?}', ' COMMAND ', usage, flags=re.MULTILINE)
        # take care of proper wrapping
        usage = re.sub(r'\[([-a-zA-Z0-9]*)\s([a-zA-Z0-9{}|_]*)\]', r'[\1\~\2]', usage)

        usage = usage.replace('%s ' % self._prog, '')
        usage = '.SH SYNOPSIS\n.nh\n.HP\n\\fB%s\\fR %s\n.hy\n' % (self._markup(self._prog),
                                                    usage)
        return usage

    def _mk_title(self, prog):
        name_version = "{0} {1}".format(prog, self._version)
        return '.TH "{0}" "{1}" "{2}" "{3}"\n'.format(
            prog, self._section, self._today, name_version)

    def _mk_name(self, prog, desc):
        """
        this method is in consitent with others ... it relies on
        distribution
        """
        desc = desc.splitlines()[0] if desc else 'it is in the name'
        # ensure starting lower case
        desc = desc[0].lower() + desc[1:]
        return '.SH NAME\n%s \\- %s\n' % (self._bold(prog), desc)

    def _mk_description(self, parser):
        desc = parser.description
        desc = '\n'.join(desc.splitlines()[1:])
        if not desc:
            return ''
        desc = desc.replace('\n\n', '\n.PP\n')
        # sub-section headings
        desc = re.sub(r'^\*(.*)\*$', r'.SS \1', desc, flags=re.MULTILINE)
        # italic commands
        desc = re.sub(r'^  ([-a-z]*)$', r'.TP\n\\fI\1\\fR', desc, flags=re.MULTILINE)
        # deindent body text, leave to troff viewer
        desc = re.sub(r'^      (\S.*)\n', '\\1\n', desc, flags=re.MULTILINE)
        # format NOTEs as indented paragraphs
        desc = re.sub(r'^NOTE\n', '.TP\nNOTE\n', desc, flags=re.MULTILINE)
        # deindent indented paragraphs after heading setup
        desc = re.sub(r'^  (.*)$', '\\1', desc, flags=re.MULTILINE)

        return '.SH DESCRIPTION\n%s\n' % self._markup(desc)

    def _mk_footer(self, sections):
        if not hasattr(sections, '__iter__'):
            return ''

        footer = []
        for section, value in sections.items():
            part = ".SH {}\n {}".format(section.upper(), value)
            footer.append(part)

        return '\n'.join(footer)

    def format_man_page(self, parser):
        page = []
        page.append(self._mk_title(self._prog))
        page.append(self._mk_name(self._prog, parser.description))
        page.append(self._mk_synopsis(parser))
        page.append(self._mk_description(parser))
        page.append(self._mk_options(parser))
        page.append(self._mk_footer(self._ext_sections))

        return ''.join(page)

    def _mk_options(self, parser):

        formatter = parser._get_formatter()

        # positionals, optionals and user-defined groups
        for action_group in parser._action_groups:
            formatter.start_section(None)
            formatter.add_text(None)
            formatter.add_arguments(action_group._group_actions)
            formatter.end_section()

        # epilog
        formatter.add_text(parser.epilog)

        # determine help from format above
        help = formatter.format_help()
        # add spaces after comma delimiters for easier reformatting
        help = re.sub(r'([a-z]),([a-z])', '\\1, \\2', help)
        # get proper indentation for argument items
        help = re.sub(r'^  (\S.*)\n', '.TP\n\\1\n', help, flags=re.MULTILINE)
        # deindent body text, leave to troff viewer
        help = re.sub(r'^    (\S.*)\n', '\\1\n', help, flags=re.MULTILINE)
        return '.SH OPTIONS\n' + help

    def _format_action_invocation(self, action, doubledash='--'):
        if not action.option_strings:
            metavar, = self._metavar_formatter(action, action.dest)(1)
            return metavar

        else:
            parts = []

            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend([self._bold(action_str) for action_str in
                              action.option_strings])

            # if the Optional takes a value, format is:
            #    -s ARGS, --long ARGS
            else:
                default = self._underline(action.dest.upper())
                args_string = self._format_args(action, default)
                for option_string in action.option_strings:
                    parts.append('%s %s' % (self._bold(option_string),
                                            args_string))

            return ', '.join(p.replace('--', doubledash) for p in parts)


class RSTManPageFormatter(ManPageFormatter):
    def _get_formatter(self, **kwargs):
        return self.formatter_class(prog=self.prog, **kwargs)

    def _markup(self, txt):
        # put general tune-ups here
        return txt

    def _underline(self, string):
        return "*{0}*".format(string)

    def _bold(self, string):
        return "**{0}**".format(string)

    def _mk_synopsis(self, parser):
        self.add_usage(parser.usage, parser._actions,
                       parser._mutually_exclusive_groups, prefix='')
        usage = self._format_usage(None, parser._actions,
                                   parser._mutually_exclusive_groups, '')

        usage = usage.replace('%s ' % self._prog, '')
        usage = 'Synopsis\n--------\n::\n\n  %s %s\n' \
                % (self._markup(self._prog), usage)
        return usage

    def _mk_title(self, prog):
        # and an easy to use reference point
        title = ".. _man_%s:\n\n" % prog.replace(' ', '-')
        title += "{0}".format(prog)
        title += '\n{0}\n\n'.format('=' * len(prog))
        return title

    def _mk_name(self, prog, desc):
        return ''

    def _mk_description(self, parser):
        desc = parser.description
        if not desc:
            return ''
        return 'Description\n-----------\n%s\n' % self._markup(desc)

    def _mk_footer(self, sections):
        if not hasattr(sections, '__iter__'):
            return ''

        footer = []
        for section, value in sections.items():
            part = "\n{0}\n{1}\n{2}\n".format(
                section,
                '-' * len(section),
                value)
            footer.append(part)

        return '\n'.join(footer)

    def _mk_options(self, parser):

        # this non-obvious maneuver is really necessary!
        formatter = self.__class__(self._prog)

        # positionals, optionals and user-defined groups
        for action_group in parser._action_groups:
            formatter.start_section(None)
            formatter.add_text(None)
            formatter.add_arguments(action_group._group_actions)
            formatter.end_section()

        # epilog
        formatter.add_text(parser.epilog)

        # determine help from format above
        option_sec = formatter.format_help()

        return '\n\nOptions\n-------\n{0}'.format(option_sec)

    def _format_action(self, action):
        # determine the required width and the entry label
        action_header = self._format_action_invocation(action, doubledash='-\\\\-')

        if action.help:
            help_text = self._expand_help(action)
            help_lines = self._split_lines(help_text, 80)
            help = ' '.join(help_lines)
        else:
            help = ''

        # return a single string
        return '{0}\n{1}\n{2}\n\n'.format(
            action_header,

            '~' * len(action_header),
            help)


def cmdline_example_to_rst(src, out=None, ref=None):
    if out is None:
        from io import StringIO
        out = StringIO()

    # place header
    out.write('.. AUTO-GENERATED FILE -- DO NOT EDIT!\n\n')
    if ref:
        # place cross-ref target
        out.write('.. {0}:\n\n'.format(ref))

    # parser status vars
    inexample = False
    incodeblock = False

    for line in src:
        if line.startswith('#% EXAMPLE START'):
            inexample = True
            incodeblock = False
            continue
        if not inexample:
            continue
        if line.startswith('#% EXAMPLE END'):
            break
        if not inexample:
            continue
        if line.startswith('#%'):
            incodeblock = not incodeblock
            if incodeblock:
                out.write('\n.. code-block:: sh\n\n')
            continue
        if not incodeblock and line.startswith('#'):
            out.write(line[(min(2, len(line) - 1)):])
            continue
        if incodeblock:
            if not line.rstrip().endswith('#% SKIP'):
                out.write('  %s' % line)
            continue
        if not len(line.strip()):
            continue
        else:
            raise RuntimeError("this should not happen")

    return out
