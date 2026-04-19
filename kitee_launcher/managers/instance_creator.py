"""
Kitee

Copyright (c) 2026 Kitee Contributors. All rights reserved.

Original repository:

Copyright (c) 2024~2025 Techarerm/TedKai
"""
import os
import json
import hashlib
import platform
import shutil
import subprocess
import zipfile
import requests
import threading
import time
from pathlib import Path
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..bk_core.definition.data import INSTANCE_GAME_FOLDER_NAME
from ..bk_core.instance.instance import (
    create_custom_config,
    create_instance_profile as core_create_instance_profile,
    parse_instance_profile,
    get_payload_java_major_version as core_get_payload_java_major_version,
    get_custom_config_path,
    get_instance_profile_path,
    update_instance_java_major_version as core_update_instance_java_major_version,
    validate_instance_request as core_validate_instance_request,
    write_custom_config,
    write_instance_profile,
)
from ..bk_core.java.java_info import create_java_version_info
from ..bk_core.java.jvm_installer import (
    find_java_home_in_extracted_runtime,
    find_java_runtime_candidates,
    mojang_java_platform_key,
    runtime_java_executable,
)
from ..bk_core.libraries.libraries import (
    dedupe_download_tasks,
    is_minecraft_library_allowed,
    maven_name_to_artifact_path,
    minecraft_os_name,
    native_classifier_keys,
    parse_maven_name,
)
from ..bk_core.game.version.version import (
    get_minecraft_version_type,
    get_version_data,
    mojang_version_manifest_url,
)
from ..bk_core.mod.loader_args import (
    extract_legacy_loader_game_args,
    serialize_loader_arguments,
)
from ..managers.mod_loader_rules import (
    get_loader_display_name,
    get_loader_maven_base,
    get_loader_metadata_url,
    get_primary_artifact_file_names,
    is_primary_loader_library,
    is_primary_loader_maven_name,
    loader_installer_metadata,
    resolve_mod_loader_java_major,
)


