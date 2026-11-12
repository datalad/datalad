# AnnexRemote - Helper module to easily develop git-annex remotes
#
# Copyright (C) 2017  Silvio Ankermann
#
# This program is free software: you can redistribute it and/or modify it under the terms of version 3 of the GNU
# General Public License as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be uselful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#

import logging

from abc import ABCMeta, abstractmethod

import sys, traceback


# Exceptions
class AnnexError(Exception):
    """
    Common base class for all annexremote exceptions.
    """


class ProtocolError(AnnexError):
    """
    Base class for protocol errors
    """


class UnsupportedRequest(ProtocolError):
    """
    Must be raised when an optional request is not supported by the remote.
    """


class UnexpectedMessage(ProtocolError):
    """
    Raised when git-annex sends a message which is not expected at the moment
    """


class RemoteError(AnnexError):
    """
    Must be raised by the remote when a request did not succeed.
    """


class NotLinkedError(AnnexError):
    """
    Will be raised when a Master instance is accessed without being
    linked to a SpecialRemote instance
    """


class AnnexLoggingHandler(logging.StreamHandler):
    """
    Stream Handler that sends log records to git annex via the special remote protocol
    """

    def __init__(self, annex):
        super().__init__()
        self.annex = annex
        self.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))

    def emit(self, record: logging.LogRecord):
        log_entry = self.format(record)
        for line in log_entry.splitlines():
            self.annex.debug(line)


