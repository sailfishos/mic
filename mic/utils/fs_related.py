# This file is part of mic
#
# Copyright (c) 2007, Red Hat, Inc.
# Copyright (c) 2009, 2010, 2011 Intel, Inc.
# Copyright (c) 2020 Jolla Ltd.
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
import sys
import errno
import stat
import random
import string
import time

from .errors import *
from mic import msger
from . import runner

def find_binary_inchroot(binary, chroot):
    paths = ["/usr/sbin",
             "/usr/bin",
             "/sbin",
             "/bin"
            ]

    for path in paths:
        bin_path = "%s/%s" % (path, binary)
        if os.path.exists("%s/%s" % (chroot, bin_path)):
            return bin_path
    return None

def find_binary_path(binary):
    if "PATH" in os.environ:
        paths = os.environ["PATH"].split(":")
    else:
        paths = []
        if "HOME" in os.environ:
            paths += [os.environ["HOME"] + "/bin"]
        paths += ["/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"]

    for path in paths:
        bin_path = "%s/%s" % (path, binary)
        if os.path.exists(bin_path):
            return bin_path
    raise CreatorError("Command '%s' is not available." % binary)

def makedirs(dirname):
    """A version of os.makedirs() that doesn't throw an
    exception if the leaf directory already exists.
    """
    try:
        os.makedirs(dirname)
    except OSError as err:
        if err.errno != errno.EEXIST:
            raise

def mksquashfs(in_img, out_img):
    fullpathmksquashfs = find_binary_path("mksquashfs")
    args = [fullpathmksquashfs, in_img, out_img]

    if not sys.stdout.isatty():
        args.append("-no-progress")

    ret = runner.show(args)
    if ret != 0:
        raise SquashfsError("'%s' exited with error (%d)" % (' '.join(args), ret))

def resize2fs(fs, size):
    resize2fs = find_binary_path("resize2fs")
    if size == 0:
        # it means to minimalize it
        return runner.show([resize2fs, '-M', fs])
    else:
        return runner.show([resize2fs, fs, "%sK" % (size / 1024,)])

def my_fuser(fp):
    fuser = find_binary_path("fuser")
    if not os.path.exists(fp):
        return False

    rc = runner.quiet([fuser, "-s", fp])
    if rc == 0:
        for pid in runner.outs([fuser, fp]).split():
            fd = open("/proc/%s/cmdline" % pid, "r")
            cmdline = fd.read()
            fd.close()
            if cmdline[:-1] == "/bin/bash":
                return True

    # not found
    return False

class BindChrootMount:
    """Represents a bind mount of a directory into a chroot."""
    def __init__(self, src, chroot, dest = None, option = None):
        self.src = src
        self.root = os.path.abspath(os.path.expanduser(chroot))
        self.option = option

        if not dest:
            dest = src
        self.dest = self.root + "/" + dest

        self.mounted = False
        self.mountcmd = find_binary_path("mount")
        self.umountcmd = find_binary_path("umount")

    def ismounted(self):
        with open('/proc/mounts') as f:
            for line in f:
                if line.split()[1] == os.path.abspath(self.dest):
                    return True

        return False

    def has_chroot_instance(self):
        lock = os.path.join(self.root, ".chroot.lock")
        return my_fuser(lock)

    def mount(self):
        if self.mounted or self.ismounted():
            return

        makedirs(self.dest)
        rc = runner.show([self.mountcmd, "--bind", self.src, self.dest])
        if rc != 0:
            raise MountError("Bind-mounting '%s' to '%s' failed" %
                             (self.src, self.dest))
        if self.option:
            rc = runner.show([self.mountcmd, "--bind", "-o", "remount,%s" % self.option, self.dest])
            if rc != 0:
                raise MountError("Bind-remounting '%s' failed" % self.dest)
        self.mounted = True

    def unmount(self):
        if self.has_chroot_instance():
            return

        if self.ismounted():
            runner.show([self.umountcmd, "-l", self.dest])
        self.mounted = False

class LoopbackMount:
    """LoopbackMount  compatibility layer for old API"""
    def __init__(self, lofile, mountdir, fstype = None):
        self.diskmount = DiskMount(LoopbackDisk(lofile,size = 0),mountdir,fstype,rmmountdir = True)
        self.losetup = False
        self.losetupcmd = find_binary_path("losetup")

    def cleanup(self):
        self.diskmount.cleanup()

    def unmount(self):
        self.diskmount.unmount()

    def lounsetup(self):
        if self.losetup:
            runner.show([self.losetupcmd, "-d", self.loopdev])
            self.losetup = False
            self.loopdev = None

    def loopsetup(self):
        if self.losetup:
            return

        self.loopdev = get_loop_device(self.losetupcmd, self.lofile)
        self.losetup = True

    def mount(self):
        self.diskmount.mount()

