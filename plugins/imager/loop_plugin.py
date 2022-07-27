# This file is part of mic
#
# Copyright (c) 2011 Intel, Inc.
# Copyright (c) 2012-2020 Jolla Ltd.
# Copyright (c) 2020 Open Mobile Platform LLC.
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

import os
import shutil
import tempfile

from mic import chroot, msger, rt_util
from mic.utils import misc, fs_related, errors, cmdln, common
from mic.conf import configmgr
from mic.plugin import pluginmgr
from mic.imager.loop import LoopImageCreator, load_mountpoints

from mic.pluginbase import ImagerPlugin
class LoopPlugin(ImagerPlugin):
    name = 'loop'

    @classmethod
    @cmdln.option("--compress-disk-image", dest="compress_image",
                  type='choice', choices=("gz", "bz2"), default=None,
                  help="Same with --compress-image")
                  # alias to compress-image for compatibility
    @cmdln.option("--compress-image", dest="compress_image",
                  type='choice', choices=("gz", "bz2"), default=None,
                  help="Compress all loop images with 'gz' or 'bz2'")
    @cmdln.option("--shrink", action='store_true', default=False,
                  help="Whether to shrink loop images to minimal size")
    def do_create(self, subcmd, opts, *args):
        """${cmd_name}: create loop image

        Usage:
            ${name} ${cmd_name} <ksfile> [OPTS]

        ${cmd_option_list}
        """

        creatoropts = common.creatoropts(args)

        creator = LoopImageCreator(creatoropts,
                                   creatoropts["pkgmgr_pcls"],
                                   opts.compress_image,
                                   opts.shrink)

        creator._recording_pkgs = creatoropts['record_pkgs']

        self.check_image_exists(creator.destdir,
                                creator.pack_to,
                                [creator.name + ".img"],
                                creatoropts['release'])

        try:
            creator.check_depend_tools()
            creator.mount(None, creatoropts["cachedir"])
            creator.install()
            creator.configure(creatoropts["repomd"])
            creator.copy_kernel()
            creator.unmount()
            creator.package(creatoropts["outdir"])

            if creatoropts['release'] is not None:
                creator.release_output(ksconf,
                                       creatoropts['outdir'],
                                       creatoropts['release'])
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
    def _do_chroot_tar(cls, target):
        mountfp_xml = os.path.splitext(target)[0] + '.xml'
        if not os.path.exists(mountfp_xml):
            raise errors.CreatorError("No mount point file found for this tar "
                                      "image, please check %s" % mountfp_xml)

        import tarfile
        tar = tarfile.open(target, 'r')
        tmpdir = misc.mkdtemp()
        tar.extractall(path=tmpdir)
        tar.close()

        mntdir = misc.mkdtemp()

        loops = []
        for (mp, label, name, size, fstype) in load_mountpoints(mountfp_xml):
            if fstype in ("ext2", "ext3", "ext4"):
                myDiskMount = fs_related.ExtDiskMount
            elif fstype == "btrfs":
                myDiskMount = fs_related.BtrfsDiskMount
            elif fstype in ("vfat", "msdos"):
                myDiskMount = fs_related.VfatDiskMount
            else:
                msger.error("Cannot support fstype: %s" % fstype)

            name = os.path.join(tmpdir, name)
            size = size * 1024 * 1024
            loop = myDiskMount(fs_related.SparseLoopbackDisk(name, size),
                               os.path.join(mntdir, mp.lstrip('/')),
                               fstype, size, label)

            try:
                msger.verbose("Mount %s to %s" % (mp, mntdir + mp))
                fs_related.makedirs(os.path.join(mntdir, mp.lstrip('/')))
                loop.mount()

            except:
                loop.cleanup()
                for lp in reversed(loops):
                    chroot.cleanup_after_chroot("img", lp, None, mntdir)

                shutil.rmtree(tmpdir, ignore_errors=True)
                raise

            loops.append(loop)

        try:
            chroot.chroot(mntdir, None, "/usr/bin/env HOME=/root /bin/bash")
        except:
            raise errors.CreatorError("Failed to chroot to %s." % target)
        finally:
            for loop in reversed(loops):
                chroot.cleanup_after_chroot("img", loop, None, mntdir)

            shutil.rmtree(tmpdir, ignore_errors=True)

    @classmethod
    def do_chroot(cls, target):
        if target.endswith('.tar'):
            import tarfile
            if tarfile.is_tarfile(target):
                LoopPlugin._do_chroot_tar(target)
                return
            else:
                raise errors.CreatorError("damaged tarball for loop images")

        img = target
        imgsize = misc.get_file_size(img) * 1024 * 1024
        imgtype = misc.get_image_type(img)
        if imgtype == "btrfsimg":
            fstype = "btrfs"
            myDiskMount = fs_related.BtrfsDiskMount
        elif imgtype in ("ext3fsimg", "ext4fsimg"):
            fstype = imgtype[:4]
            myDiskMount = fs_related.ExtDiskMount
        else:
            raise errors.CreatorError("Unsupported filesystem type: %s" \
                                      % imgtype)

        extmnt = misc.mkdtemp()
        extloop = myDiskMount(fs_related.SparseLoopbackDisk(img, imgsize),
                                                         extmnt,
                                                         fstype,
                                                         4096,
                                                         "%s label" % fstype)
        try:
            extloop.mount()

        except errors.MountError:
            extloop.cleanup()
            shutil.rmtree(extmnt, ignore_errors=True)
            raise

        try:
            envcmd = fs_related.find_binary_inchroot("env", extmnt)
            if envcmd:
                cmdline = "%s HOME=/root /bin/bash" % envcmd
            else:
                cmdline = "/bin/bash"
            chroot.chroot(extmnt, None, cmdline)
        except:
            raise errors.CreatorError("Failed to chroot to %s." % img)
        finally:
            chroot.cleanup_after_chroot("img", extloop, None, extmnt)

    @classmethod
    def do_unpack(cls, srcimg):
        image = os.path.join(tempfile.mkdtemp(dir="/var/tmp", prefix="tmp"),
                             "target.img")
        msger.info("Copying file system ...")
        shutil.copyfile(srcimg, image)
        return image
