#!/usr/bin/env python3
"""
Kitee Nuitka Build Script
Supports Windows (MSVC) and POSIX (GCC/Clang)
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


class NuitkaBuildConfig:
    def __init__(self):
        self.script_dir = Path(__file__).resolve().parent
        self.kitee_dir = self.script_dir / "kitee_launcher"
        self.main_file = self.kitee_dir / "main.py"
        self.icon_file = self.kitee_dir / "resources" / "icons" / "icon.ico"
        self.resources_dir = self.kitee_dir / "resources"
        self.bk_core_dir = self.kitee_dir / "bk_core"
        self.managers_dir = self.kitee_dir / "managers"
        self.build_dir = self.script_dir / "build"
        self.dist_dir = self.script_dir / "dist"
        self.system = platform.system()
        self.machine = platform.machine()

    def validate(self):
        """Validate all necessary files exist"""
        if not self.main_file.exists():
            raise FileNotFoundError(f"Main file not found: {self.main_file}")
        if not self.icon_file.exists():
            raise FileNotFoundError(f"Icon file not found: {self.icon_file}")
        if not self.resources_dir.exists():
            raise FileNotFoundError(f"Resources directory not found: {self.resources_dir}")
        if not self.bk_core_dir.exists():
            raise FileNotFoundError(f"bk_core directory not found: {self.bk_core_dir}")
        if not self.managers_dir.exists():
            raise FileNotFoundError(f"Managers directory not found: {self.managers_dir}")

    def get_output_name(self):
        """Get output executable name based on platform"""
        if self.system == "Windows":
            return "Kitee.exe"
        else:
            return "Kitee"

    def get_nuitka_args(self, output_file, onefile=False):
        """Build Nuitka command arguments"""
        args = [
            sys.executable,
            "-m", "nuitka",
            "--follow-imports",
            "--follow-import-to=kitee_launcher",
            "--include-package=kitee_launcher",
            '--standalone'
        ]

        # Include data files
        args.extend([
            f"--include-data-dir={self.resources_dir}=resources",
        ])

        # Output settings
        args.extend([
            f"--output-dir={self.build_dir}",
            f"--output-file={output_file}",
        ])

        # Platform-specific settings
        if self.system == "Windows":
            args.extend([
                "--windows-console-mode=disable",
                f"--windows-icon-from-ico={self.icon_file}",
                "--assume-yes-for-downloads"
            ])

        if self.system == "Darwin":
            args.extend([
                "--mode=app"
            ])

        # Onefile mode (creates single executable)
        if onefile:
            args.append("--onefile")

        # Add the main file
        args.append(str(self.main_file))

        return args

    def build(self, onefile=False, clean=False):
        """Execute the build"""
        if clean and self.build_dir.exists():
            print(f"Cleaning build directory: {self.build_dir}")
            shutil.rmtree(self.build_dir)

        if clean and self.dist_dir.exists():
            print(f"Cleaning dist directory: {self.dist_dir}")
            shutil.rmtree(self.dist_dir)

        output_name = self.get_output_name()
        nuitka_args = self.get_nuitka_args(output_name, onefile=onefile)

        print(f"\n{'='*60}")
        print(f"BakeLauncher Build Configuration")
        print(f"{'='*60}")
        print(f"Platform: {self.system} ({self.machine})")
        print(f"Python: {sys.version}")
        print(f"Main file: {self.main_file}")
        print(f"Icon: {self.icon_file}")
        print(f"Output: {output_name}")
        print(f"Onefile mode: {onefile}")
        print(f"Build directory: {self.build_dir}")
        print(f"Args: {' '.join(nuitka_args)}")
        print(f"{'='*60}\n")

        try:
            print("Starting Nuitka compilation...")
            result = subprocess.run(nuitka_args, check=True)

            # Create dist directory and move output
            self.dist_dir.mkdir(exist_ok=True)

            if self.system == "Windows" and onefile:
                # With onefile, executable is in build dir
                src = self.build_dir / output_name
                dst = self.dist_dir / output_name
                if src.exists():
                    shutil.move(str(src), str(dst))
                    print(f"\n✓ Binary built successfully: {dst}")
            else:
                # Directory mode or non-Windows
                src = self.build_dir / output_name
                if src.exists():
                    print(f"\n✓ Binary built successfully: {src}")

            return True

        except subprocess.CalledProcessError as e:
            print(f"\n✗ Build failed with error code {e.returncode}")
            return False
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Build BakeLauncher with Nuitka",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build.py              # Build with default settings
  python build.py --onefile    # Build as single executable (larger but portable)
  python build.py --clean      # Clean and rebuild
  python build.py --clean --onefile  # Clean and build single executable
        """
    )

    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build as single executable file (includes all dependencies)"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build artifacts before building"
    )

    args = parser.parse_args()

    try:
        config = NuitkaBuildConfig()
        config.validate()

        success = config.build(onefile=args.onefile, clean=args.clean)
        sys.exit(0 if success else 1)

    except FileNotFoundError as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
