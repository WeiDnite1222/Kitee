# Build System Configuration

## Overview

This document describes the **Kitee** build system configuration using Nuitka compilation.

## Project Structure

```
Kitee/
├── build.py               # Main build script (Nuitka)
├── build.sh               # POSIX wrapper script
├── pyproject.toml         # Project metadata & dependencies
├── kitee_launcher/        # Main package
│   ├── main.py            # Entry point
│   ├── gui.py             # PyWebView GUI
│   ├── background.py      # Background worker thread
│   ├── front.py           # Frontend utilities
│   ├── __init__.py
│   ├── managers/          # Manager modules
│   │   ├── account_manager.py
│   │   ├── instance_manager.py
│   │   ├── launch_manager.py
│   │   ├── instance_creator.py
│   │   └── jre_manager.py
│   ├── bk_core/           # Core library
│   │   ├── account/       # Account management (Mojang, MSA, Yggdrasil)
│   │   ├── clientlauncher/
│   │   ├── definition/    # Core definitions
│   │   ├── game/          # Game management
│   │   ├── instance/      # Instance management
│   │   ├── java/          # Java runtime management
│   │   ├── libraries/     # Library management
│   │   ├── mod/           # Mod management (Forge, Fabric)
│   │   ├── utils/         # Utility functions
│   │   └── textures/      # Icons (Bread.ico, bread.png)
│   └── resources/         # Static resources
│       ├── templates/     # HTML templates
│       ├── styles/        # CSS styles
│       ├── locales/       # i18n (en_US, zh-TW)
│       ├── scripts/       # JavaScript modules
│       └── icons/         # Game/instance icons
└── settings/              # User settings
    └── gui/               # GUI settings (TOML)
```

## Dependencies

### Required (pyproject.toml)
```toml
dependencies = [
    "pywebview",
    "tomli-w",
    "requests",
    "nuitka"
]
```

### Build Requirements
- Python 3.12
- Nuitka (compiler)
- Visual Studio Build Tools (Windows) / Xcode (macOS) / GCC (Linux)

## Build System Files

### `build.py` (Main Build Script)

#### Usage
```bash
# Default build (directory mode)
python build.py

# Single executable
python build.py --onefile

# Clean and rebuild
python build.py --clean --onefile
```

### `build.sh` (POSIX Wrapper)

#### Usage
```bash
./build.sh --onefile
```

## Nuitka Compiler Flags

### General Flags
```
--follow-imports           # Follow all imports
--follow-import-to=X       # Follow specific package imports
--include-package=X        # Include entire package
--recurse-to=X            # Recurse into package directory
```

### Data File Bundling
```
--include-data-files=SRC=DST    # Bundle data files
                                # SRC: Source path
                                # DST: Destination in executable
```

### Output Options
```
--output-dir=DIR          # Build output directory
--output-file=NAME        # Output executable name
--remove-output           # Remove build artifacts after linking
--onefile                 # Create single executable
```

### Optimization
```
-O                        # Optimize (default level)
--improve                 # More aggressive optimization
--jobs=N                  # Parallel compilation jobs (default auto)
```

### Windows-Specific
```
--windows-console-mode=disable  # Disable console window
--windows-icon-from-ico=PATH    # Embed icon in executable
```

## Troubleshooting Guide

| Issue | Solution                                               |
|-------|--------------------------------------------------------|
| "Python not found" | Add Python to PATH or use full path                    |
| Nuitka import error | `uv pip install nuitka` or 'uv sync`                   |
| MSVC not available | Install Visual Studio Build Tools                      |
| "Permission denied" build.sh | `chmod +x build.sh`                                    |
| Resources not bundled | Verify paths in `build.py` `--include-data-files`      |

## See Also

- https://nuitka.net/ - Nuitka official website
- https://nuitka.net/doc/user-manual/ - Comprehensive documentation
- https://github.com/Nuitka/Nuitka - GitHub repository