class SparseLoopbackMount(LoopbackMount):
    """SparseLoopbackMount  compatibility layer for old API"""
    def __init__(self, lofile, mountdir, size, fstype = None):
        self.diskmount = DiskMount(SparseLoopbackDisk(lofile,size),mountdir,fstype,rmmountdir = True)

    def expand(self, create = False, size = None):
        self.diskmount.disk.expand(create, size)

    def truncate(self, size = None):
        self.diskmount.disk.truncate(size)

    def create(self):
        self.diskmount.disk.create()

class SparseExtLoopbackMount(SparseLoopbackMount):
    """SparseExtLoopbackMount  compatibility layer for old API"""
    def __init__(self, lofile, mountdir, size, fstype, blocksize, fslabel):
        self.diskmount = ExtDiskMount(SparseLoopbackDisk(lofile,size), mountdir, fstype, blocksize, fslabel, rmmountdir = True)


    def __format_filesystem(self):
        self.diskmount.__format_filesystem()

    def create(self):
        self.diskmount.disk.create()

    def resize(self, size = None):
        return self.diskmount.__resize_filesystem(size)

    def mount(self):
        self.diskmount.mount()

    def __fsck(self):
        self.extdiskmount.__fsck()

    def __get_size_from_filesystem(self):
        return self.diskmount.__get_size_from_filesystem()

    def __resize_to_minimal(self):
        return self.diskmount.__resize_to_minimal()

    def resparse(self, size = None):
        return self.diskmount.resparse(size)

class Disk:
    """Generic base object for a disk

    The 'create' method must make the disk visible as a block device - eg
    by calling losetup. For RawDisk, this is obviously a no-op. The 'cleanup'
    method must undo the 'create' operation.
    """
    def __init__(self, size, device = None):
        self._device = device
        self._size = size

    def create(self):
        pass

    def cleanup(self):
        pass

    def get_device(self):
        return self._device
    def set_device(self, path):
        self._device = path
    device = property(get_device, set_device)

    def get_size(self):
        return self._size
    size = property(get_size)


class RawDisk(Disk):
    """A Disk backed by a block device.
    Note that create() is a no-op.
    """
    def __init__(self, size, device):
        Disk.__init__(self, size, device)

    def fixed(self):
        return True

    def exists(self):
        return True

class LoopbackDisk(Disk):
    """A Disk backed by a file via the loop module."""
    def __init__(self, lofile, size):
        Disk.__init__(self, size)
        self.lofile = lofile
        self.losetupcmd = find_binary_path("losetup")

    def fixed(self):
        return False

    def exists(self):
        return os.path.exists(self.lofile)

    def create(self):
        if self.device is not None:
            return

        self.device = get_loop_device(self.losetupcmd, self.lofile)

    def cleanup(self):
        if self.device is None:
            return
        msger.debug("Losetup remove %s" % self.device)
        rc = runner.show([self.losetupcmd, "-d", self.device])
        self.device = None

class SparseLoopbackDisk(LoopbackDisk):
    """A Disk backed by a sparse file via the loop module."""
    def __init__(self, lofile, size):
        LoopbackDisk.__init__(self, lofile, size)

    def expand(self, create = False, size = None):
        flags = os.O_WRONLY
        if create:
            flags |= os.O_CREAT
            if not os.path.exists(self.lofile):
                makedirs(os.path.dirname(self.lofile))

        if size is None:
            size = self.size

        msger.debug("Extending sparse file %s to %d" % (self.lofile, size))
        if create:
            fd = os.open(self.lofile, flags, 0o644)
        else:
            fd = os.open(self.lofile, flags)

        os.lseek(fd, size - 1, os.SEEK_SET)
        os.write(fd, '\x00'.encode())
        os.close(fd)

    def truncate(self, size = None):
        if size is None:
            size = self.size

        msger.debug("Truncating sparse file %s to %d" % (self.lofile, size))
        fd = os.open(self.lofile, os.O_WRONLY)
        os.ftruncate(fd, size)
        os.close(fd)

    def create(self):
        self.expand(create = True)
        LoopbackDisk.create(self)