class InstanceCreator:
    def __init__(self, gui, work_dir, instance_manager, launcher_version, background, logger):
        self.gui = gui

        # Directories
        self.work_dir = work_dir
        self.instances_dir = self.work_dir / "instances"
        self.versions_dir = self.work_dir / "versions"
        self.assets_dir = self.work_dir / "assets"
        self.libraries_dir = self.work_dir / "libraries"
        self.runtimes_dir = self.work_dir / "runtimes"

        # Objects
        self.background = background
        self.instance_manager = instance_manager
        self.create_instance_window = None

        # Logger & Lock
        self.logger = logger
        self.lock = threading.Lock()  # Instance dir lock
        self.version_lock = threading.Lock()  # Version variables lock

        # Version
        self.launcher_version = launcher_version
        self.version_cache = None
        self.version_cache_time = 0
        self.version_cache_ttl = 600

        # Paths
        self.path_locks = {}
        self.path_locks_lock = threading.Lock()
        self.mod_loader_log_path = None

    def open_create_instance_window(self):
        try:
            import webview

            if self.create_instance_window:
                self.gui.focus_window(self.create_instance_window)
                return {"ok": True, "alreadyOpen": True}

            window = webview.create_window(
                "Create Instance",
                html=self.gui.build_create_instance_html(),
                js_api=self.gui.api,
                width=520,
                height=560,
                min_size=(420, 460),
            )
            self.create_instance_window = window

            def on_closed():
                if self.create_instance_window is window:
                    self.create_instance_window = None

            window.events.closed += on_closed
            return {"ok": True}
        except Exception as exc:
            self.logger.exception("Failed to open create instance window.")
            self.create_instance_window = None
            return {"ok": False, "error": str(exc)}

    def create_instance(self, payload):
        if not isinstance(payload, dict):
            return {"ok": False, "error": "Invalid create instance request type (expected dict)."}

        instance_name = str(payload.get("name") or "").strip()
        instance_uuid = self.instance_manager.generate_instance_uuid()

        # Client Info
        client_version = str(payload.get("clientVersion") or "").strip()
        version_type = str(payload.get("type") or "release").strip() or "release"
        main_class = str(payload.get("mainClass") or "").strip()

        # Mod loader
        mod_loader = str(payload.get("modLoader") or "none").strip().lower()

        # JVM
        java_major_version = self.find_requested_java_major_version(
            str(payload.get("javaMajorVersion") or "").strip(),
            client_version,
            mod_loader,
        )

        # Flags & Custom
        download_game_files = bool(payload.get("downloadGameFiles"))
        skip_java_download = bool(payload.get("skipJavaDownload"))

        if "downloadJava" in payload:
            skip_java_download = not bool(payload.get("downloadJava"))

        mod_loader_version = str(payload.get("modLoaderVersion") or "").strip()
        if mod_loader not in ("none", "fabric", "forge", "neoforge"):
            return {"ok": False, "error": "Unsupported mod loader: {}".format(mod_loader)}
        if mod_loader != "none":
            download_game_files = True

        validation_error = self.validate_instance_request(instance_name, client_version)
        if validation_error:
            return {"ok": False, "error": validation_error}

        # Create target instance folder
        with self.lock:
            self.instances_dir.mkdir(parents=True, exist_ok=True)
            instance_dir = self.instances_dir / instance_uuid

            if instance_dir.exists():
                return {"ok": False, "error": "An instance with this UUID already exists."}

            existing_status, existing_instances = self.instance_manager.get_instances(not_front=True)
            if existing_status:
                for item in existing_instances:
                    if str(item.get("name") or "").strip().lower() == instance_name.lower():
                        return {"ok": False, "error": "An instance with this name already exists."}

        payload = {
            "name": instance_name,
            "uuid": instance_uuid,
            "clientVersion": client_version,
            "type": version_type,
            "javaMajorVersion": java_major_version,
            "mainClass": main_class,
            "skipJavaDownload": skip_java_download,
            "downloadGameFiles": download_game_files,
            "modLoader": mod_loader,
            "modLoaderVersion": mod_loader_version,
        }

        # Start create instance job (or called download game files)
        if download_game_files or not skip_java_download or mod_loader != "none":
            job_id = self.background.add_worker(
                "Create instance {}".format(instance_name),
                self.run_create_instance_job,
                payload,
            )
            return {"ok": True, "jobId": job_id}

        # Create instance profile the instance that don't need to download game files
        try:
            self.create_instance_profile(payload)
        except Exception as exc:
            self.logger.exception("Failed to create instance.")
            return {"ok": False, "error": str(exc)}

        return {"ok": True, "instanceId": instance_uuid}

    def get_minecraft_versions(self):
        """
        Get full minecraft versions (include snapshot, release, etc.)
        :return:
        """
        with self.version_lock:
            if self.version_cache and time.monotonic() - self.version_cache_time < self.version_cache_ttl:
                return self.version_cache

        try:
            response = requests.get(mojang_version_manifest_url, timeout=15)
            response.raise_for_status()
            manifest = response.json()
            versions = [
                {
                    "id": str(version.get("id") or ""),
                    "type": str(version.get("type") or "custom"),
                }
                for version in manifest.get("versions", [])
                if version.get("id")
            ]
            result = {
                "ok": True,
                "versions": versions,
                "latest": manifest.get("latest", {}),
            }
            self.set_version_cache(result)
            return result
        except Exception as exc:
            self.logger.exception("Failed to load Minecraft versions. Exception: {}".format(exc))

        # Failback to get minecraft versions from local versions dir
        local_versions = []
        if self.versions_dir.exists():
            for version_file in sorted(self.versions_dir.glob("*.json"), reverse=True):
                try:
                    version_data = json.loads(version_file.read_text(encoding="utf-8"))
                    if version_data.get("inheritsFrom"):
                        continue
                except Exception as exc:
                    self.logger.error("Failed to load version file: {}, error: {}".format(version_file, exc))

                local_versions.append({
                    "id": version_file.stem,
                    "type": "custom",
                })

        if local_versions:
            result = {"ok": True, "versions": local_versions, "latest": {}}
            self.set_version_cache(result)
            return result

        return {"ok": False, "error": "Failed to load Minecraft versions."}

    def set_version_cache(self, result):
        with self.version_lock:
            self.version_cache = result
            self.version_cache_time = time.monotonic()

    @staticmethod
    def validate_instance_request(instance_name, client_version):
        return core_validate_instance_request(instance_name, client_version)

    def run_create_instance_job(self, _, update_job, payload):
        """
        Run create instance job (Call by background thread)
        """
        try:
            update_job(state="running", status="Loading Minecraft version data...")

            version_data = get_version_data(payload["clientVersion"])
            if version_data is None:
                raise RuntimeError("Failed to load Minecraft version data.")

            # Create profile
            self.create_instance_profile(payload, version_data=version_data)

            # stuff
            instance_dir = self.instances_dir / payload["uuid"]
            java_major_version = self.get_payload_java_major_version(payload, version_data)
            payload["javaMajorVersion"] = java_major_version
            self.update_instance_java_major_version(instance_dir, java_major_version)

            # Download jvm
            if not payload.get("skipJavaDownload") and not self.has_java_runtime(java_major_version):
                self.install_java_runtime(update_job, payload, version_data)

            # Download game files
            if payload.get("downloadGameFiles"):
                self.download_game_files(update_job, payload["clientVersion"], instance_dir, version_data)

            # Install mod loader
            if payload.get("modLoader") == "fabric":
                self.install_fabric_loader(update_job, payload, instance_dir)
            elif payload.get("modLoader") in ("forge", "neoforge"):
                self.install_forge_like_loader(update_job, payload, instance_dir, java_major_version)

            update_job(state="finished", status="Instance created.", done=True)
            self.instance_manager.notify_instances_changed()
        except Exception as exc:
            self.logger.exception("Create instance job failed.")
            error_message = str(exc)

            # Combine log and error message
            log_message = self.current_mod_loader_log_message()
            if log_message and log_message not in error_message:
                error_message = "{}{}".format(error_message, log_message)

            self.notify_runtime_error(error_message)
            update_job(state="failed", status="Create failed.", error=error_message, done=True)
            raise RuntimeError(error_message) from exc

    def install_instance_mod_loader(self, instance_id, payload):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        if not isinstance(payload, dict):
            payload = {}

        loader_name = str(payload.get("modLoader") or "").strip().lower()
        if loader_name not in {"fabric", "forge", "neoforge"}:
            return {"ok": False, "error": "Select Fabric, Forge, or NeoForge."}

        instance_dir = self.instance_manager.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            return {"ok": False, "error": "Instance not found."}

        job_payload = {
            "instanceId": instance_id,
            "modLoader": loader_name,
            "modLoaderVersion": str(payload.get("modLoaderVersion") or "").strip(),
        }
        job_id = self.background.add_worker(
            "Install {} for {}".format(self.display_loader_name(loader_name), instance_id),
            self.run_install_instance_mod_loader_job,
            job_payload,
        )
        return {"ok": True, "jobId": job_id}

    def run_install_instance_mod_loader_job(self, job_id, update_job, payload):
        instance_id = payload["instanceId"]
        instance_dir = self.instance_manager.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            raise RuntimeError("Instance not found.")

        try:
            update_job(state="running", status="Reading instance...")

            # Read instance profile
            info_path = get_instance_profile_path(str(instance_dir))
            status, info = parse_instance_profile(info_path)

            if not status or not isinstance(info, dict):
                raise RuntimeError("Failed to read instance profile.")

            client_version = str(info.get("real_minecraft_version") or info.get("client_version") or "").strip()
            if not client_version:
                raise RuntimeError("Minecraft version is missing.")

            update_job(status="Loading Minecraft version data...")

            # Get target minecraft version data and java_major_version
            version_data = self.get_existing_or_remote_version_data(client_version)

            java_major_version = str(info.get("support_java_version") or "").strip()
            java_major_version = java_major_version or self.get_payload_java_major_version({"javaMajorVersion": ""},
                                                                                           version_data)
            java_major_version = self.find_requested_java_major_version(
                java_major_version,
                client_version,
                payload["modLoader"],
            )
            self.update_instance_java_major_version(instance_dir, java_major_version)

            install_payload = {
                "name": instance_id,
                "clientVersion": client_version,
                "modLoader": payload["modLoader"],
                "modLoaderVersion": payload.get("modLoaderVersion") or "",
                "javaMajorVersion": java_major_version,
            }

            # Install java runtime if current java major version are not available on runtimes dir
            if not self.has_java_runtime(java_major_version):
                self.install_java_runtime(update_job, install_payload, version_data)

            # Yup quilt is missing
            if payload["modLoader"] == "fabric":
                self.install_fabric_loader(update_job, install_payload, instance_dir)
            else:
                self.install_forge_like_loader(update_job, install_payload, instance_dir, java_major_version)

            # Create mod folder
            (instance_dir / INSTANCE_GAME_FOLDER_NAME / "mods").mkdir(parents=True, exist_ok=True)

            # Clear instance cache
            self.instance_manager.invalidate_instance_cache(instance_id)
            self.instance_manager.notify_instances_changed()
            update_job(state="finished", status="Mod loader installed.", done=True)
        except Exception as exc:
            # Handler weird mod loader exception
            self.logger.exception("Install mod loader job failed.")
            error_message = str(exc)
            log_message = self.current_mod_loader_log_message()
            if log_message and log_message not in error_message:
                error_message = "{}{}".format(error_message, log_message)
            self.notify_instance_runtime_error(instance_id, error_message)
            update_job(state="failed", status="Install mod loader failed.", error=error_message, done=True)
            raise RuntimeError(error_message) from exc

    def get_existing_or_remote_version_data(self, client_version):
        launch_manager = getattr(self.gui, "launch_manager", None)
        if launch_manager:
            try:
                return launch_manager.load_version_data(client_version)
            except Exception:
                pass

        version_data = get_version_data(client_version)
        if version_data is None:
            raise RuntimeError("Failed to load Minecraft version data.")
        return version_data

    def notify_runtime_error(self, error):
        show_error = getattr(self.gui, "show_create_instance_error", None)
        if not show_error:
            return

        show_error(error)

    def notify_instance_runtime_error(self, instance_id, error):
        show_error = getattr(self.gui, "show_instance_error", None)
        if not show_error:
            self.notify_runtime_error(error)
            return

        show_error(instance_id, error)

    def create_instance_profile(self, payload, version_data=None):
        """
        Create a new instance profile
        :param payload:
        :param version_data:
        :return:
        """
        instance_name = payload["name"]
        instance_uuid = payload["uuid"]
        client_version = payload["clientVersion"]
        instance_dir = self.instances_dir / instance_uuid
        version_type = payload.get("type") or "release"
        main_class = payload.get("mainClass") or ""
        java_major_version = payload.get("javaMajorVersion") or ""

        if version_data:
            main_class = main_class or version_data.get("mainClass", "")
            java_version = version_data.get("javaVersion", {})
            java_major_version = java_major_version or str(java_version.get("majorVersion") or "")
            try:
                version_type = get_minecraft_version_type(client_version) or version_type
            except Exception:
                pass

        self.instances_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(parents=True, exist_ok=True)

        result = core_create_instance_profile(
            instance_name=instance_name,
            instance_uuid=instance_uuid,
            instance_dir=str(instance_dir),
            client_version=client_version,
            version_type=version_type,
            is_vanilla=True,
            modify_status=False,
            mod_loader_name=False,
            mod_loader_version=False,
            launcher_version=self.launcher_version,
            java_major_version=java_major_version or None,
            main_class=main_class or None,
        )
        if result is True:
            raise RuntimeError("Instance profile already exists.")

        create_custom_config(get_custom_config_path(str(instance_dir)))

        if version_data:
            version_file = self.versions_dir / "{}.json".format(client_version)
            with self.lock_for_path(version_file):
                version_file.write_text(json.dumps(version_data, indent=4), encoding="utf-8")

    @staticmethod
    def get_payload_java_major_version(payload, version_data):
        return core_get_payload_java_major_version(payload, version_data)

    @staticmethod
    def find_requested_java_major_version(java_major_version, client_version, mod_loader):
        compatible_major = resolve_mod_loader_java_major(client_version, mod_loader)
        if compatible_major:
            return compatible_major
        return str(java_major_version or "").strip()

    @staticmethod
    def compatible_java_major_version(client_version, mod_loader):
        return resolve_mod_loader_java_major(client_version, mod_loader)

    @staticmethod
    def update_instance_java_major_version(instance_dir, java_major_version):
        return core_update_instance_java_major_version(instance_dir, java_major_version)

    def has_java_runtime(self, java_major_version):
        java_major_version = str(java_major_version or "").strip()
        if not java_major_version:
            return True

        install_dir = self.runtimes_dir / "Java_{}".format(java_major_version)
        return self.runtime_java_executable(install_dir).exists()

    def log_loader_debug(self, message):
        """
        Log mod loader installation debug message
        :param message:
        :return:
        """
        line = "[{}] {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), message)
        log_path = getattr(self, "mod_loader_log_path", None)
        if log_path:
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                    log_file.write(line)
            except Exception:
                pass

        try:
            self.logger.info("[mod-loader] {}".format(message))
        except Exception:
            pass

    def begin_mod_loader_log(self, instance_dir, loader_name, client_version, loader_version):
        """
        Write some instance profilermation to mod installation log file
        """
        log_path = instance_dir / "logs" / "mod-loader-install.log"
        self.mod_loader_log_path = log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "=== {} install {} ===\n"
            "Minecraft: {}\n"
            "Loader: {}\n"
            "Work dir: {}\n"
            "Libraries: {}\n\n".format(
                self.display_loader_name(loader_name),
                time.strftime("%Y-%m-%d %H:%M:%S"),
                client_version,
                loader_version,
                self.work_dir,
                self.libraries_dir,
            ),
            encoding="utf-8",
            errors="replace",
        )
        return log_path

    def current_mod_loader_log_message(self):
        """Exception may occur when running forge/neoforge processors,
         that's the reason why this function is created."""
        log_path = getattr(self, "mod_loader_log_path", None)
        if not log_path:
            return ""
        return " Mod loader install log: {}".format(log_path)

    def install_fabric_loader(self, update_job, payload, instance_dir):
        # Version
        client_version = payload["clientVersion"]
        loader_version = str(payload.get("modLoaderVersion") or "").strip()

        # Load metadata
        update_job(status="Loading Fabric loader metadata...", total=0, progress=0)
        if not loader_version:
            loader_version = self.get_latest_fabric_loader_version(client_version)

        if not loader_version:
            raise RuntimeError("Failed to find a Fabric loader version for {}.".format(client_version))

        # Start log
        self.begin_mod_loader_log(instance_dir, "fabric", client_version, loader_version)
        loader_data = self.get_fabric_loader_data(client_version, loader_version)
        if not loader_data:
            raise RuntimeError("Failed to load Fabric loader data.")

        # Get fabric profile ver data
        profile_version_data = self.get_fabric_profile_version_data(client_version, loader_version)
        if not profile_version_data:
            raise RuntimeError("Failed to load Fabric loader profile.")

        # Collect target fabric version require dependencies and download
        tasks = self.collect_fabric_tasks(client_version, loader_version, loader_data)
        update_job(status="Downloading Fabric loader...", total=len(tasks), progress=0)
        self.download_tasks(update_job, tasks, status_label="Downloading Fabric loader")

        # Save mod loader version data (for launch manager use)
        self.save_mod_loader_version_data(profile_version_data, client_version, "fabric", loader_version)

        # Get info and custom config path then create it
        config_path = get_custom_config_path(str(instance_dir))
        info_path = get_instance_profile_path(str(instance_dir))
        create_custom_config(config_path)

        # fabric mainClass
        main_class = (
                profile_version_data.get("mainClass")
                or loader_data.get("launcherMeta", {}).get("mainClass", {}).get("client")
        )
        if not main_class:
            raise RuntimeError("Fabric loader metadata does not contain a client main class.")

        # Update fabric mainClass and mod loder info to custom config, instance profile
        write_custom_config(config_path, "ModLoaderClass", main_class, True)
        write_instance_profile("is_vanilla", False, info_path)
        write_instance_profile("modified", True, info_path)
        write_instance_profile("mod_loader_name", "Fabric", info_path)
        write_instance_profile("mod_loader_version", loader_version, info_path)

    @staticmethod
    def get_latest_fabric_loader_version(client_version):
        response = requests.get("https://meta.fabricmc.net/v2/versions/loader/{}".format(client_version), timeout=30)
        response.raise_for_status()

        for item in response.json():
            loader = item.get("loader", {})
            if loader.get("stable") and loader.get("version"):
                return str(loader["version"])

        data = response.json()
        if data:
            return str(data[0].get("loader", {}).get("version") or "")

        return ""

    @staticmethod
    def get_fabric_loader_data(client_version, loader_version):
        response = requests.get(
            "https://meta.fabricmc.net/v2/versions/loader/{}/{}".format(client_version, loader_version),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def get_fabric_profile_version_data(client_version, loader_version):
        response = requests.get(
            "https://meta.fabricmc.net/v2/versions/loader/{}/{}/profile/json".format(
                client_version,
                loader_version,
            ),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def save_mod_loader_version_data(self, version_data, client_version, loader_name, loader_version):
        """
        Save mod loader version data to versions_dir
        :param version_data: target mod loader version
        :param client_version: client version
        :param loader_name:
        :param loader_version:
        :return:
        """
        version_id = str(version_data.get("id") or "").strip()
        if not version_id:
            version_id = "{}-loader-{}-{}".format(loader_name, loader_version, client_version)
            version_data["id"] = version_id

        version_data.setdefault("inheritsFrom", client_version)
        version_data["loaderName"] = loader_name
        version_data["loaderVersion"] = loader_version
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        version_file = self.versions_dir / "{}.json".format(version_id)
        version_file.write_text(json.dumps(version_data, indent=4), encoding="utf-8")
        return version_id

    def install_forge_like_loader(self, update_job, payload, instance_dir, java_major_version):
        """
        Comment from forge installer:
        "Please do not automate the download and installation of Forge.",
        "Our efforts are supported by ads from the download page.",
        "If you MUST automate this, please consider supporting the project through https://www.patreon.com/LexManos/"

        Support forge/neoforge:
        Forge: https://www.patreon.com/LexManos/ or download forge via https://files.minecraftforge.net/net/minecraftforge/forge/
        Neoforge: https://opencollective.com/neoforged

        > This function didn't contain any code that from the original forge/neoforge installer. <
        :param update_job:
        :param payload:
        :param instance_dir:
        :param java_major_version:
        :return:
        """
        # Client & loader info
        loader_name = str(payload.get("modLoader") or "").strip().lower()
        client_version = payload["clientVersion"]
        loader_version = str(payload.get("modLoaderVersion") or "").strip()

        # Get metadata
        update_job(status="Loading {} loader metadata...".format(self.display_loader_name(loader_name)), total=0,
                   progress=0)
        if not loader_version:
            loader_version = self.get_latest_forge_like_loader_version(client_version, loader_name)

        if not loader_version:
            raise RuntimeError("Failed to find a {} loader version for {}.".format(loader_name, client_version))

        # Start log file
        log_path = self.begin_mod_loader_log(instance_dir, loader_name, client_version, loader_version)
        self.log_loader_debug("{} install log: {}".format(loader_name, log_path))
        self.log_loader_debug(
            "{} selected version {} for Minecraft {}".format(loader_name, loader_version, client_version))

        # Prepare install paths and profile
        installer_paths = self.prepare_forge_like_installer(update_job, instance_dir, loader_name, loader_version)
        install_profile = self.load_json_file(installer_paths["install_profile"], required=False) or {}
        version_data = self.load_json_file(installer_paths["version_json"], required=False)
        if version_data is None:
            version_data = install_profile.get("versionInfo")  # For legacy forge (e.g. 1.7.0)

        if not isinstance(version_data, dict):
            raise RuntimeError(
                "{} installer does not contain version.json/versionInfo.".format(self.display_loader_name(loader_name)))

        # Save forge/neoforge ver data
        version_id = self.save_mod_loader_version_data(version_data, client_version, loader_name, loader_version)
        self.log_loader_debug("{} version json saved as versions/{}.json".format(loader_name, version_id))

        # Copy libraries that contained in the original installer to launcher libraires dir
        self.copy_embedded_loader_libraries(installer_paths["unzip"], loader_name)

        # Download dependencies
        update_job(status="Downloading {} libraries...".format(self.display_loader_name(loader_name)), total=0,
                   progress=0)
        tasks = []
        tasks.extend(self.collect_version_library_tasks(version_data, loader_name))
        tasks.extend(self.collect_version_library_tasks(install_profile, loader_name))
        tasks.extend(self.collect_processor_library_tasks(install_profile, loader_name, installer_paths["unzip"]))
        tasks = self.dedupe_download_tasks(tasks)
        self.log_loader_debug("{} library task count: {}".format(loader_name, len(tasks)))
        update_job(status="Downloading {} libraries...".format(self.display_loader_name(loader_name)), total=len(tasks),
                   progress=0)
        self.download_tasks(update_job, tasks,
                            status_label="Downloading {} libraries".format(self.display_loader_name(loader_name)))

        # Run processors
        self.run_forge_like_processors(update_job, install_profile, installer_paths, loader_name, loader_version,
                                       client_version, java_major_version)
        self.copy_embedded_loader_libraries(installer_paths["unzip"], loader_name)
        self.ensure_primary_forge_like_artifacts(version_data, installer_paths["unzip"], loader_name)

        config_path = get_custom_config_path(str(instance_dir))
        info_path = get_instance_profile_path(str(instance_dir))
        create_custom_config(config_path)

        main_class = version_data.get("mainClass")
        if not main_class:
            raise RuntimeError(
                "{} version json does not contain a mainClass.".format(self.display_loader_name(loader_name)))

        # Write forge/neoforge mainClass, game args, jvm args to custom config
        # loader_jvm_args are NECESSARY for newer forge and all neoforge version (without it client will crash on launch)
        write_custom_config(config_path, "ModLoaderClass", main_class, True)
        loader_game_args = self.serialize_loader_arguments(version_data.get("arguments", {}).get("game"))
        loader_jvm_args = self.serialize_loader_arguments(
            version_data.get("arguments", {}).get("jvm"),
            placeholders={
                "${library_directory}": str(self.libraries_dir),
                "${version_name}": version_id,
                "${classpath_separator}": os.pathsep,
            },
        )

        # Legacy forge use launchwrapper to start tweak loader, extract "--tweakClass TWEAK_CLASSNAME" from game args.
        legacy_game_args = self.extract_legacy_loader_game_args(version_data.get("minecraftArguments"))
        if legacy_game_args:
            loader_game_args = "{} {}".format(legacy_game_args, loader_game_args).strip()

        # Write game and jvm args back to custom config
        if loader_game_args:
            write_custom_config(config_path, "ModLoaderGameArgs", loader_game_args, True)
        if loader_jvm_args:
            write_custom_config(config_path, "ModLoaderJVMArgs", loader_jvm_args, True)

        # Update forge/neoforge info to instance profile
        write_instance_profile("is_vanilla", False, info_path)
        write_instance_profile("modified", True, info_path)
        write_instance_profile("mod_loader_name", self.display_loader_name(loader_name), info_path)
        write_instance_profile("mod_loader_version", loader_version, info_path)
        self.log_loader_debug("{} install config written. mainClass={}, gameArgs={}, jvmArgs={}".format(
            loader_name,
            main_class,
            loader_game_args,
            loader_jvm_args,
        ))

    @staticmethod
    def serialize_loader_arguments(arguments, placeholders=None):
        return serialize_loader_arguments(arguments, placeholders)

    @staticmethod
    def extract_legacy_loader_game_args(minecraft_arguments):
        return extract_legacy_loader_game_args(minecraft_arguments)

    @staticmethod
    def display_loader_name(loader_name):
        return get_loader_display_name(loader_name)

    def get_latest_forge_like_loader_version(self, client_version, loader_name):
        versions = self.get_forge_like_loader_versions(client_version, loader_name)
        return versions[-1] if versions else ""

    def get_forge_like_loader_versions(self, client_version, loader_name):
        """
        Get forge like loader versions. (Both of forge and neoforge use xml as the format of the version list)
        :param client_version:
        :param loader_name:
        :return:
        """
        metadata_url = get_loader_metadata_url(loader_name)
        if loader_name == "forge":
            response = requests.get(
                metadata_url,
                timeout=30,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            versions = root.find("./versioning/versions")
            all_versions = [version.text for version in versions.findall("version")] if versions is not None else []
            prefix = "{}-".format(client_version)
            return [version for version in all_versions if str(version or "").startswith(prefix)]

        if loader_name == "neoforge":
            response = requests.get(
                metadata_url,
                timeout=30,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            versions = root.find("./versioning/versions")
            all_versions = [version.text for version in versions.findall("version")] if versions is not None else []
            return self.filter_neoforge_versions(client_version, all_versions)

        return []

    @classmethod
    def filter_neoforge_versions(cls, client_version, versions):
        """
        Return versions filtered by neoforge version.
        :param client_version:
        :param versions:
        :return:
        """
        filtered = []
        for version in versions:
            if cls.extract_minecraft_version_from_neoforge(str(version or "")) == client_version:
                filtered.append(version)
        return filtered

    """
    NEOFORGE_VERSIONS_ENDPOINT = "https://maven.neoforged.net/api/maven/versions/releases/"
    NEOFORGE_GAV = "net/neoforged/neoforge"
    
    def get_specified_minecraft_neo_version_list(mc_version):
        r = requests.get(NEOFORGE_VERSIONS_ENDPOINT + quote(NEOFORGE_GAV))
    
        versions = r.json()["versions"]
    
        if not versions:
            raise Exception("No neoforge versions found")
    
        for neo_version in versions:
            # Minecraft Version Example (Old) 1.MajorVersion.MinorVersion (e.g. 1.21.11)
            # NeoForge use this scheme: MajorVersion.MinorVersion.NeoVersion (e.g. 21.11.38-beta)
            paths = neo_version.split(".")
    
            if len(paths) == 3:
                # Use default method to separate mc_version from neo_version
                mc_ver = "1."+paths[0]+"."+paths[1]
            elif len(paths) > 3:
                # Use new method for newest version of minecraft (e.g. 26.1)
                # 26.1.0.0-alpha+snapshot-1
                # MajorVersion.MiddleVersion.MinorVersion (?)
                mc_ver = paths[0] + "." + paths[1] + '.' + paths[2]
                split_by_snapshot_id = neo_version.split("+")
    
                if len(split_by_snapshot_id) == 2:
                    mc_ver = f"{mc_ver}+{split_by_snapshot_id[1]}"
            else:
                raise Exception("Invalid neoforge version: " + neo_version)
    
            print(mc_ver)
    
    NEOFORGE_REPO = "https://maven.neoforged.net/releases/"
    """

    @staticmethod
    def extract_minecraft_version_from_neoforge(loader_version):
        """
        Extract minecraft version from neoforge version.
        See above code to see how to extract minecraft version from neoforge version.
        :param loader_version:
        :return:
        """
        parts = str(loader_version or "").split(".")
        if len(parts) == 3:
            return "1.{}.{}".format(parts[0], parts[1])
        if len(parts) > 3:
            minecraft_version = "{}.{}.{}".format(parts[0], parts[1], parts[2])
            snapshot_parts = str(loader_version or "").split("+", 1)
            if len(snapshot_parts) == 2:
                minecraft_version = "{}+{}".format(minecraft_version, snapshot_parts[1])
            return minecraft_version
        return None

    def prepare_forge_like_installer(self, update_job, instance_dir, loader_name, loader_version):
        metadata = self.forge_like_loader_metadata(loader_name, loader_version)
        tmp_dir = instance_dir / ".installer_tmp" / loader_name
        installer_path = tmp_dir / "{}-installer.jar".format(loader_name)
        unzip_dir = tmp_dir / "unzipped"

        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        unzip_dir.mkdir(parents=True, exist_ok=True)

        self.log_loader_debug("{} installer url: {}".format(loader_name, metadata["installer_url"]))
        update_job(status="Downloading {} installer...".format(self.display_loader_name(loader_name)), total=1,
                   progress=0)
        self.download_one(metadata["installer_url"], installer_path)
        update_job(progress=1, status="Extracting {} installer...".format(self.display_loader_name(loader_name)))

        with zipfile.ZipFile(installer_path, "r") as installer_zip:
            installer_zip.extractall(unzip_dir)

        paths = {
            "tmp": tmp_dir,
            "installer": installer_path,
            "unzip": unzip_dir,
            "install_profile": unzip_dir / "install_profile.json",
            "version_json": unzip_dir / "version.json",
            "binpatch": unzip_dir / "data" / "client.lzma",
            "metadata": metadata,
        }
        self.log_loader_debug("{} installer extracted to {}".format(loader_name, unzip_dir))
        return paths

    @staticmethod
    def forge_like_loader_metadata(loader_name, loader_version):
        return loader_installer_metadata(loader_name, loader_version)

    def load_json_file(self, path, required=True):
        if not path.exists():
            if required:
                raise RuntimeError("Missing json file: {}".format(path))
            return None

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError("Failed to read json file {}: {}".format(path, exc))

    def collect_version_library_tasks(self, version_data, loader_name):
        tasks = []
        if not isinstance(version_data, dict):
            return tasks

        for library in version_data.get("libraries", []):
            task = self.library_to_download_task(library, loader_name)
            if task:
                tasks.append(task)
        return tasks

    def collect_processor_library_tasks(self, install_profile, loader_name, unzip_dir):
        tasks = []
        if not isinstance(install_profile, dict):
            return tasks

        for processor in install_profile.get("processors", []) or []:
            for maven_name in [processor.get("jar")] + list(processor.get("classpath", []) or []):
                if not maven_name:
                    continue
                if self.is_primary_forge_like_maven_name(maven_name, loader_name):
                    self.log_loader_debug(
                        "{} processor dependency will be resolved from installer/processors: {}".format(
                            loader_name,
                            maven_name,
                        ))
                    continue

                artifact_path = self.maven_name_to_artifact_path(maven_name)
                if not artifact_path:
                    continue

                tasks.append({
                    "name": maven_name,
                    "url": self.default_loader_maven_url(loader_name) + artifact_path,
                    "dest": self.libraries_dir / artifact_path,
                    "sha1": None,
                })

        for key_data in (install_profile.get("data") or {}).values():
            client_value = key_data.get("client") if isinstance(key_data, dict) else None
            if not isinstance(client_value, str) or ":" not in client_value:
                continue

            maven_name = client_value.strip("[]'\"")
            if self.is_primary_forge_like_maven_name(maven_name, loader_name):
                self.log_loader_debug("{} data dependency will be resolved from installer/processors: {}".format(
                    loader_name,
                    client_value,
                ))
                continue

            artifact_path = self.maven_name_to_artifact_path(maven_name)
            if artifact_path:
                if self.ensure_installer_data_artifact(maven_name, artifact_path, unzip_dir, loader_name):
                    continue

                tasks.append({
                    "name": client_value,
                    "url": self.default_loader_maven_url(loader_name) + artifact_path,
                    "dest": self.libraries_dir / artifact_path,
                    "sha1": None,
                })

        return tasks

    def library_to_download_task(self, library, loader_name):
        if not isinstance(library, dict):
            return None

        downloads = library.get("downloads", {})
        artifact = downloads.get("artifact") if isinstance(downloads, dict) else None
        if library.get("natives") and not artifact:
            return None

        if artifact and artifact.get("path"):
            url = artifact.get("url")
            if not url:
                if self.is_primary_forge_like_library(library, loader_name):
                    self.log_loader_debug(
                        "{} primary loader library will be resolved from installer/processors: {}".format(
                            loader_name,
                            library.get("name"),
                        ))
                    return None

                url = self.resolve_library_base_url(library, loader_name, default_to_minecraft=True) + artifact["path"]
            return {
                "name": library.get("name", artifact["path"]),
                "url": url,
                "dest": self.libraries_dir / artifact["path"],
                "sha1": artifact.get("sha1"),
            }

        name = library.get("name")
        if self.is_primary_forge_like_library(library, loader_name):
            self.log_loader_debug("{} primary loader library will be resolved from installer/processors: {}".format(
                loader_name,
                name,
            ))
            return None

        artifact_path = self.maven_name_to_artifact_path(name)
        if not artifact_path:
            return None

        return {
            "name": name,
            "url": self.resolve_library_base_url(library, loader_name, default_to_minecraft=True) + artifact_path,
            "dest": self.libraries_dir / artifact_path,
            "sha1": None,
        }

    @staticmethod
    def is_primary_forge_like_library(library, loader_name):
        return is_primary_loader_library(library, loader_name)

    @staticmethod
    def is_primary_forge_like_maven_name(maven_name, loader_name):
        return is_primary_loader_maven_name(maven_name, loader_name)

    def ensure_installer_data_artifact(self, maven_name, artifact_path, unzip_dir, loader_name):
        dest = self.libraries_dir / artifact_path
        if dest.exists():
            return True

        candidate = self.find_installer_data_artifact_candidate(maven_name, artifact_path, unzip_dir)
        if not candidate:
            return False

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, dest)
        self.log_loader_debug("{} data artifact filled from installer: {} -> {}".format(
            loader_name,
            candidate,
            dest,
        ))
        return True

    def find_installer_data_artifact_candidate(self, maven_name, artifact_path, unzip_dir):
        parsed = self.parse_maven_name(maven_name)
        if not parsed:
            return None

        artifact_file = Path(artifact_path).name
        artifact_id = parsed["artifact_id"]
        classifier = parsed["classifier"]
        extension = parsed["extension"]
        simple_names = [
            artifact_file,
            "{}.{}".format(classifier, extension) if classifier else "",
            "{}.{}".format(artifact_id, extension),
        ]
        simple_names = [name for name in simple_names if name]

        search_roots = [
            unzip_dir / "data",
            unzip_dir / "maven",
            unzip_dir / "libraries",
            unzip_dir,
        ]
        for root in search_roots:
            if not root.exists():
                continue

            exact = root / artifact_path
            if exact.exists() and exact.is_file():
                return exact

            for simple_name in simple_names:
                matches = list(root.rglob(simple_name))
                if matches:
                    return matches[0]

        return None

    def resolve_library_base_url(self, library, loader_name, default_to_minecraft=False):
        base_url = str(library.get("url") or "").strip()
        if not base_url:
            base_url = "https://libraries.minecraft.net/" if default_to_minecraft else self.default_loader_maven_url(
                loader_name)
        return base_url.rstrip("/") + "/"

    @staticmethod
    def default_loader_maven_url(loader_name):
        return get_loader_maven_base(loader_name)

    @staticmethod
    def dedupe_download_tasks(tasks):
        return dedupe_download_tasks(tasks)

    def copy_embedded_loader_libraries(self, unzip_dir, loader_name):
        """
        Copy libraries that contains in the installer
        :param unzip_dir:
        :param loader_name:
        :return:
        """
        copied = 0
        for embedded_root_name in ("maven", "libraries"):
            embedded_root = unzip_dir / embedded_root_name
            if not embedded_root.exists():
                continue

            for source in embedded_root.rglob("*"):
                if not source.is_file():
                    continue

                relative_path = source.relative_to(embedded_root)
                dest = self.libraries_dir / relative_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copy2(source, dest)
                    copied += 1

        self.log_loader_debug("{} embedded installer files copied: {}".format(loader_name, copied))

    def ensure_primary_forge_like_artifacts(self, version_data, unzip_dir, loader_name):
        """
        Move forge-core file to libraires dir
        :param version_data:
        :param unzip_dir:
        :param loader_name:
        :return:
        """
        for library in version_data.get("libraries", []):
            # Skip if current library are not primary libray for forge
            if not self.is_primary_forge_like_library(library, loader_name):
                continue

            # Get library relative path
            expected_path = self.get_library_expected_artifact_path(library)
            if not expected_path:
                continue

            expected_dest = self.libraries_dir / expected_path
            if expected_dest.exists():
                self.log_loader_debug("{} primary loader artifact exists: {}".format(loader_name, expected_dest))
                continue

            # Locate primary forge artifact path
            candidate = self.find_primary_forge_like_artifact_candidate(library, unzip_dir, loader_name)
            if not candidate:
                self.log_loader_debug(
                    "{} primary loader artifact missing. Expected {}; no installer candidate found.".format(
                        loader_name,
                        expected_dest,
                    ))
                continue

            # Move library to libraries dir
            expected_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, expected_dest)
            self.log_loader_debug("{} primary loader artifact filled from {} -> {}".format(
                loader_name,
                candidate,
                expected_dest,
            ))

    def get_library_expected_artifact_path(self, library):
        downloads = library.get("downloads", {})
        artifact = downloads.get("artifact") if isinstance(downloads, dict) else None
        if artifact and artifact.get("path"):
            return artifact["path"]
        return self.maven_name_to_artifact_path(library.get("name"))

    def find_primary_forge_like_artifact_candidate(self, library, unzip_dir, loader_name):
        """
        Find primary forge-core file in forge installer(unzipped)
        :param library:
        :param unzip_dir:
        :param loader_name:
        :return:
        """
        name = str(library.get("name") or "")
        parts = name.split(":")
        if len(parts) < 3:
            return None

        group_id, artifact_id, version = parts[:3]
        group_path = Path(*group_id.split("."))
        search_roots = [
            self.libraries_dir,
            unzip_dir,
            unzip_dir / "maven",
            unzip_dir / "libraries",
        ]
        file_names = get_primary_artifact_file_names(loader_name, artifact_id, version)

        exact_candidates = []
        for root in search_roots:
            artifact_dir = root / group_path / artifact_id / version
            for file_name in file_names:
                exact_candidates.append(artifact_dir / file_name)

        for candidate in exact_candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        fallback_patterns = get_primary_artifact_file_names(loader_name, artifact_id, version)
        for root in search_roots:
            if not root.exists():
                continue
            for pattern in fallback_patterns:
                matches = list(root.rglob(pattern))
                if matches:
                    return matches[0]

        self.log_loader_debug("{} primary loader candidate not found for {}".format(loader_name, name))
        return None

    def run_forge_like_processors(self, update_job, install_profile, installer_paths, loader_name, loader_version,
                                  client_version, java_major_version):
        """
        Run forge-like processors
        After this process, necessary file that requires for forge are generated done.
        :param update_job:
        :param install_profile:
        :param installer_paths:
        :param loader_name:
        :param loader_version:
        :param client_version:
        :param java_major_version:
        :return:
        """
        processors = install_profile.get("processors", []) if isinstance(install_profile, dict) else []
        client_processors = [
            processor for processor in processors
            if not processor.get("sides") or "client" in processor.get("sides", [])
        ]
        if not client_processors:
            self.log_loader_debug("{} installer has no client processors.".format(loader_name))
            return

        java_executable = self.resolve_processor_java(java_major_version)
        placeholders = self.build_forge_processor_placeholders(
            install_profile,
            installer_paths,
            loader_version,
            client_version,
        )
        self.log_loader_debug("{} processor count: {}".format(loader_name, len(client_processors)))
        update_job(status="Running {} processors...".format(self.display_loader_name(loader_name)),
                   total=len(client_processors), progress=0)

        for index, processor in enumerate(client_processors, start=1):
            command = self.build_forge_processor_command(java_executable, processor, placeholders)
            self.log_processor_start(loader_name, index, len(client_processors), processor, command)
            result = subprocess.run(command, cwd=str(self.work_dir), capture_output=True, text=True)
            self.log_processor_result(loader_name, index, result)
            if result.returncode != 0:
                raise RuntimeError("{} processor {} failed with exit code {}.{}".format(
                    self.display_loader_name(loader_name),
                    index,
                    result.returncode,
                    self.current_mod_loader_log_message(),
                ))
            update_job(progress=index, status="Running {} processors... {}/{}".format(
                self.display_loader_name(loader_name),
                index,
                len(client_processors),
            ))

    def log_processor_start(self, loader_name, index, total, processor, command):
        classpath_index = command.index("-cp") + 1 if "-cp" in command else None
        classpath_entries = []
        if classpath_index is not None and classpath_index < len(command):
            classpath_entries = command[classpath_index].split(os.pathsep)

        missing_classpath = [entry for entry in classpath_entries if entry and not Path(entry).exists()]
        self.log_loader_debug("{} processor {}/{} jar={}".format(
            loader_name,
            index,
            total,
            processor.get("jar"),
        ))
        self.log_loader_debug("{} processor {}/{} command: {}".format(
            loader_name,
            index,
            total,
            self.quote_command_for_log(command),
        ))
        if missing_classpath:
            self.log_loader_debug("{} processor {}/{} missing classpath entries:\n{}".format(
                loader_name,
                index,
                total,
                "\n".join(missing_classpath),
            ))

    def log_processor_result(self, loader_name, index, result):
        self.log_loader_debug("{} processor {} exit code: {}".format(loader_name, index, result.returncode))
        if result.stdout:
            self.log_loader_debug("{} processor {} stdout:\n{}".format(loader_name, index, result.stdout.rstrip()))
        if result.stderr:
            self.log_loader_debug("{} processor {} stderr:\n{}".format(loader_name, index, result.stderr.rstrip()))

    @staticmethod
    def quote_command_for_log(command):
        quoted = []
        for part in command:
            part = str(part)
            if any(char.isspace() for char in part) and not part.startswith('"'):
                part = '"{}"'.format(part.replace('"', '\\"'))
            quoted.append(part)
        return " ".join(quoted)

    def resolve_processor_java(self, java_major_version):
        install_dir = self.runtimes_dir / "Java_{}".format(java_major_version)
        java_executable = self.runtime_java_executable(install_dir)
        if java_executable.exists():
            return str(java_executable)
        return "java"

    def build_forge_processor_placeholders(self, install_profile, installer_paths, loader_version, client_version):
        """
        Replace default placeholders to real instance path.
        :param install_profile:
        :param installer_paths:
        :param loader_version:
        :param client_version:
        :return:
        """
        placeholders = {
            "SIDE": "client",
            "ROOT": str(self.work_dir),
            "MINECRAFT_JAR": str(self.libraries_dir / "net" / "minecraft" / client_version / "client.jar"),
            "MINECRAFT_VERSION": client_version,
            "INSTALLER": str(installer_paths["installer"]),
            "LIBRARY_DIR": str(self.libraries_dir),
            "BINPATCH": str(installer_paths["binpatch"]),
            "VERSION": loader_version,
        } # This dict may need to update if forge/neoforge update new key

        for key, value in (install_profile.get("data") or {}).items():
            client_value = value.get("client") if isinstance(value, dict) else None
            if not isinstance(client_value, str):
                continue

            normalized = client_value.strip("[]'\"")
            artifact_path = self.maven_name_to_artifact_path(normalized) if ":" in normalized else None
            if artifact_path:
                placeholders[key] = str(self.libraries_dir / artifact_path)
            else:
                placeholders[key] = str(self.locate_installer_data_path(normalized, installer_paths["unzip"]))
            self.log_loader_debug("processor placeholder {}={}".format(key, placeholders[key]))

        return placeholders

    def locate_installer_data_path(self, value, unzip_dir):
        normalized = str(value or "").replace("\\", "/").lstrip("/")
        if not normalized:
            return value

        candidates = [
            unzip_dir / normalized,
            unzip_dir / "data" / normalized,
            unzip_dir / "data" / Path(normalized).name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        self.log_loader_debug("installer data path not found for {}; using {}".format(value, candidates[0]))
        return candidates[0]

    def build_forge_processor_command(self, java_executable, processor, placeholders):
        """
        Build forge processor command (for run_forge_like_processors)
        :param java_executable:
        :param processor:
        :param placeholders:
        :return:
        """
        processor_jar = self.maven_name_to_artifact_path(processor.get("jar"))
        if not processor_jar:
            raise RuntimeError("Invalid Forge processor jar: {}".format(processor.get("jar")))

        classpath_paths = [self.libraries_dir / processor_jar]
        for maven_name in processor.get("classpath", []) or []:
            artifact_path = self.maven_name_to_artifact_path(maven_name)
            if artifact_path:
                classpath_paths.append(self.libraries_dir / artifact_path)

        main_class = self.find_jar_main_class(classpath_paths[0])
        if not main_class:
            raise RuntimeError("Could not find processor main class in {}".format(classpath_paths[0]))

        command = [
            java_executable,
            "-cp",
            os.pathsep.join(str(path) for path in classpath_paths),
            main_class,
        ]
        command.extend(self.resolve_processor_args(processor.get("args", []) or [], placeholders))
        return command

    def resolve_processor_args(self, args, placeholders):
        """
        Replace default placeholders in processor args to real value.
        :param args:
        :param placeholders:
        :return:
        """
        resolved = []
        for arg in args:
            if not isinstance(arg, str):
                resolved.append(str(arg))
                continue

            value = arg
            for key, replacement in placeholders.items():
                value = value.replace("{" + key + "}", str(replacement))

            if value.startswith("[") and value.endswith("]"):
                artifact_path = self.maven_name_to_artifact_path(value)
                if artifact_path:
                    value = str(self.libraries_dir / artifact_path)

            resolved.append(value)
        return resolved

    @staticmethod
    def find_jar_main_class(jar_path):
        if not jar_path.exists():
            return None

        with zipfile.ZipFile(jar_path, "r") as jar:
            try:
                manifest = jar.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
            except KeyError:
                return None

        for line in manifest.splitlines():
            if line.lower().startswith("main-class:"):
                return line.split(":", 1)[1].strip()
        return None

    def collect_fabric_tasks(self, client_version, loader_version, loader_data):
        tasks = [
            {
                "name": "fabric-loader",
                "url": "https://maven.fabricmc.net/net/fabricmc/fabric-loader/{}/fabric-loader-{}.jar".format(
                    loader_version,
                    loader_version,
                ),
                "dest": self.libraries_dir / "net" / "fabricmc" / "fabric-loader" / loader_version / "fabric-loader-{}.jar".format(
                    loader_version),
                "sha1": None,
            },
            {
                "name": "intermediary",
                "url": "https://maven.fabricmc.net/net/fabricmc/intermediary/{}/intermediary-{}.jar".format(
                    client_version,
                    client_version,
                ),
                "dest": self.libraries_dir / "net" / "fabricmc" / "intermediary" / client_version / "intermediary-{}.jar".format(
                    client_version),
                "sha1": None,
            },
        ]

        libraries = loader_data.get("launcherMeta", {}).get("libraries", {}).get("common", [])
        for library in libraries:
            name = library.get("name")
            if not name:
                continue

            artifact_path = self.maven_name_to_artifact_path(name)
            if not artifact_path:
                continue

            base_url = library.get("url") or "https://maven.fabricmc.net/"
            tasks.append({
                "name": name,
                "url": base_url.rstrip("/") + "/" + artifact_path,
                "dest": self.libraries_dir / artifact_path,
                "sha1": None,
            })

        return tasks

    def install_java_runtime(self, update_job, payload, version_data):
        """
        Install Java runtime (source from mojang)
        :param update_job:
        :param payload:
        :param version_data:
        :return:
        """
        java_major_version = self.get_payload_java_major_version(payload, version_data)

        install_dir = self.runtimes_dir / "Java_{}".format(java_major_version)
        with self.lock_for_path(install_dir):
            java_executable = self.runtime_java_executable(install_dir)
            info_path = install_dir / "java.version.info"

            # Check if Java runtime exists
            if info_path.exists() and java_executable.exists():
                update_job(status="Java runtime already installed.", total=1, progress=1)
                return

            # Cleanup install dir
            if install_dir.exists():
                shutil.rmtree(install_dir)
            install_dir.mkdir(parents=True, exist_ok=True)

            # Load manifest
            update_job(status="Loading Java runtime manifest...", total=0, progress=0)
            runtime_manifest = self.get_mojang_java_runtime_manifest(version_data, java_major_version)
            if runtime_manifest is None:
                self.install_azul_java_runtime(update_job, java_major_version, install_dir)
            else:
                self.download_mojang_java_runtime(update_job, runtime_manifest, install_dir)

            if not java_executable.exists():
                raise RuntimeError("Downloaded Java runtime is missing executable: {}".format(java_executable))

            # Create info
            create_java_version_info(java_major_version, platform.machine().lower(), str(install_dir))

    def get_mojang_java_runtime_manifest(self, version_data, java_major_version):
        """
        Get java runtime manifest from mojang
        :param version_data:
        :param java_major_version:
        :return:
        """
        java_version = version_data.get("javaVersion", {})
        component = java_version.get("component")
        manifest_platform = self.mojang_java_platform_key()

        if not component or not manifest_platform: # This may occur when specified java version not found or
            # current platform is unsupported
            return None

        try:
            response = requests.get(
                "https://launchermeta.mojang.com/v1/products/java-runtime/2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json",
                timeout=30,
            )
            response.raise_for_status()
            java_manifest = response.json()
            runtime_candidates = java_manifest.get(manifest_platform, {}).get(component, [])

            if not runtime_candidates:
                runtime_candidates = self.find_java_runtime_candidates(java_manifest, manifest_platform,
                                                                       java_major_version)

            if not runtime_candidates:
                return None

            manifest_url = runtime_candidates[0].get("manifest", {}).get("url")
            if not manifest_url:
                return None

            manifest_response = requests.get(manifest_url, timeout=30)
            manifest_response.raise_for_status()
            return manifest_response.json()
        except Exception as e:
            self.logger.exception(f"Failed to load Mojang Java runtime manifest. Error: {e}")
            return None

    @staticmethod
    def find_java_runtime_candidates(java_manifest, manifest_platform, java_major_version):
        return find_java_runtime_candidates(java_manifest, manifest_platform, java_major_version)

    @staticmethod
    def mojang_java_platform_key():
        return mojang_java_platform_key()

    def download_mojang_java_runtime(self, update_job, runtime_manifest, install_dir):
        """
        Download Java runtime from mojang
        :param update_job:
        :param runtime_manifest:
        :param install_dir:
        :return:
        """
        files = runtime_manifest.get("files", {})
        tasks = []

        for relative_path, file_info in files.items():
            file_type = file_info.get("type")
            dest = install_dir / relative_path

            if file_type == "directory":
                dest.mkdir(parents=True, exist_ok=True)
                continue

            raw_download = file_info.get("downloads", {}).get("raw")
            if not raw_download:
                continue

            tasks.append({
                "name": relative_path,
                "url": raw_download.get("url"),
                "dest": dest,
                "sha1": raw_download.get("sha1"),
                "executable": bool(file_info.get("executable")),
            })

        # Download jvm
        tasks = [task for task in tasks if task.get("url")]
        update_job(status="Downloading Java runtime...", total=len(tasks), progress=0)
        self.download_tasks(update_job, tasks, status_label="Downloading Java runtime")

        for task in tasks:
            if task.get("executable"):
                try:
                    os.chmod(task["dest"], 0o755)
                except OSError:
                    pass

    def install_azul_java_runtime(self, update_job, java_major_version, install_dir):
        """
        Install Azul Java runtime (source from azul)
        :param update_job:
        :param java_major_version:
        :param install_dir:
        :return:
        """

        # Get download url
        update_job(status="Loading Azul Java runtime package...", total=0, progress=0)
        status, download_url, _ = self.get_azul_java_download_url(java_major_version)
        if not status:
            raise RuntimeError("Failed to find a Java runtime download for Java {}.".format(java_major_version))

        tmp_dir = install_dir.parent / ".jvm_installer_tmp_{}".format(java_major_version)
        zip_path = tmp_dir / "jvm-azul-{}.zip".format(java_major_version)
        unzip_dir = tmp_dir / "jvm-azul-{}-unzipped".format(java_major_version)

        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Download jvm
        update_job(status="Downloading Azul Java runtime...", total=1, progress=0)
        self.download_one(download_url, zip_path)
        update_job(progress=1, status="Extracting Azul Java runtime...")

        with zipfile.ZipFile(zip_path, "r") as zip_file:
            zip_file.extractall(unzip_dir)

        # locate JAVA_HOME dir in unzipped folder
        home_dir = self.find_java_home_in_extracted_runtime(unzip_dir)
        if not home_dir:
            raise RuntimeError("JAVA_HOME not found in downloaded Java runtime.")

        # Move JAVA_HOME folder to install dir
        if install_dir.exists():
            shutil.rmtree(install_dir)
        shutil.move(str(home_dir), str(install_dir))

        shutil.rmtree(tmp_dir, ignore_errors=True)

    def get_azul_java_download_url(self, java_major_version):
        system = platform.system().lower()
        machine = platform.machine().lower()
        arch_map = {
            "amd64": "amd64",
            "x86_64": "amd64",
            "arm64": "aarch64",
            "aarch64": "aarch64",
            "i386": "i686",
            "i686": "i686",
            "x86": "i686",
        }
        platform_map = {
            "darwin": "macos",
            "windows": "windows",
            "linux": "linux",
        }
        azul_platform = platform_map.get(system, system)
        azul_arch = arch_map.get(machine, machine)

        base_url = "https://api.azul.com/metadata/v1/zulu/packages"
        for package_type in ("jre", "jdk"):
            params = {
                "java_version": java_major_version,
                "os": azul_platform,
                "arch": azul_arch,
                "java_package_type": package_type,
                "javafx_bundled": "true",
                "release_status": "ga",
                "availability_types": "CA",
                "certifications": "tck",
                "page": "1",
                "page_size": "100",
            }
            try:
                response = requests.get(base_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                self.logger.exception(f"Failed to query Azul Java packages. Error: {e}")
                continue

            if data and data[0].get("download_url"):
                return True, data[0]["download_url"], package_type

        return False, None, None

    @staticmethod
    def find_java_home_in_extracted_runtime(unzip_dir):
        return find_java_home_in_extracted_runtime(unzip_dir)

    @staticmethod
    def runtime_java_executable(install_dir):
        return runtime_java_executable(install_dir)

    def download_game_files(self, update_job, client_version, instance_dir, version_data):
        """
        Download game files
        :param update_job:
        :param client_version:
        :param instance_dir:
        :param version_data:
        :return:
        """
        game_dir = instance_dir / INSTANCE_GAME_FOLDER_NAME
        natives_dir = game_dir / "natives"

        # Create libraries and natives dir
        self.libraries_dir.mkdir(parents=True, exist_ok=True)
        if natives_dir.exists():
            shutil.rmtree(natives_dir)
        natives_dir.mkdir(parents=True, exist_ok=True)

        tasks = []

        # Client
        client_info = version_data.get("downloads", {}).get("client", {})
        client_url = client_info.get("url")
        if client_url:
            tasks.append({
                "name": "client.jar",
                "url": client_url,
                "dest": self.libraries_dir / "net" / "minecraft" / client_version / "client.jar",
                "sha1": client_info.get("sha1"),
            })

        # Library
        library_tasks, native_paths = self.collect_library_tasks(version_data, self.libraries_dir)
        tasks.extend(library_tasks)

        # Assets
        asset_index = version_data.get("assetIndex", {})
        asset_tasks = self.collect_asset_tasks(asset_index)
        tasks.extend(asset_tasks)

        # Download game file
        update_job(status="Downloading game files...", total=len(tasks), progress=0)
        self.download_tasks(update_job, tasks)

        # Extract natives
        update_job(status="Extracting natives...")
        self.extract_natives(native_paths, natives_dir)

    def collect_library_tasks(self, version_data, libraries_dir):
        """
        Collect library and natives from version data then
        :param version_data:
        :param libraries_dir:
        :return:
        """
        tasks = []
        native_paths = []

        for library in version_data.get("libraries", []):
            if not self.is_library_allowed(library):
                continue

            downloads = library.get("downloads", {})
            artifact = downloads.get("artifact")
            # Skip natives library
            has_native_classifiers = bool(downloads.get("classifiers") and library.get("natives"))
            if artifact and artifact.get("url") and artifact.get("path"):
                tasks.append({
                    "name": library.get("name", artifact.get("path")),
                    "url": artifact["url"],
                    "dest": libraries_dir / artifact["path"],
                    "sha1": artifact.get("sha1"),
                })
            elif library.get("name") and not has_native_classifiers:
                artifact_path = self.maven_name_to_artifact_path(library["name"])
                base_url = library.get("url") or "https://libraries.minecraft.net/"
                if artifact_path and base_url:
                    tasks.append({
                        "name": library.get("name"),
                        "url": base_url.rstrip("/") + "/" + artifact_path,
                        "dest": libraries_dir / artifact_path,
                        "sha1": None,
                    })

            classifiers = downloads.get("classifiers", {})

            # Filter native-library by native_classifier_keys
            for native_key in self.native_classifier_keys():
                native = classifiers.get(native_key)
                if not native or not native.get("url") or not native.get("path"):
                    continue

                dest = libraries_dir / native["path"]
                native_paths.append(dest)
                tasks.append({
                    "name": library.get("name", native.get("path")),
                    "url": native["url"],
                    "dest": dest,
                    "sha1": native.get("sha1"),
                })
                break

        return tasks, native_paths

    def collect_asset_tasks(self, asset_index):
        if not asset_index.get("url"):
            return []

        indexes_dir = self.assets_dir / "indexes"
        index_dest = indexes_dir / "{}.json".format(asset_index.get("id") or "legacy")

        self.download_one(asset_index["url"], index_dest, asset_index.get("sha1"))
        try:
            index_data = json.loads(index_dest.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError("Failed to read asset index: {}".format(exc))

        tasks = []
        for name, asset in index_data.get("objects", {}).items():
            asset_hash = asset.get("hash")
            if not asset_hash:
                continue

            tasks.append({
                "name": "asset {}".format(name),
                "url": "https://resources.download.minecraft.net/{}/{}".format(asset_hash[:2], asset_hash),
                "dest": self.assets_dir / "objects" / asset_hash[:2] / asset_hash,
                "sha1": asset_hash,
            })

        return tasks

    def download_tasks(self, update_job, tasks, status_label="Downloading game files"):
        if not tasks:
            return

        completed = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(self.download_one, task["url"], task["dest"], task.get("sha1")) for task in
                       tasks]
            for future in as_completed(futures):
                try:
                    future.result()
                except requests.HTTPError as exc:
                    response = getattr(exc, "response", None)
                    if response is None or response.status_code != 404:
                        raise
                    self.log_loader_debug("{} skipped 404 dependency: {}".format(status_label, exc))

                completed += 1
                update_job(progress=completed, status="{}... {}/{}".format(
                    status_label,
                    completed,
                    len(tasks),
                ))

    def download_one(self, url, dest, expected_sha1=None):
        dest = dest if hasattr(dest, "parent") else self.work_dir / str(dest)
        with self.lock_for_path(dest):
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists() and (not expected_sha1 or self.file_sha1(dest) == expected_sha1):
                return

            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            with dest.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        file.write(chunk)

            if expected_sha1 and self.file_sha1(dest) != expected_sha1:
                raise RuntimeError("Checksum mismatch: {}".format(dest))

    def lock_for_path(self, path):
        key = str(Path(path).resolve()).lower() if os.name == "nt" else str(Path(path).resolve())
        with self.path_locks_lock:
            lock = self.path_locks.get(key)
            if not lock:
                lock = threading.Lock()
                self.path_locks[key] = lock
            return lock

    @staticmethod
    def file_sha1(path):
        digest = hashlib.sha1()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def extract_natives(native_paths, natives_dir):
        for native_path in native_paths:
            if not native_path.exists():
                continue

            with zipfile.ZipFile(native_path, "r") as jar:
                for member in jar.namelist():
                    if member.endswith("/") or member.startswith("META-INF/"):
                        continue
                    jar.extract(member, natives_dir)

        for root, dirs, files in os.walk(natives_dir, topdown=False):
            root_path = type(natives_dir)(root)
            for file_name in files:
                source = root_path / file_name
                target = natives_dir / file_name
                if source == target:
                    continue
                if not target.exists():
                    os.replace(source, target)
            for dir_name in dirs:
                directory = root_path / dir_name
                try:
                    directory.rmdir()
                except OSError:
                    pass

    def is_library_allowed(self, library):
        return is_minecraft_library_allowed(library)

    @staticmethod
    def minecraft_os_name():
        return minecraft_os_name()

    @staticmethod
    def maven_name_to_artifact_path(name):
        return maven_name_to_artifact_path(name)

    @staticmethod
    def parse_maven_name(name):
        return parse_maven_name(name)

    @staticmethod
    def native_classifier_keys():
        return native_classifier_keys()
