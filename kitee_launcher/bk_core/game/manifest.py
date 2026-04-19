"""
bk_core

Copyright (c) 2024~2025 Techarerm/TedKai
Copyright (c) 2026 Kitee Contributors. All rights reserved.
"""
import json
import os
import requests

mojang_version_manifest_v2 = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
mojang_version_manifest_v1 = "https://piston-meta.mojang.com/mc/game/version_manifest.json"

class Manifest:
    def __init__(self, url, enable_sha1_check=False, use_local_manifest=False, local_manifest_filepath=None):
        self.url = url
        self.enable_sha1_check = enable_sha1_check

        # Custom
        self.use_local_manifest = False
        self.use_local_manifest = use_local_manifest

        self.local_manifest_filepath = local_manifest_filepath

        # Data store

def get_manifest_data(manifest: Manifest):
    url = manifest.url
    use_local_manifest = manifest.use_local_manifest

    if use_local_manifest:
        local_manifest_filepath = manifest.local_manifest_filepath

        if not(os.path.exists(local_manifest_filepath)):
            return False, None, "Local manifest file not found."

        try:
            with open(local_manifest_filepath) as local_manifest_file:
                return True, json.load(local_manifest_file), None
        except Exception as e:
            return False, None, "Exception while reading local manifest file. ERR: {}".format(e)
    else:
        try:
            r = requests.get(url)

            if r.status_code != 200:
                return False, None, "Failed to get manifest data. Status code: {}".format(r.status_code)
            else:
                return True, r.json(), None
        except Exception as e:
            return False, None, "Exception while getting manifest data. ERR: {}".format(e)


def get_version_data_from_manifest(manifest: Manifest, version_id):
    status, manifest_data, err = get_manifest_data(manifest)

    if not status:
        return False, None, "Failed to get manifest data. ERR: {}".format(err)

    versions = manifest_data.get("versions", None)

    if versions is None:
        return False, None, "Failed to get versions from manifest. The manifest data may be corrupted."

    version_data_url = None

    for version in versions:
        if version_id == version.get("id", None):
            version_data_url = version.get("url", None)

    if version_data_url is None:
        return False, None, "The specified version was not found in the version manifest."
    else:
        r = requests.get(version_data_url)

        if r.status_code != 200:
            return False, None, "Failed to get version data. Status code: {}".format(r.status_code)

        return True, r.json(), None


def check_version_exists(manifest: Manifest, version_id):
    status, manifest_data, err = get_manifest_data(manifest)

    if not status:
        return False, "Failed to get manifest data. ERR: {}".format(err)

    versions = manifest_data.get("versions", None)

    if versions is None:
        return False, "Failed to get versions from manifest. The manifest data may be corrupted."

    for version in versions:
        if version_id == version.get("id", None):
            return True, None

    return False, None


manifest_v2 = Manifest(mojang_version_manifest_v2, enable_sha1_check=True)
manifest_v1 = Manifest(mojang_version_manifest_v1)