class SpecialRemote(metaclass=ABCMeta):
    """
    Metaclass for non-export remotes.

    ...

    Attributes
    ----------
    annex : Master
        The Master object to which this remote is linked. Master acts as an abstraction layer for git-annex.
    info : dict
        Contains information describing the configuration of the remote, for display by `git annex info` in
        the form of {'Name': 'Value', ...} where both can be anything you want to be displayed to the user.
        Note: Both Name and Value *can* contain spaces.
    configs : dict
        Contains the settings which the remote uses (with getconfig() and setconfig()) in the form of
        {'Name': 'Description', ...}
        Note: Name *must not* contain spaces. Description should be reasonably short.
        Example: {'directory': "store data here"}
        Providing them makes `git annex initremote` work better, because it can check the user's input,
        and can also display a list of settings with descriptions.
        Note that the user is not required to provided all the settings listed here.
    """

    def __init__(self, annex):
        self.annex = annex
        self.info = {}
        self.configs = {}

    @abstractmethod
    def initremote(self):
        """
        Gets called when `git annex initremote` or `git annex enableremote` are run.
        This is where any one-time setup tasks can be done, for example creating the remote folder.
        Note: This may be run repeatedly over time, as a remote is initialized in different repositories,
        or as the configuration of a remote is changed. So any one-time setup tasks should be done idempotently.

        Raises
        ------
        RemoteError
            If the remote could not be initialized.
        """

    @abstractmethod
    def prepare(self):
        """
        Tells the remote that it's time to prepare itself to be used.
        Gets called whenever git annex is about to access any of the below
        methods, so it shouldn't be too expensive. Otherwise it will
        slow down operations like `git annex whereis` or `git annex info`.

        Internet connection *can* be established here, though it's
        recommended to defer this until it's actually needed.

        Raises
        ------
        RemoteError
            If the remote could not be prepared.
        """

    @abstractmethod
    def transfer_store(self, key, local_file):
        """
        Store the file in `local_file` to a unique location derived from `key`.

        It's important that, while a Key is being stored, checkpresent(key)
        not indicate it's present until all the data has been transferred.
        While the transfer is running, the remote can repeatedly call
        annex.progress(size) to indicate the number of bytes already stored.
        This will influence the progress shown to the user.

        Parameters
        ----------
        key : str
            The Key to be stored in the remote. In most cases, this is going to be the
            remote file name. It should be at least be unambiguously derived from it.
        local_file: str
            Path to the file to upload.
            Note that in some cases, local_file may contain whitespace.
            Note that local_file should not influence the filename used on the remote.

        Raises
        ------
        RemoteError
            If the file could not be stored to the remote.
        """

    @abstractmethod
    def transfer_retrieve(self, key, local_file):
        """
        Get the file identified by `key` from the remote and store it in `local_file`.

        While the transfer is running, the remote can repeatedly call
        annex.progress(size) to indicate the number of bytes already stored.
        This will influence the progress shown to the user.

        Parameters
        ----------
        key : str
            The Key to get from the remote.
        local_file: str
            Path where to store the file.
            Note that in some cases, local_file may contain whitespace.

        Raises
        ------
        RemoteError
            If the file could not be received from the remote.
        """

    @abstractmethod
    def checkpresent(self, key):
        """
        Requests the remote to check if a key is present in it.

        Parameters
        ----------
        key : str

        Returns
        -------
        bool
            True if the key is present in the remote.
            False if the key is not present.

        Raises
        ------
        RemoteError
            If the presence of the key couldn't be determined, eg. in case of connection error.

        """

    @abstractmethod
    def remove(self, key):
        """
        Requests the remote to remove a key's contents.

        Parameters
        ----------
        key : str

        Raises
        ------
        RemoteError
            If the key couldn't be deleted from the remote.
        """

    # Optional requests
    def listconfigs(self):
        # TODO (v2.0) remove
        return self.configs

    def getcost(self):
        """
        Requests the remote to return a use cost. Higher costs are more expensive.

        cheapRemoteCost = 100
        nearlyCheapRemoteCost = 110
        semiExpensiveRemoteCost = 175
        expensiveRemoteCost = 200
        veryExpensiveRemoteCost = 1000
        (taken from Config/Cost.hs)

        Returns
        -------
        int
            Indicates the cost of the remote.
        """
        raise UnsupportedRequest()

    def getavailability(self):
        """
        Asks the remote if it is locally or globally available. (Ie stored in the cloud vs on a local disk.)

        Returns
        -------
        str
            Allowed values are "global" or "local".

        """
        raise UnsupportedRequest()

    def claimurl(self, url):
        """
        Asks the remote if it wishes to claim responsibility for downloading an url.


        Parameters
        ----------
        url : str

        Returns
        -------
        bool
            True if it wants to claim this url.
            False if it doesn't.

        """
        raise UnsupportedRequest()

    def checkurl(self, url):
        """
        Asks the remote to check if the url's content can currently be downloaded (without downloading it).
        The remote can optionally provide additional information about the file.

        Parameters
        ----------
        url : str

        Returns
        -------
        Union(bool, List(Dict))
            True if the url's content can currently be downloaded and no additional information can be provided.
            False if it can't currently be downloaded.

            In order to provide additional information, a list of dictionaries can be returned.
            The dictionaries can have 3 keys: {'url': str, 'size': int, 'filename': str}. All of them are optional.

            If there is only one file to be downloaded, we could return:
            [{'size': 512, 'filename':'example_file.txt'}]

            Other examples:
            {'url':"https://example.com", 'size':512, 'filename':"example_file.txt"}
            [{'url':"Url1", 'size':512, 'filename':"Filename1"}, {'url':"Url2", 'filename':"Filename2"}]



        """
        raise UnsupportedRequest()

    def whereis(self, key):
        """
        Asks the remote to provide additional information about ways to access the
        content of a key stored in it, such as eg, public urls. This will be displayed
        to the user by eg, git annex whereis.
        Note that users expect git annex whereis to run fast, without eg, network access.

        Parameters
        ----------
        key : str

        Returns
        -------
        str
            Information about the location of the key, eg. public urls.

        """
        raise UnsupportedRequest()

    def error(self, error_msg):
        """
        Generic error. Can be sent at any time if things get too messed up to continue.
        If the program receives an error() from git-annex, it can exit with its own error().
        Eg.:
            self.annex.error("Error received. Exiting.")
            raise SystemExit

        Parameters
        ----------
        error_msg : str
            The error message received from git-annex
        """
        self.annex.error("Error received. Exiting.")
        raise SystemExit

    # Export methods
    def exportsupported(self):
        return False

    def transferexport_store(self, key, local_file, remote_file):
        raise UnsupportedRequest()

    def transferexport_retrieve(self, key, local_file, remote_file):
        raise UnsupportedRequest()

    def checkpresentexport(self, key, remote_file):
        raise UnsupportedRequest()

    def removeexport(self, key, remote_file):
        raise UnsupportedRequest()

    def removeexportdirectory(self, remote_directory):
        raise UnsupportedRequest()

    def renameexport(self, key, filename, new_filename):
        raise UnsupportedRequest()

    # Setup function to be run before initremote to handle things like authentication interactively
    def setup(self):
        print(
            "Nothing to do. Just run 'git annex initremote' with your desired parameters"
        )