class Mount:
    """A generic base class to deal with mounting things."""
    def __init__(self, mountdir):
        self.mountdir = mountdir

    def cleanup(self):
        self.unmount()

    def mount(self, options = None):
        pass

    def unmount(self):
        pass

class DiskMount(Mount):
    """A Mount object that handles mounting of a Disk."""
    def __init__(self, disk, mountdir, fstype = None, rmmountdir = True):
        Mount.__init__(self, mountdir)

        self.disk = disk
        self.fstype = fstype
        self.rmmountdir = rmmountdir

        self.mounted = False
        self.rmdir   = False
        if fstype:
            self.mkfscmd = find_binary_path("mkfs." + self.fstype)
        else:
            self.mkfscmd = None
        self.mountcmd = find_binary_path("mount")
        self.umountcmd = find_binary_path("umount")

    def cleanup(self):
        Mount.cleanup(self)
        self.disk.cleanup()

    def unmount(self):
        if self.mounted:
            msger.debug("Unmounting directory %s" % self.mountdir)
            runner.quiet('sync') # sync the data on this mount point
            rc = runner.show([self.umountcmd, "-l", self.mountdir])
            if rc == 0:
                self.mounted = False
            else:
                raise MountError("Failed to umount %s" % self.mountdir)
        if self.rmdir and not self.mounted:
            try:
                os.rmdir(self.mountdir)
            except OSError as e:
                pass
            self.rmdir = False


    def __create(self):
        self.disk.create()


    def mount(self, options = None):
        if self.mounted:
            return

        if not os.path.isdir(self.mountdir):
            msger.debug("Creating mount point %s" % self.mountdir)
            os.makedirs(self.mountdir)
            self.rmdir = self.rmmountdir

        self.__create()

        msger.debug("Mounting %s at %s" % (self.disk.device, self.mountdir))
        if options:
            args = [ self.mountcmd, "-o", options, self.disk.device, self.mountdir ]
        else:
            args = [ self.mountcmd, self.disk.device, self.mountdir ]
        if self.fstype:
            args.extend(["-t", self.fstype])

        rc = runner.show(args)
        if rc != 0:
            raise MountError("Failed to mount '%s' to '%s' with command '%s'. Retval: %s" %
                             (self.disk.device, self.mountdir, " ".join(args), rc))

        self.mounted = True

class ExtDiskMount(DiskMount):
    """A DiskMount object that is able to format/resize ext[23] filesystems."""
    def __init__(self, disk, mountdir, fstype, blocksize, fslabel, rmmountdir=True, skipformat = False, fsopts = None):
        DiskMount.__init__(self, disk, mountdir, fstype, rmmountdir)
        self.blocksize = blocksize
        self.fslabel = fslabel.replace("/", "")
        self.uuid  = None
        self.skipformat = skipformat
        self.fsopts = fsopts
        self.dumpe2fs = find_binary_path("dumpe2fs")
        self.tune2fs = find_binary_path("tune2fs")

    def __parse_field(self, output, field):
        for line in output.split("\n"):
            if line.startswith(field + ":"):
                return line[len(field) + 1:].strip()

        raise KeyError("Failed to find field '%s' in output" % field)

    def __format_filesystem(self):
        if self.skipformat:
            msger.debug("Skip filesystem format.")
            return

        msger.verbose("Formating %s filesystem on %s" % (self.fstype, self.disk.device))
        rc = runner.show([self.mkfscmd,
                          "-F", "-L", self.fslabel,
                          "-m", "1", "-b", str(self.blocksize),
                          "-O", "^64bit", # syslinux does not support 64bit filesystems
                          self.disk.device]) # str(self.disk.size / self.blocksize)])
        if rc != 0:
            raise MountError("Error creating %s filesystem on disk %s" % (self.fstype, self.disk.device))

        out = runner.outs([self.dumpe2fs, '-h', self.disk.device])

        self.uuid = self.__parse_field(out, "Filesystem UUID")
        msger.debug("Tuning filesystem on %s" % self.disk.device)
        runner.show([self.tune2fs, "-c0", "-i0", "-Odir_index", "-ouser_xattr,acl", self.disk.device])

    def __resize_filesystem(self, size = None):
        current_size = os.stat(self.disk.lofile)[stat.ST_SIZE]

        if size is None:
            size = self.disk.size

        if size == current_size:
            return

        if size > current_size:
            self.disk.expand(size)

        self.__fsck()

        resize2fs(self.disk.lofile, size)
        return size

    def __create(self):
        resize = False
        if not self.disk.fixed() and self.disk.exists():
            resize = True

        self.disk.create()

        if resize:
            self.__resize_filesystem()
        else:
            self.__format_filesystem()

    def mount(self, options = None):
        self.__create()
        DiskMount.mount(self, options)

    def __fsck(self):
        msger.info("Checking filesystem %s" % self.disk.lofile)
        runner.quiet(["/sbin/e2fsck", "-f", "-y", self.disk.lofile])

    def __get_size_from_filesystem(self):
        return int(self.__parse_field(runner.outs([self.dumpe2fs, '-h', self.disk.lofile]),
                                      "Block count")) * self.blocksize

    def __resize_to_minimal(self):
        self.__fsck()

        #
        # Use a binary search to find the minimal size
        # we can resize the image to
        #
        bot = 0
        top = self.__get_size_from_filesystem()
        while top != (bot + 1):
            t = bot + ((top - bot) / 2)

            if not resize2fs(self.disk.lofile, t):
                top = int(t)
            else:
                bot = int(t)
        return top

    def resparse(self, size = None):
        self.cleanup()
        if size == 0:
            minsize = 0
        else:
            minsize = self.__resize_to_minimal()
            self.disk.truncate(minsize)

        self.__resize_filesystem(size)
        return minsize

