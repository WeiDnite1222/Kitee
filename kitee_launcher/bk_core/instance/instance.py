"""
bk_core

Copyright (c) 2024~2025 Techarerm/TedKai
Copyright (c) 2026 Kitee Contributors. All rights reserved.
"""
import json
import os
import re
import tomllib
import uuid

import requests
from datetime import datetime
from ..definition.data import INSTANCE_GAME_FOLDER_NAME

DEFAULT_VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
DEFAULT_FABRIC_INSTALLER_VERSION_LIST = "https://meta.fabricmc.net/v2/versions/installer"
DEFAULT_INSTANCE_FORMAT = "1.0-beta-pre1"
DEFAULT_INSTANCE_PROFILE_PATH = "profile.bakelh.toml"
DEFAULT_CONFIG_PATH = "config.bakelh.json"
LEGACY_CONFIG_PATH = "instance.bakelh.cfg"

INSTANCE_PROFILE_FIELD_MAP = {
    "instance_name": ("InstanceProfile", "instanceName"),
    "instance_uuid": ("InstanceProfile", "instanceUUID"),
    "client_version": ("InstanceProfile", "clientVersion"),
    "main_class": ("InstanceProfile", "mainClass"),
    "support_java_version": ("InstanceProfile", "supportJavaVersion"),
    "type": ("InstanceProfile", "type"),
    "launcher_version": ("InstanceProfile", "launcherVersion"),
    "instance_format": ("InstanceProfile", "instanceFormat"),
    "create_date": ("InstanceProfile", "createDate"),
    "convert_by_legacy": ("InstanceProfile", "convertByLegacy"),
    "real_minecraft_version": ("InstanceProfile", "realMinecraftVersion"),
    "use_legacy_manifest": ("InstanceProfile", "useLegacyManifest"),
    "game_folder": ("InstanceStructure", "gameFolder"),
    "assets_folder": ("InstanceStructure", "assetsFolder"),
    "is_vanilla": ("ModifyInfo", "isVanilla"),
    "modified": ("ModifyInfo", "modified"),
    "mod_loader_name": ("ModifyInfo", "modLoaderName"),
    "mod_loader_version": ("ModifyInfo", "modLoaderVersion"),
    "enable_config": ("CustomConfig", "enableConfig"),
    "custom_config_path": ("CustomConfig", "customConfigPath"),
}

CUSTOM_CONFIG_ITEM_MAP = {
    "jvmargs": "customJVMArgs",
    "customjvmargs": "customJVMArgs",
    "gameargs": "customGameArgs",
    "customgameargs": "customGameArgs",
    "injectjarpath": "injectJARPath",
    "injectjarfile": "injectJARFile",
    "modloaderclass": "modLoaderClass",
    "memoryjvmargs": "memoryJVMArgs",
    "javaexecutable": "javaExecutable",
    "jvmexecutable": "javaExecutable",
    "jvmexecutablepath": "javaExecutable",
    "modloadergameargs": "modLoaderGameArgs",
    "modloaderjvmargs": "modLoaderJVMArgs",
    "customclientjar": "customClientJar",
    "extraclasspath": "extraClasspath",
    "disabledclasspath": "disabledClasspath",
    "blockedclasspath": "disabledClasspath",
}

CUSTOM_CONFIG_LIST_ITEMS = {"extraClasspath", "disabledClasspath"}

