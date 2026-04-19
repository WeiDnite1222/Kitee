"""
bk_core

Copyright (c) 2024~2025 Techarerm/TedKai
Copyright (c) 2026 Kitee Contributors. All rights reserved.
"""
import json
import os
import shutil
from types import SimpleNamespace
from ..libraries.libraries import convert_library_name_to_artifact_path
from ..utils.utils import check_url_status, multi_thread_download


FORGE_MAVEN_URL = "https://maven.minecraftforge.net/"
MOJANG_MAVEN_URL = "https://libraries.minecraft.net/"


def detect_forge_profile_depends(profile_data, return_full_data=False):
    # Set some variable
    processors_data = []
    maven_names = []
    url_libraries = []

    # Get "data" object from the profile data
    full_data = profile_data.get("data", None)
    if full_data is None:
        return False, None

    if return_full_data:
        return True, full_data

    # Get MCP_VERSION
    mcp_version = full_data.get("MCP_VERSION", {}).get("client", None)
    if mcp_version is None:
        return False, None

    # Get BINPATCH
    binpatch = full_data.get("BINPATCH", {}).get("client", None)
    if binpatch is None:
        pass

    # Put all dependencies into the waiting list
    for sub_depend, value in full_data.items():
        if "SHA" in sub_depend:
            continue

        data = value.get("client", None)
        if data is None:
            continue

        # Remove some symbols
        if "[" or "]" in data:
            data = data.replace("[", "").replace("]", "")

        if "'" in data:
            data = data.replace("'", "")
        data = f"{sub_depend}>{data}"
        processors_data.append(data)

    # classifying dependency types (MavenName or other)
    for data in processors_data:
        if ":" in data:
            maven_names.append(data)

    # Convert all maven names to maven paths
    for name in maven_names:
        components = name.split(">")
        key, maven_name = components
        status, path = convert_library_name_to_artifact_path(maven_name)
        if status:
            url = FORGE_MAVEN_URL + path
            url_libraries.append(url)

    return True, url_libraries


def convert_forge_data_to_real(depends_data, full_libraries_path):
    """
    You MUST download finished all required libraries before calling this function.
    If not, you may get error while processors forge.
    Convert all maven paths(inside the data) to the real path
    """
    redo_data = {}
    for key, value in depends_data.items():
        client_value = value.get("client", None)
        if client_value is not None:
            redo_data[key] = client_value

    for key, value in redo_data.items():
        status, path = convert_library_name_to_artifact_path(value)
        if status:
            full_path = os.path.join(full_libraries_path, path)
            redo_data[key] = full_path

    return json.dumps(redo_data, indent=4)


def get_forge_key_data(key_name, profile_data):
    data = profile_data.get("data", None)
    if data is None:
        return None

    return data.get(key_name, {}).get("client", None)


def detect_forge_processors_depends(profile_data):
    processors_data = profile_data.get("processors", None)
    main_processors_class_maven_names = []
    libraries_names = []

    if not processors_data:
        return False, None

    for data in processors_data:
        sides = data.get("sides", None)
        if sides is not None:
            continue

        # Get class name
        if "jar" in data:
            main_processors_class_maven_names.append(data["jar"])

        # Get classpath
        if "classpath" in data:
            libraries_names.extend(data["classpath"])

    # Flatten the list of libraries
    return main_processors_class_maven_names, libraries_names


def get_forge_processor_depends(main_class_name, profile_data):
    processors_data = profile_data.get("processors", None)
    if processors_data is None:
        return False, None

    selected_processor_data = None

    for data in processors_data:
        class_name = data.get("jar", None)
        if class_name == main_class_name:
            selected_processor_data = data
            break

    # Check if a matching processor was found
    if selected_processor_data is None:
        return False, None

    classpath_list = selected_processor_data.get("classpath", None)
    if classpath_list is None:
        return False, None
    return True, classpath_list


