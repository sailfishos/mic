# This file is part of mic
#
# Copyright (c) 2008, 2009, 2010 Intel, Inc.
# Copyright (c) 2020 Jolla Ltd.
# Copyright (c) 2020 Open Mobile Platform LLC.
#
# Yi Yang <yi.y.yang@intel.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; version 2 of the License
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc., 59
# Temple Place - Suite 330, Boston, MA 02111-1307, USA.

from pykickstart.commands.repo import F8_RepoData, F8_Repo
from pykickstart.version import F8

class Moblin_RepoData(F8_RepoData):
    def __init__(self, baseurl="", mirrorlist="", name="", priority=None,
                 includepkgs=[], excludepkgs=[], save=False, proxy=None,
                 proxy_username=None, proxy_password=None, debuginfo=False,
                 source=False, gpgkey=None, disable=False, ssl_verify="yes"):
        F8_RepoData.__init__(self, baseurl=baseurl, mirrorlist=mirrorlist,
                             name=name,  includepkgs=includepkgs,
                             excludepkgs=excludepkgs)
        self.save = save
        self.proxy = proxy
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.debuginfo = debuginfo
        self.disable = disable
        self.source = source
        self.gpgkey = gpgkey
        self.ssl_verify = ssl_verify.lower()
        self.priority = priority

    def _getArgsAsStr(self):
        retval = F8_RepoData._getArgsAsStr(self)

        if self.save:
            retval += " --save"
        if self.proxy:
            retval += " --proxy=%s" % self.proxy
        if self.proxy_username:
            retval += " --proxyuser=%s" % self.proxy_username
        if self.proxy_password:
            retval += " --proxypasswd=%s" % self.proxy_password
        if self.debuginfo:
            retval += " --debuginfo"
        if self.source:
            retval += " --source"
        if self.gpgkey:
            retval += " --gpgkey=%s" % self.gpgkey
        if self.disable:
            retval += " --disable"
        if self.ssl_verify:
            retval += " --ssl_verify=%s" % self.ssl_verify
        if self.priority:
            retval += " --priority=%s" % self.priority

        return retval

class Moblin_Repo(F8_Repo):
    def __init__(self, writePriority=0, repoList=None):
        F8_Repo.__init__(self, writePriority, repoList)

    def __str__(self):
        retval = ""
        for repo in self.repoList:
            retval += repo.__str__()

        return retval

    def _getParser(self):
        def list_cb (option, opt_str, value, parser):
            for d in value.split(','):
                parser.values.ensure_value(option.dest, []).append(d)

        op = F8_Repo._getParser(self)
        op.add_argument("--save", action="store_true", dest="save",
                        default=False, version=F8, help="")
        op.add_argument("--proxy", type=str, action="store", dest="proxy",
                        default=None, version=F8, help="")
        op.add_argument("--proxyuser", type=str, action="store",
                        dest="proxy_username", default=None, version=F8, help="")
        op.add_argument("--proxypasswd", type=str, action="store",
                        dest="proxy_password", default=None, version=F8, help="")
        op.add_argument("--debuginfo", action="store_true", dest="debuginfo",
                        default=False, version=F8, help="")
        op.add_argument("--source", action="store_true", dest="source",
                        default=False, version=F8, help="")
        op.add_argument("--disable", action="store_true", dest="disable",
                        default=False, version=F8, help="")
        op.add_argument("--gpgkey", type=str, action="store", dest="gpgkey",
                        default=None, version=F8, help="")
        op.add_argument("--ssl_verify", type=str, action="store",
                        dest="ssl_verify", default="yes", version=F8, help="")
        op.add_argument("--priority", type=int, action="store", dest="priority",
                        default=None, version=F8, help="")
        return op