TOML_COMMENTS = {
    "InstanceProfile": {
        "instanceName": "Display name shown in the launcher.",
        "instanceUUID": "UUID for instance folder.",
        "clientVersion": "Minecraft version selected for this instance.",
        "mainClass": "Main class used to start the client.",
        "supportJavaVersion": "Recommended Java major version.",
        "type": "Minecraft version type, such as release or snapshot.",
        "launcherVersion": "Launcher version that created this instance.",
        "instanceFormat": "BakeLauncher instance format version.",
        "createDate": "Creation timestamp.",
        "convertByLegacy": "True when converted from a legacy instance file.",
        "realMinecraftVersion": "Key from BakeLauncher.",
        "useLegacyManifest": "Key from BakeLauncher.",
    },
    "InstanceStructure": {
        "gameFolder": "Game working directory inside this instance.",
        "assetsFolder": "Assets directory. Launcher placeholders are supported.",
    },
    "ModifyInfo": {
        "isVanilla": "True when no mod loader is installed.",
        "modified": "True when this instance has mod loader metadata.",
        "modLoaderName": "Installed mod loader name, or false for vanilla.",
        "modLoaderVersion": "Installed mod loader version, or false for vanilla.",
    },
    "CustomConfig": {
        "enableConfig": "Enable custom launch configuration.",
        "customConfigPath": "Custom config file path. TOML instances use this file.",
    },
    "custom_config": {
        "modLoaderClass": "Main class override provided by a mod loader.",
        "customJVMArgs": "Extra JVM arguments appended to launch.",
        "memoryJVMArgs": "Memory JVM arguments. Leave empty for launcher defaults.",
        "javaExecutable": "Custom Java executable path. Leave empty for auto-detect.",
        "customGameArgs": "Extra Minecraft game arguments appended to launch.",
        "injectJARFile": "Legacy injected jar file name.",
        "injectJARPath": "Legacy injected jar path.",
        "modLoaderGameArgs": "Game arguments that from mod loader version data.",
        "modLoaderJVMArgs": "JVM arguments that from mod loader version data.",
        "customClientJar": "Custom client jar that replaces the default Minecraft client jar.",
        "extraClasspath": "Additional jar files appended to the launch classpath.",
        "disabledClasspath": "Default classpath entries hidden from launch.",
    },
}


def _strip_config_value(value):
    return value.strip().strip('"').strip("'")


def _parse_bool(value):
    return _strip_config_value(value).upper() == "TRUE"


def _toml_value(value):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        value = ""
    if isinstance(value, datetime):
        value = str(value)

    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _dump_toml(data, include_comments=True):
    lines = []
    root_values = {key: value for key, value in data.items() if not isinstance(value, dict)}
    section_values = {key: value for key, value in data.items() if isinstance(value, dict)}

    for key, value in root_values.items():
        if include_comments:
            comment = TOML_COMMENTS.get("", {}).get(key)
            if comment:
                lines.append(f"# {comment}")
        lines.append(f"{key} = {_toml_value(value)}")

    if root_values and section_values:
        lines.append("")

    for section_index, (section, values) in enumerate(section_values.items()):
        if section_index > 0:
            lines.append("")
        lines.append(f"[{section}]")
        for key, value in values.items():
            if include_comments:
                comment = TOML_COMMENTS.get(section, {}).get(key)
                if comment:
                    lines.append(f"# {comment}")
            lines.append(f"{key} = {_toml_value(value)}")

    return "\n".join(lines) + "\n"


def _load_toml(file_path):
    with open(file_path, "rb") as file:
        return tomllib.load(file)


def _load_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def _write_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)
        file.write("\n")


def _write_toml(file_path, data):
    if os.path.exists(file_path) and _patch_toml_file(file_path, data):
        return

    with open(file_path, "w") as file:
        file.write(_dump_toml(data))


def _patch_toml_file(file_path, data):
    try:
        with open(file_path, "r") as file:
            lines = file.readlines()
    except OSError:
        return False

    if not lines:
        return False

    updated_lines = list(lines)
    for section, values in data.items():
        if not isinstance(values, dict):
            updated_lines, _ = _patch_toml_key(updated_lines, None, section, values)
            continue

        for key, value in values.items():
            updated_lines, _ = _patch_toml_key(updated_lines, section, key, value)

    try:
        with open(file_path, "w") as file:
            file.writelines(updated_lines)
        return True
    except OSError:
        return False


def _patch_toml_key(lines, target_section, key, value):
    key_pattern = re.compile(rf"^(\s*{re.escape(str(key))}\s*=\s*)(.*?)(\r?\n?)$")
    section_pattern = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?(?:\r?\n?)$")
    current_section = None
    target_section_found = target_section is None
    insert_index = len(lines)

    for index, line in enumerate(lines):
        section_match = section_pattern.match(line)
        if section_match:
            if current_section == target_section and target_section_found:
                insert_index = index
                break
            current_section = section_match.group(1).strip()
            if current_section == target_section:
                target_section_found = True
                insert_index = len(lines)
            continue

        if current_section != target_section:
            continue

        key_match = key_pattern.match(line)
        if not key_match:
            continue

        value_text, comment_text = _split_toml_value_comment(key_match.group(2))
        del value_text
        lines[index] = f"{key_match.group(1)}{_toml_value(value)}{comment_text}{key_match.group(3)}"
        return lines, True

    if target_section is not None and not target_section_found:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append(f"[{target_section}]\n")
        insert_index = len(lines)

    lines.insert(insert_index, _format_toml_key_with_comment(target_section, key, value))
    return lines, False