class VfatDiskMount(DiskMount):
    """A DiskMount object that is able to format vfat/msdos filesystems."""
    def __init__(self, disk, mountdir, fstype, blocksize, fslabel, rmmountdir=True, skipformat = False, fsopts = None):
        DiskMount.__init__(self, disk, mountdir, fstype, rmmountdir)
        self.blocksize = blocksize
        self.fslabel = fslabel.replace("/", "")
        self.uuid = None
        self.blkidcmd = find_binary_path("blkid")
        self.skipformat = skipformat
        self.fsopts = fsopts
        self.fsckcmd = find_binary_path("fsck." + self.fstype)

    def __parse_field(self, output, field):
        for line in output.split(" "):
            if line.startswith(field + "="):
                return line[len(field) + 1:].strip().replace("\"", "")

        raise KeyError("Failed to find field '%s' in output" % field)

    def __format_filesystem(self):
        if self.skipformat:
            msger.debug("Skip filesystem format.")
            return

        msger.verbose("Formating %s filesystem on %s" % (self.fstype, self.disk.device))
        rc = runner.show([self.mkfscmd, "-n", self.fslabel, self.disk.device])
        if rc != 0:
            raise MountError("Error creating %s filesystem on disk %s" % (self.fstype,self.disk.device))
 
        msger.verbose("Tuning filesystem on %s" % self.disk.device)
        self.uuid = self.__parse_field(runner.outs([self.blkidcmd, self.disk.device]), "UUID")

    def __resize_filesystem(self, size = None):
        current_size = os.stat(self.disk.lofile)[stat.ST_SIZE]

        if size is None:
            size = self.disk.size

        if size == current_size:
            return

        if size > current_size:
            self.disk.expand(size)

        self.__fsck()

        #resize2fs(self.disk.lofile, size)
        return size

    def __create(self):
        resize = False
        if not self.disk.fixed() and self.disk.exists():
            resize = True

        self.disk.create()

        if resize:
            self.__resize_filesystem()
        else:
            self.__format_filesystem()

    def mount(self, options = None):
        self.__create()
        DiskMount.mount(self, options)

    def __fsck(self):
        msger.debug("Checking filesystem %s" % self.disk.lofile)
        runner.show([self.fsckcmd, "-y", self.disk.lofile])

    def __get_size_from_filesystem(self):
        return self.disk.size

    def __resize_to_minimal(self):
        self.__fsck()

        #
        # Use a binary search to find the minimal size
        # we can resize the image to
        #
        bot = 0
        top = self.__get_size_from_filesystem()
        return top

    def resparse(self, size = None):
        self.cleanup()
        minsize = self.__resize_to_minimal()
        self.disk.truncate(minsize)
        self.__resize_filesystem(size)
        return minsize

