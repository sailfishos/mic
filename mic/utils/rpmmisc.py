# This file is part of mic
#
# Copyright (c) 2008, 2009, 2010, 2011 Intel, Inc.
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

import os, sys, re
import fcntl
import struct
import termios
import tempfile
import shutil
import urllib
import rpm
import hashlib
from mic.utils.format import bytes_to_string
from mic import msger
from .errors import CreatorError
from .proxy import get_proxy_for
from . import runner
from urlgrabber import grabber

def myurlgrab(url, filename, proxies, progress_obj = None, ignore_404 = False):
    g = grabber.URLGrabber(netrc_optional=True)
    if progress_obj is None:
        progress_obj = TextProgress()

    if url.startswith("file:/"):
        file = url.replace("file:", "")
        if not os.path.exists(file):
            if ignore_404:
                return None
            else:
                raise CreatorError("URLGrabber error: can't find file %s" % file)
        runner.show(['cp', "-f", file, filename])
    else:
        try:
            filename = g.urlgrab(url = url, filename = filename,
                ssl_verify_host = False, ssl_verify_peer = False,
                proxies = proxies, http_headers = (('Pragma', 'no-cache'),),
                quote = 0, progress_obj = progress_obj)
        except grabber.URLGrabError as e:
            if e.errno == 14 and e.code in [404, 503] and ignore_404:
                return None
            else:
                raise CreatorError("URLGrabber error: %s - %s" % (url, e))

    return filename

def terminal_width(fd=1):
    """ Get the real terminal width """
    try:
        buf = 'abcdefgh'
        buf = fcntl.ioctl(fd, termios.TIOCGWINSZ, buf)
        return struct.unpack('hhhh', buf)[1]
    except: # IOError
        return 80

def truncate_url(url, width):
    return os.path.basename(url)[0:width]

class TextProgress(object):
    # make the class as singleton
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TextProgress, cls).__new__(cls, *args, **kwargs)

        return cls._instance

    def __init__(self, totalnum = None):
        self.total = totalnum
        self.counter = 1

    def start(self, filename, url, *args, **kwargs):
        self.url = url
        self.termwidth = terminal_width()
        msger.info("\r%-*s" % (self.termwidth, " "))
        if self.total is None:
            msger.info("\rRetrieving %s ..." % truncate_url(self.url, self.termwidth - 15))
        else:
            msger.info("\rRetrieving %s [%d/%d] ..." % (truncate_url(self.url, self.termwidth - 25), self.counter, self.total))

    def update(self, *args):
        pass

    def end(self, *args):
        if self.counter == self.total:
            msger.raw("\n")

        if self.total is not None:
            self.counter += 1

