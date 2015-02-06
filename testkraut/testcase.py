# TKLIGHT: # emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the testkraut package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Unittest compliant API for testkraut test cases"""

__docformat__ = 'restructuredtext'

import os
import re
from os.path import join as opj
from json import dumps as jds
from functools import wraps

import logging
lgr = logging.getLogger(__name__)

from testtools import TestCase, RunTest
from testtools.content import Content, text_content
from testtools.content_type import ContentType, UTF8_TEXT
from testtools import matchers as tm
from testtools.matchers import Equals, Annotate, FileExists, Contains, DirExists, \
     MatchesRegex, StartsWith, EndsWith
     # To be added whenever testtools gets upgraded (1.5.0 has those already exposed)
     #DoesNotEndWith, DoesNotStartWith

__spec_matchers__ = {
    'value': Equals,
    'contains': Contains,
    'matches': MatchesRegex,
    'startswith': StartsWith,
    'endswith': EndsWith,
#    'doesnotstartwith': DoesNotStartWith,
#    'doesnotendwith': DoesNotEndWith,
    }

import testtools.matchers as tt_matchers
# TKLIGHT: from . import matchers as tk_matchers

from .utils import get_test_library_paths, describe_system, describe_binary, \
        run_command, which, describe_python_module, _resolve_metric_value
from .spec import SPEC, SPECJSONEncoder
# TKLIGHT: from .fingerprints import get_fingerprinters, proc_fingerprint
from testkraut import cfg
# TKLIGHT: from . import metrics

#
# Utility code for template-based test cases
#
def TestArgs(*args, **kwargs):
    """Little helper to specify test arguments"""
    return (args, kwargs)

def template_case(args):
    def wrapper(func):
        func.template = args
        return func
    return wrapper

def _method_partial(func, *parameters, **kparms):
    @wraps(func)
    def wrapped(self, *args, **kw):
        kw.update(kparms)
        return func(self, *(args + parameters), **kw)
    return wrapped

class TemplateTestCase(type):
    """
    Originally based on code from
    https://bitbucket.org/lothiraldan/unittest-templates

    Copyright 2011, Boris Feld <http://boris.feld.crealio.fr>
    License: DTFYWTPL
    """
    #            DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
    #                Version 2, December 2004
    #
    # Copyright (C) 2004 Sam Hocevar <sam@hocevar.net>
    #
    # Everyone is permitted to copy and distribute verbatim or modified
    # copies of this license document, and changing it is allowed as long
    # as the name is changed.
    #
    #            DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
    #   TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION
    #
    #  0. You just DO WHAT THE FUCK YOU WANT TO.
    def __new__(cls, name, bases, attr):
        new_methods = {}
        for method_name in attr:
            if hasattr(attr[method_name], "template"):
                source = attr[method_name]
                source_name = method_name.lstrip("_")
                for test_name, args in source.template.items():
                    parg, kwargs = args
                    new_name = "test_%s" % test_name
                    new_methods[new_name] = _method_partial(source, *parg, **kwargs)
                    new_methods[new_name].__name__ = str(new_name)
        attr.update(new_methods)
        return type(name, bases, attr)

def discover_specs(paths=None):
    """Helper function to discover test SPECs in configured library locations
    """
    discovered = {}
    # for all configured test library locations
    if paths is None:
        paths = get_test_library_paths()
    cands = []
    for tld in paths:
        # look for 'spec.json' in all subdirs
        cands.extend([opj(tld, d, 'spec.json')
                        for d in os.listdir(tld)
                            if os.path.isdir(opj(tld, d))])
        # and all plain JSON files
        cands.extend([opj(tld, d)
                        for d in os.listdir(tld)
                            if d.endswith('.json')])
    for spec_fname in cands:
        if not os.path.isfile(spec_fname):
            # not a test spec
            lgr.debug("ignoring '%s' directory in library path '%s': contains no SPEC file"
                      % (subdir, tld))
            continue
        try:
            spec = SPEC(open(spec_fname))
            spec_id = spec['id'].replace('-', '_')
            if spec_id in discovered:
                lgr.warning("found duplicate test ID '%s' in %s: ignoring the latter test"
                            % (spec_id, (discovered[spec_id], spec_fname)))
                continue
            # we actually found a new one
            lgr.debug("discovered test SPEC '%s'" % spec_id)
            discovered[spec_id] = spec_fname
        # TODO: provide configuration variable allowing to avoid this
        # swallow-everything catcher to troubleshoot problems in the code
        # inside
        except Exception, e:
            # not a valid SPEC
            lgr.warning("ignoring '%s': no a valid SPEC file: %s (%s)"
                      % (spec_fname, str(e), e.__class__.__name__))
    # wrap spec file locations in TestArgs
    return dict([(k, TestArgs(v)) for k, v in discovered.iteritems()])


