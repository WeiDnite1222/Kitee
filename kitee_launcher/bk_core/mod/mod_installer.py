"""
bk_core

Copyright (c) 2024~2025 Techarerm/TedKai
Copyright (c) 2026 Kitee Contributors. All rights reserved.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from json import JSONDecodeError
from types import SimpleNamespace

import requests

from ..definition.data import INSTANCE_GAME_FOLDER_NAME
from ..instance.instance import (
    create_custom_config,
    get_instance_profile,
    get_custom_config_path,
    get_instance_profile_path,
    write_custom_config,
    write_instance_profile,
)
from ..libraries.libraries import (
    convert_library_name_to_artifact_path,
    libraries_check,
)
from ..mod.fabric import (
    download_intermediary,
    download_libraries as download_fabric_libraries,
    download_loader,
    get_fabric_version_data,
    get_support_fabric_loader_list,
)
from ..mod.forge import (
    FORGE_MAVEN_URL,
    convert_forge_data_to_real,
    convert_maven_name_to_artifact_path_in_the_args,
    detect_forge_processors_depends,
    detect_forge_profile_depends,
    download_forge_libraries_legacy,
    download_forge_libraries_modern,
    get_forge_all_processors_class_name_and_args,
    get_forge_key_data,
    get_forge_processor_depends,
    move_forge_files,
    replace_jvm_args_value_to_real,
)
from ..utils.utils import download_file, extract_zip, find_jar_file_main_class, multi_thread_download


FORGE_METADATA_URL = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"


def get_instance_paths(instance_path):
    game_dir = os.path.join(instance_path, INSTANCE_GAME_FOLDER_NAME)
    launcher_root = os.path.dirname(os.path.dirname(instance_path))
    return {
        "info": get_instance_profile_path(instance_path),
        "config": get_custom_config_path(instance_path),
        "game_dir": game_dir,
        "libraries": os.path.join(launcher_root, "libraries"),
        "installer_tmp": os.path.join(instance_path, ".installer_tmp"),
    }


def get_instance_client_version(instance_path):
    instance_profile = get_instance_profile_path(instance_path)
    status, client_version = get_instance_profile(instance_profile, info_name="client_version")
    if not status:
        return False, None
    return True, client_version


def choose_loader_version(loader_versions, loader_version=None):
    if loader_version is not None:
        return True, loader_version
    if not loader_versions:
        return False, None
    if isinstance(loader_versions, str):
        return True, loader_versions
    return True, loader_versions[0]


def install_fabric_loader(instance_path, loader_version=None):
    paths = get_instance_paths(instance_path)
    os.makedirs(paths["game_dir"], exist_ok=True)
    download_tasks = []

    create_custom_config(paths["config"])

    if not os.path.exists(paths["libraries"]):
        return False

    if not os.path.exists(paths["info"]):
        return False

    status, client_version = get_instance_client_version(instance_path)
    if not status:
        return False

    status, loader_versions = get_support_fabric_loader_list(client_version)
    if not status:
        return False

    status, loader_version = choose_loader_version(loader_versions, loader_version)
    if not status:
        return False

    loader_version_data = get_fabric_version_data(loader_version, client_version)
    if not loader_version_data:
        return False

    libraries_data = loader_version_data["launcherMeta"]["libraries"]["common"]
    loader_tasks = download_loader(loader_version, paths["libraries"])
    if not loader_tasks:
        return False
    download_tasks.extend(loader_tasks)

    intermediary_tasks = download_intermediary(client_version, paths["libraries"])
    if not intermediary_tasks:
        return False
    download_tasks.extend(intermediary_tasks)

    download_tasks.extend(download_fabric_libraries(libraries_data, paths["libraries"]))

    main_class = loader_version_data["launcherMeta"]["mainClass"]["client"]
    write_custom_config(paths["config"], "ModLoaderClass", main_class)
    write_instance_profile("is_vanilla", False, paths["info"])
    write_instance_profile("modified", True, paths["info"])
    write_instance_profile("mod_loader_name", "Fabric", paths["info"])
    write_instance_profile("mod_loader_version", loader_version, paths["info"])
    return download_tasks


def fetch_support_forge_versions(client_version, forge_metadata_url=FORGE_METADATA_URL):
    response = requests.get(forge_metadata_url)
    if response.status_code != 200:
        return False, None

    root = ET.fromstring(response.content)
    versions = root.find("./versioning/versions")
    all_versions = [version.text for version in versions.findall("version")]

    if client_version:
        filtered_versions = [
            version for version in all_versions if version.startswith(client_version)
        ]
        return True, filtered_versions
    return False, None


def install_legacy_forge(install_profile, forge_installer_dest, libraries_path, instance_cfg, loader_version):
    version_json_path = os.path.join(forge_installer_dest, "version.json")
    version_json_status = os.path.exists(version_json_path)

    if version_json_status:
        with open(version_json_path, "r") as f:
            forge_version_data = json.load(f)
    else:
        forge_version_data = install_profile.get("versionInfo", [])
        if len(forge_version_data) == 0:
            return False, None

    libraries = {}
    install_profile_libraries = install_profile.get("libraries", [])
    version_libraries = forge_version_data.get("libraries", [])
    libraries["libraries"] = libraries.get("libraries", []) + install_profile_libraries + version_libraries
    download_tasks = download_forge_libraries_legacy(libraries, libraries_path)

    main_class = forge_version_data.get("mainClass", None)
    orig_arguments = forge_version_data.get("minecraftArguments", None)
    tweak_arguments = None
    if orig_arguments is not None:
        match = re.search(r"--tweakClass\s+(\S+)", orig_arguments)
        if match:
            tweak_arguments = match.group(0)

    if main_class is not None:
        write_custom_config(instance_cfg, "ModLoaderClass", main_class)

    if tweak_arguments is not None:
        write_custom_config(instance_cfg, "ModLoaderGameArgs", tweak_arguments)

    if download_tasks:
        return download_tasks

    move_forge_files(forge_installer_dest, loader_version, libraries_path)
    libraries_check(libraries_path, ["client", "mappings", "slim", "forge", "extra", "asm"])
    return []


def prepare_forge_installer(loader_version, installer_tmp_dir):
    os.makedirs(installer_tmp_dir, exist_ok=True)

    forge_installer_url = (f"https://maven.minecraftforge.net/net/minecraftforge/forge/"
                           f"{loader_version}/forge-{loader_version}-installer.jar")
    installer_dest = os.path.join(installer_tmp_dir, "forge-installer.jar")
    unzip_dest = os.path.join(installer_tmp_dir, "forge_installer_unzipped")
    libraries_dest = os.path.join(unzip_dest, "libraries")

    if os.path.exists(installer_dest):
        os.remove(installer_dest)
    if os.path.exists(unzip_dest):
        shutil.rmtree(unzip_dest)

    os.makedirs(libraries_dest, exist_ok=True)
    if not os.path.exists(installer_dest):
        return False, download_file(forge_installer_url, installer_dest)

    extract_zip(installer_dest, unzip_dest)
    return True, {
        "installer": installer_dest,
        "unzip": unzip_dest,
        "libraries": libraries_dest,
        "install_profile": os.path.join(unzip_dest, "install_profile.json"),
        "version_json": os.path.join(unzip_dest, "version.json"),
        "binpatch": os.path.join(unzip_dest, "data", "client.lzma"),
    }


def load_install_profile(install_profile_path):
    if not os.path.exists(install_profile_path):
        return False, None

    try:
        with open(install_profile_path, "r") as f:
            return True, json.load(f)
    except JSONDecodeError:
        return False, None


def has_modern_forge_processors(install_profile_data):
    try:
        processors_data = install_profile_data["processors"]
        if len(processors_data) <= 0:
            processors_data = install_profile_data["BAKEBAKE"]
        return len(processors_data) > 0
    except KeyError:
        return False


def download_forge_processor_dependencies(install_profile_data, libraries_dest):
    processors_maven_class_list, processors_args_list = get_forge_all_processors_class_name_and_args(
        install_profile_data
    )
    processors_maven_class_list_no_usage, libraries = detect_forge_processors_depends(install_profile_data)

    download_queue = []
    for name in processors_maven_class_list:
        status, processor_class_path = convert_library_name_to_artifact_path(name)
        if not status:
            continue
        url = FORGE_MAVEN_URL + processor_class_path
        dest = os.path.join(libraries_dest, processor_class_path)
        download_queue.append([(url, dest)])

    for library in libraries:
        status, library_path = convert_library_name_to_artifact_path(library)
        if not status:
            continue
        url = FORGE_MAVEN_URL + library_path
        dest = os.path.join(libraries_dest, library_path)
        download_queue.append([(url, dest)])

    download_tasks = multi_thread_download(download_queue, "Processors libraries")
    download_tasks.extend(download_forge_libraries_modern(install_profile_data, libraries_dest))
    return processors_maven_class_list, processors_args_list, download_tasks


def build_forge_processor_commands(
    install_profile_data,
    processors_maven_class_list,
    processors_args_list,
    libraries_dest,
    client_jar_path,
    binpatch_path,
):
    status, depends_data = detect_forge_profile_depends(install_profile_data, return_full_data=True)
    if not status:
        return False, None, None

    placeholders_data = convert_forge_data_to_real(depends_data, libraries_dest)
    placeholders = ast.literal_eval(placeholders_data)
    placeholders.update({
        "MINECRAFT_JAR": client_jar_path,
        "SIDE": "client",
        "BINPATCH": binpatch_path,
    })

    processors_command_list = []
    processors_main_class_list = []
    for processor_class, processor_args in zip(processors_maven_class_list, processors_args_list):
        libraries_path_string = ""
        status, libraries = get_forge_processor_depends(processor_class, install_profile_data)
        status, processor_class_path = convert_library_name_to_artifact_path(processor_class)
        processor_class_path = os.path.join(libraries_dest, processor_class_path)

        for library in libraries:
            status, library_path = convert_library_name_to_artifact_path(library)
            full_path = os.path.join(libraries_dest, library_path)
            libraries_path_string += full_path + ";"

        libraries_path_string += processor_class_path
        if libraries_path_string.endswith(";"):
            libraries_path_string = libraries_path_string[:-1]

        processors_main_class_list.append(find_jar_file_main_class(processor_class_path))
        try:
            resolved_args = [
                arg.format(**placeholders) if isinstance(arg, str) else arg
                for arg in processor_args
            ]
        except KeyError:
            return False, None, None

        final_args = convert_maven_name_to_artifact_path_in_the_args(
            resolved_args, libraries_dest
        )
        full_args = " ".join(final_args)
        command = f'java -Xmx4G -cp "{libraries_path_string}" {processors_main_class_list[-1]} {full_args}'
        processors_command_list.append(command)

    return True, processors_main_class_list, processors_command_list


def run_forge_processors(processors_main_class_list, processors_command_list, retry_limit=3):
    for _ in range(retry_limit):
        failed = False
        for processor_name, command in zip(processors_main_class_list, processors_command_list):
            try:
                subprocess.run(command, shell=True, check=True)
            except Exception:
                failed = True
                break
        if not failed:
            return True
    return False


def write_forge_launch_config(version_json, instance_custom_config, instance_libraries, client_version):
    game_args = None
    jvm_args = None

    game_main_class = version_json.get("mainClass", None)
    if game_main_class is not None:
        write_custom_config(instance_custom_config, "ModLoaderClass", game_main_class)

    if version_json.get("arguments", None):
        arguments_dict = version_json.get("arguments")
        game_args = arguments_dict.get("game", None)
        jvm_args = arguments_dict.get("jvm", None)

    final_game_args = ""
    final_jvm_args = ""
    if game_args is not None:
        for arg in game_args:
            final_game_args += arg + " "

    if jvm_args is not None:
        for orig_arg in jvm_args:
            arg = replace_jvm_args_value_to_real(instance_libraries, client_version, orig_arg)
            final_jvm_args += arg + " "

    if final_game_args != "":
        write_custom_config(instance_custom_config, "ModLoaderGameArgs", final_game_args)

    if final_jvm_args != "":
        write_custom_config(instance_custom_config, "ModLoaderJVMArgs", final_jvm_args)


def install_forge_loader(instance_path, loader_version=None, installer_tmp_dir=None):
    paths = get_instance_paths(instance_path)
    os.makedirs(paths["game_dir"], exist_ok=True)

    if not os.path.exists(paths["libraries"]):
        return False

    if not os.path.exists(paths["config"]):
        create_custom_config(paths["config"])

    status, client_version = get_instance_client_version(instance_path)
    if not status:
        return False

    status, forge_versions = fetch_support_forge_versions(client_version)
    if not status:
        return False

    status, loader_version = choose_loader_version(forge_versions, loader_version)
    if not status:
        return False

    if installer_tmp_dir is None:
        installer_tmp_dir = paths["installer_tmp"]

    status, installer_paths = prepare_forge_installer(loader_version, installer_tmp_dir)
    if not status:
        return installer_paths

    status, install_profile_data = load_install_profile(installer_paths["install_profile"])
    if not status:
        return False

    if not has_modern_forge_processors(install_profile_data):
        return install_legacy_forge(
            install_profile_data,
            installer_paths["unzip"],
            paths["libraries"],
            paths["config"],
            loader_version,
        )

    if not os.path.exists(installer_paths["version_json"]):
        return False

    with open(installer_paths["version_json"], "r") as f:
        version_json = json.load(f)

    if not os.path.exists(installer_paths["binpatch"]):
        return False

    detect_forge_profile_depends(install_profile_data)
    processors_maven_class_list, processors_args_list, download_tasks = download_forge_processor_dependencies(
        install_profile_data,
        installer_paths["libraries"],
    )

    download_tasks.extend(download_forge_libraries_modern(version_json, paths["libraries"]))
    download_tasks.extend(download_forge_libraries_modern(install_profile_data, paths["libraries"]))
    if download_tasks:
        return download_tasks

    client_jar_path = os.path.join(paths["libraries"], "net", "minecraft", client_version, "client.jar")
    if not os.path.exists(client_jar_path):
        return False

    status, processors_main_class_list, processors_command_list = build_forge_processor_commands(
        install_profile_data,
        processors_maven_class_list,
        processors_args_list,
        installer_paths["libraries"],
        client_jar_path,
        installer_paths["binpatch"],
    )
    if not status:
        return False

    if not run_forge_processors(processors_main_class_list, processors_command_list):
        return False

    move_forge_files(installer_paths["unzip"], loader_version, paths["libraries"])
    forge_client_maven_path = get_forge_key_data("PATCHED", install_profile_data)
    status, forge_client_path = convert_library_name_to_artifact_path(forge_client_maven_path)
    if not status:
        return False

    full_forge_client_path = os.path.join(paths["libraries"], forge_client_path)
    if not os.path.exists(full_forge_client_path):
        return False

    write_forge_launch_config(version_json, paths["config"], paths["libraries"], client_version)
    libraries_check(paths["libraries"], ["client", "mappings", "slim", "forge", "extra", "srg"])
    return []


def install_mod_loader(instance_path, loader_name, loader_version=None):
    loader_name = loader_name.lower()
    if loader_name == "fabric":
        return install_fabric_loader(instance_path, loader_version=loader_version)
    if loader_name == "forge":
        return install_forge_loader(instance_path, loader_version=loader_version)
    return False


mod_installer = SimpleNamespace(
    install_fabric_loader=install_fabric_loader,
    fetch_support_forge_versions=fetch_support_forge_versions,
    install_legacy_forge=install_legacy_forge,
    install_forge_loader=install_forge_loader,
    install_mod_loader=install_mod_loader,
)