class ExportRemote(SpecialRemote):
    """
    Metaclass for remotes that support non-export *and* export behaviour.

    ...

    Attributes
    ----------
    annex : Master
        The Master object to which this remote is linked. Master acts as an abstraction layer for git-annex.
    info : dict
        Contains information describing the configuration of the remote, for display by `git annex info` in
        the form of {'Name': 'Value', ...} where both can be anything you want to be displayed to the user.
        Note: Both Name and Value *can* contain spaces.
    configs : dict
        Contains the settings which the remote uses (with getconfig() and setconfig()) in the form of
        {'Name': 'Description', ...}
        Note: Name *must not* contain spaces. Description should be reasonably short.
        Example: {'directory': "store data here"}
        Providing them makes `git annex initremote` work better, because it can check the user's input,
        and can also display a list of settings with descriptions.
        Note that the user is not required to provided all the settings listed here.
    """

    def exportsupported(self):
        return True

    @abstractmethod
    def transferexport_store(self, key, local_file, remote_file):
        """
        Requests the transfer of a file on local disk to the special remote.
        Note that it's important that, while a file is being stored,
        checkpresentexport() not indicate it's present until all the data
        has been transferred.
        While the transfer is running, the remote can send any number of progress(size) messages.


        Parameters
        ----------
        key : str
            The Key to be stored in the remote.
        local_file: str
            Path to the file to upload.
            Note that in some cases, local_file may contain whitespace.
        remote_file : str
            The path to the location to which the file will be uploaded.
            It will be in the form of a relative path, and may contain
            path separators, whitespace, and other special characters.

        Raises
        ------
        RemoteError
            If the key couldn't be stored on the remote.
        """

    @abstractmethod
    def transferexport_retrieve(self, key, local_file, remote_file):
        """
        Requests the transfer of a file from the special remote to the local disk.
        Note that it's important that, while a file is being stored,
        checkpresentexport() not indicate it's present until all the data
        has been transferred.
        While the transfer is running, the remote can send any number of progress(size) messages.


        Parameters
        ----------
        key : str
            The Key to get from the remote.
        local_file: str
            Path where to store the file.
            Note that in some cases, local_file may contain whitespace.
        remote_file : str
            The remote path of the file to download.
            It will be in the form of a relative path, and may contain
            path separators, whitespace, and other special characters.

        Raises
        ------
        RemoteError
            If the key couldn't be stored on the remote.
        """

    @abstractmethod
    def checkpresentexport(self, key, remote_file):
        """
        Requests the remote to check if the file is present in it.

        Parameters
        ----------
        key : str
            The key of the file to check.
        remote_file : str
            The remote path of the file to check.

        Returns
        -------
        bool
            True if the file is present in the remote.
            False if the file is not present in the remote

        Raises
        ------
        RemoteError
            If the the presence of the key couldn't be determined.
        """

    @abstractmethod
    def removeexport(self, key, remote_file):
        """
        Requests the remote to remove content stored by transferexportstore().

        Parameters
        ----------
        key : str
            The key of the file to check.
        remote_file : str
            The remote path of the file to delete.

        Raises
        ------
        RemoteError
            If the the remote file couldn't be deleted.
        """

    def removeexportdirectory(self, remote_directory):
        """
        Requests the remote to remove an exported directory.
        If the remote does not use directories, or removeexport() cleans
        up directories that are empty, this does not need to be implemented.

        Parameters
        ----------
        remote_directory : str
            The remote path to the directory to delete.
            The directory will be in the form of a relative path,
            and may contain path separators, whitespace, and other special characters.
            Typically the directory will be empty, but it could possibly contain
            files or other directories, and it's ok to remove those,
            but not required to do so.

        Raises
        ------
        RemoteError
            If the the remote directory couldn't be deleted.
        """
        raise UnsupportedRequest()

    def renameexport(self, key, filename, new_filename):
        """
        Requests the remote rename a file stored on it from `filename` to `new_filename`.
        Remotes that support exports but not renaming do not need to implement this.

        Parameters
        ----------
        key : str
            The key of the file to rename
        filename : str
            The old path to the file.
        new_filename : str
            The new path to the file.

        Raises
        ------
        RemoteError
            If the the remote directory couldn't be deleted.
        """
        raise UnsupportedRequest()


