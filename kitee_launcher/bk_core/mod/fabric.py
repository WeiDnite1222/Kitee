"""
bk_core

Copyright (c) 2024~2025 Techarerm/TedKai
"""
import os
import requests
from types import SimpleNamespace
from ..utils.utils import download_file, multi_thread_download


FABRIC_MAVEN_URL = "https://maven.fabricmc.net"



def get_fabric_version_data(loader_version, client_version):
    if not loader_version or not client_version:
        return None

    fabric_version_url = f"https://meta.fabricmc.net/v2/versions/loader/{client_version}/{loader_version}"
    response = requests.get(fabric_version_url)
    if not response.ok:
        return None

    version_data = response.json()
    if "launcherMeta" in version_data:
        return version_data

    return None


def get_fabric_profile_version_data(loader_version, client_version):
    if not loader_version or not client_version:
        return None

    fabric_profile_url = (
        f"https://meta.fabricmc.net/v2/versions/loader/"
        f"{client_version}/{loader_version}/profile/json"
    )
    response = requests.get(fabric_profile_url)
    if not response.ok:
        return None

    version_data = response.json()
    if version_data.get("id"):
        return version_data

    return None


def download_loader(loader_version, libraries_path):
    # Check loader version valid
    if not loader_version:
        return False

    loader_path = f"/net/fabricmc/fabric-loader/{loader_version}/fabric-loader-{loader_version}.jar"
    loader_url = FABRIC_MAVEN_URL + loader_path
    loader_dest = libraries_path + loader_path

    return download_file(loader_url, loader_dest)


def download_intermediary(client_version, libraries_path):
    if not client_version:
        return False

    intermediary_path = f"/net/fabricmc/intermediary/{client_version}/intermediary-{client_version}.jar"
    intermediary_url = FABRIC_MAVEN_URL + intermediary_path
    intermediary_dest = libraries_path + intermediary_path
    return download_file(intermediary_url, intermediary_dest)


def download_libraries(libraries_data, libraries_path):
    download_queue = []

    for lib in libraries_data:
        group_id, artifact_id, version = lib["name"].split(":")

        # Create directory structure (use '/' for URL paths)
        group_path = group_id.replace(".", "/")  # Convert groupId to folder structure using "/"
        library_path = os.path.join(libraries_path, group_path, artifact_id, version)

        # Ensure the target folder exists
        os.makedirs(library_path, exist_ok=True)

        # Construct the download URL using the corrected path
        url = f"{FABRIC_MAVEN_URL}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.jar"

        # Full path where the JAR will be saved
        destination = os.path.join(str(library_path), f"{artifact_id}-{version}.jar")

        # Download the library
        fabric_lib_url_and_dest = [
            (url, destination)
        ]
        download_queue.append(fabric_lib_url_and_dest)
    return multi_thread_download(download_queue, "Fabric libraries")


def get_support_fabric_loader_list(client_version, full_list=False, only_stable=False):
    if not client_version:
        return False, None

    fabric_support_version_url = f"https://meta.fabricmc.net/v2/versions/loader/{client_version}"

    # Get the list of all loader versions
    response = requests.get(fabric_support_version_url)
    if response.status_code != 200:
        return False, None

    loader_data = response.json()
    loader_versions = []

    # Only return the stable version
    if only_stable:
        for loader in loader_data:
            if loader["loader"]["stable"]:
                return True, loader["loader"]["version"]
        return False, None

    if full_list:
        # Collect the available Fabric loader versions
        for loader in loader_data:
            loader_versions.append(loader["loader"]["version"])
    else:
        # Collect only 20 versions in the list
        version_length = 0
        for loader in loader_data:
            if version_length < 20:
                loader_versions.append(loader["loader"]["version"])
            else:
                break
            version_length += 1

    if not loader_versions:
        return False, None

    return True, loader_versions


fabric = SimpleNamespace(
    get_fabric_version_data=get_fabric_version_data,
    get_fabric_profile_version_data=get_fabric_profile_version_data,
    download_loader=download_loader,
    download_intermediary=download_intermediary,
    download_libraries=download_libraries,
    get_support_fabric_loader_list=get_support_fabric_loader_list,
)