def _format_toml_key_with_comment(section, key, value):
    comment = TOML_COMMENTS.get(section or "", {}).get(key)
    if comment:
        return f"# {comment}\n{key} = {_toml_value(value)}\n"
    return f"{key} = {_toml_value(value)}\n"


def _split_toml_value_comment(text):
    in_string = False
    escaped = False
    quote_char = ""

    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if in_string and char == "\\":
            escaped = True
            continue
        if char in ('"', "'"):
            if in_string and char == quote_char:
                in_string = False
                quote_char = ""
            elif not in_string:
                in_string = True
                quote_char = char
            continue
        if char == "#" and not in_string:
            comment_start = index
            while comment_start > 0 and text[comment_start - 1].isspace():
                comment_start -= 1
            return text[:comment_start].rstrip(), text[comment_start:]

    return text.rstrip(), ""


def _get_nested_value(data, section, key, default=None):
    return data.get(section, {}).get(key, default)


def _set_nested_value(data, section, key, value):
    data.setdefault(section, {})
    data[section][key] = value


def _default_instance_profile_dict(
        instance_name=None,
        instance_uuid=None,
        client_version=None,
        version_type=None,
        launcher_version=None,
        main_class=None,
        java_major_version=None,
        instance_format=DEFAULT_INSTANCE_FORMAT,
        create_date=None,
        convert_by_legacy=False,
        real_minecraft_version=None,
        use_legacy_manifest=False,
        game_folder=f"{INSTANCE_GAME_FOLDER_NAME}",
        assets_folder="$[LAUNCHER_LOCAL_ASSETS_DIR]",
        is_vanilla=False,
        modify_status=False,
        mod_loader_name=False,
        mod_loader_version=False,
        enable_config=True,
        cfg_path=DEFAULT_CONFIG_PATH,
):
    if create_date is None:
        create_date = datetime.now()
    if real_minecraft_version is None:
        real_minecraft_version = client_version

    return _instance_profile_dict_from_flat({
        "instance_name": instance_name,
        "instance_uuid": instance_uuid,
        "client_version": client_version,
        "main_class": main_class,
        "support_java_version": java_major_version,
        "type": version_type,
        "launcher_version": launcher_version,
        "instance_format": instance_format,
        "create_date": str(create_date),
        "convert_by_legacy": convert_by_legacy,
        "real_minecraft_version": real_minecraft_version,
        "use_legacy_manifest": use_legacy_manifest,
        "game_folder": game_folder,
        "assets_folder": assets_folder,
        "is_vanilla": is_vanilla,
        "modified": modify_status,
        "mod_loader_name": mod_loader_name,
        "mod_loader_version": mod_loader_version,
        "enable_config": enable_config,
        "custom_config_path": cfg_path,
    })


def _default_custom_config_dict():
    return {
        "custom_config": {
            "modLoaderClass": "",
            "customJVMArgs": "",
            "memoryJVMArgs": "",
            "javaExecutable": "",
            "customGameArgs": "",
            "injectJARFile": "",
            "injectJARPath": "",
            "modLoaderGameArgs": "",
            "modLoaderJVMArgs": "",
            "customClientJar": "",
            "extraClasspath": [],
            "disabledClasspath": [],
        }
    }


def _normalize_custom_config(data):
    normalized = _default_custom_config_dict()
    custom_config = data.get("custom_config") if isinstance(data, dict) else {}
    if not isinstance(custom_config, dict):
        custom_config = {}

    normalized_config = normalized["custom_config"]
    for key, value in custom_config.items():
        mapped_key = CUSTOM_CONFIG_ITEM_MAP.get(str(key).lower(), key)
        if mapped_key in CUSTOM_CONFIG_LIST_ITEMS:
            if isinstance(value, list):
                normalized_config[mapped_key] = [str(item) for item in value if str(item or "").strip()]
            elif str(value or "").strip():
                normalized_config[mapped_key] = [item.strip() for item in str(value).split(os.pathsep) if item.strip()]
            else:
                normalized_config[mapped_key] = []
            continue

        normalized_config[mapped_key] = "" if value is None else value

    return normalized


