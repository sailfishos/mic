#!/usr/bin/python -t

from __future__ import with_statement
import os
import sys
import string
import optparse
import logging

import micng.utils.cmdln as cmdln
import micng.configmgr as configmgr
import micng.pluginmgr as pluginmgr

class Creator(cmdln.Cmdln):
    """
    ${command_list}
    ${help_list}
    ${option_list}
    """
    conf = None
    man_header = None
    man_footer = None

    def __init__(self, *args, **kwargs):
        cmdln.Cmdln.__init__(self, *args, **kwargs)
        # load configmgr
        self.configmgr = configmgr.getConfigMgr()
        # load pluginmgr
        self.pluginmgr = pluginmgr.PluginMgr()
        self.pluginmgr.loadPlugins()
        self.plugincmds = self.pluginmgr.getImagerPlugins()
        # mix-in do_subcmd interface
        for subcmd, klass in self.plugincmds:
            if not hasattr(klass, 'do_create'):
                logging.warn("Unsurpport subcmd: %s" % subcmd)
                continue
            func = getattr(klass, 'do_create')
            setattr(self.__class__, "do_"+subcmd, func)

    def get_optparser(self):
        optparser = cmdln.CmdlnOptionParser(self)
        optparser.add_option('-d', '--debug', action='store_true', help='print debug info')
        optparser.add_option('-v', '--verbose', action='store_true', help='verbose output')
        #optparser.add_option('-o', '--outdir', type='string', action='store', dest='outdir', default=None, help='output directory')
        return optparser 

    def preoptparse(self, argv):
        pass

    def postoptparse(self):
        if self.options.verbose is True:
            logging.getLogger().setLevel(logging.INFO)
        if self.options.debug is True:
            logging.getLogger().setLevel(logging.DEBUG)
        #if self.options.outdir is not None:
        #    self.configmgr.create['outdir'] = self.options.outdir

    def main(self, argv=None):
        if argv is None:
            argv = sys.argv
        else:
            argv = argv[:] # don't modify caller's list

        self.optparser = self.get_optparser()
        if self.optparser: # i.e. optparser=None means don't process for opts
            try:
                self.preoptparse(argv)
                self.options, args = self.optparser.parse_args(argv)
            except cmdln.CmdlnUserError, ex:
                msg = "%s: %s\nTry '%s help' for info.\n"\
                      % (self.name, ex, self.name)
                self.stderr.write(self._str(msg))
                self.stderr.flush()
                return 1
            except cmdln.StopOptionProcessing, ex:
                return 0
        else:
            self.options, args = None, argv[1:]
        self.postoptparse()

        if args:
            if os.geteuid() != 0:
                print >> sys.stderr, "You must run %s as root" % sys.argv[0]
                return 1
            try:
                return self.cmd(args)
            except Exception, e:
                print e
        else:
            return self.emptyline()

#if __name__ == "__main__":
#    logging.getLogger().setLevel(logging.ERROR)
#    create = Creator()
#    ret = create.main(sys.argv)
#    sys.exit(ret)