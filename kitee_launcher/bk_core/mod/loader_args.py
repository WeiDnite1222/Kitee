"""
bk_core

Copyright (c) 2026 Kitee Contributors. All rights reserved.
"""


def serialize_loader_arguments(arguments, placeholders=None):
    if placeholders is None:
        placeholders = {}
    if arguments is None:
        return ""

    if isinstance(arguments, str):
        values = [arguments]
    elif isinstance(arguments, list):
        values = []
        for arg in arguments:
            if isinstance(arg, str):
                values.append(arg)
            elif isinstance(arg, dict) and "value" in arg:
                value = arg["value"]
                if isinstance(value, list):
                    values.extend(str(item) for item in value)
                else:
                    values.append(str(value))
    else:
        values = [str(arguments)]

    resolved = []
    for value in values:
        for placeholder, replacement in placeholders.items():
            value = value.replace(placeholder, replacement)
        resolved.append(value)

    return " ".join(resolved).strip()


def extract_legacy_loader_game_args(minecraft_arguments):
    args = str(minecraft_arguments or "").strip().split()
    if "--tweakClass" not in args:
        return ""

    index = args.index("--tweakClass")
    if index + 1 >= len(args):
        return "--tweakClass"
    return "--tweakClass {}".format(args[index + 1])
