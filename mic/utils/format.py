#!/usr/bin/python3
#
# Copyright (c) 2020 Jolla Ltd.
# Copyright (c) 2020 Open Mobile Platform LLC
# Contact: Juho Hämäläinen <juho.hamalainen@jolla.com>
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


# Convert all bytes type objects to str, goes
# through lists and dicts recursively.
def bytes_to_string(source):
    if source is None:
        return None

    elif isinstance(source, bytes):
        return source.decode()

    elif isinstance(source, list):
        ret = []
        for v in source:
            ret.append(bytes_to_string(v))
        return ret

    elif isinstance(source, dict):
        ret = {}
        for k, v in source.items():
            ret[bytes_to_string(k)] = bytes_to_string(v)
        return ret

    return source