class BtrfsDiskMount(DiskMount):
    """A DiskMount object that is able to format/resize btrfs filesystems."""
    def __init__(self, disk, mountdir, fstype, blocksize, fslabel, rmmountdir=True, skipformat = False, fsopts = None, subvolumes=None, snapshots=None):
        self.__check_btrfs()
        DiskMount.__init__(self, disk, mountdir, fstype, rmmountdir)
        self.blocksize = blocksize
        self.fslabel = fslabel.replace("/", "")
        self.uuid  = None
        self.skipformat = skipformat
        self.fsopts = fsopts
        self.blkidcmd = find_binary_path("blkid")
        self.btrfscmd = find_binary_path("btrfs")
        self.btrfsckcmd = find_binary_path("btrfsck")
        self.subvolumes = subvolumes
        self.snapshots = snapshots
        self.snapped = False

    def __get_subvolume_metadata(self):
        #subvolume_metadata_file = "%s/.subvolume_metadata" % self.disk.mountdir
        subvolume_metadata_file = "%s.subvolume_metadata" % self.disk.lofile
        if not os.path.exists(subvolume_metadata_file):
            return

        fd = open(subvolume_metadata_file, "r")
        content = fd.read()
        fd.close()

        for line in content.splitlines():
            items = line.split("\t")
            if items and len(items) == 4:
                self.subvolumes.append({'size': 0, # In sectors
                                        'mountpoint': items[2], # Mount relative to chroot
                                        'fstype': "btrfs", # Filesystem type
                                        'fsopts': items[3] + ",subvol=%s" %  items[1], # Filesystem mount options
                                        'disk': p['disk'], # physical disk name holding partition
                                        'device': None, # kpartx device node for partition
                                        'mount': None, # Mount object
                                        'subvol': items[1], # Subvolume name
                                        'boot': False, # Bootable flag
                                        'mounted': False # Mount flag
                                   })

    def __get_subvolume_id(self, rootpath, subvol):
        argv = [ self.btrfscmd, "subvolume", "list", rootpath ]

        rc, out = runner.runtool(argv)
        msger.debug(out)

        if rc != 0:
            raise MountError("Failed to get subvolume id from %s', return code: %d." % (rootpath, rc))

        subvolid = -1
        for line in out.splitlines():
            if line.endswith(" path %s" % subvol):
                subvolid = line.split()[1]
                if not subvolid.isdigit():
                    raise MountError("Invalid subvolume id: %s" % subvolid)
                subvolid = int(subvolid)
                break
        return subvolid

    def __create_subvolume_snapshots(self):
        if not self.snapshots or self.snapped:
            return

        """ Remount with subvolid=0 """
        if self.fsopts:
            mountopts = self.fsopts + ",subvolid=0"
        else:
            mountopts = "subvolid=0"

        rc = runner.show([self.umountcmd, self.mountdir])
        if rc != 0:
            raise MountError("Failed to umount %s" % self.mountdir)

        rc = runner.show([self.mountcmd, "-o", mountopts, self.disk.device, self.mountdir])
        if rc != 0:
            raise MountError("Failed to mount %s" % self.mountdir)
                                                                                                                                                               
        """ Create all the subvolume snapshots """
        for snap in self.snapshots:
            subvolpath = os.path.join(self.mountdir, snap["base"])
            snapshotpath = os.path.join(self.mountdir, snap["name"])
            msger.info("Creating snapshot %s based on %s..." % (snap["name"] ,snap["base"]))
            rc = runner.show([ self.btrfscmd, "subvolume", "snapshot", subvolpath, snapshotpath ])
            if rc != 0:
                raise MountError("Failed to create subvolume snapshot '%s' for '%s', return code: %d." % (snapshotpath, subvolpath, rc))

        self.snapped = True

    def __create_subvolume_metadata(self):
        if len(self.subvolumes) == 0:
            return

        argv = [ self.btrfscmd, "subvolume", "list", self.mountdir ]
        rc, out = runner.runtool(argv)
        msger.debug(out)

        if rc != 0:
            raise MountError("Failed to get subvolume id from %s', return code: %d." % (self.mountdir, rc))

        subvolid_items = out.splitlines()
        subvolume_metadata = ""
        for subvol in self.subvolumes:
            for line in subvolid_items:
                if line.endswith(" path %s" % subvol["subvol"]):
                    subvolid = line.split()[1]
                    if not subvolid.isdigit():
                        raise MountError("Invalid subvolume id: %s" % subvolid)

                    subvolid = int(subvolid)
                    fsopts = subvol["fsopts"]
                    subvolume_metadata += "%d\t%s\t%s\t%s\n" % (subvolid, subvol["subvol"], subvol['mountpoint'], fsopts)

        if subvolume_metadata:
            fd = open("%s.subvolume_metadata" % self.disk.lofile,"w")
            #fd = open("%s/.subvolume_metadata" % self.mountdir, "w")
            fd.write(subvolume_metadata)
            fd.close()

    def __create_subvolumes(self):
        """ Create all the subvolumes """
        if not self.subvolumes:
            return

        for subvol in self.subvolumes:
            if subvol.get("quota", False):
                argv = [ self.btrfscmd, "quota", "enable", self.mountdir ]

                rc = runner.show(argv)
                if rc != 0:
                    raise MountError("Failed to enable quota '%s', return code: %d." % (subvol["subvol"], rc))
                
            argv = [ self.btrfscmd, "subvolume", "create", self.mountdir + "/" + subvol["subvol"]]

            rc = runner.show(argv)
            if rc != 0:
                raise MountError("Failed to create subvolume '%s', return code: %d." % (subvol["subvol"], rc))

        """ Set default subvolume, subvolume for "/" is default """
        subvol = None
        for subvolume in self.subvolumes:
            if subvolume["mountpoint"] == "/":
                subvol = subvolume
                break

        if subvol:
            """ Get default subvolume id """
            subvolid = self.__get_subvolume_id(self.mountdir, subvol["subvol"])
            """ Set default subvolume """
            if subvolid != -1:
                rc = runner.show([ self.btrfscmd, "subvolume", "set-default", "%d" % subvolid, self.mountdir])
                if rc != 0:
                    raise MountError("Failed to set default subvolume id: %d', return code: %d." % (subvolid, rc))

        self.__create_subvolume_metadata()

    def __mount_subvolumes(self):
        if self.skipformat:
            """ Get subvolume info """
            self.__get_subvolume_metadata()
            """ Set default mount options """
            if len(self.subvolumes) != 0:
                for subvol in self.subvolumes:
                    if subvol["mountpoint"] == "/":
                        self.fsopts = subvol["fsopts"]
                        break

        if len(self.subvolumes) == 0:
            """ Return directly if no subvolumes """
            return

        """ Remount to make default subvolume mounted """
        rc = runner.show([self.umountcmd, self.mountdir])
        if rc != 0:
            raise MountError("Failed to umount %s" % self.mountdir)

        rc = runner.show([self.mountcmd, "-o", self.fsopts, self.disk.device, self.mountdir])
        if rc != 0:
            raise MountError("Failed to mount %s on %s" % (self.disk.device, self.mountdir))

        for subvol in self.subvolumes:
            if subvol["mountpoint"] == "/":
                continue
            subvolid = self.__get_subvolume_id(self.mountdir, subvol["subvol"])
            if subvolid == -1:
                msger.debug("WARNING: invalid subvolume %s" % subvol["subvol"])
                continue
            """ Replace subvolume name with subvolume ID """
            opts = []
            opts.extend(["defaults", "subvolrootid=0", "subvolid=%s" % subvolid])
            fsopts = ",".join(opts)
            mountpoint = os.path.join(self.mountdir + subvol['mountpoint'])
            makedirs(mountpoint)
            rc = runner.show([self.mountcmd, "-o", fsopts, self.disk.device, mountpoint])
            if rc != 0:
                raise MountError("Failed to mount subvolume %s to %s" % (subvol["subvol"], mountpoint))
            subvol["mounted"] = True

    def __unmount_subvolumes(self):
        """ It may be called multiple times, so we need to chekc if it is still mounted. """
        for subvol in self.subvolumes:
            if subvol["mountpoint"] == "/":
                continue
            if not subvol["mounted"]:
                continue
            mountpoint = self.mountdir + subvol['mountpoint']
            rc = runner.show([self.umountcmd, mountpoint])
            if rc != 0:
                raise MountError("Failed to unmount subvolume %s from %s" % (subvol["subvol"], mountpoint))
            subvol["mounted"] = False

        self.__create_subvolume_snapshots()

    def __check_btrfs(self):
        found = False
        """ Need to load btrfs module to mount it """
        load_module("btrfs")
        for line in open("/proc/filesystems"):
            if line.find("btrfs") > -1:
                found = True
                break
        if not found:
            raise MountError("Your system can't mount btrfs filesystem, please make sure your kernel has btrfs support and the module btrfs.ko has been loaded.")

        # disable selinux, selinux will block write
        if os.path.exists("/usr/sbin/setenforce"):
            runner.show(["/usr/sbin/setenforce", "0"])

    def __parse_field(self, output, field):
        for line in output.split(" "):
            if line.startswith(field + "="):
                return line[len(field) + 1:].strip().replace("\"", "")

        raise KeyError("Failed to find field '%s' in output" % field)

    def __format_filesystem(self):
        if self.skipformat:
            msger.debug("Skip filesystem format.")
            return

        msger.verbose("Formating %s filesystem on %s" % (self.fstype, self.disk.device))
        # For now hardcode the 'no extref' option
        msger.verbose("Hardcode in /usr/lib/python2.7/site-packages/mic/utils/fs_related.py for the 'no extref' option (-O ^extref). See JB#39420")
        rc = runner.show([self.mkfscmd, "-O", "^extref", "-L", self.fslabel, self.disk.device])
        if rc != 0:
            raise MountError("Error creating %s filesystem on disk %s" % (self.fstype,self.disk.device))

        self.uuid = self.__parse_field(runner.outs([self.blkidcmd, "-c /dev/null", self.disk.device]), "UUID")

    def __resize_filesystem(self, size = None):
        current_size = os.stat(self.disk.lofile)[stat.ST_SIZE]

        if size is None:
            size = self.disk.size

        if size == current_size:
            return

        if size > current_size:
            self.disk.expand(size)

        self.__fsck()
        return size

    def __create(self):
        resize = False
        if not self.disk.fixed() and self.disk.exists():
            resize = True

        self.disk.create()

        if resize:
            self.__resize_filesystem()
        else:
            self.__format_filesystem()

    def mount(self, options = None):
        self.__create()
        DiskMount.mount(self, options)
        self.__create_subvolumes()
        self.__mount_subvolumes()

    def unmount(self):
        self.__unmount_subvolumes()
        DiskMount.unmount(self)

    def __fsck(self):
        msger.debug("Checking filesystem %s" % self.disk.lofile)
        runner.quiet([self.btrfsckcmd, self.disk.lofile])

    def __get_size_from_filesystem(self):
        return self.disk.size

    def __resize_to_minimal(self):
        self.__fsck()

        return self.__get_size_from_filesystem()

    def resparse(self, size = None):
        self.cleanup()
        minsize = self.__resize_to_minimal()
        self.disk.truncate(minsize)
        self.__resize_filesystem(size)
        return minsize