class RPMInstallCallback:
    """ Command line callback class for callbacks from the RPM library.
    """

    def __init__(self, ts, output=1):
        self.output = output
        self.callbackfilehandles = {}
        self.total_actions = 0
        self.total_installed = 0
        self.installed_pkg_names = []
        self.total_removed = 0
        self.mark = "+"
        self.marks = 40
        self.lastmsg = None
        self.tsInfo = None # this needs to be set for anything else to work
        self.ts = ts
        self.filelog = False
        self.logString = []
        self.headmsg = "Installing"

    def _dopkgtup(self, hdr):
        tmpepoch = hdr['epoch']
        if tmpepoch is None: epoch = '0'
        else: epoch = str(tmpepoch)

        return (bytes_to_string(hdr['name']),
                bytes_to_string(hdr['arch']),
                epoch,
                bytes_to_string(hdr['version']),
                bytes_to_string(hdr['release']))

    def _makeHandle(self, hdr):
        handle = '%s:%s.%s-%s-%s' % (hdr['epoch'], hdr['name'], hdr['version'],
          hdr['release'], hdr['arch'])

        return handle

    def _localprint(self, msg):
        if self.output:
            msger.info(msg)

    def _makefmt(self, percent, progress = True):
        l = len(str(self.total_actions))
        size = "%s.%s" % (l, l)
        fmt_done = "[%" + size + "s/%" + size + "s]"
        done = fmt_done % (self.total_installed + self.total_removed,
                           self.total_actions)
        marks = self.marks - (2 * l)
        width = "%s.%s" % (marks, marks)
        fmt_bar = "%-" + width + "s"
        if progress:
            bar = fmt_bar % (self.mark * int(marks * (percent / 100.0)), )
            fmt = "\r  %-10.10s: %-20.20s " + bar + " " + done
        else:
            bar = fmt_bar % (self.mark * marks, )
            fmt = "  %-10.10s: %-20.20s "  + bar + " " + done
        return fmt

    def _logPkgString(self, hdr):
        """return nice representation of the package for the log"""
        (n,a,e,v,r) = self._dopkgtup(hdr)
        if e == '0':
            pkg = '%s.%s %s-%s' % (n, a, v, r)
        else:
            pkg = '%s.%s %s:%s-%s' % (n, a, e, v, r)

        return pkg

    def callback(self, what, bytes, total, h, user):
        if what == rpm.RPMCALLBACK_TRANS_START:
            pass

        elif what == rpm.RPMCALLBACK_TRANS_PROGRESS:
            pass

        elif what == rpm.RPMCALLBACK_TRANS_STOP:
            if bytes == 6:
                self.total_actions = total
                self.total_installed = 0
                self.total_removed = 0

        elif what == rpm.RPMCALLBACK_INST_OPEN_FILE:
            self.lastmsg = None
            hdr = None
            if h is not None:
                try:
                    hdr, rpmloc = h
                except:
                    rpmloc = h
                    hdr = readRpmHeader(self.ts, h)

                handle = self._makeHandle(hdr)
                fd = os.open(rpmloc, os.O_RDONLY)
                self.callbackfilehandles[handle]=fd
                self.total_installed += 1
                self.installed_pkg_names.append(hdr['name'])
                return fd
            else:
                self._localprint("No header - huh?")

        elif what == rpm.RPMCALLBACK_INST_CLOSE_FILE:
            hdr = None
            if h is not None:
                try:
                    hdr, rpmloc = h
                except:
                    rpmloc = h
                    hdr = readRpmHeader(self.ts, h)

                handle = self._makeHandle(hdr)
                os.close(self.callbackfilehandles[handle])
                fd = 0

                # log stuff
                #pkgtup = self._dopkgtup(hdr)
                self.logString.append(self._logPkgString(hdr))

        elif what == rpm.RPMCALLBACK_INST_PROGRESS:
            if h is not None:
                percent = (self.total_installed*100)/self.total_actions
                if total > 0:
                    try:
                        hdr, rpmloc = h
                    except:
                        rpmloc = h

                    m = re.match("(.*)-(\d+.*)-(\d+\.\d+)\.(.+)\.rpm", os.path.basename(rpmloc))
                    if m:
                        pkgname = m.group(1)
                    else:
                        pkgname = os.path.basename(rpmloc)
                if self.output:
                    fmt = self._makefmt(percent)
                    msg = fmt % (self.headmsg, pkgname)
                    if msg != self.lastmsg:
                        self.lastmsg = msg

                        msger.info(msg)

                        if self.total_installed == self.total_actions:
                            msger.verbose("Installed packages:")
                            msger.verbose('\n'.join(self.logString))

        elif what == rpm.RPMCALLBACK_UNINST_START:
            pass

        elif what == rpm.RPMCALLBACK_UNINST_PROGRESS:
            pass

        elif what == rpm.RPMCALLBACK_UNINST_STOP:
            self.total_removed += 1

        elif what == rpm.RPMCALLBACK_REPACKAGE_START:
            pass

        elif what == rpm.RPMCALLBACK_REPACKAGE_STOP:
            pass

        elif what == rpm.RPMCALLBACK_REPACKAGE_PROGRESS:
            pass

def readRpmHeader(ts, filename):
    """ Read an rpm header. """

    fd = os.open(filename, os.O_RDONLY)
    h = ts.hdrFromFdno(fd)
    os.close(fd)
    return h

def splitFilename(filename):
    """ Pass in a standard style rpm fullname

        Return a name, version, release, epoch, arch, e.g.::
            foo-1.0-1.i386.rpm returns foo, 1.0, 1, i386
            1:bar-9-123a.ia64.rpm returns bar, 9, 123a, 1, ia64
    """

    if filename[-4:] == '.rpm':
        filename = filename[:-4]

    archIndex = filename.rfind('.')
    arch = filename[archIndex+1:]

    relIndex = filename[:archIndex].rfind('-')
    rel = filename[relIndex+1:archIndex]

    verIndex = filename[:relIndex].rfind('-')
    ver = filename[verIndex+1:relIndex]

    epochIndex = filename.find(':')
    if epochIndex == -1:
        epoch = ''
    else:
        epoch = filename[:epochIndex]

    name = filename[epochIndex + 1:verIndex]
    return name, ver, rel, epoch, arch

