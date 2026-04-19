import os
import json
import platform
import time
import tempfile
import subprocess
import threading
import struct
import zipfile
import re
from pathlib import Path
from ..bk_core.clientlauncher.clauncher import clientLauncher
from ..bk_core.definition.data import INSTANCE_GAME_FOLDER_NAME
from ..bk_core.game.version.version import get_version_data, get_version_data_from_exist_data, merge_version_libraries
from ..bk_core.instance.instance import (
    get_instance_profile,
    parse_instance_profile,
    read_custom_config,
    get_custom_config_path,
    get_instance_profile_path,
)
from ..bk_core.libraries.libraries import (
    is_minecraft_library_allowed,
    maven_name_to_artifact_path,
    minecraft_os_name,
)
from ..managers.mod_loader_rules import (
    build_loader_version_id_candidates,
    get_loader_client_jar_relative_path,
    is_ignored_classpath_java_compatibility_jar,
)

class LaunchManager:
    def __init__(self, gui, launcher, background, instance_manager, jre_manager, account_manager,
                 instances_dir, logger, log_writer=None):
        self.gui = gui
        self.launcher = launcher
        self.background = background

        # Managers
        self.jre_manager = jre_manager
        self.account_manager = account_manager
        self.instance_manager = instance_manager

        # Directories
        self.instances_dir = instances_dir
        self.work_dir = instances_dir.parent
        self.versions_dir = self.work_dir / "versions"
        self.assets_dir = self.work_dir / "assets"
        self.libraries_dir = self.work_dir / "libraries"
        self.runtimes_dir = self.work_dir / "runtimes"

        # Logger
        self.logger = logger

        # Instance Log
        self.log_writer = log_writer

        # vars for launch game
        self.client_processes = {}
        self.client_log_files = {}
        self.launch_log_line_limit = 20000

        # clientLauncher
        self.c_launcher = None

    def launch_instance(self, instance_id):
        """
        Launch instances
        :param instance_id:
        :return:
        """
        instance_id = str(instance_id).strip()

        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        instance_dir = self.instance_manager.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            return {"ok": False, "error": "Instance not found."}

        job_id = self.background.add_worker(
            "Launch instance {}".format(instance_id),
            self.run_launch_instance_job,
            instance_id,
        )
        return {"ok": True, "jobId": job_id}

    def run_launch_instance_job(self, job_id, update_job, instance_id):
        try:
            update_job(state="running", status="Preparing launch...")
            client = self.build_client(instance_id)

            update_job(status="Starting Minecraft...")

            status, error, _ = clientLauncher.start_client(
                client,
                interface_starter=lambda client_object: self.start_client_from_interface(instance_id, client_object),
            )
            if not status:
                raise RuntimeError(error or "Failed to start Minecraft.")

            update_job(state="finished", status="Launch started.", done=True)
        except Exception as exc:
            self.notify_runtime_error(instance_id, exc)
            self.write_launch_error(instance_id, exc)
            raise

    def notify_runtime_error(self, instance_id, error):
        show_error = getattr(self.gui, "show_instance_error", None)
        if not show_error:
            return

        show_error(instance_id, error)

    def create_c_launcher(self):
        self.c_launcher = clientLauncher()
        self.c_launcher.initialize()

    def build_client(self, instance_id):
        """
        Build client
        :param instance_id:
        :return:
        """
        # Get instance dir
        instance_dir = self.instance_manager.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            raise RuntimeError("Instance not found.")

        # Get instance profile path and custom config path
        info_path = get_instance_profile_path(str(instance_dir))
        custom_config_path = get_custom_config_path(str(instance_dir))
        status, info = get_instance_profile(info_path, info_name=None, ignore_not_found=True)
        if not status:
            raise RuntimeError("Failed to read instance profile.")

        # Load profile and extract necessary information for launch
        instance_profile = self.load_instance_profile(info_path)
        instance_name, _, client_version, _, _, _, _ = info

        # Client Ver
        base_client_version = self.resolve_base_client_version(instance_profile)
        if not base_client_version:
            raise RuntimeError("Instance profile is missing a Minecraft version.")

        launch_version_id = self.resolve_launch_version_id(instance_profile, base_client_version)
        self.logger.debug("Launch version resolved: instance_id={}, base_ver={}, launch_ver={}".format(
            instance_id,
            base_client_version,
            launch_version_id,
        ))

        # Dirs
        game_dir = instance_dir / INSTANCE_GAME_FOLDER_NAME
        natives_dir = game_dir / "natives"

        # Use merged version data from mod loader and vanilla Minecraft
        version_data = self.load_merged_version_data(launch_version_id)

        # Find mainClass
        mod_loader_class = self.resolve_instance_mod_loader_class(info, custom_config_path)
        main_class = mod_loader_class or self.get_instance_field(info_path, "main_class") or version_data.get("mainClass")
        if not main_class:
            raise RuntimeError("Main class not found.")

        # Build classpath from version data
        classpath = self.build_classpath(base_client_version, version_data, instance_profile, custom_config_path)

        # Assets
        asset_index = version_data.get("assetIndex", {}).get("id") or base_client_version

        # Account
        account = self.get_launch_account()
        username = str(account.get("Username") or "Player")
        access_token = str(account.get("AccessToken") or "")
        uuid = str(account.get("UUID") or "00000000-0000-0000-0000-000000000000")

        # Java Virtual Machine
        java_major_version = self.get_instance_field(info_path, "support_java_version")
        configured_java = read_custom_config(custom_config_path, "JavaExecutable") or ""
        java_executable = self.find_instance_require_java_executable(configured_java, java_major_version)

        # Check all libraries that in classpath are compatibility with current java version
        self.validate_classpath_java_compatibility(classpath, java_major_version)

        if not java_executable:
            raise RuntimeError("Support java executable does not exist. (Require ver: {})".format(java_major_version))

        # Create clientLauncher obj
        if not self.c_launcher:
            self.create_c_launcher()

        # JVM Args
        memory_jvm_args = str(read_custom_config(custom_config_path, "MemoryJVMArgs") or "").strip()
        jvm_args = self.c_launcher.generate_jvm_args(
            launch_version_id,
            versions_folder=str(self.versions_dir),
            without_ram_args=bool(memory_jvm_args),
        )
        if isinstance(jvm_args, tuple):
            jvm_args = "{} {}".format(jvm_args[0], jvm_args[1])

        # Version jvm args
        version_jvm_args = self.generate_version_jvm_args(
            version_data,
            launch_version_id,
            str(natives_dir),
            classpath,
        )
        mod_loader_jvm_args = ""
        if not version_jvm_args:
            mod_loader_jvm_args = read_custom_config(custom_config_path, "ModLoaderJVMArgs")

        custom_jvm_args = " ".join(
            str(value or "").strip()
            for value in (
                memory_jvm_args,
                version_jvm_args,
                read_custom_config(custom_config_path, "CustomJVMArgs"),
                mod_loader_jvm_args,
            )
            if str(value or "").strip()
        )
        # Combine default jvm_args and custom_jvm_args together
        if custom_jvm_args:
            jvm_args = "{} {}".format(jvm_args, custom_jvm_args).strip()

        # Generate game args
        status, game_args = self.c_launcher.generate_game_args(
            launch_version_id,
            username,
            access_token,
            str(game_dir),
            str(self.assets_dir),
            asset_index,
            uuid,
            versions_folder=str(self.versions_dir),
        )
        if not status:
            raise RuntimeError("Failed to generate game arguments.")

        mod_loader_game_args = str(read_custom_config(custom_config_path, "ModLoaderGameArgs") or "").strip()
        # Combine vanilla and mod loader game args
        if mod_loader_game_args:
            game_args = "{} {}".format(game_args, mod_loader_game_args).strip()

        return self.c_launcher.create_client_instance(
            client_name=f"{instance_id}",
            java_executable=java_executable,
            jvm_args=jvm_args,
            natives_path=str(natives_dir),
            classpath=classpath,
            main_class=main_class,
            game_args=game_args,
        )

    def find_instance_require_java_executable(self, configured_java, java_major_version):
        configured_java = str(configured_java or "").strip()
        if configured_java:
            if not java_major_version:
                return configured_java

            # Check if the configured java is support expect java version
            checker = getattr(self.jre_manager, "java_executable_matches_major", None)
            if checker and checker(configured_java, java_major_version):
                return configured_java

            self.logger.warning(
                "Configured Java executable does not match requested Java {}: {}".format(
                    java_major_version,
                    configured_java,
                )
            )

        return self.jre_manager.find_specified_java_version_executable_from_runtimes(java_major_version)

    @staticmethod
    def load_instance_profile(info_path):
        status, profile = parse_instance_profile(info_path)
        if not status:
            raise RuntimeError("Failed to read instance profile: {}".format(profile))
        return profile

    @staticmethod
    def resolve_base_client_version(profile):
        client_version = str(profile.get("client_version") or "").strip()
        real_minecraft_version = str(profile.get("real_minecraft_version") or "").strip()
        mod_loader_name = str(profile.get("mod_loader_name") or "").strip()
        mod_loader_version = str(profile.get("mod_loader_version") or "").strip()
        has_mod_loader = mod_loader_name.lower() not in ("", "false", "none") or mod_loader_version.lower() not in ("", "false", "none")

        if has_mod_loader and real_minecraft_version:
            return real_minecraft_version

        return real_minecraft_version or client_version

    def resolve_launch_version_id(self, profile, base_client_version):
        if not self.has_mod_loader(profile):
            return base_client_version

        mod_loader_name = str(profile.get("mod_loader_name") or "").strip().lower()
        mod_loader_version = str(profile.get("mod_loader_version") or "").strip()
        loader_version_id = self.find_mod_loader_version_id(
            mod_loader_name,
            mod_loader_version,
            base_client_version,
        )
        return loader_version_id or base_client_version

    @staticmethod
    def has_mod_loader(profile):
        mod_loader_name = str(profile.get("mod_loader_name") or "").strip().lower()
        mod_loader_version = str(profile.get("mod_loader_version") or "").strip().lower()
        return (
            mod_loader_name not in ("", "false", "none")
            or mod_loader_version not in ("", "false", "none")
        )

    def find_mod_loader_version_id(self, mod_loader_name, mod_loader_version, base_client_version):
        """
        Find mod loader version id in versions dir
        :param mod_loader_name:
        :param mod_loader_version:
        :param base_client_version:
        :return:
        """
        candidates = []
        if mod_loader_version:
            candidates.extend(
                build_loader_version_id_candidates(
                    mod_loader_name,
                    mod_loader_version,
                    base_client_version,
                )
            )

        for candidate in candidates:
            if (self.versions_dir / "{}.json".format(candidate)).exists():
                return candidate

        if not self.versions_dir.exists():
            return None

        for version_file in self.versions_dir.glob("*.json"):
            try:
                version_data = json.loads(version_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            version_id = str(version_data.get("id") or version_file.stem)
            inherits_from = str(version_data.get("inheritsFrom") or "")

            # Skip if inherits_from ver is not same as base_client_version
            if inherits_from and inherits_from != base_client_version:
                continue

            saved_loader_name = str(version_data.get("loaderName") or "").strip().lower()
            saved_loader_version = str(version_data.get("loaderVersion") or "").strip().lower()
            # Skip if loader ver not same
            if saved_loader_name == mod_loader_name and saved_loader_version == mod_loader_version.lower():
                return version_id

            normalized_id = version_id.lower()
            if mod_loader_name and mod_loader_name not in normalized_id:
                continue
            if (
                mod_loader_version
                and mod_loader_version.lower() not in normalized_id
                and mod_loader_version.lower().replace("{}-".format(base_client_version).lower(), "") not in normalized_id
            ):
                continue

            return version_id

        return None

    def resolve_instance_mod_loader_class(self, info, custom_config_path):
        """
        Resolve mod loader class from custom config file
        :param info:
        :param custom_config_path:
        :return:
        """
        return self.instance_manager.get_mod_loader_info(info, custom_config_path)["mainClass"]

    def get_launch_account(self):
        status, account_or_error = self.account_manager.get_current_account_data_for_launch()
        if status:
            return account_or_error

        raise RuntimeError(account_or_error or "No current account selected.")

    def build_classpath(self, client_version, version_data, profile=None, custom_config_path=None):
        items = self.build_classpath_items(client_version, version_data, profile, custom_config_path)
        classpath = [item["path"] for item in items if item.get("enabled") and item.get("exists")]
        missing_paths = [
            item["path"]
            for item in items
            if item.get("enabled") and item.get("required") and not item.get("exists")
        ]

        if missing_paths:
            shown = "\n".join(missing_paths[:10])
            if len(missing_paths) > 10:
                shown = "{}\n... and {} more".format(shown, len(missing_paths) - 10)
            raise RuntimeError("Missing shared libraries. Download game files first:\n{}".format(shown))

        return os.pathsep.join(dict.fromkeys(classpath))

    def build_classpath_items(self, client_version, version_data, profile=None, custom_config_path=None):
        disabled_paths = self.get_disabled_classpath_set(custom_config_path)
        items = []

        for library in version_data.get("libraries", []):
            if not self.is_library_allowed(library):
                continue

            relative_path = self.get_library_artifact_path(library)
            if not relative_path:
                continue

            library_path = self.libraries_dir / relative_path
            path_text = str(library_path)
            items.append({
                "id": path_text,
                "name": library.get("name") or Path(relative_path).name,
                "path": path_text,
                "kind": "library",
                "source": "default",
                "enabled": path_text not in disabled_paths,
                "blockable": True,
                "required": True,
                "exists": library_path.exists(),
            })

        if not self.uses_production_client_provider(version_data):
            client_jar = self.resolve_client_jar_path(client_version, profile, custom_config_path)
            client_path = str(client_jar)
            items.append({
                "id": client_path,
                "name": client_jar.name,
                "path": client_path,
                "kind": "client",
                "source": "custom-client" if self.get_custom_client_jar(custom_config_path) else "default",
                "enabled": client_path not in disabled_paths,
                "blockable": True,
                "required": True,
                "exists": client_jar.exists(),
            })

        for extra_path in self.get_extra_classpath(custom_config_path):
            jar_path = Path(extra_path)
            path_text = str(jar_path)
            items.append({
                "id": path_text,
                "name": jar_path.name,
                "path": path_text,
                "kind": "extra",
                "source": "extra",
                "enabled": True,
                "blockable": False,
                "required": False,
                "exists": jar_path.exists(),
            })

        return items

    @staticmethod
    def get_custom_config_list(custom_config_path, key):
        value = read_custom_config(custom_config_path, key) if custom_config_path else []
        if isinstance(value, list):
            return [str(item) for item in value if str(item or "").strip()]
        if str(value or "").strip():
            return [item.strip() for item in str(value).split(os.pathsep) if item.strip()]
        return []

    def get_extra_classpath(self, custom_config_path):
        return self.get_custom_config_list(custom_config_path, "ExtraClasspath")

    def get_disabled_classpath_set(self, custom_config_path):
        return set(self.get_custom_config_list(custom_config_path, "DisabledClasspath"))

    @staticmethod
    def get_custom_client_jar(custom_config_path):
        if not custom_config_path:
            return ""
        return str(read_custom_config(custom_config_path, "CustomClientJar") or "").strip()

    def resolve_client_jar_path(self, client_version, profile=None, custom_config_path=None):
        custom_client_jar = self.get_custom_client_jar(custom_config_path)
        if custom_client_jar:
            return Path(custom_client_jar)

        profile = profile or {}
        mod_loader_name = str(profile.get("mod_loader_name") or "").strip().lower()
        mod_loader_version = str(profile.get("mod_loader_version") or "").strip()

        if mod_loader_version:
            loader_client_jar = get_loader_client_jar_relative_path(mod_loader_name, mod_loader_version)
            if loader_client_jar:
                loader_client_jar = self.libraries_dir / loader_client_jar
                if loader_client_jar.exists():
                    return loader_client_jar

        return self.libraries_dir / "net" / "minecraft" / client_version / "client.jar"

    def uses_production_client_provider(self, version_data):
        jvm_args = version_data.get("arguments", {}).get("jvm", [])
        if not isinstance(jvm_args, list):
            return False

        for raw_arg in jvm_args:
            values = self.resolve_argument_value(raw_arg, {})
            if any("client-extra" in value for value in values):
                return True

        return False

    def validate_classpath_java_compatibility(self, classpath, java_major_version):
        java_major = self.parse_java_major_version(java_major_version)
        if not java_major:
            return

        supported_class_major = java_major + 44
        incompatible = self.find_incompatible_classpath_entry(classpath, supported_class_major)
        if not incompatible:
            return

        jar_path, class_name, class_major = incompatible
        required_java = class_major - 44
        raise RuntimeError(
            "Java {} is too old for one of the launch libraries.\n"
            "Library: {}\n"
            "Class: {}\n"
            "Class file version: {} (requires Java {} or newer)\n"
            "Selected Java supports up to class file version {}.\n"
            "Choose a newer Java runtime for this instance or reinstall the matching mod loader version.".format(
                java_major,
                jar_path,
                class_name,
                class_major,
                required_java,
                supported_class_major,
            )
        )

    @staticmethod
    def parse_java_major_version(java_major_version):
        value = str(java_major_version or "").strip()
        if not value:
            return None

        if value.startswith("1."):
            value = value.split(".", 2)[1]
        else:
            value = value.split(".", 1)[0]

        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def find_incompatible_classpath_entry(classpath, supported_class_major):
        for jar_path in str(classpath or "").split(os.pathsep):
            if not jar_path.lower().endswith(".jar") or not os.path.exists(jar_path):
                continue
            if LaunchManager.is_optional_high_version_compatibility_jar(jar_path):
                continue

            try:
                with zipfile.ZipFile(jar_path) as jar_file:
                    for entry in jar_file.infolist():
                        if not entry.filename.endswith(".class"):
                            continue
                        if entry.filename == "module-info.class" or entry.filename.endswith("/module-info.class"):
                            continue
                        if entry.filename.startswith("META-INF/versions/"):
                            continue

                        with jar_file.open(entry) as class_file:
                            header = class_file.read(8)
                        if len(header) != 8:
                            continue

                        magic, _, class_major = struct.unpack(">IHH", header)
                        if magic != 0xCAFEBABE:
                            continue
                        if class_major > supported_class_major:
                            return jar_path, entry.filename, class_major
            except zipfile.BadZipFile:
                continue
            except OSError:
                continue

        return None

    @staticmethod
    def is_optional_high_version_compatibility_jar(jar_path):
        return is_ignored_classpath_java_compatibility_jar(jar_path)

    def generate_version_jvm_args(self, version_data, version_id, natives_dir, classpath):
        raw_args = version_data.get("arguments", {}).get("jvm", [])
        if not isinstance(raw_args, list):
            return ""

        placeholders = {
            "natives_directory": natives_dir,
            "launcher_name": "Kitee",
            "launcher_version": self.launcher.version,
            "classpath": classpath,
            "classpath_separator": os.pathsep,
            "library_directory": str(self.libraries_dir),
            "version_name": version_id,
        }
        args = []
        for raw_arg in raw_args:
            args.extend(self.resolve_argument_value(raw_arg, placeholders))

        return " ".join(
            self.quote_command_argument(arg)
            for arg in self.filter_embedded_launch_args(args)
        )

    def resolve_argument_value(self, raw_arg, placeholders):
        if isinstance(raw_arg, str):
            return [self.replace_argument_placeholders(raw_arg, placeholders)]

        if not isinstance(raw_arg, dict):
            return []

        rules = raw_arg.get("rules")
        if rules and not self.are_argument_rules_allowed(rules):
            return []

        value = raw_arg.get("value")
        if isinstance(value, list):
            return [self.replace_argument_placeholders(str(item), placeholders) for item in value]
        if value is not None:
            return [self.replace_argument_placeholders(str(value), placeholders)]

        return []

    @staticmethod
    def replace_argument_placeholders(value, placeholders):
        for key, replacement in placeholders.items():
            value = value.replace("${" + key + "}", str(replacement))
        return value

    def are_argument_rules_allowed(self, rules):
        allowed = False
        for rule in rules:
            action = rule.get("action")
            os_rule = rule.get("os") or {}
            features_rule = rule.get("features") or {}
            matches_os = self.matches_os_rule(os_rule)
            matches_features = not features_rule

            if matches_os and matches_features:
                allowed = action == "allow"

        return allowed

    def matches_os_rule(self, os_rule):
        os_name = os_rule.get("name")
        os_arch = str(os_rule.get("arch") or "").lower()
        os_version = os_rule.get("version")

        if os_name is not None and os_name != self.minecraft_os_name():
            return False
        if os_arch and os_arch not in platform.machine().lower():
            return False
        if os_version and not re.search(str(os_version), platform.version()):
            return False

        return True

    @staticmethod
    def filter_embedded_launch_args(args):
        filtered = []
        skip_next = False
        for index, arg in enumerate(args):
            if skip_next:
                skip_next = False
                continue

            if arg == "-cp" or arg == "-classpath":
                skip_next = True
                continue
            if arg.startswith("-Djava.library.path="):
                continue
            if arg.startswith("-XX:HeapDumpPath="):
                continue
            if arg == "${classpath}" and index > 0 and args[index - 1] in ("-cp", "-classpath"):
                continue

            filtered.append(arg)

        return filtered

    @staticmethod
    def quote_command_argument(arg):
        arg = str(arg)
        if not arg:
            return '""'
        if arg.startswith('"') and arg.endswith('"'):
            return arg
        if any(char.isspace() for char in arg):
            return '"{}"'.format(arg.replace('"', '\\"'))
        return arg

    def get_library_artifact_path(self, library):
        downloads = library.get("downloads", {})
        artifact = downloads.get("artifact") if isinstance(downloads, dict) else None
        if artifact and artifact.get("path"):
            return artifact["path"]

        if library.get("natives"):
            return None

        name = library.get("name")
        if not name:
            return None

        return self.maven_name_to_artifact_path(name)

    @staticmethod
    def maven_name_to_artifact_path(name):
        return maven_name_to_artifact_path(name, path_separator=os.sep)

    def is_library_allowed(self, library):
        return is_minecraft_library_allowed(library)

    @staticmethod
    def minecraft_os_name():
        return minecraft_os_name()

    def load_version_data(self, client_version):
        version_data = get_version_data_from_exist_data(client_version, str(self.versions_dir))
        if version_data is not None:
            return version_data

        version_data = get_version_data(client_version)
        if version_data is None:
            raise RuntimeError("Failed to load version data.")

        self.versions_dir.mkdir(parents=True, exist_ok=True)
        version_file = self.versions_dir / "{}.json".format(client_version)
        version_file.write_text(json.dumps(version_data, indent=4), encoding="utf-8")
        return version_data

    def load_merged_version_data(self, version_id):
        version_data = self.load_version_data(version_id)
        inherited_version = str(version_data.get("inheritsFrom") or "").strip()
        if not inherited_version:
            return version_data

        parent_data = self.load_merged_version_data(inherited_version) # This version data is from vanilla Minecraft
        merged = dict(parent_data)

        for key, value in version_data.items():
            if key in ("arguments", "libraries"):
                continue
            merged[key] = value

        # Merge libraries and arguments
        merged["libraries"] = merge_version_libraries(
            parent_data.get("libraries", []),
            version_data.get("libraries", []),
        )
        merged["arguments"] = self.merge_version_arguments(
            parent_data.get("arguments", {}),
            version_data.get("arguments", {}),
        )
        return merged

    @staticmethod
    def merge_version_arguments(parent_arguments, child_arguments):
        if not isinstance(parent_arguments, dict):
            parent_arguments = {}
        if not isinstance(child_arguments, dict):
            child_arguments = {}

        merged = dict(parent_arguments)
        for key in ("game", "jvm"):
            parent_values = parent_arguments.get(key, [])
            child_values = child_arguments.get(key, [])

            if not isinstance(parent_values, list):
                parent_values = [parent_values]
            if not isinstance(child_values, list):
                child_values = [child_values]

            merged[key] = parent_values + child_values

        for key, value in child_arguments.items():
            if key not in merged:
                merged[key] = value

        return merged

    def get_instance_field(self, info_path, field_name):
        status, value = get_instance_profile(info_path, info_name=field_name, ignore_not_found=True)
        if not status:
            return None
        return value

    def write_launch_error(self, instance_id, error):
        if self.log_writer is None:
            return

        try:
            self.log_writer(instance_id, "[ERROR] Launch failed: {}\n".format(error))
        except Exception:
            self.logger.exception("Failed to write launch error to instance log.")

    def process_launch_instances(self, instance_id):
        """
        Launch instances
        :param instance_id:
        :return:
        """
        # Clean instance log
        self.instance_manager.clear_instance_log(instance_id)


        # Open instance window for target instance
        open_result = self.instance_manager.open_instance_window(instance_id, initial_page="launch")
        if not open_result.get("ok"):
            return open_result

        return self.launch_instance(instance_id)

    def process_launch_multiple_instances(self, instance_ids):
        """
        Launches multiple instances.
        :param instance_ids:
        :return:
        """
        values = {}
        for instance_id in instance_ids:
            self.instance_manager.clear_instance_log(instance_id)

        for instance_id in instance_ids:
            open_result = self.instance_manager.open_instance_window(instance_id, initial_page="launch")
            if not open_result.get("ok"):
                values[instance_id] = open_result
                return open_result

        for instance_id in instance_ids:
            values[instance_id] = self.launch_instance(instance_id)

        return values

    def start_client_from_interface(self, instance_id, client_object):
        log_path = self.instance_manager.get_instance_log_path(instance_id)
        game_dir = self.resolve_instance_game_dir(instance_id)
        game_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8", errors="replace", buffering=1)
        log_file.write("=== Launch {} ===\n".format(time.strftime("%Y-%m-%d %H:%M:%S")))
        log_file.flush()

        if os.name == "nt":
            process = subprocess.Popen(
                ["cmd", "/c", self.write_launch_batch(client_object.launch_command)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
                cwd=str(game_dir),
            )
        else:
            process = subprocess.Popen(
                client_object.launch_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,
                cwd=str(game_dir),
            )

        self.client_processes[instance_id] = process
        self.client_log_files[instance_id] = log_file
        self.watch_client_process(instance_id, process, log_file)
        return {
            "process": process,
            "pid": process.pid,
            "logger": {
                "mode": "interface",
                "logPath": str(log_path),
            },
        }

    def resolve_instance_game_dir(self, instance_id):
        detail = self.instance_manager.get_instance_detail(instance_id)
        if not detail.get("ok"):
            raise RuntimeError(detail.get("error") or "Failed to get instance detail.")
        return Path(detail["path"]) / INSTANCE_GAME_FOLDER_NAME

    def watch_client_process(self, client_name, process, log_file):
        def watch():
            line_count = 0
            limit_reached = False

            try:
                for line in process.stdout or []:
                    if line_count < self.launch_log_line_limit:
                        log_file.write(line)
                        line_count += 1
                        continue

                    if not limit_reached:
                        log_file.write(
                            "\n[INFO] Log line limit reached ({} lines). Recording stopped; output is still being drained.\n".format(
                                self.launch_log_line_limit,
                            )
                        )
                        log_file.flush()
                        limit_reached = True
            except Exception:
                pass

            exit_code = process.wait()
            message = "\n[INFO] Client exited with code {}.\n".format(exit_code)
            if exit_code:
                message = "\n[ERROR] Client exited with code {}.\n".format(exit_code)

            try:
                log_file.write(message)
                log_file.flush()
                log_file.close()
            except Exception:
                pass

            self.client_log_files.pop(client_name, None)

        watcher = threading.Thread(target=watch, name="ClientLogWatcher-{}".format(client_name), daemon=True)
        watcher.start()

    def append_instance_launch_log(self, instance_id, message):
        log_path = self.instance_manager.get_instance_log_path(instance_id)
        with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
            log_file.write(message)

    def get_instance_log(self, instance_id, offset=0):
        try:
            log_path = self.instance_manager.get_instance_log_path(instance_id)
            if not log_path.exists():
                return {
                    "ok": True,
                    "path": str(log_path),
                    "text": "",
                    "offset": 0,
                    "size": 0,
                }

            safe_offset = max(0, int(offset or 0))
            size = log_path.stat().st_size
            if safe_offset > size:
                safe_offset = 0

            with log_path.open("rb") as log_file:
                log_file.seek(safe_offset)
                data = log_file.read()
                next_offset = log_file.tell()

            return {
                "ok": True,
                "path": str(log_path),
                "text": data.decode("utf-8", errors="replace"),
                "offset": next_offset,
                "size": size,
            }
        except Exception as exc:
            self.logger.exception("Failed to read instance log.")
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def write_launch_batch(launch_command):
        with tempfile.NamedTemporaryFile(
            suffix=".bat",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as batch:
            batch.write("@echo off\r\n")
            batch.write("chcp 65001 >nul\r\n")
            batch.write(launch_command)
            batch.write("\r\n")
            return batch.name