class DeviceMapperSnapshot(object):
    def __init__(self, imgloop, cowloop):
        self.imgloop = imgloop
        self.cowloop = cowloop

        self.__created = False
        self.__name = None
        self.dmsetupcmd = find_binary_path("dmsetup")

        """Load dm_snapshot if it isn't loaded"""
        load_module("dm_snapshot")

    def get_path(self):
        if self.__name is None:
            return None
        return os.path.join("/dev/mapper", self.__name)
    path = property(get_path)

    def create(self):
        if self.__created:
            return

        self.imgloop.create()
        self.cowloop.create()

        self.__name = "imgcreate-%d-%d" % (os.getpid(),
                                           random.randint(0, 2**16))

        size = os.stat(self.imgloop.lofile)[stat.ST_SIZE]

        table = "0 %d snapshot %s %s p 8" % (size / 512,
                                             self.imgloop.device,
                                             self.cowloop.device)

        args = [self.dmsetupcmd, "create", self.__name, "--table", table]
        if runner.show(args) != 0:
            self.cowloop.cleanup()
            self.imgloop.cleanup()
            raise SnapshotError("Could not create snapshot device using: " + ' '.join(args))

        self.__created = True

    def remove(self, ignore_errors = False):
        if not self.__created:
            return

        time.sleep(2)
        rc = runner.show([self.dmsetupcmd, "remove", self.__name])
        if not ignore_errors and rc != 0:
            raise SnapshotError("Could not remove snapshot device")

        self.__name = None
        self.__created = False

        self.cowloop.cleanup()
        self.imgloop.cleanup()

    def get_cow_used(self):
        if not self.__created:
            return 0

        #
        # dmsetup status on a snapshot returns e.g.
        #   "0 8388608 snapshot 416/1048576"
        # or, more generally:
        #   "A B snapshot C/D"
        # where C is the number of 512 byte sectors in use
        #
        out = runner.outs([self.dmsetupcmd, "status", self.__name])
        try:
            return int((out.split()[3]).split('/')[0]) * 512
        except ValueError:
            raise SnapshotError("Failed to parse dmsetup status: " + out)

