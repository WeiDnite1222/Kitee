"""
bk_core

Copyright (c) 2024~2025 Techarerm/TedKai
"""
import os
import platform
import re
from ..utils.utils import download_file, multi_thread_download, multithread_download


def libraries_check(libraries_folder, filter_names=None):
    """This function is under testing! Find all available libraries and detect the duplicate version."""
    if filter_names is None:
        filter_names = []

    def semantic_version_key(version):
        """
        Convert a semantic version string to a comparable tuple.
        Handles invalid versions by returning a fallback tuple.
        """
        try:
            return tuple(map(int, version.split('.')))
        except ValueError:
            # Fallback for non-semantic versions (place them last during sorting)
            return tuple()

    def normalize_library_name(file_name):
        """
        Extract the base library name (excluding suffixes like '-client' or '-universal').
        """
        if "-" in file_name:
            return file_name.split("-")[0]
        return file_name

    def should_skip_file(file_name):
        """
        Check if a file should be skipped based on filter_names.
        """
        return any(filter_name in file_name for filter_name in filter_names)

    def find_duplicates(library_versions):
        for lib_name, versions in library_versions.items():
            # Group by normalized file name to ensure distinct library types
            grouped_versions = {}
            for version, path, file in versions:
                base_name = normalize_library_name(file)
                if base_name not in grouped_versions:
                    grouped_versions[base_name] = []
                grouped_versions[base_name].append((version, path, file))

            for base_name, grouped in grouped_versions.items():
                # Sort versions by semantic versioning (newer versions first)
                grouped.sort(key=lambda x: semantic_version_key(x[0]), reverse=True)

                # Check for duplicates
                if len(grouped) > 1:
                    print(f"Found duplicate libraries for {lib_name} ({base_name}):")
                    for version, path, file in grouped:
                        print(f"  Version: {version}, Path: {path}, File: {file}")

                    # Identify the newest version
                    newest_version = grouped[0]
                    print(f"  Keeping: {newest_version[1]}/{newest_version[2]}")
                    print()

                    for version, path, file in grouped[1:]:  # Skip the newest version
                        file_to_delete = os.path.join(path, file)

                        # Check if the file should be skipped
                        if should_skip_file(file):
                            print(f"  Skipping deletion for filtered file: {file_to_delete}")
                            continue

                        print(f"  Deleting duplicate: {file_to_delete}")
                        try:
                            os.remove(file_to_delete)  # Delete the duplicate file
                            print(f"  Successfully deleted: {file_to_delete}")
                        except OSError as e:
                            print(f"  Error deleting {file_to_delete}: {e}")

                    print()

    library_versions = {}

    # Traverse the libraries folder to find directories containing JAR files
    for root, dirs, files in os.walk(libraries_folder):
        for file in files:
            if file.endswith(".jar") and "natives" not in file:
                # Extract library name and version from the path
                parts = root.split(os.sep)
                if len(parts) >= 2:
                    library_name = parts[-2]
                    version = parts[-1]
                else:
                    library_name = None
                    version = None
                if library_name and version:
                    # Organize by library name and append versions with their paths
                    if library_name not in library_versions:
                        library_versions[library_name] = []
                    library_versions[library_name].append((version, root, file))

    # Check for duplicates
    find_duplicates(library_versions)


def convert_library_name_to_artifact_path(library_path, only_return_artifact_name=False):
    extra_id = None
    classifier = None
    extension = ".jar"
    try:
        # Remove the square brackets
        library_path = library_path.strip("[]")

        # Split the library path into components
        components = library_path.split(":")
        if len(components) > 3:
            # Handle the components
            group_id = components[0]
            artifact_id = components[1]
            version_and_classifier = components[2]
            if len(components) >= 3:
                extra_id = components[3]
            artifact_version = version_and_classifier
        else:
            group_id = components[0]
            artifact_id = components[1]
            version_and_classifier = components[2]
            artifact_version = version_and_classifier
            if "@" in version_and_classifier:
                artifact_version, extension = version_and_classifier.split("@")
                extension = "." + extension

        if extra_id is not None:
            if "@" in extra_id:
                extension = "-" + extra_id.replace("@", ".")
            else:
                extension = "-" + extra_id + ".jar"

        # Convert group_id to group_path by replacing '.' with the file separator
        group_path = "/".join(group_id.split("."))

        # Construct the file name
        if classifier:
            artifact_file_name = f"{artifact_id}-{artifact_version}{extension}"
        else:
            artifact_file_name = f"{artifact_id}-{artifact_version}{extension}"

        # Construct the full artifact path
        artifact_path = f"{group_path}/{artifact_id}/{artifact_version}/{artifact_file_name}"

        if only_return_artifact_name:
            return True, artifact_id

        return True, artifact_path

    except Exception as e:
        return False, None


def parse_maven_name(name):
    normalized = str(name or "").strip().strip("[]").strip("'\"")
    parts = normalized.split(":")
    if len(parts) < 3:
        return None

    group_id, artifact_id, version = parts[:3]
    classifier = parts[3] if len(parts) > 3 else ""
    extension = "jar"
    if "@" in version:
        version, extension = version.split("@", 1)
    if classifier and "@" in classifier:
        classifier, extension = classifier.split("@", 1)

    return {
        "group_id": group_id,
        "artifact_id": artifact_id,
        "version": version,
        "classifier": classifier,
        "extension": extension,
    }


def maven_name_to_artifact_path(name, path_separator="/"):
    parsed = parse_maven_name(name)
    if not parsed:
        return None

    group_id = parsed["group_id"]
    artifact_id = parsed["artifact_id"]
    version = parsed["version"]
    classifier = parsed["classifier"]
    extension = parsed["extension"]

    file_name = "{}-{}".format(artifact_id, version)
    if classifier:
        file_name = "{}-{}".format(file_name, classifier)
    file_name = "{}.{}".format(file_name, extension)

    return path_separator.join(group_id.split(".") + [artifact_id, version, file_name])


def minecraft_os_name():
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "osx"
    return "linux"


def is_minecraft_library_allowed(library):
    rules = library.get("rules")
    if not rules:
        return True

    allowed = False
    current_os = minecraft_os_name()
    current_arch = platform.machine().lower()
    for rule in rules:
        action = rule.get("action")
        os_rule = rule.get("os") or {}
        os_name = os_rule.get("name")
        os_arch = str(os_rule.get("arch") or "").lower()
        matches_os = os_name is None or os_name == current_os
        matches_arch = not os_arch or os_arch in current_arch

        if matches_os and matches_arch:
            allowed = action == "allow"

    return allowed


def native_classifier_keys():
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        keys = ["natives-windows"]
        if "arm" in machine:
            keys.insert(0, "natives-windows-arm64")
        elif "64" in machine or "amd64" in machine:
            keys.insert(0, "natives-windows-64")
        else:
            keys.insert(0, "natives-windows-32")
        return keys

    if system == "darwin":
        if "arm" in machine:
            return ["natives-macos-arm64", "natives-macos", "natives-osx"]
        return ["natives-macos", "natives-osx"]

    return ["natives-linux-aarch64", "natives-linux"] if "arm" in machine else ["natives-linux"]


def dedupe_download_tasks(tasks):
    deduped = []
    seen = set()
    for task in tasks:
        key = str(task.get("dest") or task.get("url") or task.get("name"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(task)
    return deduped
