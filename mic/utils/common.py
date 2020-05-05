#!/usr/bin/python3
#
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

import os, errno
from mic import rt_util
from mic.utils import misc, errors
from mic.conf import configmgr
from mic.plugin import pluginmgr

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

def creatoropts(args):

    if not args:
        raise errors.Usage("need one argument as the path of ks file")

    if len(args) != 1:
        raise errors.Usage("Extra arguments given")

    creatoropts = configmgr.create
    ksconf = args[0]

    if not os.path.exists(ksconf):
        raise errors.CreatorError("Can't find the file: %s" % ksconf)

    if not 'record_pkgs' in creatoropts:
        creatoropts['record_pkgs'] = []

    if creatoropts['release'] is not None:
        if 'name' not in creatoropts['record_pkgs']:
            creatoropts['record_pkgs'].append('name')

    ksconf = misc.normalize_ksfile(ksconf, creatoropts['tokenmap'])
    configmgr._ksconf = ksconf

    # Called After setting the configmgr._ksconf as the creatoropts['name'] is reset there.
    if creatoropts['release'] is not None:
        creatoropts['outdir'] = "%s/%s/images/%s/" % (creatoropts['outdir'], creatoropts['release'], creatoropts['name'])

    # try to find the pkgmgr
    pkgmgr = None
    for (key, pcls) in pluginmgr.get_plugins('backend').items():
        if key == creatoropts['pkgmgr']:
            pkgmgr = pcls
            break

    if not pkgmgr:
        pkgmgrs = list(pluginmgr.get_plugins('backend').keys())
        raise errors.CreatorError("Can't find package manager: %s (availables: %s)" % (creatoropts['pkgmgr'], ', '.join(pkgmgrs)))

    creatoropts['pkgmgr_pcls'] = pkgmgr

    if creatoropts['runtime']:
        rt_util.runmic_in_runtime(creatoropts['runtime'], creatoropts, ksconf, None)

    # Write the normalized kickstart to outdir
    # It has to be done this way in case the source ks is same as dest ks
    mkdir_p(creatoropts['outdir'])
    dst_ks = "%s/%s.ks" % (creatoropts['outdir'], creatoropts['name'])
    with open(configmgr._ksconf, 'r') as src_ksf:
        src_ks = src_ksf.read()
        with open(dst_ks, 'w') as dst_ksf:
            dst_ksf.write(src_ks)

    creatoropts['dst_ks'] = dst_ks

    return creatoropts