class TestFromSPEC(TestCase):
    __metaclass__ = TemplateTestCase

    _system_info = None

    # list of paths the search when looking up files. This list is prepended
    # with the path of the executed test spec and then iterated over in
    # ascending order
    search_dirs = []

    def __init__(self, *args, **kwargs):
        TestCase.__init__(self, *args, **kwargs)
        self._workdir = None
        self._environ_restore = None

# derived classes should have this
#    @template_case(discover_specs())
    def _run_spec_test(self, spec_filename):
        wdir = self._workdir
        self._details['exec_info'] = {}
        # get the SPEC
        spec = SPEC(open(spec_filename))
        self._cur_spec = spec
        spec_id = spec['id']
        self._details['spec_info'] = spec.copy()
        # _relevant_ environment bits (variables mentioned in the SPEC)
        env_info = {}
        self._details['env_info'] = env_info
        # metrics
        metric_info = {}
        self._details['metric_info'] = metric_info
        # fingerprints
        fingerprints = {}
        self._details['output_info'] = fingerprints
        # get the environment in shape, accoridng to SPEC
        env_info.update(self._prepare_environment(spec))
        # prepare the testbed, place test input into testbed
        from .lookup import prepare_local_testbed
        prepare_local_testbed(
                spec, wdir,
                search_dirs=[os.path.dirname(spec_filename)] + self.search_dirs,
                cache=None, force_overwrite=True)
        # final test: do we have all dependencies
        # NEEDS to be done after testbed setup, in case custom scripts are
        # listed
        self._verify_dependencies(spec)
        for idx, testspec in enumerate(spec['tests']):
            os.environ['TESTKRAUT_SUBTEST_IDX'] = str(idx)
            if not 'id' in testspec:
                subtestid = str(idx)
            else:
                subtestid = testspec['id']
            # execute the actual test implementation
            self._execute_any_test_implementation(subtestid, testspec)
            del os.environ['TESTKRAUT_SUBTEST_IDX']
        # check for expected output
        initial_cwd = os.getcwdu()
        os.chdir(self._workdir)
        try:
            self._check_output_presence(spec)
            # TKLIGHT: self._compute_metrics(spec, metric_info)
            # TKLIGHT: self._fingerprint_output(spec, fingerprints)
            self._check_assertions(spec, metric_info)
        finally:
            os.chdir(initial_cwd)

    def setUp(self):
        """Runs prior each test run"""
        super(TestFromSPEC, self).setUp()
        # a place to store additional information gather during test execution
        # added automatically to the test protocol
        self._details = {}
        # reference to the currently processed test SPEC
        self._cur_spec = None
        import tempfile
        # check if we have a concurent test run
        assert(self._workdir is None)
        self._workdir = tempfile.mkdtemp(prefix='testkraut')
        lgr.debug("created work dir at '%s'" % self._workdir)
        # post testbed path into the environment
        os.environ['TESTKRAUT_TESTBED_PATH'] = self._workdir

    def tearDown(self):
        """Runs after each test run"""
        super(TestFromSPEC, self).tearDown()
        ct = ContentType('application', 'json')
        # information on test dependencies mentioned in the SPEC
        self._get_dep_info()
        # configure default set of information to be reported for any test run
        # still can figure out why this can't be a loop
        self.addDetail('spec_info',
                Content(ct, lambda: [self._jds(self._details['spec_info'])]))
        self.addDetail('dep_info',
                Content(ct, lambda: [self._jds(self._details['dep_info'])]))
        self.addDetail('exec_info',
                Content(ct, lambda: [self._jds(self._details['exec_info'])]))
        self.addDetail('env_info',
                Content(ct, lambda: [self._jds(self._details['env_info'])]))
        self.addDetail('metric_info',
                Content(ct, lambda: [self._jds(self._details['metric_info'])]))
        self.addDetail('output_info',
                Content(ct, lambda: [self._jds(self._details['output_info'])]))
        self.addDetail('sys_info',
                Content(ct, lambda: [self._jds(self._get_system_info())]))
        # restore environment to its previous state
        self._restore_environment()
        # after EVERYTHING is done
        # remove status var again
        del os.environ['TESTKRAUT_TESTBED_PATH']
        # wipe out testbed
        if not self._workdir is None:
            lgr.debug("remove work dir at '%s'" % self._workdir)
            import shutil
            shutil.rmtree(self._workdir)
            self._workdir = None

    def _execute_any_test_implementation(self, testid, testspec):
        # NOTE: Any test execution implementation needs to handle
        # expected failures individually
        type_ = testspec['type']
        try:
            test_exec = getattr(self, '_execute_%s_test' % type_)
        except AttributeError:
            raise ValueError("unsupported test type '%s'" % type_)
        lgr.info("run test '%s' via %s()"
                 % (testid, test_exec.__name__))
        # move into testbed
        initial_cwd = os.getcwdu()
        os.chdir(self._workdir)
        # run the test
        try:
            self._details['exec_info'][testid] = dict(
                    type=testspec['type']
                )
            ret = test_exec(testid, testspec)
        finally:
            os.chdir(initial_cwd)

    def _execute_python_test(self, testid, testspec):
        from cStringIO import StringIO
        import sys
        execinfo = self._details['exec_info'][testid]
        try:
            rescue_stdout = sys.stdout
            rescue_stderr = sys.stderr
            sys.stdout = capture_stdout = StringIO()
            sys.stderr = capture_stderr = StringIO()
            try:
                if 'code' in testspec:
                    exec testspec['code'] in {}, {}
                elif 'file' in testspec:
                    execfile(testspec['file'], {}, {})
                else:
                    raise ValueError("no test code found")
            except Exception, e:
                execinfo['exception'] = dict(type=e.__class__.__name__,
                                             info=str(e))
                if not 'shouldfail' in testspec or testspec['shouldfail'] == False:
                    lgr.error("%s: %s" % (e.__class__.__name__, str(e)))
                    self.assertThat(e,
                        Annotate("exception occured while executing Python test code in test '%s': %s (%s)"
                                 % (testid, str(e), e.__class__.__name__), Equals(None)))
                return
            if 'shouldfail' in testspec and testspec['shouldfail'] == True:
                self.assertThat(e,
                    Annotate("an expected failure did not occur in test '%s': %s (%s)"
                                 % (testid, str(e), e.__class__.__name__), Equals(None)))
        finally:
            execinfo['stdout'] = capture_stdout.getvalue()
            execinfo['stderr'] = capture_stderr.getvalue()
            sys.stdout = rescue_stdout
            sys.stderr = rescue_stderr

    def _execute_shell_test(self, testid, testspec):
        import subprocess
        cmd = testspec['command']
        execinfo = self._details['exec_info'][testid]
        if isinstance(cmd, list):
            # convert into a cmd string to execute via shell
            # to get all envvar expansion ...
            cmd = subprocess.list2cmdline(cmd)
        # for the rest we need to execute stuff in the root of the testbed
        try:
            lgr.debug("attempting to execute command '%s'" % cmd)
            texec = subprocess.Popen(cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    shell=True)
            texec.wait()
            # record the exit code
            execinfo['exitcode'] = texec.returncode
            # store test output
            for chan in ('stderr', 'stdout'):
                execinfo[chan] = getattr(texec, chan).read()
                #lgr.debug('%s: %s' % (chan, execinfo[chan]))
            if texec.returncode != 0 and 'shouldfail' in testspec \
               and testspec['shouldfail'] == True:
                   # failure is expected
                   return
            self.assertThat(
                texec.returncode,
                Annotate("test shell command '%s' yielded non-zero exit code" % cmd,
                         Equals(0)))
        except OSError, e:
            lgr.error("%s: %s" % (e.__class__.__name__, str(e)))
            if not 'shouldfail' in testspec or testspec['shouldfail'] == False:
                self.assertThat(e,
                    Annotate("test command execution failed: %s (%s)"
                             % (e.__class__.__name__, str(e)), Equals(None)))
        if 'shouldfail' in testspec and testspec['shouldfail'] == True:
            self.assertThat(e,
                Annotate("an expected failure did not occur in test '%s': %s (%s)"
                             % (testid, str(e), e.__class__.__name__), Equals(None)))

    def _execute_nipype_test(self, testid, testspec):
        # TODO merge/refactor this one with the plain python code method
        from cStringIO import StringIO
        import sys
        execinfo = self._details['exec_info'][testid]
        try:
            import nipype
        except ImportError:
            self.skipTest("Nipype not found, skipping test")
        # where is the workflow
        if 'file' in testspec:
            testwffilepath = testspec['file']
            lgr.debug("using custom workflow file name '%s'" % testwffilepath)
        else:
            testwffilepath = 'workflow.py'
            lgr.debug("using default workflow file name '%s'" % testwffilepath)
        # execute the script and extract the workflow
        locals = dict()
        try:
            execfile(testwffilepath, dict(), locals)
        except Exception, e:
            lgr.error("%s: %s" % (e.__class__.__name__, str(e)))
            self.assertThat(e,
                Annotate("test workflow setup failed: %s (%s)"
                         % (e.__class__.__name__, str(e)), Equals(None)))
        self.assertThat(locals,
            Annotate("test workflow script create expected workflow object",
                     Contains('test_workflow')))
        workflow = locals['test_workflow']
        # make sure nipype executes it in the right place
        workflow.base_dir=os.path.abspath(opj(os.curdir, '_workflow_exec'))
        # we want content, not time based hashing
        if 'execution' in workflow.config:
            workflow.config['execution']['hash_method'] = "content"
        else:
            workflow.config['execution'] = dict(hash_method="content")
        # execution
        try:
            rescue_stdout = sys.stdout
            rescue_stderr = sys.stderr
            sys.stdout = capture_stdout = StringIO()
            sys.stderr = capture_stderr = StringIO()
            try:
                exec_graph = workflow.run()
            except Exception, e:
                execinfo['exception'] = dict(type=e.__class__.__name__,
                                             info=str(e))
                if not 'shouldfail' in testspec or testspec['shouldfail'] == False:
                    lgr.error("%s: %s" % (e.__class__.__name__, str(e)))
                    self.assertThat(e,
                        Annotate("exception occured while executing Nipype workflow in test '%s': %s (%s)"
                                 % (testid, str(e), e.__class__.__name__),
                                 Equals(None)))
                return
            if 'shouldfail' in testspec and testspec['shouldfail'] == True:
                self.assertThat(e,
                    Annotate("an expected failure did not occur in test '%s': %s (%s)"
                                 % (testid, str(e), e.__class__.__name__),
                                 Equals(None)))
        finally:
            execinfo['stdout'] = capture_stdout.getvalue()
            execinfo['stderr'] = capture_stderr.getvalue()
            sys.stdout = rescue_stdout
            sys.stderr = rescue_stderr

        # try dumping provenance info
        try:
            from nipype.pipeline.utils import write_prov
            write_prov(exec_graph,
                       filename=opj(workflow.base_dir, 'provenance.json'))
        except ImportError:
            lgr.debug("local nipype version doesn't support provenance capture")


    def _check_output_presence(self, spec):
        outspec = spec.get('outputs', {})
        unmatched_output = []
        for ospec_id in outspec:
            ospec = outspec[ospec_id]
            ospectype = ospec['type']
            if ospectype == 'file':
                self.assertThat(
                    ospec['value'],
                    Annotate('expected output file missing', FileExists()))
            elif ospectype == 'directory':
                self.assertThat(
                    ospec['value'],
                    Annotate('expected output directory missing', DirExists()))
            elif ospectype == 'string' and ospec_id.startswith('tests'):
                execinfo = self._details['exec_info']
                sec, idx, field = ospec_id.split('::')
                for f, matcher in __spec_matchers__.iteritems():
                    if f in ospec:
                        # allow for multiple target values (given a matcher) being
                        # specified.  For some matchers it might make no sense
                        # (e.g. "endswith")
                        targets = ospec[f]
                        for target in (targets if isinstance(targets, list) else [targets]):
                            self.assertThat(
                                 execinfo[idx][field],
                                 Annotate("unexpected output for '%s'" % ospec_id,
                                           matcher(target)))
            else:
                raise NotImplementedError(
                        "dunno how to handle output type '%s' yet"
                        % ospectype)
            # TODO check for file type

    def _compute_metrics(self, spec, info):
        metricspecs = spec.get('metrics', {})
        for mid, mspec in metricspecs.iteritems():
            metric = mspec.get('metric', None)
            if metric is None:
                lgr.warning("broken metric spec '%s': no metric given" % mid)
                continue
            # import the metric
            try:
                metric = getattr(metrics, metric)
            except AttributeError:
                lgr.warning("unsupported metric '%s' in spec '%s'" % (metric, mid))
                continue
            # metric instance
            args = mspec.get('args', None)
            if args is None:
                val = metric()
            elif isinstance(args, list):
                val = metric(*args)
            elif isinstance(args, dict):
                val = metric(**args)
            else:
                val = metric(args)
            info[mid] = val

    def _check_assertions(self, spec, metric_info):
        specs = spec.get('assertions', {})
        for aid, aspec in specs.iteritems():
            lgr.debug("check assertion '%s'" % aid)
            # preconditions
            self.assertThat(aspec, Contains('value'))
            self.assertThat(aspec, Contains('matcher'))
            # matcher
            # TKLIGHT
            #try:
            #    matcher = getattr(tk_matchers, aspec['matcher'])
            #except AttributeError:
            try:
                matcher = getattr(tt_matchers, aspec['matcher'])
            except AttributeError:
                lgr.warning("unsupported matcher '%s' in spec '%s'" % (matcher, aid))
                continue
            # matcher instance
            args = aspec.get('args', None)
            if args is None:
                assertion = matcher()
            elif isinstance(args, list):
                assertion = matcher(*[_resolve_metric_value(v, metric_info)
                                            for v in args])
            elif isinstance(args, dict):
                assertion = matcher(
                        **dict(
                            zip([(k, _resolve_metric_value(v, metric_info))
                                            for k, v in args.iteritems()])))
            else:
                assertion = matcher(_resolve_metric_value(args, metric_info))
            # value to match
            value = aspec['value']
            self.assertThat(_resolve_metric_value(value, metric_info),
                            assertion)
            lgr.debug("verified assertion '%s'" % aid)

    def _fingerprint_output(self, spec, info):
        from .utils import sha1sum
        # for all known outputs
        ofilespecs = spec.get_outputs('file')
        # cache fingerprinted files tp avoid duplication for identical files
        fp_cache = {}
        # deterministic order to help stabilize reference filename for duplicates
        for oname in sorted(ofilespecs.keys()):
            ospec = ofilespecs[oname]
            filename = ospec['value']
            sha1 = sha1sum(filename)
            fingerprints = {}
            oinfo = {'type': 'file', 'name': filename, 'sha1sum': sha1,
                     'fingerprints': fingerprints}
            if sha1 in fp_cache:
                # we already had this file
                ospec['identical_with'] = fp_cache[sha1]
                lgr.debug("'%s' is a duplicate of '%s'" % (oname, fp_cache[sha1]))
                continue
            fp_cache[sha1] = oname
            info[oname] = oinfo
            lgr.debug("generating fingerprints for '%s'" % filename)
            # gather fingerprinting callables
            fingerprinters = set()
            for tag in ospec.get('tags', []):
                fingerprinters = fingerprinters.union(get_fingerprinters(tag))
            # for the unique set of fingerprinting functions
            for fingerprinter in fingerprinters:
                proc_fingerprint(fingerprinter, fingerprints, filename,
                                 ospec.get('tags', []))

    def _get_system_info(self):
        if TestFromSPEC._system_info is None:
            if cfg.getboolean('testrun', 'skip platform description',
                              default=False):
                TestFromSPEC._system_info = {}
            else:
                TestFromSPEC._system_info = describe_system()
        return TestFromSPEC._system_info

    def _verify_dependencies(self, spec):
        for dep_id, depspec in spec.get('dependencies', {}).iteritems():
            if not 'type' in depspec or not 'location' in depspec:
                raise ValueError("dependency SPEC '%s' contains no 'type' or no 'location' field"
                                 % dep_id)
            loc = depspec['location']
            type_ = depspec['type']
            if type_ == 'executable':
                if not (os.path.exists(os.path.expandvars(loc))
                        or not which(loc) is None):
                    self.skipTest("cannot find required executable '%s'" % loc)
            elif type_ == 'python_module':
                try:
                    _ = __import__(loc)
                except ImportError:
                    self.skipTest("cannot import required Python module '%s'" % loc)
            else:
                lgr.warning("not verifying unknown dependency type '%s'" % type_)

    def _prepare_environment(self, spec):
        # returns the relevant bits of the environment
        info = {}
        self._environ_restore = {}
        env_spec = spec.get('environment', {})
        for env in env_spec:
            # store the current value
            self._environ_restore[env] = os.environ.get(env, None)
            if env_spec[env] is None:
                # unset if null
                if env in os.environ:
                    del os.environ[env]
            elif isinstance(env_spec[env], basestring):
                # set if string
                # set the new one
                os.environ[env] = str(env_spec[env])
            elif env_spec[env] is True:
                # this variable is required to be present
                if not cfg.getboolean('testrun', 'fail on missing environment',
                                      default=False) \
                   and not env in os.environ:
                    self.skipTest("required environment variable '%s' not set"
                                  % env)
                else:
                    self.assertThat(os.environ, Contains(env))
            # grab envvar values if anyhow listed
            info[env] = os.environ.get(env, None)
        if not len(self._environ_restore):
            self._environ_restore = None
        return info

    def _restore_environment(self):
        if self._environ_restore is None:
            return
        for env, val in self._environ_restore.iteritems():
            if val is None:
                if env in os.environ:
                    del os.environ[env]
            else:
                os.environ[env] = str(val)
        self._environ_restore = None

    def _get_dep_info(self):
        info = {}
        self._details['dep_info'] = info
        if cfg.getboolean('testrun', 'skip dependency description',
                          default=False):
            return
        spec = self._cur_spec
        for dep_id, depspec in spec.get('dependencies', {}).iteritems():
            if not 'type' in depspec or not 'location' in depspec:
                raise ValueError("dependency SPEC '%s' contains no 'type' or no 'location' field"
                                 % dep_id)
            deptype = depspec['type']
            deploc = depspec['location']
            # TODO implement support for more dependency types
            if deptype == 'executable':
                dephash = describe_binary(deptype, deploc, info)
            elif deptype == 'python_module':
                from imp import find_module
                try:
                    mfile, mpath, mdescr = find_module(deploc.replace('.', '/'))
                except ImportError:
                    # swallow the error -- if it can't be imported the test was
                    # skipped anyway
                    continue
                if mfile is None:
                    # a package
                    mpath = opj(mpath, '__init__.py')
                dephash = describe_python_module(deptype, mpath, info)
            else:
                raise ValueError("unsupported dependency type '%s' in '%s'"
                                 % (deptype, dep_id))

            # check version information
            have_version = False
            if 'version_file' in depspec:
                verfilename = depspec['version_file']
                extract_regex = r'.*'
                if isinstance(verfilename, list):
                    verfilename, extract_regex = verfilename
                # expand the filename
                verfilename = os.path.realpath(os.path.expandvars(verfilename))
                try:
                    file_content = open(verfilename).read().strip()
                    version = re.findall(extract_regex, file_content)[0]
                    if len(version):
                        info[dephash]['version'] = version
                        have_version = True
                except:
                    lgr.debug("failed to read version from '%s'"
                              % verfilename)
            if not have_version and 'version_cmd' in depspec:
                vercmd = depspec['version_cmd']
                extract_regex = r'.*'
                if isinstance(vercmd, list):
                    vercmd, extract_regex = vercmd
                ret = run_command(vercmd)
                try:
                    # this will throw an exception if nothing is found
                    version = re.findall(extract_regex, '\n'.join(ret['stderr']))[0]
                    if len(version):
                        info[dephash]['version'] = version
                        have_version = True
                except:
                    try:
                        version = re.findall(extract_regex, '\n'.join(ret['stdout']))[0]
                        if len(version):
                            info[dephash]['version'] = version
                            have_version = True
                    except:
                        lgr.debug("failed to read version from '%s'" % vercmd)


    def _jds(self, content):
        return jds(content, indent=2, sort_keys=True, cls=SPECJSONEncoder)


def generate_testkraut_tests(search_dirs_, discover_dirs_):

    class TestKrautTests(TestFromSPEC):
        __metaclass__ = TemplateTestCase
        search_dirs = search_dirs_
        @template_case(discover_specs(discover_dirs_))
        def _run_spec_test(self, spec_filename):
            return TestFromSPEC._run_spec_test(self, spec_filename)

    return TestKrautTests

# The generator itself is not a test function, so please nose here
generate_testkraut_tests.__test__ = False