def get_forge_all_processors_class_name_and_args(profile_data):
    processors_data = profile_data.get("processors", None)
    server_required = profile_data.get("server_required", None)  # ???
    if processors_data is None:
        return False, None

    processors_maven_class_name_list = []
    processors_args_list = []

    for data in processors_data:
        sides = data.get("sides", None)

        if sides is None:
            name = data.get("jar", None)
            args_list = data.get("args", None)

            processors_maven_class_name_list.append(name)
            processors_args_list.append(args_list)

    return processors_maven_class_name_list, processors_args_list


def download_forge_libraries_modern(profile_data, libraries_path):
    libraries = profile_data.get("libraries", {})
    download_queue = []
    for library in libraries:
        url = library.get("downloads", {}).get("artifact", {}).get("url", None)
        if url is None:
            continue
        if len(url) <= 0:
            continue
        path = library.get("downloads", {}).get("artifact", {}).get("path", None)
        if path is None:
            continue
        dest = os.path.join(libraries_path, path)
        library_dir = os.path.dirname(dest)
        os.makedirs(library_dir, exist_ok=True)

        # Download the library
        lib_url_and_dest = [
            (url, dest)
        ]
        download_queue.append(lib_url_and_dest)

    return multi_thread_download(download_queue, "Forge libraries")


def download_forge_libraries_legacy(libraries_data, libraries_path):
    libraries = libraries_data.get("libraries", {})
    download_queue = []
    for library in libraries:
        url = library.get("downloads", {}).get("artifact", {}).get("url", None)
        if url is None or len(url) == 0:
            # Pre-Legacy forge "serverreq": true"
            # server_require = library.get("serverreq", False)
            # client_require = library.get("clientreq", False)
            # if not client_require:
            # if server_require:
            # continue
            # Maven Path example : de.oceanlabs.mcp:mcp_config:1.12.2-20200226.224830@zip
            artifact = library.get("downloads", {}).get("artifact", None)
            maven_path = library.get("name", None)
            # If is legacy forge core file, skip it
            if artifact is not None:
                continue
            # Convert maven path to the real path
            # de.oceanlabs.mcp:mcp_config:1.12.2-20200226.224830@zip =>
            # de/oceanlabs/mcp/mcp_config/1.12.2-20200226.224830/mcp_config-1.12.2-20200226.224830.zip
            status, path = convert_library_name_to_artifact_path(maven_path)
            if not status:
                continue
            # Stitch into a url
            orig_maven_url = library.get("url", None)
            if orig_maven_url is None:
                url = MOJANG_MAVEN_URL + path
            else:
                url = FORGE_MAVEN_URL + path
        else:
            # For legacy forge (pre-modern)
            path = library.get("downloads", {}).get("artifact", {}).get("path", None)

        dest = os.path.join(libraries_path, path)
        library_dir = os.path.dirname(dest)
        os.makedirs(library_dir, exist_ok=True)
        final_url = url.replace("\\", "/")
        # Download the library
        lib_url_and_dest = [
            (final_url, dest)
        ]
        status = check_url_status(final_url)
        if status:
            download_queue.append(lib_url_and_dest)

    return multi_thread_download(download_queue, "Forge libraries")


def convert_maven_name_to_artifact_path_in_the_args(arguments, libraries_path):
    new_arguments = []

    for arg in arguments:
        # Detect and process strings in the form of '[ ... ]'
        if arg.startswith("[") and arg.endswith("]"):
            # Convert Maven path to real path
            status, real_path = convert_library_name_to_artifact_path(arg)
            if not status:
                new_arguments.append(arg)
                continue
            new_path = os.path.join(libraries_path, real_path)
            new_arguments.append(new_path)
        else:
            # Keep non-Maven path arguments unchanged
            new_arguments.append(arg)

    return new_arguments


