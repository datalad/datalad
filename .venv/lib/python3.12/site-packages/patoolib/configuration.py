# Copyright (C) 2013-2023 Bastian Kleineidam
"""Define basic configuration data like version or application name."""

AppName: str = "patool"
Version: str = "4.1.0"
MyName: str = "Bastian Kleineidam"
MyEmail: str = "bastian.kleineidam@web.de"

App: str = AppName + " " + Version
Author: str = MyName
AuthorEmail: str = MyEmail
Copyright: str = "Copyright (C) 2004-2023 " + Author
Url: str = "https://github.com/wummel/patool"
SupportUrl: str = "https://github.com/wummel/patool/issues/"
License: str = "GPL-3"
Description: str = "portable archive file manager"