def create_image_minimizer(path, image, minimal_size):
    """
    Builds a copy-on-write image which can be used to
    create a device-mapper snapshot of an image where
    the image's filesystem is as small as possible

    The steps taken are:
      1) Create a sparse COW
      2) Loopback mount the image and the COW
      3) Create a device-mapper snapshot of the image
         using the COW
      4) Resize the filesystem to the minimal size
      5) Determine the amount of space used in the COW
      6) Restroy the device-mapper snapshot
      7) Truncate the COW, removing unused space
      8) Create a squashfs of the COW
    """
    imgloop = LoopbackDisk(image, None) # Passing bogus size - doesn't matter

    cowloop = SparseLoopbackDisk(os.path.join(os.path.dirname(path), "osmin"),
                                 64 * 1024 * 1024)

    snapshot = DeviceMapperSnapshot(imgloop, cowloop)

    try:
        snapshot.create()

        resize2fs(snapshot.path, minimal_size)

        cow_used = snapshot.get_cow_used()
    finally:
        snapshot.remove(ignore_errors = (not sys.exc_info()[0] is None))

    cowloop.truncate(cow_used)

    mksquashfs(cowloop.lofile, path)

    os.unlink(cowloop.lofile)

def load_module(module):
    found = False
    for line in open('/proc/modules'):
        if line.startswith("%s " % module):
            found = True
            break
    if not found:
        msger.info("Loading %s..." % module)
        runner.quiet(['modprobe', module])