class Protocol(object):
    """
    Helper class handling the receiving part of the protocol (git-annex to remote)
    It parses the requests coming from git-annex and calls the respective
    method of the remote object.

    It is not further documented as it was never intended to be part of the public API.
    """

    def __init__(self, remote):
        self.remote = remote
        self.version = "VERSION 1"
        self.exporting = False
        self.extensions = list()

    def command(self, line):
        line = line.strip()
        parts = line.split(" ", 1)
        if not parts:
            raise ProtocolError("Got empty line")

        method = self.lookupMethod(parts[0]) or self.do_UNKNOWN

        try:
            if len(parts) == 1:
                reply = method()
            else:
                reply = method(parts[1])
        except TypeError as e:
            raise SyntaxError(e)
        else:
            if method != self.do_EXPORT:
                self.exporting = False
            return reply

    def lookupMethod(self, command):
        return getattr(self, "do_" + command.upper(), None)

    def check_key(self, key):
        if len(key.split()) != 1:
            raise ValueError("Invalid key. Key contains whitespace character")

    def do_UNKNOWN(self, *arg):
        raise UnsupportedRequest()

    def do_INITREMOTE(self):
        try:
            self.remote.initremote()
        except RemoteError as e:
            return "INITREMOTE-FAILURE {e}".format(e=e)
        else:
            return "INITREMOTE-SUCCESS"

    def do_EXTENSIONS(self, param):
        self.extensions = param.split(" ")
        return "EXTENSIONS"

    def do_PREPARE(self):
        try:
            self.remote.prepare()
        except RemoteError as e:
            return "PREPARE-FAILURE {e}".format(e=e)
        else:
            return "PREPARE-SUCCESS"

    def do_TRANSFER(self, param):
        try:
            (method, key, file_) = param.split(" ", 2)
        except ValueError:
            raise SyntaxError("Expected Key File")

        if not (method == "STORE" or method == "RETRIEVE"):
            return self.do_UNKNOWN()

        func = getattr(self.remote, "transfer_{}".format(method.lower()), None)
        try:
            func(key, file_)
        except RemoteError as e:
            return "TRANSFER-FAILURE {method} {key} {e}".format(
                method=method, key=key, e=e
            )
        else:
            return "TRANSFER-SUCCESS {method} {key}".format(method=method, key=key)

    def do_CHECKPRESENT(self, key):
        self.check_key(key)
        try:
            if self.remote.checkpresent(key):
                return "CHECKPRESENT-SUCCESS {key}".format(key=key)
            else:
                return "CHECKPRESENT-FAILURE {key}".format(key=key)
        except RemoteError as e:
            return "CHECKPRESENT-UNKNOWN {key} {e}".format(key=key, e=e)

    def do_REMOVE(self, key):
        self.check_key(key)

        try:
            self.remote.remove(key)
        except RemoteError as e:
            return "REMOVE-FAILURE {key} {e}".format(key=key, e=e)
        else:
            return "REMOVE-SUCCESS {key}".format(key=key)

    def do_LISTCONFIGS(self):
        reply = []
        for name, description in sorted(self.remote.listconfigs().items()):
            if " " in name:
                raise ValueError(
                    "Name must not contain space characters: {}".format(name)
                )
            reply.append("CONFIG {} {}".format(name, description))
        reply.append("CONFIGEND")
        return "\n".join(reply)

    def do_GETCOST(self):
        cost = self.remote.getcost()
        try:
            cost = int(cost)
        except ValueError:
            raise ValueError("Cost must be an integer")
        return "COST {cost}".format(cost=cost)

    def do_GETAVAILABILITY(self):
        reply = self.remote.getavailability()
        if reply == "global":
            return "AVAILABILITY GLOBAL"
        elif reply == "local":
            return "AVAILABILITY LOCAL"
        else:
            raise ValueError("Availability must be either 'global' or 'local'")

    def do_CLAIMURL(self, url):
        if self.remote.claimurl(url):
            return "CLAIMURL-SUCCESS"
        else:
            return "CLAIMURL-FAILURE"

    def do_CHECKURL(self, url):
        try:
            reply = self.remote.checkurl(url)
        except RemoteError as e:
            return "CHECKURL-FAILURE {e}".format(e=e).rstrip()
        if not reply:
            return "CHECKURL-FAILURE"
        elif reply is True:
            return "CHECKURL-CONTENTS UNKNOWN"

        if len(reply) == 1 and "url" not in reply[0]:
            entry = reply[0]
            size = entry.get("size", "UNKNOWN")

            returnvalue = " ".join(("CHECKURL-CONTENTS", str(size)))

            if "filename" in entry and entry["filename"]:
                returnvalue = " ".join((returnvalue, entry["filename"]))
            return returnvalue

        returnvalue = "CHECKURL-MULTI"
        for entry in reply:
            if "url" not in entry:
                raise ValueError("Url must be present when specifying multiple values.")
            if " " in entry["url"]:
                raise ValueError("Url must not contain spaces.")

            size = entry.get("size", "UNKNOWN")
            filename = entry.get("filename", "")
            if " " in filename:
                raise ValueError("Filename must not contain spaces.")

            returnvalue = " ".join((returnvalue, entry["url"], str(size), filename))
        return returnvalue

    def do_WHEREIS(self, key):
        self.check_key(key)
        reply = self.remote.whereis(key)
        if reply:
            return "WHEREIS-SUCCESS {reply}".format(reply=reply)
        else:
            return "WHEREIS-FAILURE"

    def do_GETINFO(self):
        info = self.remote.info
        reply = []
        for field in sorted(info):
            reply.append("INFOFIELD {}".format(field))
            reply.append("INFOVALUE {}".format(info[field]))
        reply.append("INFOEND")
        return "\n".join(reply)

    def do_ERROR(self, message):
        self.remote.error(message)

    def do_EXPORTSUPPORTED(self):
        if self.remote.exportsupported():
            return "EXPORTSUPPORTED-SUCCESS"
        else:
            return "EXPORTSUPPORTED-FAILURE"

    def do_EXPORT(self, name):
        self.exporting = name

    def do_TRANSFEREXPORT(self, param):
        if not self.exporting:
            raise ProtocolError("Export request without prior EXPORT")
        try:
            (method, key, file_) = param.split(" ", 2)
        except ValueError:
            raise SyntaxError("Expected Key File")

        if not (method == "STORE" or method == "RETRIEVE"):
            return self.do_UNKNOWN()

        func = getattr(self.remote, "transferexport_{}".format(method.lower()), None)
        try:
            func(key, file_, self.exporting)
        except RemoteError as e:
            return "TRANSFER-FAILURE {method} {key} {e}".format(
                method=method, key=key, e=e
            )
        else:
            return "TRANSFER-SUCCESS {method} {key}".format(method=method, key=key)

    def do_CHECKPRESENTEXPORT(self, key):
        if not self.exporting:
            raise ProtocolError("Export request without prior EXPORT")
        self.check_key(key)
        try:
            if self.remote.checkpresentexport(key, self.exporting):
                return "CHECKPRESENT-SUCCESS {key}".format(key=key)
            else:
                return "CHECKPRESENT-FAILURE {key}".format(key=key)
        except RemoteError as e:
            return "CHECKPRESENT-UNKNOWN {key} {e}".format(key=key, e=e)

    def do_REMOVEEXPORT(self, key):
        if not self.exporting:
            raise ProtocolError("Export request without prior EXPORT")
        self.check_key(key)

        try:
            self.remote.removeexport(key, self.exporting)
        except RemoteError as e:
            return "REMOVE-FAILURE {key} {e}".format(key=key, e=e)
        else:
            return "REMOVE-SUCCESS {key}".format(key=key)

    def do_REMOVEEXPORTDIRECTORY(self, name):
        try:
            self.remote.removeexportdirectory(name)
        except RemoteError:
            return "REMOVEEXPORTDIRECTORY-FAILURE"
        else:
            return "REMOVEEXPORTDIRECTORY-SUCCESS"

    def do_RENAMEEXPORT(self, param):
        if not self.exporting:
            raise ProtocolError("Export request without prior EXPORT")
        try:
            (key, new_name) = param.split(None, 1)
        except ValueError:
            raise SyntaxError("Expected TRANSFER STORE Key File")

        try:
            self.remote.renameexport(key, self.exporting, new_name)
        except RemoteError:
            return "RENAMEEXPORT-FAILURE {key}".format(key=key)
        else:
            return "RENAMEEXPORT-SUCCESS {key}".format(key=key)


