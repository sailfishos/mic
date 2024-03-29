# This file is part of mic
#
# Copyright (c) 2010, 2011 Intel, Inc.
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
import urllib
import rpm

import zypp

from mic import msger
from mic.kickstart import ksparser, ksconstants
from mic.utils import misc, rpmmisc, runner, fs_related
from mic.utils.proxy import get_proxy_for
from mic.utils.errors import CreatorError, RepoError, RpmError
from mic.imager.baseimager import BaseImageCreator
from mic.utils.format import bytes_to_string

from functools import cmp_to_key

def cmpEVR(ed1, ed2):
    (e1, v1, r1) = list(map(str, [ed1.epoch(), ed1.version(), ed1.release()]))
    (e2, v2, r2) = list(map(str, [ed2.epoch(), ed2.version(), ed2.release()]))
    return rpm.labelCompare((e1, v1, r1), (e2, v2, r2))

def cmpPackage(x, y):
    # Note: lower value means higher priority
    result = y.repoInfo().priority() - x.repoInfo().priority()
    return cmpEVR(x.edition(), y.edition()) if result == 0 else result

class RepositoryStub:
    def __init__(self):
        self.name = None
        self.baseurl = []
        self.mirrorlist = None
        self.proxy = None
        self.proxy_username = None
        self.proxy_password = None

        self.enabled = True
        self.autorefresh = True
        self.keeppackages = True
        self.priority = None

