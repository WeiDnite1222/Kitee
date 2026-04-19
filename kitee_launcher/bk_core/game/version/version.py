"""
bk_core

Copyright (c) 2024~2025 Techarerm/TedKai
Copyright (c) 2026 Kitee Contributors. All rights reserved.

A function to get version_manifest data or get the specified version data
"""
import copy
import json
import os
import requests

mojang_version_manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def get_version_data(version_id, custom_version_manifest_url=mojang_version_manifest_url):
    """
    Get version_manifest_v2.json and find requires version of json data
    """

    # parameter stuff
    version_manifest_url = custom_version_manifest_url

    response = requests.get(version_manifest_url)
    data = response.json()
    version_list = data['versions']

    version_url = None
    for v in version_list:
        if v['id'] == version_id:
            version_url = v['url']
            break

    if version_url is None:
        return None

    try:
        # Get version data
        version_response = requests.get(version_url)
        version_data = version_response.json()
        return version_data
    except Exception as e:
        return None


def check_minecraft_version_are_valid(version_id):
    """Check minecraft version is valid"""

    version_data = get_version_data(version_id)
    if version_data is None:
        return False
    else:
        test = version_data.get('libraries', None)
        if test is None:
            return False
        else:
            return True

def get_minecraft_version_type(version_id, custom_version_manifest_url=mojang_version_manifest_url):
    """Get version type"""

    # parameter stuff
    version_manifest_url = custom_version_manifest_url

    response = requests.get(version_manifest_url)
    data = response.json()

    for version in data["versions"]:
        if version["id"] == version_id:
            return version["type"]

    return None


def get_minecraft_version_url(version_id, custom_version_manifest_url=mojang_version_manifest_url):
    """
    Get minecraft version url using version_id
    """
    # parameter stuff
    version_manifest_url = custom_version_manifest_url

    response = requests.get(version_manifest_url)
    data = response.json()
    version_list = data['versions']

    version_url = None
    for v in version_list:
        if v['id'] == version_id:
            version_url = v['url']
            break

    if version_url is None:
        print(f"Unable to find same as requires version id: {version_id} in the version_manifest.")
        print("Failed to get version data. Cause by unknown Minecraft version.")
        return None

    return version_url


def get_minecraft_version_list(
    custom_version_manifest_url=mojang_version_manifest_url,
    only_return_release=False,
    only_return_snapshot=False,
):
    """Get the full minecraft version list from version_manifest_v2.json"""

    # parameter stuff
    version_manifest_url = custom_version_manifest_url

    response = requests.get(version_manifest_url)
    data = response.json()
    version_list = data['versions']

    release_version_id_list = []
    full_version_id_list = []
    snapshot_version_id_list = []
    for v in version_list:
        v_id = v['id']
        full_version_id_list.append(v_id)
        if v["type"] == "snapshot":
            snapshot_version_id_list.append(v_id)
        elif v["type"] == "release":
            release_version_id_list.append(v_id)

    if only_return_release:
        return release_version_id_list
    elif only_return_snapshot:
        return snapshot_version_id_list

    return full_version_id_list


def get_stable_or_newest_minecraft_version(version_type, custom_version_manifest_url=mojang_version_manifest_url):
    """Get the newest minecraft version from version_manifest_v2.json (key 'latest' > 'release' and 'snapshot'"""
    # parameter stuff
    version_manifest_url = custom_version_manifest_url

    response = requests.get(version_manifest_url)
    data = response.json()
    latest_data = data.get("latest", {})

    latest_release = latest_data.get("release", None)
    latest_snapshot = latest_data.get("snapshot", None)

    if version_type == 'stable' or version_type == 'release':
        return latest_release
    elif version_type == 'snapshot' or version_type == 'newest':
        return latest_snapshot
    else:
        return latest_data


def find_main_class(client_version, custom_version_data=None):
    """Get mainClass from version data"""
    if custom_version_data is not None:
        version_data = custom_version_data
    else:
        version_data = get_version_data(client_version)

    main_class = version_data.get("mainClass", None)

    if main_class is None:
        return False, None
    return True, main_class


