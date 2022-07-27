# This file is part of mic
#
# Copyright (c) 2011 Intel, Inc.
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
import shutil
from mic import msger
from mic.utils import errors

class _MetaTable(type):
    def __init__(cls, name, bases, attrs):
        if not hasattr(cls, 'plugins'):
            cls.plugins = {}

        elif 'mic_plugin_type' in attrs:
                if attrs['mic_plugin_type'] not in cls.plugins:
                    cls.plugins[attrs['mic_plugin_type']] = {}

        elif hasattr(cls, 'mic_plugin_type') and 'name' in attrs:
                cls.plugins[cls.mic_plugin_type][attrs['name']] = cls

    def show_plugins(cls):
        for cls in cls.plugins[cls.mic_plugin_type]:
            print(cls)

    def get_plugins(cls):
        return cls.plugins


class _Plugin(metaclass=_MetaTable):
    pass

class ImagerPlugin(_Plugin):
    mic_plugin_type = "imager"

    @classmethod
    def check_image_exists(self, destdir, apacking=None,
                                          images=[],
                                          release=None):

        # if it's a packing file, reset images
        if apacking:
            images = [apacking]

        # release option will override images
        if release is not None:
            images = [os.path.basename(destdir.rstrip('/'))]
            destdir = os.path.dirname(destdir.rstrip('/'))

        for name in images:
            if not name:
                continue

            image = os.path.join(destdir, name)
            if not os.path.exists(image):
                continue

            if msger.ask("Target image/dir: %s already exists, "
                         "clean up and continue?" % image):
                if os.path.isdir(image):
                    shutil.rmtree(image)
                else:
                    os.unlink(image)
            else:
                raise errors.Abort("Cancled")

    def do_create(self):
        pass

    def do_chroot(self):
        pass

class BackendPlugin(_Plugin):
    mic_plugin_type="backend"

    # suppress the verbose rpm warnings
    if msger.get_loglevel() != 'debug':
        import rpm
        rpm.setVerbosity(rpm.RPMLOG_ERR)

    def addRepository(self):
        pass

def get_plugins(typen):
    ps = ImagerPlugin.get_plugins()
    if typen in ps:
        return ps[typen]
    else:
        return None

__all__ = ['ImagerPlugin', 'BackendPlugin', 'get_plugins']