class LoopDevice(object):
    def __init__(self, loopid=None):
        self.device = None
        self.loopid = loopid
        self.created = False
        self.kpartxcmd = find_binary_path("kpartx")
        self.losetupcmd = find_binary_path("losetup")

        import atexit
        atexit.register(self.close)

    def _genloopid(self):
        import glob
        fint = lambda x: x[9:].isdigit() and int(x[9:]) or 0
        maxid = 1 + max([x for x in map(fint, glob.glob("/dev/loop[0-9]*")) if x<100])
        if maxid < 10: maxid = 10
        if maxid >= 100: raise
        return maxid

    def _kpseek(self, device):
        rc, out = runner.runtool([self.kpartxcmd, '-l', '-v', device])
        if rc != 0:
            raise MountError("Can't query dm snapshot on %s" % device)
        for line in out.splitlines():
            if line and line.startswith("loop"):
                return True
        return False

    def _loseek(self, device):
        import re
        rc, out = runner.runtool([self.losetupcmd, '-a'])
        if rc != 0:
            raise MountError("Failed to run 'losetup -a'")
        for line in out.splitlines():
            m = re.match("([^:]+): .*", line)
            if m and m.group(1) == device:
                return True
        return False

    def create(self):
        if not self.created:
            if not self.loopid:
                self.loopid = self._genloopid()
            self.device = "/dev/loop%d" % self.loopid
            if os.path.exists(self.device):
                if self._loseek(self.device):
                    raise MountError("Device busy: %s" % self.device)
                else:
                    self.created = True
                    return
            try:
                os.mknod(self.device,
                         0o664 | stat.S_IFBLK,
                         os.makedev(7, self.loopid))
            except:
                raise MountError("Failed to create device %s" % self.device)
            else:
                self.created = True

    def close(self):
        if self.created:
            try:
                self.cleanup()
                self.device = None
            except MountError as e:
                msger.error("%s" % e)

    def cleanup(self):

        if self.device is None:
            return


        if self._kpseek(self.device):
            if self.created:
                for i in range(3, os.sysconf("SC_OPEN_MAX")):
                    try:
                        os.close(i)
                    except:
                        pass
            runner.quiet([self.kpartxcmd, "-d", self.device])
        if self._loseek(self.device):
            runner.quiet([self.losetupcmd, "-d", self.device])
        # FIXME: should sleep a while between two loseek
        if self._loseek(self.device):
            msger.warning("Can't cleanup loop device %s" % self.device)
        else:
            os.unlink(self.device)

DEVICE_LOCKFILE = "/var/lock/__mic_loopdev.lock"

def get_loop_device(losetupcmd, lofile):
    global DEVICE_LOCKFILE

    import fcntl
    makedirs(os.path.realpath(os.path.dirname(DEVICE_LOCKFILE)))
    fp = open(DEVICE_LOCKFILE, 'w')
    fcntl.flock(fp, fcntl.LOCK_EX)
    try:
        devinst = LoopDevice()
        devinst.create()
    except:
        rc, out = runner.runtool([losetupcmd, "-f"])
        if rc != 0:
            raise MountError("1-Failed to allocate loop device for '%s'" % lofile)
        loopdev = out.split()[0]
    else:
        loopdev = devinst.device
    finally:
        try:
            fcntl.flock(fp, fcntl.LOCK_UN)
            fp.close()
            os.unlink(DEVICE_LOCKFILE)
        except:
            pass

    rc = runner.show([losetupcmd, loopdev, lofile])
    if rc != 0:
        raise MountError("2-Failed to allocate loop device for '%s'" % lofile)

    return loopdev


