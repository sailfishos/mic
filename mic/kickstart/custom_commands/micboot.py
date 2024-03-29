# This file is part of mic
#
# Copyright (c) 2008, 2009, 2010 Intel, Inc.
# Copyright (c) 2020 Jolla Ltd.
# Copyright (c) 2020 Open Mobile Platform LLC.
#
# Anas Nashif
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
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from pykickstart.commands.bootloader import F8_Bootloader
from pykickstart.version import F8

class Moblin_Bootloader(F8_Bootloader):
    def __init__(self, writePriority=10, appendLine="", driveorder=None,
                 forceLBA=False, location="", md5pass="", password="",
                 upgrade=False, menus=""):
        F8_Bootloader.__init__(self, writePriority, appendLine, driveorder,
                                forceLBA, location, md5pass, password, upgrade)

        self.menus = ""

    def _getArgsAsStr(self):
        ret = F8_Bootloader._getArgsAsStr(self)

        if self.menus == "":
            ret += " --menus=%s" %(self.menus,)
        return ret

    def _getParser(self):
        op = F8_Bootloader._getParser(self)
        op.add_argument("--menus", dest="menus", version=F8, help="")
        return op