def getCanonX86Arch(arch):
    #
    if arch == "i586":
        f = open("/proc/cpuinfo", "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if line.startswith("model name") and line.find("Geode(TM)") != -1:
                return "geode"
        return arch
    # only athlon vs i686 isn't handled with uname currently
    if arch != "i686":
        return arch

    # if we're i686 and AuthenticAMD, then we should be an athlon
    f = open("/proc/cpuinfo", "r")
    lines = f.readlines()
    f.close()
    for line in lines:
        if line.startswith("vendor") and line.find("AuthenticAMD") != -1:
            return "athlon"
        # i686 doesn't guarantee cmov, but we depend on it
        elif line.startswith("flags") and line.find("cmov") == -1:
            return "i586"

    return arch

def getCanonX86_64Arch(arch):
    if arch != "x86_64":
        return arch

    vendor = None
    f = open("/proc/cpuinfo", "r")
    lines = f.readlines()
    f.close()
    for line in lines:
        if line.startswith("vendor_id"):
            vendor = line.split(':')[1]
            break
    if vendor is None:
        return arch

    if vendor.find("Authentic AMD") != -1 or vendor.find("AuthenticAMD") != -1:
        return "amd64"
    if vendor.find("GenuineIntel") != -1:
        return "ia32e"
    return arch

def getCanonArch():
    arch = os.uname()[4]

    if (len(arch) == 4 and arch[0] == "i" and arch[2:4] == "86"):
        return getCanonX86Arch(arch)

    if arch == "x86_64":
        return getCanonX86_64Arch(arch)

    return arch

# Copy from libsatsolver:poolarch.c, with cleanup
archPolicies = {
    "x86_64":       "x86_64:i686:i586:i486:i386",
    "i686":         "i686:i586:i486:i386",
    "i586":         "i586:i486:i386",
    "i486":         "i486:i386",
    "ia64":         "ia64:i686:i586:i486:i386",
    "aarch64":      "aarch64",
    "armv7tnhl":    "armv7tnhl:armv7thl:armv7nhl:armv7hl",
    "armv7thl":     "armv7thl:armv7hl",
    "armv7nhl":     "armv7nhl:armv7hl",
    "armv7hl":      "armv7hl",
    "armv7l":       "armv7l:armv6l:armv5tejl:armv5tel:armv5l:armv4tl:armv4l:armv3l",
    "armv6l":       "armv6l:armv5tejl:armv5tel:armv5l:armv4tl:armv4l:armv3l",
    "armv5tejl":    "armv5tejl:armv5tel:armv5l:armv4tl:armv4l:armv3l",
    "armv5tel":     "armv5tel:armv5l:armv4tl:armv4l:armv3l",
    "armv5l":       "armv5l:armv4tl:armv4l:armv3l",
    "mipsel":       "mipsel",
}

# dict mapping arch -> ( multicompat, best personality, biarch personality )
multilibArches = {
    "x86_64":  ( "athlon", "x86_64", "athlon" ),
}

# from yumUtils.py
arches = {
    # ia32
    "athlon": "i686",
    "i686": "i586",
    "geode": "i586",
    "i586": "i486",
    "i486": "i386",
    "i386": "noarch",

    # amd64
    "x86_64": "athlon",
    "amd64": "x86_64",
    "ia32e": "x86_64",

    # arm
    "armv7tnhl": "armv7nhl",
    "armv7nhl": "armv7hl",
    "armv7hl": "noarch",
    "armv7l": "armv6l",
    "armv6l": "armv5tejl",
    "armv5tejl": "armv5tel",
    "armv5tel": "noarch",

    #itanium
    "ia64": "noarch",
}

def isMultiLibArch(arch=None):
    """returns true if arch is a multilib arch, false if not"""
    if arch is None:
        arch = getCanonArch()

    if arch not in arches: # or we could check if it is noarch
        return False

    if arch in multilibArches:
        return True

    if arches[arch] in multilibArches:
        return True

    return False

def getBaseArch():
    myarch = getCanonArch()
    if myarch not in arches:
        return myarch

    if isMultiLibArch(arch=myarch):
        if myarch in multilibArches:
            return myarch
        else:
            return arches[myarch]

    if myarch in arches:
        basearch = myarch
        value = arches[basearch]
        while value != 'noarch':
            basearch = value
            value = arches[basearch]

        return basearch

def checkRpmIntegrity(bin_rpm, package):
    return runner.quiet([bin_rpm, "-K", "--nosignature", package])

def checkRpmChecksum(package, checksum):
    # The checksum from rpm includes a preceding type .. eg: sha256-834561aa3...
    (sumtype, csum) = str(checksum).split("-")
    h = hashlib.new(sumtype)
    with open(package, "rb") as f:
        for chunk in iter(lambda: f.read(512*h.block_size), b''): 
            h.update(chunk)
    if h.hexdigest() == csum:
        return True
    msger.warning("package %s %s checksum %s from repo.xml is not same as the cached rpm digest %s-%s " \
                  % (package, sumtype, checksum, sumtype, h.hexdigest()))
    return False

def checkSig(ts, package):
    """ Takes a transaction set and a package, check it's sigs,
        return 0 if they are all fine
        return 1 if the gpg key can't be found
        return 2 if the header is in someway damaged
        return 3 if the key is not trusted
        return 4 if the pkg is not gpg or pgp signed
    """

    value = 0
    currentflags = ts.setVSFlags(0)
    fdno = os.open(package, os.O_RDONLY)
    try:
        hdr = ts.hdrFromFdno(fdno)

    except rpm.error as e:
        if str(e) == "public key not availaiable":
            value = 1
        if str(e) == "public key not available":
            value = 1
        if str(e) == "public key not trusted":
            value = 3
        if str(e) == "error reading package header":
            value = 2
    else:
        error, siginfo = getSigInfo(hdr)
        if error == 101:
            os.close(fdno)
            del hdr
            value = 4
        else:
            del hdr

    try:
        os.close(fdno)
    except OSError:
        pass

    ts.setVSFlags(currentflags) # put things back like they were before
    return value

def getSigInfo(hdr):
    """ checks signature from an hdr hand back signature information and/or
        an error code
    """

    import locale
    locale.setlocale(locale.LC_ALL, 'C')

    string = '%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{(none)}|}|}|}|'
    siginfo = hdr.sprintf(string)
    if siginfo != '(none)':
        error = 0
        sigtype, sigdate, sigid = siginfo.split(',')
    else:
        error = 101
        sigtype = 'MD5'
        sigdate = 'None'
        sigid = 'None'

    infotuple = (sigtype, sigdate, sigid)
    return error, infotuple

def _pager_file(savepath):

    if os.path.splitext(savepath)[1].upper() in ('.HTM', '.HTML'):
        pagers = ('w3m', 'links', 'lynx', 'less', 'more')
    else:
        pagers = ('less', 'more')

    file_showed = False
    for pager in pagers:
        cmd = "%s %s" % (pager, savepath)
        try:
            os.system(cmd)
        except OSError:
            continue
        else:
            file_showed = True
            break

    if not file_showed:
        f = open(savepath)
        msger.raw(f.read())
        f.close()
        msger.pause()

def checkRepositoryEULA(name, repo):
    """ This function is to check the EULA file if provided.
        return True: no EULA or accepted
        return False: user declined the EULA
    """
    proxies = {}
    proxy = repo.proxy

    if proxy:
        proxy_username = repo.proxy_username
        proxy_password = repo.proxy_password

        if proxy_username:
            proxy_netloc = urllib.parse.urlsplit(proxy).netloc
            if proxy_password:
                proxy = 'http://%s:%s@%s' % (proxy_username, proxy_password, proxy_netloc)
            else:
                proxy = 'http://%s@%s' % (proxy_username, proxy_netloc)

    else:
        proxy = get_proxy_for(repo.baseurl[0])

    if proxy:
        proxies = {str(repo.baseurl[0].split(':')[0]): str(proxy)}

    # download all remote files to one temp dir
    baseurl = None
    repo_lic_dir = tempfile.mkdtemp(prefix = 'repolic')

    for url in repo.baseurl:

        # try to download
        repo_eula_url = urllib.parse.urljoin(url, "LICENSE.txt")

        repo_eula_path = myurlgrab(repo_eula_url,
                                   os.path.join(repo_lic_dir, repo.id + '_LICENSE.txt'),
                                   proxies, ignore_404 = True)
        if repo_eula_path:
            # found
            baseurl = url
            break

    if not baseurl:
        shutil.rmtree(repo_lic_dir) #cleanup
        return True

    # show the license file
    msger.info('For the software packages in this yum repo:')
    msger.info('    %s: %s' % (name, baseurl))
    msger.info('There is an "End User License Agreement" file that need to be checked.')
    msger.info('Please read the terms and conditions outlined in it and answer the followed qustions.')
    msger.pause()

    _pager_file(repo_eula_path)

    # Asking for the "Accept/Decline"
    if not msger.ask('Would you agree to the terms and conditions outlined in the above End User License Agreement?'):
        msger.warning('Will not install pkgs from this repo.')
        shutil.rmtree(repo_lic_dir) #cleanup
        return False

    # try to find support_info.html for extra infomation
    repo_info_url = urllib.parse.urljoin(baseurl, "support_info.html")
    repo_info_path = myurlgrab(repo_eula_url,
                               os.path.join(repo_lic_dir, repo.id + '_LICENSE.txt'),
                               proxies, ignore_404 = True)
    if repo_info_path:
        msger.info('There is one more file in the repo for additional support information, please read it')
        msger.pause()
        _pager_file(repo_info_path)

    #cleanup
    shutil.rmtree(repo_lic_dir)
    return True
