# This file is part of mic
#
# Copyright (c) 2007 Red Hat, Inc.
# Copyright (c) 2011 Intel, Inc.
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

class CreatorError(Exception):
    """An exception base class for all imgcreate errors."""
    keyword = '<creator>'

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.keyword + str(self.msg)

class Usage(CreatorError):
    keyword = '<usage>'

    def __str__(self):
        return self.keyword + str(self.msg) + ', please use "--help" for more info'

class Abort(CreatorError):
    keyword = ''

class ConfigError(CreatorError):
    keyword = '<config>'

class KsError(CreatorError):
    keyword = '<kickstart>'

class RepoError(CreatorError):
    keyword = '<repo>'

class RpmError(CreatorError):
    keyword = '<rpm>'

class MountError(CreatorError):
    keyword = '<mount>'

class SnapshotError(CreatorError):
    keyword = '<snapshot>'

class SquashfsError(CreatorError):
    keyword = '<squashfs>'

class BootstrapError(CreatorError):
    keyword = '<bootstrap>'

class RuntimeError(CreatorError):
    keyword = '<runtime>'
