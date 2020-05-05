#!/usr/bin/python3
#
# Copyright (c) 2008, 2009, 2010 Intel, Inc.
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

from pykickstart.base import *
from pykickstart.errors import *
from pykickstart.options import *
from pykickstart.version import F8

class Moblin_Desktop(KickstartCommand):
    def __init__(self, writePriority=0,
                       defaultdesktop=None,
                       defaultdm=None,
                       autologinuser="meego",
                       session=None):

        KickstartCommand.__init__(self, writePriority)

        self.op = self._getParser()

        self.defaultdesktop = defaultdesktop
        self.autologinuser = autologinuser
        self.defaultdm = defaultdm
        self.session = session

    def __str__(self):
        retval = ""

        if self.defaultdesktop != None:
            retval += " --defaultdesktop=%s" % self.defaultdesktop
        if self.session != None:
            retval += " --session=\"%s\"" % self.session
        if self.autologinuser != None:
            retval += " --autologinuser=%s" % self.autologinuser
        if self.defaultdm != None:
            retval += " --defaultdm=%s" % self.defaultdm

        if retval != "":
            retval = "# Default Desktop Settings\ndesktop %s\n" % retval

        return retval

    def _getParser(self):
        op = KSOptionParser(prog="desktop", version=F8, description="")

        op.add_argument("--defaultdesktop", dest="defaultdesktop",
                                            action="store",
                                            type=str,
                                            version=F8,
                                            help="")
        op.add_argument("--autologinuser", dest="autologinuser",
                                           action="store",
                                           type=str,
                                           version=F8,
                                           help="")
        op.add_argument("--defaultdm", dest="defaultdm",
                                       action="store",
                                       type=str,
                                       version=F8,
                                       help="")
        op.add_argument("--session", dest="session",
                                     action="store",
                                     type=str,
                                     version=F8,
                                     help="")
        return op

    def parse(self, args):
        opts, extra = self.op.parse_known_args(args=args, lineno=self.lineno)

        if extra:
            m = "Unexpected arguments to %(command)s command: %(options)s" \
                  % {"command": "desktop", "options": extra}
            raise KickstartValueError(formatErrorMsg(self.lineno, msg=m))

        self.set_to_self(opts)
