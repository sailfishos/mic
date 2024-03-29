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

import os, sys
from . import msger
from . import pluginbase
from mic.conf import configmgr
from mic.utils import errors

__ALL__ = ['PluginMgr', 'pluginmgr']

PLUGIN_TYPES = ["imager", "backend"] # TODO  "hook"

class PluginMgr(object):
    plugin_dirs = {}

    # make the manager class as singleton
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PluginMgr, cls).__new__(cls, *args, **kwargs)

        return cls._instance

    def __init__(self):
        self.plugin_dir = configmgr.common['plugin_dir']

    def append_dirs(self, dirs):
        for path in dirs:
            self._add_plugindir(path)

        # load all the plugins AGAIN
        self._load_all()

    def _add_plugindir(self, path):
        path = os.path.abspath(os.path.expanduser(path))

        if not os.path.isdir(path):
            msger.warning("Plugin dir is not a directory or does not exist: %s"\
                          % path)
            return

        if path not in self.plugin_dirs:
            self.plugin_dirs[path] = False
            # the value True/False means "loaded"

    def _load_all(self):
        for (pdir, loaded) in self.plugin_dirs.items():
            if loaded: continue

            sys.path.insert(0, pdir)
            for mod in [x[:-3] for x in os.listdir(pdir) if x.endswith(".py")]:
                if mod and mod != '__init__':
                    if mod in sys.modules:
                        #self.plugin_dirs[pdir] = True
                        msger.warning("Module %s already exists, skip" % mod)
                    else:
                        try:
                            pymod = __import__(mod)
                            self.plugin_dirs[pdir] = True
                            msger.debug("Plugin module %s:%s imported"\
                                        % (mod, pymod.__file__))
                        except ImportError as e:
                            msger.warning('Loading failed, skip plugin %s/%s'\
                                          % (os.path.basename(pdir), mod))

            del(sys.path[0])

    def get_plugins(self, ptype):
        """ the return value is dict of name:class pairs """

        if ptype not in PLUGIN_TYPES:
            raise errors.CreatorError('%s is not valid plugin type' % ptype)

        self._add_plugindir(os.path.join(self.plugin_dir, ptype))
        self._load_all()

        return pluginbase.get_plugins(ptype)

pluginmgr = PluginMgr()