class Master(object):
    """
    Metaclass for non-export remotes.

    ...

    Attributes
    ----------
    input : io.TextIOBase
        Where to listen for git-annex request messages.
        Default: sys.stdin
    output : io.TextIOBase
        Where to send replies and special remote messages
        Default: sys.stdout
    remote : SpecialRemote
        A class implementing either the SpecialRemote or the
        ExternalSpecialRemote interface to which this master is linked.
    """

    def __init__(self, output=sys.stdout):
        """
        Initialize the Master with an output.

        Parameters
        ----------
        output : io.TextIOBase
            Where to send replies and special remote messages
            Default: sys.stdout
        """
        self.output = output

    def LinkRemote(self, remote):
        """
        Link the Master to a remote. This must be done before calling Listen()

        Parameters
        ----------
        remote : SpecialRemote
            A class implementing either the SpecialRemote or the
            ExternalSpecialRemote interface to which this master will be linked.
        """
        self.remote = remote
        self.protocol = Protocol(remote)

    def LoggingHandler(self):
        """
        Gets an instance of AnnexLoggingHandler

        Returns
        -------
        AnnexLoggingHandler
        """
        return AnnexLoggingHandler(self)

    def Listen(self, input=sys.stdin):
        """
        Listen on `input` for messages from git annex.

        Parameters
        ----------
        input : io.TextIOBase
            Where to listen for git-annex request messages.
            Default: sys.stdin

        Raises
        ----------
        NotLinkedError
            If there is no remote linked to this master.
        """
        if not (hasattr(self, "remote") and hasattr(self, "protocol")):
            raise NotLinkedError("Please execute LinkRemote(remote) first.")

        self.input = input
        self._send(self.protocol.version)
        while True:
            # due to a bug in python 2 we can't use an iterator here: https://bugs.python.org/issue1633941
            line = self.input.readline()
            if not line:
                break
            line = line.rstrip()
            try:
                reply = self.protocol.command(line)
                if reply:
                    self._send(reply)
            except UnsupportedRequest:
                self._send("UNSUPPORTED-REQUEST")
            except Exception as e:
                for line in traceback.format_exc().splitlines():
                    self.debug(line)
                self.error(e)
                raise SystemExit

    def _ask(self, request, reply_keyword, reply_count):
        self._send(request)
        line = self.input.readline().rstrip().split(" ", reply_count)
        if line and line[0] == reply_keyword:
            line.extend([""] * (reply_count + 1 - len(line)))
            return line[1:]
        else:
            raise UnexpectedMessage(
                "Expected {reply_keyword} and {reply_count} values. Got {line}".format(
                    reply_keyword=reply_keyword, reply_count=reply_count, line=line
                )
            )

    def _askvalues(self, request):
        self._send(request)
        reply = []
        while True:
            # due to a bug in python 2 we can't use an iterator here: https://bugs.python.org/issue1633941
            line = self.input.readline()
            line = line.rstrip()
            line = line.split(" ", 1)
            if len(line) == 2 and line[0] == "VALUE":
                reply.append(line[1])
            elif len(line) == 1 and line[0] == "VALUE":
                return reply
            else:
                raise UnexpectedMessage("Expected VALUE {value}")

    def _askvalue(self, request):
        (reply,) = self._ask(request, "VALUE", 1)
        return reply

    def getconfig(self, setting):
        """
        Gets one of the special remote's configuration settings,
        which can have been passed by the user when running `git annex initremote`,
        `git annex enableremote` or can have been set by a previous setconfig(). Can be run at any time.
        It's recommended that special remotes that use this implement listconfigs().

        Parameters
        ----------
        setting : str
            Which setting to get

        Returns
        -------
        str
            The requested setting. If the setting is not set, the value will an empty string.

        Raises
        ----------
        UnexpectedMessage
            If git-annex does not respond correctly to this request, which is very unlikely.
        """
        return self._askvalue("GETCONFIG {}".format(setting))

    def setconfig(self, setting, value):
        """
        Sets one of the special remote's configuration settings.
        Normally this is sent during initremote(), which allows these settings to be
        stored in the git-annex branch, so will be available if the same special remote
        is used elsewhere. (If sent after initremote(), the changed configuration will
        only be available while the remote is running.)

        Parameters
        ----------
        setting : str
            The name of the setting
        value : str
            The value of the setting
        """
        self._send("SETCONFIG {} {}".format(setting, value))

    def getstate(self, key):
        """
        Gets any state that has been stored for the key via setstate().

        Parameters
        ----------
        key : str
            The key for which to get the state

        Returns
        -------
        str
            The requested state. If the state is not set, the value will an empty string.

        Raises
        ----------
        UnexpectedMessage
            If git-annex does not respond correctly to this request, which is very unlikely.
        """
        return self._askvalue("GETSTATE {key}".format(key=key))

    def setstate(self, key, value):
        """
        Can be used to store some form of state for a Key. The state stored can be anything
        this remote needs to store, in any format. It is stored in the git-annex branch.
        Note that this means that if multiple repositories are using the same special
        remote, and store different state, whichever one stored the state last will win.
        Also, it's best to avoid storing much state, since this will bloat the git-annex
        branch. Most remotes will not need to store any state.

        Parameters
        ----------
        key : str
            The key for which to store the state
        value : str
            The state for the key to store
        """
        self._send("SETSTATE {key} {value}".format(key=key, value=value))

    def debug(self, *args):
        """
        Tells git-annex to display the message if --debug is enabled.

        Parameters
        ----------
        message : str
            The message to be displayed to the user
        """

        self._send("DEBUG", *args)

    def error(self, *args):
        """
        Generic error. Can be sent at any time if things get too messed up to continue.
        When possible, raise a RemoteError inside the respective functions.
        The special remote program should exit after sending this, as git-annex will
        not talk to it any further.

        Parameters
        ----------
        error_msg : str
            The error message to be sent to git-annex
        """
        self._send("ERROR", *args)

    def progress(self, progress):
        """
        Indicates the current progress of the transfer (in bytes). May be repeated
        any number of times during the transfer process, but it's wasteful to update
        the progress until at least another 1% of the file has been sent.
        This is highly recommended for *_store(). (It is optional but good for *_retrieve().)

        Parameters
        ----------
        progress : int
            The current progress of the transfer in bytes.
        """
        self._send("PROGRESS {progress}".format(progress=int(progress)))

    def dirhash(self, key):
        """
        Gets a two level hash associated with a Key. Something like "aB/Cd".
        This is always the same for any given Key, so can be used for eg,
        creating hash directory structures to store Keys in. This is the
        same directory hash that git-annex uses inside .git/annex/objects/

        Parameters
        ----------
        key : str
            The key for which to get the hash

        Returns
        -------
        str
            The two level hash. (eg. "aB/Cd")

        Raises
        ----------
        UnexpectedMessage
            If git-annex does not respond correctly to this request, which is very unlikely.
        """
        return self._askvalue("DIRHASH {key}".format(key=key))

    def dirhash_lower(self, key):
        """
        Gets a two level hash associated with a Key, using only lower-case.
        Something like "abc/def".
        This is always the same for any given Key, so can be used for eg,
        creating hash directory structures to store Keys in. This is the
        same directory hash that is used by eg, the directory special remote.

        Parameters
        ----------
        key : str
            The key for which to get the hash

        Returns
        -------
        str
            The two level hash. (eg. "abc/def")

        Raises
        ----------
        UnexpectedMessage
            If git-annex does not respond correctly to this request, which is very unlikely.
        """
        return self._askvalue("DIRHASH-LOWER {key}".format(key=key))

    def setcreds(self, setting, user, password):
        """
        When some form of user and password is needed to access a special
        remote, this can be used to securely store them for later use.
        (Like setconfig(), this is normally sent only during initremote().)
        Note that creds are normally only stored in the remote's
        configuration when it's surely safe to do so; when gpg encryption
        is used, in which case the creds will be encrypted using it.
        If creds are not stored in the configuration, they'll only be stored
        in a local file. (embedcreds can be set to yes by the user or by
        setconfig() to force the creds to be stored in the remote's configuration).

        Parameters
        ----------
        setting : str
            Indicates which value in a remote's configuration
            can be used to store the creds.
        user : str
            The username to be stored
        password : str
            The password to be stored
        """
        self._send("SETCREDS", setting, user, password)

    def getcreds(self, setting):
        """
        Gets any creds that were previously stored in the remote's
        configuration or a file.

        Parameters
        ----------
        setting : str
            Indicates which value in a remote's configuration
            where the credentials are stored.

        Returns
        ----------
        dict of str : str
            A dict containing username of password in the form:
            {'user': "username", 'password': "password"}
            If there are no credentials found, both 'user' and 'password' are empty.
            Note: In version 2.0, a named tuple will be used instead of a dict.

        Raises
        ----------
        UnexpectedMessage
            If git-annex does not respond correctly to this request, which is very unlikely.
        """
        (user, password) = self._ask(
            "GETCREDS {setting}".format(setting=setting), "CREDS", 2
        )
        # TODO: (v2.0) use namedtuple instead of dict
        return {"user": user, "password": password}

    def getuuid(self):
        """
        Queries for the UUID of the special remote being used.

        Returns
        ----------
        str
            The UUID of the special remote

        """
        return self._askvalue("GETUUID")

    def getgitdir(self):
        """
        Queries for the path to the git directory of the repository that
        is using the external special remote.

        Returns
        ----------
        str
            The (relative) path to the git directory
        """

        return self._askvalue("GETGITDIR")

    def setwanted(self, prefcontent):
        """
        Can be used to set the preferred content of a repository. Normally
        this is not configured by a special remote, but it may make sense
        in some situations to hint at the kind of content that should be
        stored in the special remote.
        Note that if an unparsable expression is set, git-annex will ignore it.

        Parameters
        ----------
        prefcontent : str
            The PreferredContentExpression,
            see https://git-annex.branchable.com/git-annex-preferred-content/
        """
        self._send("SETWANTED", prefcontent)

    def getwanted(self):
        """
        Gets the current preferred content setting of the repository.

        Returns
        ----------
        str
            The PreferredContentExpression,
            see https://git-annex.branchable.com/git-annex-preferred-content/

        Raises
        ----------
        UnexpectedMessage
            If git-annex does not respond correctly to this request, which is very unlikely.
        """
        return self._askvalue("GETWANTED")

    def seturlpresent(self, key, url):
        """
        Records a URL where the Key can be downloaded from.
        Note that this does not make git-annex think that the url is present
        on the web special remote.
        Keep in mind that this stores the url in the git-annex branch. This
        can result in bloat to the branch if the url is large and/or does not
        delta pack well with other information (such as the names of keys)
        already stored in the branch.

        Parameters
        ----------
        key : str
            The key for which to record a URL
        url : str
            The URL from which the key can be downloaded
        """
        self._send("SETURLPRESENT", key, url)

    def seturlmissing(self, key, url):
        """
        Records that the key can no longer be downloaded from the specified URL.

        Parameters
        ----------
        key : str
            The key for which to delete the URL
        url : str
            The URL which is no longer accessible
        """
        self._send("SETURLMISSING", key, url)

    def seturipresent(self, key, uri):
        """
        Records a URI where the Key can be downloaded from.
        For example, "ipfs:ADDRESS" is used for the ipfs special remote;
        its CLAIMURL handler checks for such URIS and claims them.

        Parameters
        ----------
        key : str
            The key for which to record a URI
        uri : str
            The URI from which the key can be downloaded
        """
        self._send("SETURIPRESENT", key, uri)

    def seturimissing(self, key, uri):
        """
        Records that the key can no longer be downloaded from the specified URI.

        Parameters
        ----------
        key : str
            The key for which to delete the URI
        uri : str
            The URI which is no longer accessible
        """
        self._send("SETURIMISSING", key, uri)

    def geturls(self, key, prefix):
        """
        Gets the recorded URLs where a key can be downloaded from.

        Parameters
        ----------
        key : str
            The key for which to get the URLs
        prefix : str
            Only urls that start with the prefix will be returned.
            The Prefix may be empty to get all urls.

        Returns
        ----------
        list of str
            The URLs from which the key can be downloaded

        Raises
        ----------
        UnexpectedMessage
            If git-annex does not respond correctly to this request, which is very unlikely.
        """
        return self._askvalues("GETURLS {key} {prefix}".format(key=key, prefix=prefix))

    def info(self, message):
        """
        Tells git-annex to display the message to the user.
        When git-annex is in --json mode, the message will be emitted immediately
        in its own json object, with an "info" field.

        Important: This is a protocol extension and may raise a ProtocolError if
        the particular version of git-annex does not support it. Remotes using info()
        should always prepare to handle the exception.

        Parameters
        ----------
        message : str
            The message to be displayed to the user

        Raises
        ----------
        ProtocolError
            If INFO is not available in this version of git-annex.
        """
        if "INFO" in self.protocol.extensions:
            self._send("INFO", message)
        else:
            raise ProtocolError("INFO not available")

    def getgitremotename(self):
        """
        Gets the name of the git remote that represents this special remote.
        This can be used, for example, to look up git configuration belonging to that
        git remote. This name will often be the same as what is passed to git-annex
        initremote and enableremote, but it is possible for git remotes to be renamed,
        and this will provide the remote's current name.

        Important: This is a protocol extension and may raise a ProtocolError if
        the particular version of git-annex does not support it. Remotes using
        getgetremotename() should always prepare to handle the exception.

        Returns
        ----------
        str
            The name of the git remote that represents this special remote

        Raises
        ----------
        ProtocolError
            If GETGITREMOTENAME is not available in this version of git-annex.
        """
        if "GETGITREMOTENAME" in self.protocol.extensions:
            return self._askvalue("GETGITREMOTENAME")
        else:
            raise ProtocolError("GETGITREMOTENAME not available")

    def _send(self, *args, **kwargs):
        print(*args, file=self.output, **kwargs)
        self.output.flush()