def _flatten_instance_profile(data):
    profile = {}
    for field, (section, key) in INSTANCE_PROFILE_FIELD_MAP.items():
        profile[field] = _get_nested_value(data, section, key)
    return profile


def _instance_profile_dict_from_flat(info):
    data = {}
    for field, value in info.items():
        if field in INSTANCE_PROFILE_FIELD_MAP:
            section, key = INSTANCE_PROFILE_FIELD_MAP[field]
            _set_nested_value(data, section, key, value)
    return data


def get_instance_profile_path(instance_dir):
    return os.path.join(instance_dir, DEFAULT_INSTANCE_PROFILE_PATH)


def get_custom_config_path(instance_dir):
    json_path = os.path.join(instance_dir, DEFAULT_CONFIG_PATH)
    return json_path


def validate_instance_request(instance_name, client_version):
    if not instance_name:
        return "Instance name is required."

    if not client_version:
        return "Minecraft version is required."

    if any(char in instance_name for char in '<>:"/\\|?*'):
        return "Instance name contains invalid path characters."

    return None


def get_payload_java_major_version(payload, version_data):
    java_major_version = str(payload.get("javaMajorVersion") or "").strip()
    if java_major_version:
        return java_major_version

    java_version = version_data.get("javaVersion", {})
    java_major_version = str(java_version.get("majorVersion") or "").strip()
    return java_major_version or "8"


def update_instance_java_major_version(instance_dir, java_major_version):
    info_path = get_instance_profile_path(str(instance_dir))
    if java_major_version:
        write_instance_profile("support_java_version", str(java_major_version), info_path)


def _legacy_custom_config_candidates(config_file_path):
    config_dir = os.path.dirname(config_file_path)
    return [
        os.path.join(config_dir, LEGACY_CONFIG_PATH),
    ]


def _write_custom_config_file(config_file_path, data):
    _write_json(config_file_path, _normalize_custom_config(data))


def _load_custom_config_from_file(config_file_path):
    return _normalize_custom_config(_load_json(config_file_path))


def create_instance_profile(
        instance_name,
        instance_uuid,
        instance_dir,
        client_version,
        version_type,
        is_vanilla,
        modify_status,
        mod_loader_name,
        mod_loader_version,
        launcher_version,
        convert_by_legacy=False,
        use_legacy_manifest=False,
        real_minecraft_version=None,
        java_major_version=None,
        main_class=None,
        instance_format=DEFAULT_INSTANCE_FORMAT,
        create_date=None,
        game_folder=f"{INSTANCE_GAME_FOLDER_NAME}",
        assets_folder="$[LAUNCHER_LOCAL_ASSETS_DIR]",
        enable_config=True,
        cfg_path=DEFAULT_CONFIG_PATH,
        instance_profile_path=None,
):
    if instance_profile_path is None:
        instance_profile_path = os.path.join(instance_dir, DEFAULT_INSTANCE_PROFILE_PATH)

    if not os.path.exists(instance_dir):
        os.makedirs(instance_dir)

    # Avoid overwriting profile data.
    if os.path.exists(instance_profile_path):
        return True

    instance_profile = _default_instance_profile_dict(
        instance_name=instance_name,
        instance_uuid=instance_uuid,
        client_version=client_version,
        version_type=version_type,
        launcher_version=launcher_version,
        is_vanilla=is_vanilla,
        modify_status=modify_status,
        mod_loader_name=mod_loader_name,
        mod_loader_version=mod_loader_version,
        convert_by_legacy=convert_by_legacy,
        use_legacy_manifest=use_legacy_manifest,
        real_minecraft_version=real_minecraft_version,
        java_major_version=java_major_version,
        main_class=main_class,
        instance_format=instance_format,
        create_date=create_date,
        game_folder=game_folder,
        assets_folder=assets_folder,
        enable_config=enable_config,
        cfg_path=cfg_path,
    )
    _write_toml(instance_profile_path, instance_profile)
    return None


def get_instance_type(minecraft_version, version_manifest_url=DEFAULT_VERSION_MANIFEST_URL):
    response = requests.get(version_manifest_url)
    data = response.json()

    version_info = next((v for v in data["versions"] if v["id"] == minecraft_version), None)
    if version_info:
        return version_info["type"]
    return None