def create_version_data(
        minecraft_version,
        version_data,
        without_check_hash=False,
        versions_folder=None,
        launcher_root_dir=None,
):
    """
    Create ${version}.json at versions_folder.
    """
    if launcher_root_dir is None:
        launcher_root_dir = os.getcwd()

    if versions_folder is None:
        versions_folder = os.path.join(launcher_root_dir, "versions")

    version_data_file_path = os.path.join(versions_folder, f"{minecraft_version}.json")

    if not os.path.exists(versions_folder):
        os.makedirs(versions_folder)

    if os.path.exists(version_data_file_path):
        if without_check_hash:
            return version_data_file_path

        version_data = get_version_data(minecraft_version)
        if version_data is None:
            return None

        os.remove(version_data_file_path)

    with open(version_data_file_path, "w") as f:
        json.dump(version_data, f, indent=4)

    return None


def merge_inherited_version_data(version_data, versions_folder):
    inherits_from = version_data.get("inheritsFrom")
    if not inherits_from:
        return version_data

    parent_data = get_version_data_from_exist_data(
        inherits_from,
        versions_folder,
        resolve_inheritance=True,
    )
    if parent_data is None:
        parent_data = get_version_data(inherits_from)

    if parent_data is None:
        return version_data

    merged_data = copy.deepcopy(parent_data)
    child_data = copy.deepcopy(version_data)

    parent_libraries = merged_data.get("libraries", [])
    child_libraries = child_data.pop("libraries", [])
    if parent_libraries or child_libraries:
        merged_data["libraries"] = merge_version_libraries(parent_libraries, child_libraries)

    parent_arguments = merged_data.get("arguments")
    child_arguments = child_data.pop("arguments", None)
    if isinstance(parent_arguments, dict) and isinstance(child_arguments, dict):
        merged_arguments = copy.deepcopy(parent_arguments)
        for key, child_value in child_arguments.items():
            parent_value = merged_arguments.get(key)
            if isinstance(parent_value, list) and isinstance(child_value, list):
                merged_arguments[key] = parent_value + child_value
            else:
                merged_arguments[key] = child_value
        merged_data["arguments"] = merged_arguments
    elif child_arguments is not None:
        merged_data["arguments"] = child_arguments

    if "minecraftArguments" in child_data:
        child_minecraft_args = str(child_data.pop("minecraftArguments") or "").strip()
        if child_minecraft_args:
            merged_data["minecraftArguments"] = child_minecraft_args

    merged_data.update(child_data)
    return merged_data


def get_library_merge_key(library):
    name = str(library.get("name") or "")
    parts = name.split(":")
    if len(parts) < 3:
        return name

    group_id, artifact_id = parts[:2]
    classifier = parts[3] if len(parts) > 3 else ""
    library_kind = "native" if library.get("natives") else "artifact"
    rules = library.get("rules")
    rules_key = ""
    if rules:
        rules_key = json.dumps(rules, sort_keys=True, separators=(",", ":"))

    return ":".join([group_id, artifact_id, classifier, library_kind, rules_key])


def merge_version_libraries(parent_libraries, child_libraries):
    merged_libraries = []
    library_indexes = {}

    for library in list(parent_libraries or []) + list(child_libraries or []):
        if not isinstance(library, dict):
            merged_libraries.append(library)
            continue

        key = get_library_merge_key(library)
        if key in library_indexes:
            merged_libraries[library_indexes[key]] = library
            continue

        library_indexes[key] = len(merged_libraries)
        merged_libraries.append(library)

    return merged_libraries


def get_version_data_from_exist_data(minecraft_version, versions_folder, resolve_inheritance=True):
    version_data_file_path = os.path.join(versions_folder, f"{minecraft_version}.json")

    if os.path.exists(version_data_file_path):
        with open(version_data_file_path, "r") as f:
            version_data = json.load(f)
            if resolve_inheritance:
                return merge_inherited_version_data(version_data, versions_folder)
            return version_data
    else:
        return None