def replace_jvm_args_value_to_real(libraries_path, minecraft_version, full_args):
    if os.name == "nt":
        library_separator = ";"
    else:
        library_separator = ":"

    replacements = {
        "${library_directory}": libraries_path,
        "${version_name}": minecraft_version,
        "${classpath_separator}": library_separator,
    }

    # Initialize final_args with the original full_args
    final_args = full_args

    # Apply each replacement progressively
    for placeholder, value in replacements.items():
        final_args = final_args.replace(placeholder, value)

    return final_args


def move_forge_files(
    unzip_dest,
    loader_version,
    instance_libraries,
    custom_forge_like_loader_name=None,
    custom_forge_like_loader_maven_name=None,
):
    # For forge-like loader (Or the loader name "neoforge")
    if custom_forge_like_loader_name is not None:
        name = custom_forge_like_loader_name
    else:
        name = "forge"

    if custom_forge_like_loader_maven_name is not None:
        maven_name = custom_forge_like_loader_maven_name
    else:
        maven_name = "minecraftforge"
    # Some recommended path (The path of the forge core file)
    forge_lib_dir = os.path.join(instance_libraries, "net", maven_name, name, loader_version)
    forge_core_dir = os.path.join(instance_libraries, "maven", "net", maven_name, name, loader_version)
    forge_client_dir = os.path.join(instance_libraries, "net", maven_name, name, loader_version)
    os.makedirs(forge_lib_dir, exist_ok=True)
    os.makedirs(forge_core_dir, exist_ok=True)

    # Recommended core files names
    forge_universal_name = f"{name}-{loader_version}-universal.jar"
    forge_core_name = f"{name}-{loader_version}.jar"
    forge_client_name = f"{name}-{loader_version}-client.jar"

    # Move universal jar
    universal_candidates = [
        os.path.join(unzip_dest, forge_universal_name),
        os.path.join(unzip_dest, "maven", "net", maven_name, name, loader_version, forge_universal_name),
        os.path.join(unzip_dest, "libraries", "net", maven_name, name, loader_version, forge_universal_name)
    ]
    for src_path in universal_candidates:
        if os.path.exists(src_path):
            shutil.move(src_path, os.path.join(forge_lib_dir, forge_universal_name))

    # Move core jar
    core_candidates = [
        os.path.join(unzip_dest, forge_core_name),
        os.path.join(unzip_dest, "maven", "net", maven_name, name, loader_version, forge_core_name),
        os.path.join(unzip_dest, "libraries", "net", maven_name, name, loader_version, forge_core_name)
    ]
    for src_path in core_candidates:
        if os.path.exists(src_path):
            shutil.move(src_path, os.path.join(forge_core_dir, forge_core_name))

    # Move client jar
    client_candidates = [
        os.path.join(unzip_dest, forge_client_name),
        os.path.join(unzip_dest, "maven", "net", maven_name, name, loader_version, forge_client_name),
        os.path.join(unzip_dest, "libraries", "net", maven_name, name, loader_version, forge_client_name)
    ]

    for src_path in client_candidates:
        if os.path.exists(src_path):
            shutil.move(src_path, os.path.join(forge_client_dir, forge_client_name))


forge = SimpleNamespace(
    forge_maven_url=FORGE_MAVEN_URL,
    mojang_maven_url=MOJANG_MAVEN_URL,
    detect_forge_profile_depends=detect_forge_profile_depends,
    convert_forge_data_to_real=convert_forge_data_to_real,
    get_forge_key_data=get_forge_key_data,
    detect_forge_processors_depends=detect_forge_processors_depends,
    get_forge_processor_depends=get_forge_processor_depends,
    get_forge_all_processors_class_name_and_args=get_forge_all_processors_class_name_and_args,
    download_forge_libraries_modern=download_forge_libraries_modern,
    download_forge_libraries_legacy=download_forge_libraries_legacy,
    convert_maven_name_to_artifact_path_in_the_args=convert_maven_name_to_artifact_path_in_the_args,
    replace_jvm_args_value_to_real=replace_jvm_args_value_to_real,
    move_forge_files=move_forge_files,
)