def create_custom_config(config_file_path, exist_ok=False):
    if exist_ok and os.path.exists(config_file_path):
        os.remove(config_file_path)

    if os.path.exists(config_file_path):
        return True

    default_data = _default_custom_config_dict()
    _write_custom_config_file(config_file_path, default_data)

    return True


def _load_custom_config(config_file_path, not_found_create=False):
    if not os.path.exists(config_file_path):
        if not not_found_create:
            raise FileNotFoundError("Target custom config path {} does not exist".format(config_file_path))
        create_custom_config(config_file_path)
        return True, _default_custom_config_dict()

    return True, _load_custom_config_from_file(config_file_path)


def check_custom_config_valid(config_file_path):
    status, data = _load_custom_config(config_file_path)
    return status and isinstance(data, dict)


def read_custom_config(config_file_path, item):
    status, data = _load_custom_config(config_file_path)
    if not status:
        return None

    custom_item = CUSTOM_CONFIG_ITEM_MAP.get(item.lower(), item)
    return data["custom_config"].get(custom_item)


def write_custom_config(custom_config_path, item, data, write_new_if_not_found=False):
    custom_item = CUSTOM_CONFIG_ITEM_MAP.get(item.lower())
    if not custom_item:
        raise ValueError(f"Invalid item: {item}")

    config_file_exists = os.path.exists(custom_config_path)
    if not config_file_exists and not write_new_if_not_found:
        raise FileNotFoundError(f"The file {custom_config_path} does not exist.")

    status, file_data = _load_custom_config(custom_config_path)
    if not status:
        if write_new_if_not_found:
            file_data = _default_custom_config_dict()
        else:
            raise FileNotFoundError(f"The file {custom_config_path} does not exist.")

    file_data = _normalize_custom_config(file_data)
    found = custom_item in file_data["custom_config"]

    if found or write_new_if_not_found:
        if custom_item in CUSTOM_CONFIG_LIST_ITEMS:
            if isinstance(data, list):
                file_data["custom_config"][custom_item] = [str(item) for item in data if str(item or "").strip()]
            elif str(data or "").strip():
                file_data["custom_config"][custom_item] = [str(data)]
            else:
                file_data["custom_config"][custom_item] = []
        else:
            file_data["custom_config"][custom_item] = data

    _write_custom_config_file(custom_config_path, file_data)
    return found


def write_instance_profile(item_name, new_data, instance_profile_path):
    if not os.path.exists(instance_profile_path):
        return False

    if item_name not in INSTANCE_PROFILE_FIELD_MAP:
        return False

    section, key = INSTANCE_PROFILE_FIELD_MAP[item_name]
    try:
        data = _load_toml(instance_profile_path)
        if not isinstance(data, dict):
            data = {}

        _set_nested_value(data, section, key, new_data)
        _write_toml(instance_profile_path, data)
        return True
    except tomllib.TOMLDecodeError:
        pass

    status, info = parse_instance_profile(instance_profile_path)
    if not status:
        return False

    instance_profile = _instance_profile_dict_from_flat(info)
    _set_nested_value(instance_profile, section, key, new_data)
    _write_toml(instance_profile_path, instance_profile)
    return True


def parse_instance_profile(instance_profile_path):
    if not os.path.exists(instance_profile_path):
        return False, None

    try:
        data = _load_toml(instance_profile_path)
        return True, _flatten_instance_profile(data)
    except Exception as e:
        return False, f"FailedToReadInstanceProfile>Error: {e}"

def get_instance_profile(instance_profile_path, info_name=None, ignore_not_found=False):
    """
    Args list:
    instance_profile_path: Path to the instance profile file.
    info_name: Get selected instance profile data (not found return False and None)
    If info_name is not found return True, {All available data}...
    """
    status, info = parse_instance_profile(instance_profile_path)
    del ignore_not_found

    if not status:
        return False, info

    if info_name is None:
        return True, (
            info["instance_name"],
            info["instance_uuid"],
            info["client_version"],
            info["type"],
            info["launcher_version"],
            info["instance_format"],
            info["create_date"],
        )

    if info_name in info:
        return True, info[info_name]

    return False, None


def generate_instance_uuid():
    return str(uuid.uuid4())
