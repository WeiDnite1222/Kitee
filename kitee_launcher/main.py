"""
Kitee

Copyright (c) 2026 Kitee Contributors. All rights reserved.

Original repository:

Copyright (c) 2024~2025 Techarerm/TedKai
"""

import os
import platform
import sys
import argparse
import logging
import threading
from pathlib import Path

from kitee_launcher import __version__ as LAUNCHER_VERSION
from kitee_launcher.bk_core import __version__ as BK_CORE_VERSION
from kitee_launcher.background import Background
from kitee_launcher.gui import KiteeMainGUI

class KiteeLauncher:
    def __init__(self):
        # Logger
        self.logger = logging.getLogger(f'Launcher/{__name__}')

        # Version
        self.version = LAUNCHER_VERSION
        self.bk_core_version = BK_CORE_VERSION

        # Arguments
        self.args = None
        self.interface_args = None

        # Flags
        self.verbose = False
        self.debug = False

        # Vars
        self.work_dir = None
        self.program_dir = Path(__file__).resolve().parent
        self.arguments_parser()

        # Configure Logger
        self.level = logging.INFO if not self.verbose else logging.DEBUG
        self.logger.setLevel(self.level)
        self.logger.propagate = False

        self.formatter = logging.Formatter('[%(levelname)s/%(name)s]: %(message)s')
        self.handler = logging.StreamHandler(sys.stdout)
        self.handler.setFormatter(self.formatter)

        if self.verbose:
            self.logger.addHandler(self.handler)

        # Interfaces
        self.gui = None
        self.cli = None # Not sure if it will be added back in the future

        # Threads
        self.background = threading.Thread()

        # Platform
        self.platform = platform.system()

    def main(self):
        # Check work dir
        if not self.work_dir:
            self.work_dir = Path(os.getcwd())
        else:
            try:
                os.chdir(self.work_dir)
            except Exception as e:
                self.logger.critical(f'Set working directory to {self.work_dir} failed. Got error: {e}')
                sys.exit(1)

        self.create_background_thread()
        self.create_gui()

        self.background.start()
        self.gui.initialize()
        self.gui.mainloop()

    def create_background_thread(self):
        self.background = Background(
            self,
            self.bg_callback
        )

    def create_gui(self):
        self.gui = KiteeMainGUI(
            self,
            self.interface_args,
            None
        )

    def bg_callback(self):
        self.logger.debug(f'Background stopped.')

    def arguments_parser(self):
        parser = argparse.ArgumentParser(
            description='Kitee Launcher Arguments Info'
        )

        parser.add_argument('-v','--verbose', action='store_true',
                            help='Verbose output')
        parser.add_argument('-d','--debug', action='store_true',
                            help='Enable debug mode')
        parser.add_argument("-w", "--work-dir",
                            help="Set work directory")

        args = sys.argv[1:] # main.py -a -b -c -> -a -b -c

        # Split the arguments that used by interface from sys.argv
        if "-i" in args or "--interface" in args:
            interface_args_start_index = args.index("-i") if "-i" in args else args.index("--interface")
            main_args_raw, self.interface_args = args[:interface_args_start_index], args[interface_args_start_index:]
        else:
            main_args_raw, self.interface_args = args, []

        args, unknown_args = parser.parse_known_args(main_args_raw)

        self.logger.warning("Unknown arguments: {}".format(unknown_args)) if len(unknown_args) > 0 else None

        if args.verbose:
            self.verbose = True

        if args.debug:
            self.debug = True

        if args.work_dir:
            self.work_dir = Path(args.work_dir)

    def get_program_path(self, name):
        return self.program_dir / name

    def get_work_path(self, name):
        return self.work_dir / name


if __name__ == '__main__':
    KiteeLauncher().main()
