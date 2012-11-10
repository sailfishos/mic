#!/usr/bin/python -tt
#
# Copyright (c) 2011 Intel, Inc.
# Copyright (c) 2012 Jolla Ltd.
# Contact: Islam Amer <islam.amer@jollamobile.com>
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

import os
import sys

from mic import chroot, msger, rt_util
from mic.utils import cmdln, misc, errors, fs_related, common
from mic.imager import fs
from mic.conf import configmgr
from mic.plugin import pluginmgr

from mic.pluginbase import ImagerPlugin
class FsPlugin(ImagerPlugin):
    name = 'fs'

    @classmethod
    @cmdln.option("--include-src",
                  dest="include_src",
                  action="store_true",
                  default=False,
                  help="Generate a image with source rpms included")
    def do_create(self, subcmd, opts, *args):
        """${cmd_name}: create fs image

        Usage:
            ${name} ${cmd_name} <ksfile> [OPTS]

        ${cmd_option_list}
        """

        creatoropts = common.creatoropts(args)

        creator = fs.FsImageCreator(creatoropts, creatoropts['pkgmgr_pcls'])
        creator._recording_pkgs = creatoropts['record_pkgs']
        creator._include_src = opts.include_src

        self.check_image_exists(creator.destdir,
                                creator.pack_to,
                                [creator.name],
                                creatoropts['release'])

        try:
            creator.check_depend_tools()
            creator.mount(None, creatoropts["cachedir"])
            creator.install()
            #Download the source packages ###private options
            if opts.include_src:
                installed_pkgs =  creator.get_installed_packages()
                msger.info('--------------------------------------------------')
                msger.info('Generating the image with source rpms included ...')
                if not misc.SrcpkgsDownload(installed_pkgs, creatoropts["repomd"], creator._instroot, creatoropts["cachedir"]):
                    msger.warning("Source packages can't be downloaded")

            creator.configure(creatoropts["repomd"])
            creator.copy_kernel()
            creator.unmount()
            creator.package(creatoropts["outdir"])
            if creatoropts['release'] is not None:
                creator.release_output(ksconf, creatoropts['outdir'], creatoropts['release'])
            else:
                creator.outimage.append(creatoropts['dst_ks'])

            creator.print_outimage_info()
        except errors.CreatorError:
            raise
        finally:
            creator.cleanup()

        msger.info("Finished.")
        return 0

    @classmethod
    def do_chroot(self, target):#chroot.py parse opts&args
            try:
                envcmd = fs_related.find_binary_inchroot("env", target)
                if envcmd:
                    cmdline = "%s HOME=/root /bin/bash" % envcmd
                else:
                    cmdline = "/bin/bash"
                chroot.chroot(target, None, cmdline)
            finally:
                chroot.cleanup_after_chroot("dir", None, None, None)
                return 1

