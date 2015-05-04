# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" Protocolling  command calls.
"""

from os import linesep


class ProtocolInterface(object):
    """Interface class for protocols used by the Runner.
    """

    def __init__(self):
        pass

    def write_section(self, cmd, time, exception):
        """Adds a section to the protocol.

        Parameters:
        -----------
        cmd: list
          The actual command and its options/arguments as a list
        time:
          Execution time of the command in seconds.
        exception: Exception
          The exception raised by the command if any or None otherwise.
        """
        pass

    def write_ext_commands(self):
        """Indicates whether or not the protocol is supposed to include
        external command calls.

        Returns:
        --------
        bool
        """
        pass

    def write_callables(self):
        """Indicates whether or not the protocol is supposed to include
        calls of python callables.

        Returns:
        --------
        bool
        """
        pass

    def do_execute(self):
        """Indicates whether or not the called commands are
        supposed to actually be executed.

        Returns:
        --------
        bool
        """
        pass

    def get_protocol(self):
        """Get the current state of the protocol.

        Returns:
        --------
        str
        """
        pass


class NoProtocol(ProtocolInterface):
    """Don't protocol anything.
    Provides default value for the Runner.
    TODO: Better name?
    """

    def __init__(self):
        super(NoProtocol, self).__init__()

    def write_section(self, cmd, time, exception):
        pass

    def write_ext_commands(self):
        return False

    def write_callables(self):
        return False

    def do_execute(self):
        return True

    def get_protocol(self):
        return "No protocol available."


class DryRunProtocol(ProtocolInterface):
    """Implementation of ProtocolInterface for dry runs.
    """
    def __init__(self):
        super(DryRunProtocol, self).__init__()
        self._protocol = "DRY RUNS:" + linesep

    def write_section(self, cmd, time, exception):
        self._protocol += ' '.join(cmd) + linesep

    def write_ext_commands(self):
        return True

    def write_callables(self):
        return True

    def do_execute(self):
        return False

    def get_protocol(self):
        return self._protocol


class ExecutionTimeProtocol(ProtocolInterface):

    def __init__(self):
        super(ExecutionTimeProtocol, self).__init__()
        self._protocol = "Execution time protocol:" + linesep

    def write_section(self, cmd, time, exception):
        self._protocol += "Command: " + ' '.join(cmd) + linesep
        self._protocol += "Execution time: " + str(time) + linesep
        if exception:
            self._protocol += "Exception (%s): %s" % \
                              (type(exception), exception) + linesep

    def write_ext_commands(self):
        return True

    def write_callables(self):
        return True

    def do_execute(self):
        return True

    def get_protocol(self):
        return self._protocol