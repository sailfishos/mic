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

import os, sys, re
from optparse import SUPPRESS_HELP

from mic import msger
from mic.utils import cmdln, errors, rpmmisc
from .conf import configmgr
from .plugin import pluginmgr

class Creator(cmdln.Cmdln):
    """${name}: create an image

    Usage:
        ${name} SUBCOMMAND <ksfile> [OPTS]

    ${command_list}
    ${option_list}
    """

    name = 'mic create(cr)'

    def __init__(self, *args, **kwargs):
        cmdln.Cmdln.__init__(self, *args, **kwargs)
        self._subcmds = []

        # get cmds from pluginmgr
        # mix-in do_subcmd interface
        for subcmd, klass in pluginmgr.get_plugins('imager').items():
            if not hasattr(klass, 'do_create'):
                msger.warning("Unsurpport subcmd: %s" % subcmd)
                continue

            func = getattr(klass, 'do_create')
            setattr(self.__class__, "do_"+subcmd, func)
            self._subcmds.append(subcmd)

    def get_optparser(self):
        optparser = cmdln.CmdlnOptionParser(self)
        optparser.add_option('-d', '--debug', action='store_true',
                             dest='debug',
                             help=SUPPRESS_HELP)
        optparser.add_option('-v', '--verbose', action='store_true',
                             dest='verbose',
                             help=SUPPRESS_HELP)
        optparser.add_option('', '--logfile', type='string', dest='logfile',
                             default=None,
                             help='Path of logfile')
        optparser.add_option('-c', '--config', type='string', dest='config',
                             default=None,
                             help='Specify config file for mic')
        optparser.add_option('-k', '--cachedir', type='string', action='store',
                             dest='cachedir', default=None,
                             help='Cache directory to store the downloaded')
        optparser.add_option('-o', '--outdir', type='string', action='store',
                             dest='outdir', default=None,
                             help='Output directory')
        optparser.add_option('-A', '--arch', type='string', dest='arch',
                             default=None,
                             help='Specify repo architecture')
        optparser.add_option('', '--release', type='string', dest='release',
                             default=None, metavar='RID',
                             help='Generate a release of RID with all necessary'
                                  ' files, when @BUILD_ID@ is contained in '
                                  'kickstart file, it will be replaced by RID')
        optparser.add_option("", "--record-pkgs", type="string",
                             dest="record_pkgs", default=None,
                             help='Record the info of installed packages, '
                                  'multiple values can be specified which '
                                  'joined by ",", valid values: "name", '
                                  '"url", "content", "license"')
        optparser.add_option('', '--pkgmgr', type='string', dest='pkgmgr',
                             default=None,
                             help='Specify backend package manager')
        optparser.add_option('', '--local-pkgs-path', type='string',
                             dest='local_pkgs_path', default=None,
                             help='Path for local pkgs(rpms) to be installed')
        optparser.add_option('', '--runtime', type='string',
                             dest='runtime', default=None,
                             #help='Specify  runtime mode, avaiable: bootstrap')
                             help=SUPPRESS_HELP)
        # --taring-to is alias to --pack-to
        optparser.add_option('', '--taring-to', type='string',
                             dest='pack_to', default=None,
                             help=SUPPRESS_HELP)
        optparser.add_option('', '--pack-to', type='string',
                             dest='pack_to', default=None,
                             help='Pack the images together into the specified'
                                  ' achive, extension supported: .zip, .tar, '
                                  '.tar.gz, .tar.bz2, etc. by default, .tar '
                                  'will be used')
        optparser.add_option('', '--copy-kernel', action='store_true',
                             dest='copy_kernel',
                             help='Copy kernel files from image /boot directory'
                                  ' to the image output directory.')
        optparser.add_option('', '--tokenmap', type='string', dest='tokenmap',
                             default=None, metavar='TOKENMAP',
                             help='comma separated pairs of TOKEN:VALUE mappings,'
                                  ' when @TOKEN@ is contained in kickstart file'
                                  ' it will be replaced by VALUE')
        return optparser

    def preoptparse(self, argv):
        optparser = self.get_optparser()

        largs = []
        rargs = []
        while argv:
            arg = argv.pop(0)

            if arg in ('-h', '--help'):
                rargs.append(arg)

            elif optparser.has_option(arg):
                largs.append(arg)

                if optparser.get_option(arg).takes_value():
                    try:
                        largs.append(argv.pop(0))
                    except IndexError:
                        raise errors.Usage("option %s requires arguments" % arg)

            else:
                if arg.startswith("--"):
                    if "=" in arg:
                        opt = arg.split("=")[0]
                    else:
                        opt = None
                elif arg.startswith("-") and len(arg) > 2:
                    opt = arg[0:2]
                else:
                    opt = None

                if opt and optparser.has_option(opt):
                    largs.append(arg)
                else:
                    rargs.append(arg)

        return largs + rargs

    def postoptparse(self):
        abspath = lambda pth: os.path.abspath(os.path.expanduser(pth))

        if self.options.verbose:
            msger.set_loglevel('verbose')
        if self.options.debug:
            msger.set_loglevel('debug')

        if self.options.logfile:
            msger.set_interactive(False)
            msger.set_logfile(self.options.logfile)
            configmgr.create['logfile'] = self.options.logfile

        if self.options.config:
            configmgr.reset()
            configmgr._siteconf = self.options.config

        if self.options.outdir is not None:
            configmgr.create['outdir'] = abspath(self.options.outdir)
        if self.options.cachedir is not None:
            configmgr.create['cachedir'] = abspath(self.options.cachedir)
        os.environ['ZYPP_LOCKFILE_ROOT'] = configmgr.create['cachedir']

        if self.options.local_pkgs_path is not None:
            if not os.path.exists(self.options.local_pkgs_path):
                msger.error('Local pkgs directory: \'%s\' not exist' \
                              % self.options.local_pkgs_path)
            configmgr.create['local_pkgs_path'] = self.options.local_pkgs_path

        if self.options.release:
            configmgr.create['release'] = self.options.release

        if self.options.record_pkgs:
            configmgr.create['record_pkgs'] = []
            for infotype in self.options.record_pkgs.split(','):
                if infotype not in ('name', 'url', 'content', 'license'):
                    raise errors.Usage('Invalid pkg recording: %s, valid ones:'
                                       ' "name", "url", "content", "license"' \
                                       % infotype)

                configmgr.create['record_pkgs'].append(infotype)

        if self.options.arch is not None:
            supported_arch = sorted(list(rpmmisc.archPolicies.keys()), reverse=True)
            if self.options.arch in supported_arch:
                configmgr.create['arch'] = self.options.arch
            else:
                raise errors.Usage('Invalid architecture: "%s".\n'
                                   '  Supported architectures are: \n'
                                   '  %s' % (self.options.arch,
                                               ', '.join(supported_arch)))

        if self.options.pkgmgr is not None:
            configmgr.create['pkgmgr'] = self.options.pkgmgr

        if self.options.runtime:
            configmgr.create['runtime'] = self.options.runtime

        if self.options.pack_to is not None:
            configmgr.create['pack_to'] = self.options.pack_to

        if self.options.copy_kernel:
            configmgr.create['copy_kernel'] = self.options.copy_kernel

        if self.options.tokenmap:
            tokenmap = {}
            for pair in self.options.tokenmap.split(","):
                token, value = pair.split(":",1)
                tokenmap[token] = value

            if not "RELEASE" in tokenmap and self.options.release:
                tokenmap["RELEASE"] = self.options.release
            if not "BUILD_ID" in tokenmap and "RELEASE" in tokenmap:
                tokenmap["BUILD_ID"] = tokenmap["RELEASE"]

            configmgr.create['tokenmap'] = tokenmap

    def main(self, argv=None):
        if argv is None:
            argv = sys.argv
        else:
            argv = argv[:] # don't modify caller's list

        self.optparser = self.get_optparser()
        if self.optparser:
            try:
                argv = self.preoptparse(argv)
                self.options, args = self.optparser.parse_args(argv)

            except cmdln.CmdlnUserError as ex:
                msg = "%s: %s\nTry '%s help' for info.\n"\
                      % (self.name, ex, self.name)
                msger.error(msg)

            except cmdln.StopOptionProcessing as ex:
                return 0
        else:
            # optparser=None means no process for opts
            self.options, args = None, argv[1:]

        if not args:
            return self.emptyline()

        self.postoptparse()

        if os.geteuid() != 0 and args[0] != 'help':
            msger.error('root permission is required to continue, abort')

        return self.cmd(args)

    def do_auto(self, subcmd, opts, *args):
        """${cmd_name}: auto detect image type from magic header

        Usage:
            ${name} ${cmd_name} <ksfile>

        ${cmd_option_list}
        """
        def parse_magic_line(re_str, pstr, ptype='mic'):
            ptn = re.compile(re_str)
            m = ptn.match(pstr)
            if not m or not m.groups():
                return None

            inline_argv = m.group(1).strip()
            if ptype == 'mic':
                m2 = re.search('(?P<format>\w+)', inline_argv)
            elif ptype == 'mic2':
                m2 = re.search('(-f|--format(=)?)\s*(?P<format>\w+)',
                               inline_argv)
            else:
                return None

            if m2:
                cmdname = m2.group('format')
                inline_argv = inline_argv.replace(m2.group(0), '')
                return (cmdname, inline_argv)

            return None

        if not args:
            self.do_help(['help', subcmd])
            return None

        if len(args) != 1:
            raise errors.Usage("Extra arguments given")

        if not os.path.exists(args[0]):
            raise errors.CreatorError("Can't find the file: %s" % args[0])

        with open(args[0], 'r') as rf:
            first_line = rf.readline()

        mic_re = '^#\s*-\*-mic-options-\*-\s+(.*)\s+-\*-mic-options-\*-'
        mic2_re = '^#\s*-\*-mic2-options-\*-\s+(.*)\s+-\*-mic2-options-\*-'

        result = parse_magic_line(mic_re, first_line, 'mic') \
                 or parse_magic_line(mic2_re, first_line, 'mic2')
        if not result:
            raise errors.KsError("Invalid magic line in file: %s" % args[0])

        if result[0] not in self._subcmds:
            raise errors.KsError("Unsupport format '%s' in %s"
                                 % (result[0], args[0]))

        argv = ' '.join(result + args).split()
        self.main(argv)