from mic.pluginbase import BackendPlugin
class Zypp(BackendPlugin):
    name = 'zypp'

    def __init__(self, target_arch, instroot, cachedir):
        self.cachedir = cachedir
        self.instroot  = instroot
        self.target_arch = target_arch

        self.__pkgs_license = {}
        self.__pkgs_content = {}
        self.__pkgs_urls = {}
        self.repos = []
        self.to_deselect = []
        self.localpkgs = {}
        self.repo_manager = None
        self.repo_manager_options = None
        self.Z = None
        self.ts = None
        self.ts_pre = None
        self.incpkgs = {}
        self.excpkgs = {}
        self.pre_pkgs = []
        self.probFilterFlags = [ rpm.RPMPROB_FILTER_OLDPACKAGE,
                                 rpm.RPMPROB_FILTER_REPLACEPKG ]

        self.has_prov_query = True

    def doFileLogSetup(self, uid, logfile):
        # don't do the file log for the livecd as it can lead to open fds
        # being left and an inability to clean up after ourself
        pass

    def closeRpmDB(self):
        pass

    def close(self):
        if self.ts:
            self.ts.closeDB()
            self.ts = None

        if self.ts_pre:
            self.ts_pre.closeDB()
            self.ts = None

        self.closeRpmDB()

        if not os.path.exists("/etc/fedora-release") and \
           not os.path.exists("/etc/sailfish-release") and \
           not os.path.exists("/etc/meego-release"):
            for i in range(3, os.sysconf("SC_OPEN_MAX")):
                try:
                    os.close(i)
                except:
                    pass

    def __del__(self):
        self.close()

    def _cleanupRpmdbLocks(self, installroot):
        # cleans up temporary files left by bdb so that differing
        # versions of rpm don't cause problems
        import glob
        for f in glob.glob(installroot + "/var/lib/rpm/__db*"):
            os.unlink(f)

    def setup(self):
        self._cleanupRpmdbLocks(self.instroot)

    def whatObsolete(self, pkg, flag, evr):
        query = zypp.PoolQuery()
        query.addKind(zypp.ResKind.package)
        query.addAttribute(zypp.SolvAttr.obsoletes, pkg)
        query.setMatchExact()
        if flag and evr:
            query.addAttribute(zypp.SolvAttr.edition, flag+evr)

        for pi in sorted(query.queryResults(self.Z.pool()),
                         key=cmp_to_key(lambda x,y: cmpPackage(self._castKind(x), self._castKind(y))),
                         reverse=True):
            return pi
        return None

    def _splitPkgString(self, pkg):
        flags = [">=", "<=", "=", ">", "<"]
        evr = None
        f = None
        for flag in flags:
          if flag in pkg:
              f = flag
              pkg, evr = pkg.rsplit(flag,1)
              break

        sp = pkg.rsplit(".",1)
        name = sp[0]
        arch = None
        if len(sp) == 2:
            arch = sp[1]
            sysarch = zypp.Arch(self.target_arch)
            if not zypp.Arch(arch).compatible_with (sysarch):
                arch = None
                name = ".".join(sp)
        return name, arch, f, evr

    def _castKind(self, poolitem):
        item = None
        if zypp.isKindPattern(poolitem):
            item = zypp.asKindPattern(poolitem)
        elif zypp.isKindPackage(poolitem):
            item = zypp.asKindPackage(poolitem)
        elif zypp.isKindResolvable(poolitem):
            item = zypp.asKindResolvable(poolitem)
        return item

    def selectPackage(self, pkg):
        """Select a given package or package pattern, can be specified
        with name.arch or name* or *name
        """

        if not self.Z:
            self.__initialize_zypp()

        def markPoolItem(obs, pi):
            if obs == None:
                pi.status().setToBeInstalled (zypp.ResStatus.USER)
            else:
                obs.status().setToBeInstalled (zypp.ResStatus.USER)

        found = False
        startx = pkg.startswith("*")
        endx = pkg.endswith("*")
        ispattern = startx or endx
        name, arch, flag, evr = self._splitPkgString(pkg)
        msger.debug("selectPackage %s %s %s %s" % (name, arch, flag, evr))

        q = zypp.PoolQuery()
        q.addKind(zypp.ResKind.package)

        if ispattern:
            if startx and not endx:
                pattern = '%s$' % (pkg[1:])
            if endx and not startx:
                pattern = '^%s' % (pkg[0:-1])
            if endx and startx:
                pattern = '%s' % (pkg[1:-1])
            q.setMatchRegex()
            q.addAttribute(zypp.SolvAttr.name,pattern)

        elif arch:
            q.setMatchExact()
            q.addAttribute(zypp.SolvAttr.name,name)

        elif flag and evr:
            q.setMatchExact()
            q.addAttribute(zypp.SolvAttr.name,name)
            q.addAttribute(zypp.SolvAttr.edition,flag+evr)

        else:
            q.setMatchExact()
            q.addAttribute(zypp.SolvAttr.name,pkg)


        for item in sorted(
                        q.queryResults(self.Z.pool()),
                        key=cmp_to_key(lambda x,y: cmpPackage(self._castKind(x), self._castKind(y))),
                        reverse=True):

            xitem = self._castKind(item)
            msger.debug("item found %s %s" % (xitem.name(), xitem.edition()))
            if xitem.name() in list(self.excpkgs.keys()) and \
               self.excpkgs[xitem.name()] == xitem.repoInfo().name():
                continue
            if xitem.name() in list(self.incpkgs.keys()) and \
               self.incpkgs[xitem.name()] != xitem.repoInfo().name():
                continue

            found = True
            obspkg = self.whatObsolete(xitem.name(), flag, evr)
            if obspkg:
                msger.debug("selecting %s %s which obsoletes %s" % (self._castKind(obspkg).name(), self._castKind(obspkg).edition(), xitem.name()))

            if arch:
                if arch == str(xitem.arch()):
                    item.status().setToBeInstalled (zypp.ResStatus.USER)
            else:
                markPoolItem(obspkg, item)
            if not ispattern:
                break

        # Can't match using package name, then search from packge
        # provides infomation
        if found == False and not ispattern:
            msger.debug("package name %s not found searching provides" % name)
            q.addAttribute(zypp.SolvAttr.provides, name)
            q.addAttribute(zypp.SolvAttr.name,'')

            if flag and evr:
                q.addAttribute(zypp.SolvAttr.edition,flag+evr)

            for item in sorted(
                            q.queryResults(self.Z.pool()),
                            key=cmp_to_key(lambda x,y: cmpPackage(self._castKind(x), self._castKind(y))),
                            reverse=True):

                xitem = self._castKind(item)
                msger.debug("item found %s %s" % (xitem.name(), xitem.edition()))
                if xitem.name() in list(self.excpkgs.keys()) and \
                   self.excpkgs[xitem.name()] == xitem.repoInfo().name():
                    continue
                if xitem.name() in list(self.incpkgs.keys()) and \
                   self.incpkgs[xitem.name()] != xitem.repoInfo().name():
                    continue

                found = True
                obspkg = self.whatObsolete(xitem.name(), flag, evr)
                if obspkg:
                    msger.debug("selecting %s %s which obsoletes %s" % (self._castKind(obspkg).name(), self._castKind(obspkg).edition(), xitem.name()))

                markPoolItem(obspkg, item)
                break

        if found:
            return None
        else:
            raise CreatorError("Unable to find package: %s" % (pkg,))

    def inDeselectPackages(self, item):
        """check if specified pacakges are in the list of inDeselectPackages
        """

        name = item.name()
        for pkg in self.to_deselect:
            startx = pkg.startswith("*")
            endx = pkg.endswith("*")
            ispattern = startx or endx
            pkgname, pkgarch, flag, evr = self._splitPkgString(pkg)
            if not ispattern:
                if pkgarch:
                    if name == pkgname and str(item.arch()) == pkgarch:
                        return True;
                else:
                    if name == pkgname:
                        return True;
            else:
                if startx and name.endswith(pkg[1:]):
                        return True;
                if endx and name.startswith(pkg[:-1]):
                        return True;

        return False;

    def deselectPackage(self, pkg):
        """collect packages should not be installed"""
        msger.debug("marking %s for deselect" % pkg)
        self.to_deselect.append(pkg)

    def derefGroups(self):
        self.buildTransaction()

        todo = zypp.GetResolvablesToInsDel(self.Z.pool())
        installed_pkgs = todo._toInstall
        groups_found = False
        for xitem in installed_pkgs:
            if zypp.isKindPattern(xitem):
                item = self._castKind(xitem)
                msger.debug("%s is going to be derefed" % item.name())
                self.selectGroup(item.name())
                groups_found = True

        return groups_found

    def selectGroup(self, grp, include = ksconstants.GROUP_DEFAULT):
        if not self.Z:
            self.__initialize_zypp()
        found = False
        q=zypp.PoolQuery()
        q.addKind(zypp.ResKind.pattern)
        msger.debug("looking for %s" % grp)
        for item in sorted(
                        q.queryResults(self.Z.pool()),
                        key=cmp_to_key(lambda x,y: cmpPackage(self._castKind(x), self._castKind(y))),
                        reverse=True):
            xitem = self._castKind(item)
            summary = "%s" % xitem.summary()
            name = "%s" % xitem.name()
            msger.debug("checking %s version %s" % (name, xitem.edition()))
            if name == grp or summary == grp:
                found = True
                msger.info("marking pattern %s %s to be installed" % ( name, xitem.edition() ))
                item.status().setToBeInstalled (zypp.ResStatus.USER)
                break

        if found:
            if include == ksconstants.GROUP_REQUIRED:
                list(map(
                    lambda p: self.deselectPackage(p),
                    list(grp.default_packages.keys())))

            return None
        else:
            raise CreatorError("Unable to find pattern: %s" % (grp,))

    def addRepository(self, name,
                            url = None,
                            mirrorlist = None,
                            proxy = None,
                            proxy_username = None,
                            proxy_password = None,
                            inc = None,
                            exc = None,
                            ssl_verify = True,
                            cost=None,
                            priority=None):
        # TODO: Handle cost attribute for repos

        if not self.repo_manager:
            self.__initialize_repo_manager()

        if not proxy and url:
            proxy = get_proxy_for(url)

        repo = RepositoryStub()
        repo.name = name
        repo.id = name
        repo.proxy = proxy
        repo.proxy_username = proxy_username
        repo.proxy_password = proxy_password
        repo.ssl_verify = ssl_verify
        repo.baseurl.append(url)
        if inc:
            for pkg in inc:
                self.incpkgs[pkg] = name
        if exc:
            for pkg in exc:
                self.excpkgs[pkg] = name

        # check LICENSE files
        if not rpmmisc.checkRepositoryEULA(name, repo):
            msger.warning('skip repo:%s for failed EULA confirmation' % name)
            return None

        if mirrorlist:
            repo.mirrorlist = mirrorlist

        # Enable gpg check for verifying corrupt packages
        repo.gpgcheck = 0
        if priority:
            repo.priority = priority

        try:
            repo_info = zypp.RepoInfo()
            repo_info.setAlias(repo.name)
            repo_info.setName(repo.name)
            repo_info.setEnabled(repo.enabled)
            repo_info.setGpgCheck(repo.gpgcheck)
            repo_info.setAutorefresh(repo.autorefresh)
            repo_info.setKeepPackages(repo.keeppackages)
            baseurl = zypp.Url(repo.baseurl[0])
            if not ssl_verify:
                baseurl.setQueryParam("ssl_verify", "no")
            if proxy:
                scheme, host, path, parm, query, frag = urllib.parse.urlparse(proxy)

                proxyinfo = host.split(":")
                host = proxyinfo[0]

                port = "80"
                if len(proxyinfo) > 1:
                    port = proxyinfo[1]

                if proxy.startswith("socks") and len(proxy.rsplit(':', 1)) == 2:
                    host = proxy.rsplit(':', 1)[0]
                    port = proxy.rsplit(':', 1)[1]

                baseurl.setQueryParam ("proxy", host)
                baseurl.setQueryParam ("proxyport", port)

            repo.baseurl[0] = baseurl.asCompleteString()
            self.repos.append(repo)

            repo_info.addBaseUrl(baseurl)

            if repo.priority:
                repo_info.setPriority(repo.priority)

            self.repo_manager.addRepository(repo_info)

            self.__build_repo_cache(name)

        except RuntimeError as e:
            raise CreatorError(str(e))

        msger.verbose('repo: %s was added' % name)
        return repo

    def installHasFile(self, file):
        return False

    def preInstall(self, pkg):
        self.pre_pkgs.append(pkg)

    def runInstall(self, checksize = 0):
        #FIXME: WHY? os.environ["HOME"] = "/"
        os.environ["LD_PRELOAD"] = ""
        self.buildTransaction()

        todo = zypp.GetResolvablesToInsDel(self.Z.pool())
        installed_pkgs = todo._toInstall
        dlpkgs = []
        for xitem in installed_pkgs:
            if not zypp.isKindPattern(xitem):
                item = self._castKind(xitem)
                if not self.inDeselectPackages(item):
                    dlpkgs.append(item)
                    msger.debug("%s is going to be installed" % item.name())

        # record all pkg and the content
        localpkgs = list(self.localpkgs.keys())
        for package in dlpkgs:
            license = ''
            if package.name() in localpkgs:
                hdr = rpmmisc.readRpmHeader(self.ts, self.localpkgs[package.name()])
                pkg_long_name = misc.RPM_FMT % {
                                    'name': hdr['name'],
                                    'arch': hdr['arch'],
                                    'ver_rel': '%s-%s' % (hdr['version'],
                                                          hdr['release']),
                                }
                license = hdr['license']

            else:
                pkg_long_name = misc.RPM_FMT % {
                                    'name': package.name(),
                                    'arch': package.arch(),
                                    'ver_rel': package.edition(),
                                }

                license = package.license()

            self.__pkgs_content[pkg_long_name] = {} #TBD: to get file list
            self.__pkgs_urls[pkg_long_name] = self.get_url(package)

            if license in list(self.__pkgs_license.keys()):
                self.__pkgs_license[license].append(pkg_long_name)
            else:
                self.__pkgs_license[license] = [pkg_long_name]

        total_count = len(dlpkgs)
        cached_count = 0
        download_total_size = sum([int(x.downloadSize()) for x in dlpkgs])
        localpkgs = list(self.localpkgs.keys())

        msger.info("Checking packages cache and packages integrity ...")
        for po in dlpkgs:
            # Check if it is cached locally
            if po.name() in localpkgs:
                cached_count += 1
            else:
                local = self.getLocalPkgPath(po)
                if os.path.exists(local):
                    if self.checkPkg(local, po.checksum()) != 0:
                        os.unlink(local)
                    else:
                        download_total_size -= int(po.downloadSize())
                        cached_count += 1
        cache_avail_size = misc.get_filesystem_avail(self.cachedir)
        if cache_avail_size < download_total_size:
            raise CreatorError("No enough space used for downloading.")

        # record the total size of installed pkgs
        install_total_size = sum([int(x.installSize()) for x in dlpkgs])
        # check needed size before actually download and install

        # FIXME: for multiple partitions for loop type, check fails
        #        skip the check temporarily
        #if checksize and install_total_size > checksize:
        #    raise CreatorError("No enough space used for installing, "
        #                       "please resize partition size in ks file")

        download_count =  total_count - cached_count
        msger.info("%d packages to be installed, "
                   "%d packages gotten from cache, "
                   "%d packages to be downloaded" \
                   % (total_count, cached_count, download_count))

        try:
            if download_count > 0:
                msger.info("Downloading packages ...")
            self.downloadPkgs(dlpkgs, download_count)

            self.installPkgs(dlpkgs)

        except (RepoError, RpmError):
            raise
        except Exception as e:
            raise CreatorError("Package installation failed: %s" % (e,))

    def getAllContent(self):
        return self.__pkgs_content

    def getAllUrls(self):
        return self.__pkgs_urls

    def getPkgsLicense(self):
        return self.__pkgs_license

    def getFilelist(self, pkgname):
        if not pkgname:
            return None

        if not self.ts:
            self.__initialize_transaction()

        mi = self.ts.dbMatch('name', pkgname)
        for header in mi:
            return bytes_to_string(header['FILENAMES'])

    def __initialize_repo_manager(self):
        if self.repo_manager:
            return

        # Clean up repo metadata
        shutil.rmtree(self.cachedir + "/etc", ignore_errors = True)
        shutil.rmtree(self.cachedir + "/solv", ignore_errors = True)
        shutil.rmtree(self.cachedir + "/raw", ignore_errors = True)

        zypp.KeyRing.setDefaultAccept( zypp.KeyRing.ACCEPT_UNSIGNED_FILE
                                     | zypp.KeyRing.ACCEPT_VERIFICATION_FAILED
                                     | zypp.KeyRing.ACCEPT_UNKNOWNKEY
                                     | zypp.KeyRing.TRUST_KEY_TEMPORARILY
                                     )

        self.repo_manager_options = \
                zypp.RepoManagerOptions(zypp.Pathname(self.instroot))

        self.repo_manager_options.knownReposPath = \
                zypp.Pathname(self.cachedir + "/etc/zypp/repos.d")

        self.repo_manager_options.repoCachePath = \
                zypp.Pathname(self.cachedir)

        self.repo_manager_options.repoRawCachePath = \
                zypp.Pathname(self.cachedir + "/raw")

        self.repo_manager_options.repoSolvCachePath = \
                zypp.Pathname(self.cachedir + "/solv")

        self.repo_manager_options.repoPackagesCachePath = \
                zypp.Pathname(self.cachedir + "/packages")

        self.repo_manager = zypp.RepoManager(self.repo_manager_options)

    def __build_repo_cache(self, name):
        repo = self.repo_manager.getRepositoryInfo(name)
        if self.repo_manager.isCached(repo) or not repo.enabled():
            return

        msger.info('Refreshing repository: %s ...' % name)
        self.repo_manager.buildCache(repo, zypp.RepoManager.BuildIfNeeded)

    def __initialize_zypp(self):
        if self.Z:
            return

        zconfig = zypp.ZConfig_instance()

        # Set system architecture
        if self.target_arch:
            zconfig.setSystemArchitecture(zypp.Arch(self.target_arch))

        msger.info("zypp architecture is <%s>" % zconfig.systemArchitecture())

        # repoPackagesCachePath is corrected by this
        self.repo_manager = zypp.RepoManager(self.repo_manager_options)
        repos = self.repo_manager.knownRepositories()
        for repo in repos:
            if not repo.enabled():
                continue
            self.repo_manager.loadFromCache(repo)

        self.Z = zypp.ZYppFactory_instance().getZYpp()
        self.Z.initializeTarget(zypp.Pathname(self.instroot))
        self.Z.target().load()

    def buildTransaction(self):
        if not self.Z:
            self.__initialize_zypp()

        if not self.Z.resolver().resolvePool():
            probs = self.Z.resolver().problems()

            for problem in probs:
                description = bytes_to_string(problem.description())
                details = bytes_to_string(problem.details())
                msger.warning("repo problem: {}, {}".format(description, details))

            raise RepoError("found %d resolver problem, abort!" \
                            % len(probs))

    def getLocalPkgPath(self, po):
        repoinfo = po.repoInfo()
        cacheroot = repoinfo.packagesPath()
        location= po.location()
        rpmpath = str(location.filename())
        pkgpath = "%s/%s" % (cacheroot, os.path.basename(rpmpath))
        return pkgpath

    def installLocal(self, pkg, po=None, updateonly=False):
        if not self.ts:
            self.__initialize_transaction()

        solvfile = "%s/.solv" % (self.cachedir)

        rc, out = runner.runtool([fs_related.find_binary_path("rpms2solv"),
                                  pkg])
        if rc == 0:
            f = open(solvfile, "w+")
            f.write(out)
            f.close()

            warnmsg = self.Z.pool().loadRepoSolv(_solv, tmpRepo);(solvfile,
                                                     os.path.basename(pkg))
            if warnmsg:
                msger.warning(warnmsg)

            os.unlink(solvfile)
        else:
            msger.warning('Can not get %s solv data.' % pkg)

        hdr = rpmmisc.readRpmHeader(self.ts, pkg)
        arch = zypp.Arch(hdr['arch'])
        sysarch = zypp.Arch(self.target_arch)

        if arch.compatible_with (sysarch):
            pkgname = hdr['name']
            self.localpkgs[pkgname] = pkg
            self.selectPackage(pkgname)
            msger.info("Marking %s to be installed" % (pkg))

        else:
            msger.warning("Cannot add package %s to transaction. "
                          "Not a compatible architecture: %s" \
                          % (pkg, hdr['arch']))

    def downloadPkgs(self, package_objects, count):
        localpkgs = list(self.localpkgs.keys())
        progress_obj = rpmmisc.TextProgress(count)

        for po in package_objects:
            if po.name() in localpkgs:
                continue

            filename = self.getLocalPkgPath(po)
            if os.path.exists(filename):
                if self.checkPkg(filename, po.checksum()) == 0:
                    continue

            dirn = os.path.dirname(filename)
            if not os.path.exists(dirn):
                os.makedirs(dirn)

            url = self.get_url(po)
            proxies = self.get_proxies(po)

            try:
                filename = rpmmisc.myurlgrab(url,
                                             filename,
                                             proxies,
                                             progress_obj)
            except CreatorError:
                self.close()
                raise

    def preinstallPkgs(self):
        if not self.ts_pre:
            self.__initialize_transaction()

        self.ts_pre.order()
        cb = rpmmisc.RPMInstallCallback(self.ts_pre)
        cb.headmsg = "Preinstall"
        installlogfile = "%s/__catched_stderr.buf" % (self.instroot)

        # start to catch stderr output from librpm
        msger.enable_logstderr(installlogfile)

        errors = self.ts_pre.run(cb.callback, '')
        # stop catch
        msger.disable_logstderr()
        self.ts_pre.closeDB()
        self.ts_pre = None

        if errors is not None:
            if len(errors) == 0:
                msger.warning('scriptlet or other non-fatal errors occurred '
                              'during transaction.')

            else:
                for e in errors:
                    msger.warning(e[0])
                raise RepoError('Could not run transaction.')

    def installPkgs(self, package_objects):
        if not self.ts:
            self.__initialize_transaction()

        # Set filters
        probfilter = 0
        for flag in self.probFilterFlags:
            probfilter |= flag
        self.ts.setProbFilter(probfilter)
        self.ts_pre.setProbFilter(probfilter)

        localpkgs = list(self.localpkgs.keys())

        for po in package_objects:
            pkgname = po.name()
            if pkgname in localpkgs:
                rpmpath = self.localpkgs[pkgname]
            else:
                rpmpath = self.getLocalPkgPath(po)

            if not os.path.exists(rpmpath):
                # Maybe it is a local repo
                baseurl = str(po.repoInfo().baseUrls()[0])
                baseurl = baseurl.strip()

                location = po.location()
                location = str(location.filename())

                if baseurl.startswith("file:/"):
                    rpmpath = baseurl[5:] + "/%s" % (location)

            if not os.path.exists(rpmpath):
                raise RpmError("Error: %s doesn't exist" % rpmpath)

            h = rpmmisc.readRpmHeader(self.ts, rpmpath)

            if pkgname in self.pre_pkgs:
                msger.verbose("pre-install package added: %s" % pkgname)
                self.ts_pre.addInstall(h, rpmpath, 'u')

            self.ts.addInstall(h, rpmpath, 'u')

        unresolved_dependencies = self.ts.check()
        if not unresolved_dependencies:
            if self.pre_pkgs:
                self.preinstallPkgs()

            self.ts.order()
            cb = rpmmisc.RPMInstallCallback(self.ts)
            installlogfile = "%s/__catched_stderr.buf" % (self.instroot)

            # start to catch stderr output from librpm
            msger.enable_logstderr(installlogfile)

            errors = self.ts.run(cb.callback, '')
            # stop catch
            msger.disable_logstderr()
            self.ts.closeDB()
            self.ts = None

            if errors is not None:
                if len(errors) == 0:
                    msger.warning('scriptlet or other non-fatal errors occurred '
                                  'during transaction.')

                else:
                    for e in errors:
                        msger.warning(e[0])
                    raise RepoError('Could not run transaction.')

        else:
            for pkg, need, needflags, sense, key in unresolved_dependencies:
                package = '-'.join(pkg)

                if needflags == rpm.RPMSENSE_LESS:
                    deppkg = ' < '.join(need)
                elif needflags == rpm.RPMSENSE_EQUAL:
                    deppkg = ' = '.join(need)
                elif needflags == rpm.RPMSENSE_GREATER:
                    deppkg = ' > '.join(need)
                else:
                    deppkg = '-'.join(need)

                if sense == rpm.RPMDEP_SENSE_REQUIRES:
                    msger.warning("[%s] Requires [%s], which is not provided" \
                                  % (package, deppkg))

                elif sense == rpm.RPMDEP_SENSE_CONFLICTS:
                    msger.warning("[%s] Conflicts with [%s]" %(package,deppkg))

            raise RepoError("Unresolved dependencies, transaction failed.")

    def __initialize_transaction(self):
        if not self.ts:
            self.ts = rpm.TransactionSet(self.instroot)
            # Set to not verify DSA signatures.
            self.ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES|rpm._RPMVSF_NODIGESTS)

        if not self.ts_pre:
            self.ts_pre = rpm.TransactionSet(self.instroot)
            # Just unpack the files, don't run scripts
            self.ts_pre.setFlags(rpm.RPMTRANS_FLAG_ALLFILES | rpm.RPMTRANS_FLAG_NOSCRIPTS)
            # Set to not verify DSA signatures.
            self.ts_pre.setVSFlags(rpm._RPMVSF_NOSIGNATURES|rpm._RPMVSF_NODIGESTS)

    def checkPkg(self, pkg, checksum=None):
        ret = 1
        if not os.path.exists(pkg):
            return ret
        if checksum and not rpmmisc.checkRpmChecksum(pkg, checksum):
            msger.warning("package %s checksum mismatch - redownloading" \
                          % (pkg))
            return ret
        ret = rpmmisc.checkRpmIntegrity('rpm', pkg)
        if ret != 0:
            msger.warning("package %s is damaged: %s" \
                          % (os.path.basename(pkg), pkg))

        return ret

    def _add_prob_flags(self, *flags):
        for flag in flags:
           if flag not in self.probFilterFlags:
               self.probFilterFlags.append(flag)

    def get_proxies(self, pobj):
        if not pobj:
            return None

        proxy = None
        proxies = None
        repoinfo = pobj.repoInfo()
        reponame = "%s" % repoinfo.name()
        repos = [r for r in self.repos if r.name == reponame]
        repourl = str(repoinfo.baseUrls()[0])

        if repos:
            proxy = repos[0].proxy
        if not proxy:
            proxy = get_proxy_for(repourl)
        if proxy:
            proxies = {str(repourl.split(':')[0]): str(proxy)}

        return proxies

    def get_url(self, pobj):
        if not pobj:
            return None

        name = str(pobj.repoInfo().name())
        try:
            repo = [r for r in self.repos if r.name == name][0]
        except IndexError:
            return None

        baseurl = repo.baseurl[0]

        index = baseurl.find("?")
        if index > -1:
            baseurl = baseurl[:index]

        location = pobj.location()
        location = str(location.filename())
        if location.startswith("./"):
            location = location[2:]

        return os.path.join(baseurl, location)

    def package_url(self, pkgname):

        if not self.Z:
            self.__initialize_zypp()

        q = zypp.PoolQuery()
        q.addKind(zypp.ResKind.package)
        q.setMatchExact()
        q.addAttribute(zypp.SolvAttr.name, pkgname)
        items = q.queryResults(self.Z.pool())

        if items:
            items = sorted(items,
                           key=cmp_to_key(lambda x,y: cmpPackage(self._castKind(x), self._castKind(y))),
                           reverse=True)

            item = self._castKind(items[0])
            url = self.get_url(item)
            proxies = self.get_proxies(item)
            return (url, proxies)

        return (None, None)
