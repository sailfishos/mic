#
# Chris Lumens <clumens@redhat.com>
# David Lehman <dlehman@redhat.com>
#
# Copyright 2005, 2006, 2007, 2011 Red Hat, Inc.
# Copyright (c) 2020 Jolla Ltd.
# Copyright (c) 2020 Open Mobile Platform LLC.
#
# This copyrighted material is made available to anyone wishing to use, modify,
# copy, or redistribute it subject to the terms and conditions of the GNU
# General Public License v.2.  This program is distributed in the hope that it
# will be useful, but WITHOUT ANY WARRANTY expressed or implied, including the
# implied warranties of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.  Any Red Hat
# trademarks that are incorporated in the source code or documentation are not
# subject to the GNU General Public License and may only be used or replicated
# with the express permission of Red Hat, Inc. 
#
from pykickstart.base import BaseData, KickstartCommand
from pykickstart.errors import formatErrorMsg, KickstartValueError
from pykickstart.options import KSOptionParser
from pykickstart.version import F8

from argparse import Action
import warnings

class BTRFSData(BaseData):
    removedKeywords = BaseData.removedKeywords
    removedAttrs = BaseData.removedAttrs

    def __init__(self, *args, **kwargs):
        BaseData.__init__(self, *args, **kwargs)
        self.format = kwargs.get("format", True)
        self.preexist = kwargs.get("preexist", False)
        self.label = kwargs.get("label", "")
        self.mountpoint = kwargs.get("mountpoint", "")
        self.devices = kwargs.get("devices", [])
        self.dataLevel = kwargs.get("data", None)
        self.metaDataLevel = kwargs.get("metadata", None)

        # subvolume-specific
        self.subvol = kwargs.get("subvol", False)
        self.parent = kwargs.get("parent", "")
        self.snapshot = kwargs.get("snapshot", False)
        self.base = kwargs.get("base", "")
        self.quota = kwargs.get("quota", False)
        self.name = kwargs.get("name", None)        # required

    def __eq__(self, y):
        if not y:
            return False

        return self.mountpoint == y.mountpoint

    def __ne__(self, y):
        return not self == y

    def _getArgsAsStr(self):
        retval = ""
        if not self.format:
            retval += " --noformat"
        if self.preexist:
            retval += " --useexisting"
        if self.label:
            retval += " --label=%s" % self.label
        if self.dataLevel:
            retval += " --data=%s" % self.dataLevel
        if self.metaDataLevel:
            retval += " --metadata=%s" % self.metaDataLevel
        if self.subvol:
            retval += " --subvol --name=%s" % self.name
        if self.parent:
            retval += " --parent=%s" % self.parent
        if self.snapshot:
            retval += " --snapshot --name=%s" % self.name
        if self.quota:
            retval += " --quota"
        if self.base:
            retval += " --base=%s" % self.base

        return retval

    def __str__(self):
        retval = BaseData.__str__(self)
        retval += "btrfs %s" % self.mountpoint
        retval += self._getArgsAsStr()
        return retval + " " + " ".join(self.devices) + "\n"

class BTRFS(KickstartCommand):
    removedKeywords = KickstartCommand.removedKeywords
    removedAttrs = KickstartCommand.removedAttrs

    def __init__(self, writePriority=132, *args, **kwargs):
        KickstartCommand.__init__(self, writePriority, *args, **kwargs)

        # A dict of all the RAID levels we support.  This means that if we
        # support more levels in the future, subclasses don't have to
        # duplicate too much.
        self.levelMap = { "RAID0": "raid0", "0": "raid0",
                          "RAID1": "raid1", "1": "raid1",
                          "RAID10": "raid10", "10": "raid10",
                          "single": "single" }

        self.op = self._getParser()
        self.btrfsList = kwargs.get("btrfsList", [])

    def __str__(self):
        retval = ""
        for btr in self.btrfsList:
            retval += btr.__str__()

        return retval

    def _getParser(self):
        # Have to be a little more complicated to set two values.
        class ValueAction(Action):
            def __call__(self, parser, namespace, values, option_string):
                namespace.format = False
                namespace.preexist = True

        class LevelAction(Action):
            def __init__(self, option_strings, dest, **kwargs):
                self._levelMap = kwargs.pop('_levelMap', [])
                super(LevelAction, self).__init__(option_strings, dest, **kwargs)

            def __call__(self, parser, namespace, value, option_string):
                setattr(namespace, self.dest, self._levelMap.get(value))

        op = KSOptionParser(prog="btrfs", version=F8, description="")
        op.add_argument("--noformat", action=ValueAction,
                        dest="format", default=True, nargs=0, version=F8, help="")
        op.add_argument("--useexisting", action=ValueAction,
                        dest="preexist", default=False, nargs=0, version=F8, help="")

        # label, data, metadata
        op.add_argument("--label", dest="label", default="", version=F8, help="")
        op.add_argument("--data", dest="dataLevel", action=LevelAction,
                        type=str, version=F8, help="", _levelMap=self.levelMap)
        op.add_argument("--metadata", dest="metaDataLevel", action=LevelAction,
                        type=str, version=F8, help="", _levelMap=self.levelMap)

        op.add_argument("--quota", dest="quota", action="store_true",
                        default=False, version=F8, help="")
        #
        # subvolumes
        #
        op.add_argument("--subvol", dest="subvol", action="store_true",
                        default=False, version=F8, help="")

        # parent must be a device spec (LABEL, UUID, &c)
        op.add_argument("--parent", dest="parent", default="", version=F8, help="")
        op.add_argument("--snapshot", dest="snapshot", action="store_true",
                        default=False, version=F8, help="")
        op.add_argument("--name", dest="name", default="", version=F8, help="")
        op.add_argument("--base", dest="base", default="", version=F8, help="")

        return op

    def parse(self, args):
        (namespace, extra) = self.op.parse_known_args(args=args, lineno=self.lineno)
        data = self.handler.BTRFSData()
        self.set_to_obj(namespace, data)
        data.lineno = self.lineno

        if len(extra) == 0 and not data.snapshot:
            raise KickstartValueError(formatErrorMsg(self.lineno, msg="btrfs must be given a mountpoint"))

        if len(extra) == 1 and not data.subvol:
            raise KickstartValueError(formatErrorMsg(self.lineno, msg="btrfs must be given a list of partitions"))
        elif len(extra) == 1:
            raise KickstartValueError(formatErrorMsg(self.lineno, msg="btrfs subvol requires specification of parent volume"))

        if data.subvol and not data.name:
            raise KickstartValueError(formatErrorMsg(self.lineno, msg="btrfs subvolume requires a name"))

        if data.snapshot and not data.name:
            raise KickstartValueError(formatErrorMsg(self.lineno, msg="btrfs snapshot requires a name"))

        if data.snapshot and data.subvol:
            raise KickstartValueError(formatErrorMsg(self.lineno, msg="btrfs subvolume cannot be snapshot at the same time"))

        if data.snapshot and not data.base:
            raise KickstartValueError(formatErrorMsg(self.lineno, msg="btrfs snapshot requires a base"))

        if len(extra) > 0:
            data.mountpoint = extra[0]
            data.devices = extra[1:]

        # Check for duplicates in the data list.
        if data in self.dataList():
            warnings.warn("A btrfs volume with the mountpoint '{}' has already been defined.".format(data.label))

        return data

    def dataList(self):
        return self.btrfsList
