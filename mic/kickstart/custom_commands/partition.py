# This file is part of mic
#
# Marko Saukko <marko.saukko@cybercom.com>
#
# Copyright (C) 2011 Nokia Corporation and/or its subsidiary(-ies).
# Copyright (c) 2020 Jolla Ltd.
# Copyright (c) 2020 Open Mobile Platform LLC.
#
# This copyrighted material is made available to anyone wishing to use, modify,
# copy, or redistribute it subject to the terms and conditions of the GNU
# General Public License v.2. This program is distributed in the hope that it
# will be useful, but WITHOUT ANY WARRANTY expressed or implied, including the
# implied warranties of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

from pykickstart.commands.partition import F17_PartData, F17_Partition
from pykickstart.version import FC4, F23

class MeeGo_PartData(F17_PartData):
    removedKeywords = F17_PartData.removedKeywords
    removedAttrs = F17_PartData.removedAttrs

    def __init__(self, *args, **kwargs):
        F17_PartData.__init__(self, *args, **kwargs)
        self.deleteRemovedAttrs()
        self.align = kwargs.get("align", None)
        self.mkfsopts = kwargs.get("mkfsopts", "")

    def _getArgsAsStr(self):
        retval = F17_PartData._getArgsAsStr(self)

        if self.align:
            retval += " --align"
        if self.mkfsopts:
            retval += " --mkfsoptions=\"%s\"" % self.mkfsopts

        return retval

class MeeGo_Partition(F17_Partition):
    removedKeywords = F17_Partition.removedKeywords
    removedAttrs = F17_Partition.removedAttrs

    def _getParser(self):
        op = F17_Partition._getParser(self)
        # The alignment value is given in kBytes. e.g., value 8 means that
        # the partition is aligned to start from 8096 byte boundary.
        op.add_argument("--align", type=int, action="store", dest="align",
                        default=None, version=FC4, help="")
        op.add_argument("--mkfsoptions", dest="mkfsopts", version=F23, help="""
                        Specifies additional parameters to be passed to the
                        program that makes a filesystem on this partition. This
                        is similar to ``--fsprofile`` but works for all
                        filesystems, not just the ones that support the profile
                        concept. No processing is done on the list of arguments,
                        so they must be supplied in a format that can be passed
                        directly to the mkfs program. This means multiple
                        options should be comma-separated or surrounded by
                        double quotes, depending on the filesystem.""")
        return op
