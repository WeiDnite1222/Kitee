"""
Kitee

Copyright (c) 2026 Kitee Contributors. All rights reserved.

Original repository:

Copyright (c) 2024~2025 Techarerm/TedKai
"""
import json
import base64
import os
import threading
import shutil
import time
import zipfile
from pathlib import Path

from ..bk_core.definition.data import INSTANCE_GAME_FOLDER_NAME
from ..bk_core.instance.instance import (
    create_custom_config,
    get_instance_profile,
    parse_instance_profile,
    read_custom_config,
    get_custom_config_path,
    get_instance_profile_path,
    write_custom_config,
    write_instance_profile,
    generate_instance_uuid,
)


class InstanceManager:
    def __init__(self, gui, jre_manager, instances_dir, logger):
        self.instances_dir = instances_dir
        self.logger = logger
        self.lock = threading.Lock()
        self.item_cache = {}
        self.detail_cache = {}
        self.jvm_cache = None
        self.jvm_cache_time = 0
        self.jvm_cache_ttl = 15
        self.gui = gui
        self.jre_manager = jre_manager

        self.instance_windows = {}

    def get_instances(self, not_front=False):
        """
        Get instance lists (FrontOnly)
        :return:
        """
        with self.lock:
            if not self.instances_dir.exists():
                if not not_front:
                    return {
                        "ok": True,
                        "instancesDir": str(self.instances_dir),
                        "instances": [],
                    }

                return True, []

            items = []
            try:
                for instance_dir in sorted(self.instances_dir.iterdir(), key=lambda path: path.name.lower()):
                    if not instance_dir.is_dir():
                        continue

                    items.append(self.build_instance_item(instance_dir))
            except Exception as exc:
                self.logger.exception("Failed to list instances.")
                if not not_front:
                    return {"ok": False, "error": str(exc), "instances": []}

                return False, []

            if not not_front:
                return {
                    "ok": True,
                    "instancesDir": str(self.instances_dir),
                    "instances": items,
                }

            return True, items

    def generate_instance_uuid(self):
        try_count = 0
        uuid = None

        existing_ids = set()
        status_code, items = self.get_instances(not_front=True)
        if status_code:
            existing_ids = {str(item.get("id") or "") for item in items}

        while try_count < 5:
            uuid = generate_instance_uuid()

            if uuid not in existing_ids:
                break

            try_count += 1

        if uuid in existing_ids:
            raise RuntimeError("Unable to generate instance uuid. UUID generator may broken")

        return uuid

    def build_instance_item(self, instance_dir):
        """
        Build instance item
        :param instance_dir:
        :return:
        """
        # Get target instance_dir's signature and cached
        signature = self.get_instance_signature(instance_dir)
        cache_key = self.get_instance_cache_key(instance_dir)
        cached = self.item_cache.get(cache_key)

        # Return exist cache if available
        if cached and cached.get("signature") == signature:
            return dict(cached["item"])

        # Check instance profile if it exists
        info_path = get_instance_profile_path(str(instance_dir))
        has_info = os.path.exists(info_path)
        instance_profile = None
        parsed_info = {}
        status_code = False

        if has_info:
            # Read instance profile
            status_code, instance_profile = get_instance_profile(info_path, info_name=None)
            parse_status, parsed = parse_instance_profile(info_path)
            if parse_status and isinstance(parsed, dict):
                parsed_info = parsed

        item = {
            "id": instance_dir.name,
            "folderName": instance_dir.name,
            "name": instance_dir.name,
            "path": str(instance_dir),
            "infoPath": info_path if has_info else "",
            "clientVersion": "",
            "type": "legacy" if not has_info else "unknown",
            "launcherVersion": "",
            "instanceFormat": "",
            "createDate": "",
            "editable": has_info,
            "error": "",
            "icon": self.get_instance_icon_payload(instance_dir, parsed_info),
            "modLoaderName": parsed_info.get("mod_loader_name") or "",
        }

        # Return base item if instance profile is not available
        if not has_info:
            self.item_cache[cache_key] = {"signature": signature, "item": dict(item)}
            return item

        # Insert error message into item if got exception
        if not status_code:
            if has_info:
                item["error"] = str(instance_profile or "")
            self.item_cache[cache_key] = {"signature": signature, "item": dict(item)}
            return item

        # Insert instance profile
        instance_name, instance_uuid, client_version, version_type, launcher_version, instance_format, create_date = instance_profile
        item.update({
            "name": instance_name or instance_dir.name,
            "id": instance_uuid or instance_dir.name,
            "uuid": instance_uuid or "",
            "clientVersion": client_version or "",
            "type": version_type or "unknown",
            "launcherVersion": launcher_version or "",
            "instanceFormat": instance_format or "",
            "createDate": str(create_date or ""),
        })
        cache_key = item["id"]
        self.item_cache[cache_key] = {"signature": signature, "item": dict(item)}
        return item

    @staticmethod
    def get_instance_cache_key(instance_dir):
        info_path = get_instance_profile_path(str(instance_dir))
        if os.path.exists(info_path):
            status, info = parse_instance_profile(info_path)
            if status and isinstance(info, dict):
                return str(info.get("instance_uuid") or instance_dir.name)
        return instance_dir.name

    def get_instance_signature(self, instance_dir):
        """
        Get instance signature (for instance manager to check if instance is changed)
        :param instance_dir:
        :return:
        """
        info_path = get_instance_profile_path(str(instance_dir))
        custom_config_path = get_custom_config_path(str(instance_dir))
        icon_path = self.get_instance_icon_path(instance_dir)
        try:
            icon_mtime = os.stat(icon_path).st_mtime_ns if os.path.exists(icon_path) else 0
            config_mtime = os.stat(custom_config_path).st_mtime_ns if os.path.exists(custom_config_path) else 0
            if os.path.exists(info_path):
                return "info", os.stat(info_path).st_mtime_ns, config_mtime, icon_mtime
            return "dir", instance_dir.stat().st_mtime_ns, config_mtime, icon_mtime
        except OSError:
            return "missing", 0

    @staticmethod
    def get_instance_icon_path(instance_dir):
        return Path(instance_dir, "icon.png")

    def get_instance_icon_payload(self, instance_dir, info=None):
        """
        Get instance icon payload (FrontOnly)
        :param instance_dir:
        :param info:
        :return:
        """

        # Get custom icon path
        icon_path = self.get_instance_icon_path(instance_dir)

        # Return custom icon payload if it available
        if icon_path.exists() and icon_path.is_file():
            try:
                mime_path = Path(instance_dir, "icon.mime")
                mime = "image/png"
                if mime_path.exists():
                    saved_mime = mime_path.read_text(encoding="utf-8").strip()
                    if saved_mime in {"image/png", "image/jpeg", "image/webp"}:
                        mime = saved_mime
                encoded = base64.b64encode(icon_path.read_bytes()).decode("ascii")
                return {
                    "type": "custom",
                    "src": "data:{};base64,{}".format(mime, encoded),
                }
            except Exception as exc:
                self.logger.exception("Failed to read instance icon. Got exception {}".format(exc))
                return {}

        mod_loader = ""
        instance_name = instance_dir.name
        if isinstance(info, dict):
            mod_loader = str(info.get("mod_loader_name") or "").strip()
            instance_name = str(info.get("instance_name") or instance_name).strip()

        return {
            "type": "letter",
            "src": "",
            "initial": self.get_instance_icon_initial(instance_name),
            "recommended": "modded" if mod_loader and mod_loader.lower() not in {"false", "none"} else "grass",
        }

    @staticmethod
    def get_instance_icon_initial(name):
        for char in str(name or "").strip():
            code = ord(char)
            if (
                48 <= code <= 57
                or 65 <= code <= 90
                or 97 <= code <= 122
                or 0x3400 <= code <= 0x9fff
                or 0xf900 <= code <= 0xfaff
            ):
                return char.upper()
        return "?"

    def get_instance_dir(self, instance_id):
        """
        Get instance directory by instance id (uuid)
        :param instance_id:
        :return:
        """
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return None

        if not self.instances_dir.exists():
            return None

        for instance_dir in self.instances_dir.iterdir():
            if not instance_dir.is_dir():
                continue

            info_path = get_instance_profile_path(str(instance_dir))
            if not os.path.exists(info_path):
                continue

            status, info = parse_instance_profile(info_path)
            if not status or not isinstance(info, dict):
                continue

            if str(info.get("instance_uuid") or "").strip() == instance_id:
                return instance_dir

        direct_dir = self.instances_dir / instance_id
        if direct_dir.exists() and direct_dir.is_dir():
            return direct_dir

        return None

    def get_instance_mods_dir(self, instance_id):
        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return None
        return instance_dir / INSTANCE_GAME_FOLDER_NAME / "mods"

    def get_instance_game_dir(self, instance_id):
        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return None
        return instance_dir / INSTANCE_GAME_FOLDER_NAME

    def get_instance_worlds_dir(self, instance_id):
        game_dir = self.get_instance_game_dir(instance_id)
        if not game_dir:
            return None
        return game_dir / "saves"

    def get_instance_resource_packs_dir(self, instance_id):
        game_dir = self.get_instance_game_dir(instance_id)
        if not game_dir:
            return None
        return game_dir / "resourcepacks"

    @staticmethod
    def get_path_size(path):
        try:
            if path.is_file():
                return path.stat().st_size
            total = 0
            for child in path.rglob("*"):
                if child.is_file():
                    total += child.stat().st_size
            return total
        except OSError:
            return 0

    @staticmethod
    def get_file_data_uri(path):
        """
        Convert file to base64 data url
        :param path:
        :return:
        """
        try:
            if not path.exists() or not path.is_file():
                return ""
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return "data:image/png;base64,{}".format(encoded)
        except Exception:
            return ""

    @staticmethod
    def get_zip_image_data_uri(zip_path, image_name):
        try:
            with zipfile.ZipFile(zip_path) as archive:
                with archive.open(image_name) as image_file:
                    encoded = base64.b64encode(image_file.read()).decode("ascii")
                    return "data:image/png;base64,{}".format(encoded)
        except Exception:
            return ""

    @staticmethod
    def format_timestamp(path):
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_ctime))
        except OSError:
            return ""

    @staticmethod
    def get_unique_child_path(parent, source_name):
        """
        Generate unique child path (For world import)
        :param parent:
        :param source_name:
        :return:
        """
        source_path = Path(source_name)
        stem = source_path.stem
        suffix = source_path.suffix
        target = parent / source_path.name
        counter = 1
        while target.exists():
            target = parent / "{} ({}){}".format(stem, counter, suffix)
            counter += 1
        return target

    @staticmethod
    def resolve_instance_child_path(parent, child_name):
        if not parent or not parent.exists() or not parent.is_dir():
            return None

        child_name = Path(str(child_name or "")).name
        if not child_name:
            return None

        candidate = (parent / child_name).resolve()
        try:
            if candidate.parent != parent.resolve():
                return None
        except OSError:
            return None
        return candidate

    def instance_has_mod_loader(self, instance_dir):
        info_path = get_instance_profile_path(str(instance_dir))
        status, info = parse_instance_profile(info_path)
        if not status:
            return False

        custom_config_path = get_custom_config_path(str(instance_dir))
        return bool(self.get_mod_loader_info(info, custom_config_path).get("installed"))

    def ensure_instance_mods_dir(self, instance_id):
        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return None, "Instance not found."

        mods_dir = self.get_instance_mods_dir(instance_id)
        if not self.instance_has_mod_loader(instance_dir):
            return mods_dir, "Mod Loader Unavailable: Install Mod Loader first"

        mods_dir.mkdir(parents=True, exist_ok=True)
        return mods_dir, ""

    def resolve_instance_mod_path(self, instance_id, file_name):
        mods_dir = self.get_instance_mods_dir(instance_id)
        if not mods_dir or not mods_dir.exists() or not mods_dir.is_dir():
            return None

        file_name = Path(str(file_name or "")).name
        if not file_name:
            return None

        candidate = (mods_dir / file_name).resolve()
        try:
            if candidate.parent != mods_dir.resolve():
                return None
        except OSError:
            return None
        return candidate

    def get_unique_mod_target(self, mods_dir, source_name):
        source_path = Path(source_name)
        stem = source_path.stem
        suffix = source_path.suffix
        target = mods_dir / source_path.name
        counter = 1
        while target.exists():
            target = mods_dir / "{} ({}){}".format(stem, counter, suffix)
            counter += 1
        return target

    def get_instance_mods(self, instance_id):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return {"ok": False, "error": "Instance not found."}

        mods_dir, unavailable_reason = self.ensure_instance_mods_dir(instance_id)
        if unavailable_reason:
            return {
                "ok": True,
                "available": False,
                "modsDir": str(mods_dir),
                "error": unavailable_reason,
                "mods": [],
            }

        mods = []
        try:
            for mod_path in sorted(mods_dir.iterdir(), key=lambda path: path.name.lower()):
                if not mod_path.is_file():
                    continue

                stat = mod_path.stat()
                enabled = not mod_path.name.lower().endswith(".disabled")
                display_name = mod_path.name[:-9] if not enabled else mod_path.name
                mods.append({
                    "name": mod_path.name,
                    "displayName": display_name,
                    "enabled": enabled,
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                })
        except Exception as exc:
            self.logger.exception("Failed to list instance mods.")
            return {"ok": False, "error": str(exc)}

        return {
            "ok": True,
            "available": True,
            "modsDir": str(mods_dir),
            "mods": mods,
        }

    def add_instance_mods(self, instance_id, file_paths):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        mods_dir, unavailable_reason = self.ensure_instance_mods_dir(instance_id)
        if unavailable_reason:
            return {"ok": False, "error": unavailable_reason}

        if isinstance(file_paths, (str, os.PathLike)):
            file_paths = [file_paths]
        if not isinstance(file_paths, list) or not file_paths:
            return {"ok": False, "error": "No mod files selected."}

        copied = []
        try:
            for file_path in file_paths:
                source = Path(str(file_path or "")).expanduser()
                if not source.exists() or not source.is_file():
                    continue
                if source.suffix.lower() not in {".jar", ".disabled"} and not source.name.lower().endswith(".jar.disabled"):
                    continue

                target = self.get_unique_mod_target(mods_dir, source.name)
                shutil.copy2(source, target)
                copied.append(target.name)
        except Exception as exc:
            self.logger.exception("Failed to add instance mods.")
            return {"ok": False, "error": str(exc)}

        if not copied:
            return {"ok": False, "error": "No supported mod files were added."}

        result = self.get_instance_mods(instance_id)
        result.update({"added": copied})
        return result

    def import_instance_mod_payloads(self, instance_id, payloads):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        mods_dir, unavailable_reason = self.ensure_instance_mods_dir(instance_id)
        if unavailable_reason:
            return {"ok": False, "error": unavailable_reason}

        if not isinstance(payloads, list) or not payloads:
            return {"ok": False, "error": "No mod files selected."}

        imported = []
        try:
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue

                file_name = Path(str(payload.get("name") or "")).name
                data_url = str(payload.get("dataUrl") or "")
                if not file_name.lower().endswith((".jar", ".jar.disabled")):
                    continue
                if "base64," not in data_url:
                    continue

                encoded = data_url.split("base64,", 1)[1]
                raw = base64.b64decode(encoded, validate=True)
                target = self.get_unique_mod_target(mods_dir, file_name)
                target.write_bytes(raw)
                imported.append(target.name)
        except Exception as exc:
            self.logger.exception("Failed to import instance mods.")
            return {"ok": False, "error": str(exc)}

        if not imported:
            return {"ok": False, "error": "No supported mod files were imported."}

        result = self.get_instance_mods(instance_id)
        result.update({"added": imported})
        return result

    def browse_instance_mods(self, instance_id):
        mods_dir, unavailable_reason = self.ensure_instance_mods_dir(instance_id)
        if unavailable_reason:
            return {"ok": False, "error": unavailable_reason}

        window = self.instance_windows.get(str(instance_id or "").strip())
        if not window:
            return {"ok": False, "error": "Instance window not found."}

        try:
            import webview
            paths = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=("Minecraft mods (*.jar;*.jar.disabled)", "All files (*.*)"),
            )
        except Exception as exc:
            self.logger.exception("Failed to browse instance mods.")
            return {"ok": False, "error": str(exc)}

        if not paths:
            return self.get_instance_mods(instance_id)

        return self.add_instance_mods(instance_id, list(paths))

    def remove_instance_mod(self, instance_id, file_name):
        mod_path = self.resolve_instance_mod_path(instance_id, file_name)
        if not mod_path or not mod_path.exists() or not mod_path.is_file():
            return {"ok": False, "error": "Mod file not found."}

        try:
            mod_path.unlink()
        except Exception as exc:
            self.logger.exception("Failed to remove instance mod.")
            return {"ok": False, "error": str(exc)}

        return self.get_instance_mods(instance_id)

    def set_instance_mod_enabled(self, instance_id, file_name, enabled):
        mod_path = self.resolve_instance_mod_path(instance_id, file_name)
        if not mod_path or not mod_path.exists() or not mod_path.is_file():
            return {"ok": False, "error": "Mod file not found."}

        enabled = bool(enabled)
        name = mod_path.name
        if enabled and name.lower().endswith(".disabled"):
            target_name = name[:-9]
        elif not enabled and not name.lower().endswith(".disabled"):
            target_name = "{}.disabled".format(name)
        else:
            return self.get_instance_mods(instance_id)

        target = self.get_unique_mod_target(mod_path.parent, target_name)
        try:
            mod_path.rename(target)
        except Exception as exc:
            self.logger.exception("Failed to update instance mod state.")
            return {"ok": False, "error": str(exc)}

        return self.get_instance_mods(instance_id)

    def get_instance_worlds(self, instance_id):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        worlds_dir = self.get_instance_worlds_dir(instance_id)
        if not worlds_dir:
            return {"ok": False, "error": "Instance not found."}

        worlds_dir.mkdir(parents=True, exist_ok=True)
        worlds = []
        try:
            for world_path in sorted(worlds_dir.iterdir(), key=lambda path: path.name.lower()):
                if not world_path.is_dir():
                    continue
                if not (world_path / "level.dat").exists():
                    continue

                worlds.append({
                    "name": world_path.name,
                    "path": str(world_path),
                    "icon": self.get_file_data_uri(world_path / "icon.png"),
                    "created": self.format_timestamp(world_path),
                    "size": self.get_path_size(world_path),
                })
        except Exception as exc:
            self.logger.exception("Failed to list instance worlds.")
            return {"ok": False, "error": str(exc), "worlds": []}

        return {"ok": True, "worldsDir": str(worlds_dir), "worlds": worlds}

    def browse_import_instance_world(self, instance_id):
        worlds_dir = self.get_instance_worlds_dir(instance_id)
        if not worlds_dir:
            return {"ok": False, "error": "Instance not found."}

        window = self.instance_windows.get(str(instance_id or "").strip())
        if not window:
            return {"ok": False, "error": "Instance window not found."}

        try:
            import webview
            paths = window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        except Exception as exc:
            self.logger.exception("Failed to browse world import.")
            return {"ok": False, "error": str(exc)}

        if not paths:
            return self.get_instance_worlds(instance_id)

        source = Path(str(paths[0] if isinstance(paths, (list, tuple)) else paths)).expanduser()
        if not source.exists() or not source.is_dir() or not (source / "level.dat").exists():
            return {"ok": False, "error": "Select a Minecraft world folder."}

        try:
            worlds_dir.mkdir(parents=True, exist_ok=True)
            target = self.get_unique_child_path(worlds_dir, source.name)
            shutil.copytree(source, target)
            result = self.get_instance_worlds(instance_id)
            result["imported"] = target.name
            return result
        except Exception as exc:
            self.logger.exception("Failed to import world.")
            return {"ok": False, "error": str(exc)}

    def delete_instance_world(self, instance_id, world_name):
        world_path = self.resolve_instance_child_path(self.get_instance_worlds_dir(instance_id), world_name)
        if not world_path or not world_path.exists() or not world_path.is_dir():
            return {"ok": False, "error": "World not found."}

        try:
            shutil.rmtree(world_path)
            return self.get_instance_worlds(instance_id)
        except Exception as exc:
            self.logger.exception("Failed to delete world.")
            return {"ok": False, "error": str(exc)}

    def get_instance_resource_packs(self, instance_id):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        packs_dir = self.get_instance_resource_packs_dir(instance_id)
        if not packs_dir:
            return {"ok": False, "error": "Instance not found."}

        packs_dir.mkdir(parents=True, exist_ok=True)
        packs = []
        try:
            for pack_path in sorted(packs_dir.iterdir(), key=lambda path: path.name.lower()):
                if pack_path.is_file() and pack_path.suffix.lower() != ".zip":
                    continue
                if not pack_path.is_file() and not pack_path.is_dir():
                    continue

                icon = self.get_file_data_uri(pack_path / "pack.png") if pack_path.is_dir() else self.get_zip_image_data_uri(pack_path, "pack.png")
                packs.append({
                    "name": pack_path.name,
                    "path": str(pack_path),
                    "icon": icon,
                    "created": self.format_timestamp(pack_path),
                    "size": self.get_path_size(pack_path),
                    "type": "folder" if pack_path.is_dir() else "zip",
                })
        except Exception as exc:
            self.logger.exception("Failed to list resource packs.")
            return {"ok": False, "error": str(exc), "packs": []}

        return {"ok": True, "packsDir": str(packs_dir), "packs": packs}

    def browse_import_instance_resource_pack(self, instance_id):
        packs_dir = self.get_instance_resource_packs_dir(instance_id)
        if not packs_dir:
            return {"ok": False, "error": "Instance not found."}

        window = self.instance_windows.get(str(instance_id or "").strip())
        if not window:
            return {"ok": False, "error": "Instance window not found."}

        try:
            import webview
            paths = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=("Resource packs (*.zip)", "All files (*.*)"),
            )
        except Exception as exc:
            self.logger.exception("Failed to browse resource pack import.")
            return {"ok": False, "error": str(exc)}

        if not paths:
            return self.get_instance_resource_packs(instance_id)

        imported = []
        try:
            packs_dir.mkdir(parents=True, exist_ok=True)
            for path in paths:
                source = Path(str(path or "")).expanduser()
                if not source.exists() or not source.is_file() or source.suffix.lower() != ".zip":
                    continue
                target = self.get_unique_child_path(packs_dir, source.name)
                shutil.copy2(source, target)
                imported.append(target.name)
        except Exception as exc:
            self.logger.exception("Failed to import resource pack.")
            return {"ok": False, "error": str(exc)}

        if not imported:
            return {"ok": False, "error": "No resource pack zip files were imported."}

        result = self.get_instance_resource_packs(instance_id)
        result["imported"] = imported
        return result

    def delete_instance_resource_pack(self, instance_id, pack_name):
        pack_path = self.get_instance_resource_packs_dir(instance_id) / pack_name
        if not pack_path or not pack_path.exists():
            return {"ok": False, "error": "Resource pack not found."}

        try:
            if pack_path.is_dir():
                shutil.rmtree(pack_path)
            else:
                pack_path.unlink()
            return self.get_instance_resource_packs(instance_id)
        except Exception as exc:
            self.logger.exception("Failed to delete resource pack.")
            return {"ok": False, "error": str(exc)}

    def get_instance_client_settings(self, instance_id):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return {"ok": False, "error": "Instance not found."}

        info_path = get_instance_profile_path(str(instance_dir))
        status, info = parse_instance_profile(info_path)
        if not status:
            return {"ok": False, "error": str(info)}

        custom_config_path = get_custom_config_path(str(instance_dir))
        mod_loader_info = self.get_mod_loader_info(info, custom_config_path)
        custom_jar = str(read_custom_config(custom_config_path, "CustomClientJar") or "").strip()
        custom_jar_path = Path(custom_jar) if custom_jar else None

        return {
            "ok": True,
            "instanceId": instance_id,
            "minecraftVersion": info.get("client_version") or "",
            "realMinecraftVersion": info.get("real_minecraft_version") or "",
            "modLoader": mod_loader_info,
            "mainClass": mod_loader_info.get("mainClass") or info.get("main_class") or "",
            "baseMainClass": info.get("main_class") or "",
            "customJar": {
                "path": custom_jar,
                "exists": bool(custom_jar_path and custom_jar_path.exists() and custom_jar_path.is_file()),
            },
            "classpath": self.get_instance_classpath_payload(info, custom_config_path),
        }

    def get_instance_classpath_payload(self, info, custom_config_path):
        try:
            launch_manager = getattr(self.gui, "launch_manager", None)
            if not launch_manager:
                return {"ok": False, "error": "Launch manager is not ready.", "items": []}

            base_version = launch_manager.resolve_base_client_version(info)
            launch_version = launch_manager.resolve_launch_version_id(info, base_version)
            version_data = launch_manager.load_version_data(launch_version)
            return {
                "ok": True,
                "baseVersion": base_version,
                "launchVersion": launch_version,
                "items": launch_manager.build_classpath_items(base_version, version_data, info, custom_config_path),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "items": []}

    def save_instance_client_settings(self, instance_id, values):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        if not isinstance(values, dict):
            return {"ok": False, "error": "Invalid client settings."}

        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return {"ok": False, "error": "Instance not found."}

        info_path = get_instance_profile_path(str(instance_dir))
        status, info = parse_instance_profile(info_path)
        if not status:
            return {"ok": False, "error": str(info)}

        custom_config_path = get_custom_config_path(str(instance_dir))
        try:
            create_custom_config(custom_config_path)
            if "mainClass" in values:
                main_class = str(values.get("mainClass") or "").strip()
                if self.get_mod_loader_info(info, custom_config_path).get("installed"):
                    write_custom_config(custom_config_path, "ModLoaderClass", main_class, True)
                else:
                    write_instance_profile("main_class", main_class, info_path)

            self.invalidate_instance_cache(instance_id)
            return self.get_instance_client_settings(instance_id)
        except Exception as exc:
            self.logger.exception("Failed to save client settings.")
            return {"ok": False, "error": str(exc)}

    def browse_instance_client_jar(self, instance_id):
        instance_id = str(instance_id or "").strip()
        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return {"ok": False, "error": "Instance not found."}

        window = self.instance_windows.get(instance_id)
        if not window:
            return {"ok": False, "error": "Instance window not found."}

        try:
            import webview
            paths = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Java archive (*.jar)", "All files (*.*)"),
            )
        except Exception as exc:
            self.logger.exception("Failed to browse client jar.")
            return {"ok": False, "error": str(exc)}

        if not paths:
            return self.get_instance_client_settings(instance_id)

        source = Path(str(paths[0] if isinstance(paths, (list, tuple)) else paths)).expanduser()
        if not source.exists() or not source.is_file() or source.suffix.lower() != ".jar":
            return {"ok": False, "error": "Select a .jar file."}

        custom_dir = instance_dir / "client"
        target = custom_dir / "custom-client.jar"
        custom_config_path = get_custom_config_path(str(instance_dir))
        try:
            custom_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            create_custom_config(custom_config_path)
            write_custom_config(custom_config_path, "CustomClientJar", str(target), True)
            self.invalidate_instance_cache(instance_id)
            result = self.get_instance_client_settings(instance_id)
            result["insertedJar"] = str(target)
            return result
        except Exception as exc:
            self.logger.exception("Failed to insert custom client jar.")
            return {"ok": False, "error": str(exc)}

    def clear_instance_client_jar(self, instance_id):
        instance_id = str(instance_id or "").strip()
        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return {"ok": False, "error": "Instance not found."}

        custom_config_path = get_custom_config_path(str(instance_dir))
        try:
            create_custom_config(custom_config_path)
            write_custom_config(custom_config_path, "CustomClientJar", "", True)
            self.invalidate_instance_cache(instance_id)
            return self.get_instance_client_settings(instance_id)
        except Exception as exc:
            self.logger.exception("Failed to clear custom client jar.")
            return {"ok": False, "error": str(exc)}

    def browse_instance_classpath_jar(self, instance_id):
        instance_id = str(instance_id or "").strip()
        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return {"ok": False, "error": "Instance not found."}

        window = self.instance_windows.get(instance_id)
        if not window:
            return {"ok": False, "error": "Instance window not found."}

        try:
            import webview
            paths = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Java archive (*.jar)", "All files (*.*)"),
            )
        except Exception as exc:
            self.logger.exception("Failed to browse classpath jar.")
            return {"ok": False, "error": str(exc)}

        if not paths:
            return self.get_instance_client_settings(instance_id)

        source = Path(str(paths[0] if isinstance(paths, (list, tuple)) else paths)).expanduser()
        if not source.exists() or not source.is_file() or source.suffix.lower() != ".jar":
            return {"ok": False, "error": "Select a .jar file."}

        return self.insert_instance_classpath(instance_id, str(source))

    def insert_instance_classpath(self, instance_id, jar_path):
        instance_id = str(instance_id or "").strip()
        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return {"ok": False, "error": "Instance not found."}

        source = Path(str(jar_path or "")).expanduser()
        if not source.exists() or not source.is_file() or source.suffix.lower() != ".jar":
            return {"ok": False, "error": "Select a .jar file."}

        custom_config_path = get_custom_config_path(str(instance_dir))
        try:
            create_custom_config(custom_config_path)
            extra_classpath = read_custom_config(custom_config_path, "ExtraClasspath") or []
            if not isinstance(extra_classpath, list):
                extra_classpath = [str(extra_classpath)] if str(extra_classpath or "").strip() else []

            source_text = str(source)
            if source_text not in extra_classpath:
                extra_classpath.append(source_text)
                write_custom_config(custom_config_path, "ExtraClasspath", extra_classpath, True)

            self.invalidate_instance_cache(instance_id)
            result = self.get_instance_client_settings(instance_id)
            result["insertedClasspath"] = source_text
            return result
        except Exception as exc:
            self.logger.exception("Failed to insert classpath jar.")
            return {"ok": False, "error": str(exc)}

    def set_instance_classpath_enabled(self, instance_id, classpath_id, enabled):
        instance_id = str(instance_id or "").strip()
        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir:
            return {"ok": False, "error": "Instance not found."}

        classpath_id = str(classpath_id or "").strip()
        if not classpath_id:
            return {"ok": False, "error": "Classpath item is required."}

        custom_config_path = get_custom_config_path(str(instance_dir))
        try:
            create_custom_config(custom_config_path)
            extra_classpath = read_custom_config(custom_config_path, "ExtraClasspath") or []
            disabled_classpath = read_custom_config(custom_config_path, "DisabledClasspath") or []
            if not isinstance(extra_classpath, list):
                extra_classpath = [str(extra_classpath)] if str(extra_classpath or "").strip() else []
            if not isinstance(disabled_classpath, list):
                disabled_classpath = [str(disabled_classpath)] if str(disabled_classpath or "").strip() else []

            if classpath_id in extra_classpath and not enabled:
                extra_classpath = [item for item in extra_classpath if item != classpath_id]
                write_custom_config(custom_config_path, "ExtraClasspath", extra_classpath, True)
            elif enabled:
                disabled_classpath = [item for item in disabled_classpath if item != classpath_id]
                write_custom_config(custom_config_path, "DisabledClasspath", disabled_classpath, True)
            elif classpath_id not in disabled_classpath:
                disabled_classpath.append(classpath_id)
                write_custom_config(custom_config_path, "DisabledClasspath", disabled_classpath, True)

            self.invalidate_instance_cache(instance_id)
            return self.get_instance_client_settings(instance_id)
        except Exception as exc:
            self.logger.exception("Failed to update classpath item.")
            return {"ok": False, "error": str(exc)}

    def invalidate_instance_cache(self, instance_id=None):
        if instance_id is None:
            self.item_cache.clear()
            self.detail_cache.clear()
            return

        instance_id = str(instance_id or "").strip()
        self.item_cache.pop(instance_id, None)
        self.detail_cache.pop(instance_id, None)

    def rename_instance(self, instance_id, new_name):
        instance_id = str(instance_id or "").strip()
        new_name = str(new_name or "").strip()

        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        if not new_name:
            return {"ok": False, "error": "Instance name is required."}

        if any(char in new_name for char in '<>:"/\\|?*'):
            return {"ok": False, "error": "Instance name contains invalid path characters."}

        with self.lock:
            try:
                instance_dir = self.get_instance_dir(instance_id)
                if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
                    return {"ok": False, "error": "Instance not found."}

                info_path = get_instance_profile_path(str(instance_dir))
                if os.path.exists(info_path):
                    write_instance_profile("instance_name", new_name, info_path)
                self.invalidate_instance_cache(instance_id)
            except Exception as exc:
                self.logger.exception("Failed to rename instance.")
                return {"ok": False, "error": str(exc)}

            return {"ok": True, "instanceId": instance_id}

    def delete_instance(self, instance_id):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        with self.lock:
            instance_dir = self.get_instance_dir(instance_id)
            if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
                return {"ok": False, "error": "Instance not found."}

            try:
                shutil.rmtree(instance_dir)
                self.invalidate_instance_cache(instance_id)
            except Exception as exc:
                self.logger.exception("Failed to delete instance.")
                return {"ok": False, "error": str(exc)}

        return {"ok": True}

    def get_instance_jvm_settings(self, instance_id):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            return {"ok": False, "error": "Instance not found."}

        info_path = get_instance_profile_path(str(instance_dir))
        status, info = parse_instance_profile(info_path)
        if not status:
            return {"ok": False, "error": str(info)}

        custom_config_path = get_custom_config_path(str(instance_dir))
        return {
            "ok": True,
            "instanceId": instance_id,
            "configPath": custom_config_path,
            "settings": {
                "supportJavaVersion": info.get("support_java_version") or "",
                "javaExecutable": read_custom_config(custom_config_path, "JavaExecutable") or "",
                "memoryJVMArgs": read_custom_config(custom_config_path, "MemoryJVMArgs") or "",
                "customJVMArgs": read_custom_config(custom_config_path, "CustomJVMArgs") or "",
                "modLoaderJVMArgs": read_custom_config(custom_config_path, "ModLoaderJVMArgs") or "",
            },
        }

    def save_instance_jvm_settings(self, instance_id, values):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        if not isinstance(values, dict):
            return {"ok": False, "error": "Invalid JVM settings."}

        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            return {"ok": False, "error": "Instance not found."}

        info_path = get_instance_profile_path(str(instance_dir))
        custom_config_path = get_custom_config_path(str(instance_dir))

        try:
            create_custom_config(custom_config_path)

            if "supportJavaVersion" in values:
                write_instance_profile("support_java_version", str(values.get("supportJavaVersion") or "").strip(), info_path)

            custom_fields = {
                "javaExecutable": "JavaExecutable",
                "memoryJVMArgs": "MemoryJVMArgs",
                "customJVMArgs": "CustomJVMArgs",
            }
            for payload_key, config_key in custom_fields.items():
                if payload_key not in values:
                    continue
                write_custom_config(custom_config_path, config_key, str(values.get(payload_key) or ""), True)

            self.invalidate_instance_cache(instance_id)
        except Exception as exc:
            self.logger.exception("Failed to save JVM settings.")
            return {"ok": False, "error": str(exc)}

        return {"ok": True}

    def get_jvms(self, force=False):
        with self.lock:
            if not force and self.jvm_cache and time.monotonic() - self.jvm_cache_time < self.jvm_cache_ttl:
                return self.jvm_cache

            runtimes = self.jre_manager.scan_jvms()
            result = {
                "ok": True,
                "runtimesDir": self.jre_manager.runtimes_dir.as_posix(),
                "jvms": runtimes,
            }
            self.jvm_cache = result
            self.jvm_cache_time = time.monotonic()
            return result

    def get_instance_detail(self, instance_id):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            return {"ok": False, "error": "Instance not found."}

        signature = self.get_instance_signature(instance_dir)
        cached = self.detail_cache.get(instance_id)
        if cached and cached.get("signature") == signature:
            return dict(cached["detail"])

        info_path = get_instance_profile_path(str(instance_dir))
        status, info = parse_instance_profile(info_path)
        if not status:
            print(info_path)
            return {"ok": False, "error": str(info)}

        custom_config_path = get_custom_config_path(str(instance_dir))
        mod_loader_info = self.get_mod_loader_info(info, custom_config_path)
        display_info = dict(info)
        display_info["effective_main_class"] = mod_loader_info.get("mainClass") or info.get("main_class") or ""
        display_info["mod_loader_name"] = mod_loader_info.get("name") or ""
        display_info["mod_loader_version"] = mod_loader_info.get("version") or ""

        detail = {
            "ok": True,
            "id": instance_id,
            "path": str(instance_dir),
            "infoPath": info_path,
            "configPath": custom_config_path,
            "info": display_info,
            "rawInfo": info,
            "modLoader": mod_loader_info,
            "icon": self.get_instance_icon_payload(instance_dir, info),
        }
        self.detail_cache[instance_id] = {"signature": signature, "detail": dict(detail)}
        return detail

    def get_mod_loader_info(self, info, custom_config_path=None):
        info = info if isinstance(info, dict) else {}
        raw_name = str(info.get("mod_loader_name") or "").strip()
        raw_version = str(info.get("mod_loader_version") or "").strip()
        name = self.normalize_mod_loader_value(raw_name)
        version = self.normalize_mod_loader_value(raw_version)
        installed = bool(name or version)
        loader_class = ""

        if custom_config_path:
            loader_class = str(read_custom_config(custom_config_path, "ModLoaderClass") or "").strip()

        if not loader_class and self.normalize_mod_loader_name(name) == "fabric":
            loader_class = "net.fabricmc.loader.impl.launch.knot.KnotClient"

        return {
            "installed": installed,
            "name": name,
            "version": version,
            "mainClass": loader_class,
            "displayName": self.format_mod_loader_display_name(name),
        }

    @staticmethod
    def normalize_mod_loader_value(value):
        value = str(value or "").strip()
        if value.lower() in {"", "false", "none", "null"}:
            return ""
        return value

    @staticmethod
    def normalize_mod_loader_name(name):
        return str(name or "").strip().lower().replace(" ", "").replace("-", "")

    @staticmethod
    def format_mod_loader_display_name(name):
        normalized = InstanceManager.normalize_mod_loader_name(name)
        if normalized == "neoforge":
            return "NeoForge"
        if normalized == "forge":
            return "Forge"
        if normalized == "fabric":
            return "Fabric"
        return str(name or "").strip()

    def save_instance_detail(self, instance_id, values):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        if not isinstance(values, dict):
            return {"ok": False, "error": "Invalid instance settings."}

        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            return {"ok": False, "error": "Instance not found."}

        info_path = get_instance_profile_path(str(instance_dir))
        editable_fields = {
            "instance_name",
            "client_version",
            "type",
            "main_class",
            "support_java_version",
            "real_minecraft_version",
            "game_folder",
            "assets_folder",
            "enable_config",
            "custom_config_path",
        }

        try:
            for key, value in values.items():
                if key not in editable_fields:
                    continue
                write_instance_profile(key, value, info_path)
            self.invalidate_instance_cache(instance_id)
        except Exception as exc:
            self.logger.exception("Failed to save instance settings.")
            return {"ok": False, "error": str(exc)}

        return {"ok": True}

    def save_instance_icon(self, instance_id, payload):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        if not isinstance(payload, dict):
            return {"ok": False, "error": "Invalid icon payload."}

        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            return {"ok": False, "error": "Instance not found."}

        data_url = str(payload.get("dataUrl") or "")
        marker = "base64,"
        if marker not in data_url:
            return {"ok": False, "error": "Icon data is missing."}

        header, encoded = data_url.split(marker, 1)
        mime = ""
        for candidate in ("image/png", "image/jpeg", "image/webp"):
            if candidate in header:
                mime = candidate
                break

        if not mime:
            return {"ok": False, "error": "Icon must be PNG, JPEG, or WebP."}

        try:
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > 2 * 1024 * 1024:
                return {"ok": False, "error": "Icon must be 2 MB or smaller."}

            icon_path = self.get_instance_icon_path(instance_dir)
            icon_path.write_bytes(raw)
            Path(instance_dir, "icon.mime").write_text(mime, encoding="utf-8")
            self.invalidate_instance_cache(instance_id)
            return {"ok": True, "iconPath": str(icon_path)}
        except Exception as exc:
            self.logger.exception("Failed to save instance icon.")
            return {"ok": False, "error": str(exc)}

    def clear_instance_icon(self, instance_id):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        instance_dir = self.get_instance_dir(instance_id)
        if not instance_dir or not instance_dir.exists() or not instance_dir.is_dir():
            return {"ok": False, "error": "Instance not found."}

        try:
            icon_path = self.get_instance_icon_path(instance_dir)
            if icon_path.exists():
                icon_path.unlink()
            mime_path = Path(instance_dir, "icon.mime")
            if mime_path.exists():
                mime_path.unlink()
            self.invalidate_instance_cache(instance_id)
            return {"ok": True}
        except Exception as exc:
            self.logger.exception("Failed to clear instance icon.")
            return {"ok": False, "error": str(exc)}

    def notify_instances_changed(self):
        self.gui.evaluate_main_js("window.__bakeInstancesChanged && window.__bakeInstancesChanged();")

    def evaluate_instance_window_js(self, instance_id, script):
        window = self.instance_windows.get(str(instance_id or "").strip())
        if not window:
            return

        try:
            window.evaluate_js(script)
        except Exception:
            pass

    def get_instance_log_path(self, instance_id):
        detail = self.get_instance_detail(instance_id)
        if not detail.get("ok"):
            raise RuntimeError(detail.get("error") or "Failed to get instance detail.")
        return Path(detail["path"], "logs", "current.log")

    def clear_instance_log(self, instance_id):
        try:
            log_path = self.get_instance_log_path(instance_id)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("", encoding="utf-8")
            return {"ok": True, "path": str(log_path)}
        except Exception as exc:
            self.logger.exception("Failed to clear instance log.")
            return {"ok": False, "error": str(exc)}

    def open_instance_window(self, instance_id, initial_page="overview"):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            return {"ok": False, "error": "Instance id is required."}

        try:
            import webview

            if instance_id in self.instance_windows:
                self.gui.focus_window(self.instance_windows[instance_id])
                self.evaluate_instance_window_js(
                    instance_id,
                    "window.__bakeShowInstancePage && window.__bakeShowInstancePage({});".format(json.dumps(initial_page)),
                )
                return {"ok": True, "alreadyOpen": True}

            detail = self.get_instance_detail(instance_id)
            if not detail.get("ok"):
                return detail

            self.clear_instance_log(instance_id)

            title = "Instance: {}".format(detail.get("info", {}).get("instance_name") or instance_id)

            window = webview.create_window(
                title,
                html=self.gui.build_instance_window_html(instance_id, initial_page=initial_page, initial_detail=detail),
                js_api=self.gui.api,
                width=880,
                height=620,
                min_size=(640, 420),
            )
            self.instance_windows[instance_id] = window

            def on_closed():
                if self.instance_windows.get(instance_id) is window:
                    self.instance_windows.pop(instance_id, None)

            window.events.closed += on_closed
            return {"ok": True}
        except Exception as exc:
            self.logger.exception("Failed to open instance window.")
            self.instance_windows.pop(instance_id, None)
            return {"ok": False, "error": str(exc)}
