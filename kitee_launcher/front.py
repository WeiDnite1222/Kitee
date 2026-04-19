import platform
from pathlib import Path
from .bk_core.java.java_info import create_java_version_info
from .bk_core.java.jvm_installer import runtime_java_executable

class FrontendAPI:
    def __init__(self, launcher, gui, settings, logger):
        self._logger = logger
        self._launcher = launcher
        self._gui = gui
        self._settings = settings

    # ======================== Settings ========================
    def get_settings(self):
        with self._settings.lock:
            try:
                if not self._settings.exists():
                    self._settings.create()
            except Exception as e:
                return {
                    "status": "error",
                    "message": str(e),
                }

            return {
                "status": "ok",
                "settings": self._settings.mload()
            }

    def update_settings(self, settings):
        with self._settings.lock:
            try:
                self._settings.update(settings)
            except Exception as e:
                return {
                    "status": "error",
                    "message": str(e),
                }

            return {
                "status": "ok",
                "settings": self._settings.mload()
            }

    def update_new_settings(self, new_settings):
        with self._settings.lock:
            try:
                self._settings.update_new_settings(new_settings)
            except Exception as e:
                return {
                    "status": "error",
                    "message": str(e),
                }

            return {
                "status": "ok",
            }

    def save_settings(self):
        with self._settings.lock:
            try:
                self._settings.save()
            except Exception as e:
                return {
                    "status": "error",
                    "message": str(e),
                }

            return {
                "status": "ok",
            }

    def get_frontend_settings(self):
        with self._settings.lock:
            try:
                self._ensure_settings_loaded()
                return {
                    "ok": True,
                    "frontend": self._build_frontend_settings_payload(self._settings.mload()),
                }
            except Exception as exc:
                self._logger.exception("Failed to get frontend settings.")
                return {"ok": False, "error": str(exc)}

    def save_frontend_settings(self, settings):
        with self._settings.lock:
            try:
                self._ensure_settings_loaded()
                self._settings.update(self._frontend_settings_to_file_settings(settings))
                self._settings.save()
                return {
                    "ok": True,
                    "frontend": self._build_frontend_settings_payload(self._settings.mload()),
                }
            except Exception as exc:
                self._logger.exception("Failed to save frontend settings.")
                return {"ok": False, "error": str(exc)}

    def browse_frontend_background_image(self):
        window = self._gui.window
        if not window:
            return {"ok": False, "error": "Main window not found."}

        try:
            import webview
            paths = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=(
                    "Media files (*.png;*.jpg;*.jpeg;*.gif;*.webp;*.bmp;*.webm)",
                    "All files (*.*)",
                ),
            )
        except Exception as exc:
            self._logger.exception("Failed to browse frontend background image.")
            return {"ok": False, "error": str(exc)}

        if not paths:
            return {"ok": False, "cancelled": True}

        image_path = Path(paths[0])
        return {
            "ok": True,
            "image": str(image_path),
            "imageDataUri": self._gui.image_to_base64_data_url(image_path),
        }

    def _ensure_settings_loaded(self):
        if not self._settings.exists():
            self._settings.create(exist_ok=True)
        self._settings.read_from_exist()

    def _build_frontend_settings_payload(self, data):
        frontend = data.get("frontend") if isinstance(data.get("frontend"), dict) else {}
        main = data.get("main") if isinstance(data.get("main"), dict) else {}
        tabs = frontend.get("tabs") if isinstance(frontend.get("tabs"), dict) else {}
        instances = data.get("instances") if isinstance(data.get("instances"), dict) else {}
        background = data.get("background") if isinstance(data.get("background"), dict) else {}

        image_path = background.get("imagePath") or ""
        child_image_path = background.get("childImagePath") or ""

        return {
            "language": frontend.get("language") or main.get("language") or "en_US",
            "theme": frontend.get("theme") or "light",
            "tabs": {
                "order": tabs.get("order") or [],
                "active": tabs.get("active") or tabs.get("current") or "home_container",
                "detached": tabs.get("detached") or [],
                "hidden": tabs.get("hidden") or [],
            },
            "instances": {
                "display": instances.get("display") or instances.get("displayMode") or "icon",
            },
            "background": {
                "image": image_path,
                "imageDataUri": self._image_data_uri(image_path),
                "blur": background.get("blur", 0),
                "mediaOpacity": background.get("mediaOpacity", 100),
                "surfaceAlpha": background.get("surfaceAlpha", 60),
                "childMode": background.get("childMode") or "inherit",
                "childImage": child_image_path,
                "childImageDataUri": self._image_data_uri(child_image_path),
                "childBlur": background.get("childBlur", 0),
            },
        }

    def _frontend_settings_to_file_settings(self, settings):
        if not isinstance(settings, dict):
            raise TypeError("settings must be a dict")

        file_settings = {}

        language = self._non_empty_string(settings.get("language"))
        theme = self._non_empty_string(settings.get("theme"))
        if language or theme or isinstance(settings.get("tabs"), dict):
            file_settings["frontend"] = {}
            if language:
                file_settings.setdefault("main", {})["language"] = language
                file_settings["frontend"]["language"] = language
            if theme:
                file_settings["frontend"]["theme"] = theme

            tabs = settings.get("tabs")
            if isinstance(tabs, dict):
                file_settings["frontend"]["tabs"] = {
                    "order": tabs.get("order") if isinstance(tabs.get("order"), list) else [],
                    "current": self._non_empty_string(tabs.get("active")) or "home_container",
                    "detached": tabs.get("detached") if isinstance(tabs.get("detached"), list) else [],
                    "hidden": tabs.get("hidden") if isinstance(tabs.get("hidden"), list) else [],
                }

        instances = settings.get("instances")
        if isinstance(instances, dict):
            file_settings["instances"] = {
                "displayMode": self._non_empty_string(instances.get("display")) or "icon",
            }

        background = settings.get("background")
        if isinstance(background, dict):
            file_settings["background"] = {
                "imagePath": self._string_value(background.get("image")),
                "blur": self._int_value(background.get("blur"), 0),
                "mediaOpacity": self._int_value(background.get("mediaOpacity"), 100),
                "surfaceAlpha": self._int_value(background.get("surfaceAlpha"), 60),
                "childMode": self._non_empty_string(background.get("childMode")) or "inherit",
                "childImagePath": self._string_value(background.get("childImage")),
                "childBlur": self._int_value(background.get("childBlur"), 0),
            }

        return file_settings

    def _image_data_uri(self, image_path):
        if not image_path:
            return ""
        return self._gui.image_to_base64_data_url(Path(image_path))

    @staticmethod
    def _string_value(value):
        return "" if value is None else str(value)

    @staticmethod
    def _non_empty_string(value):
        value = "" if value is None else str(value).strip()
        return value

    @staticmethod
    def _int_value(value, fallback):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    # ======================== Language ========================

    def get_available_languages(self):
        return self._gui.get_available_languages()

    # ======================== File Dialog ========================

    def browse_file(self, file_types, multiple=False):
        window = self._gui.window
        if not window:
            return {"ok": False, "error": "Main window not found."}

        try:
            import webview
            paths = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=multiple,
                file_types=file_types,
            )
        except Exception as exc:
            self._logger.exception("Failed to browse file.")
            return {"ok": False, "error": str(exc)}

        if not paths:
            return {"ok": False, "cancelled": True}

        return {
            "ok": True,
            "filePath": str(paths[0]) if not multiple else paths,
        }


    def browse_folder(self, multiple=False):
        window = self._gui.window
        if not window:
            return {"ok": False, "error": "Main window not found."}

        try:
            import webview
            paths = window.create_folder_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=multiple,
            )
        except Exception as exc:
            self._logger.exception("Failed to browse folder.")
            return {"ok": False, "error": str(exc)}

        if not paths:
            return {"ok": False, "cancelled": True}

        return {
            "ok": True,
            "folderPath": str(paths[0]) if not multiple else paths,
        }

    # ======================== Tab ========================

    def detach_tab(self, target_id, title, body_html):
        return self._gui.create_detached_tab(target_id, title, body_html)

    def dock_tab(self, target_id):
        return self._gui.dock_detached_tab(target_id)

    def focus_detached_tab(self, target_id):
        return self._gui.focus_detached_tab(target_id)

    def handle_overlay_action(self, overlay_id, action_id):
        return self._gui.handle_overlay_action(overlay_id, action_id)

    # ======================== Account ========================
    def get_accounts(self):
        return self._gui.account_manager.get_accounts()

    def create_offline_account(self, username):
        return self._gui.account_manager.create_offline_account(username)

    def switch_account(self, account_id):
        return self._gui.account_manager.switch_account(account_id)

    def delete_account(self, account_id):
        return self._gui.account_manager.delete_account(account_id)

    def clear_account_data(self):
        return self._gui.account_manager.clear_account_data()

    def start_msa_login(self):
        return self._gui.account_manager.start_msa_login()

    # ======================== Instance ========================
    def get_instances(self):
        return self._gui.instance_manager.get_instances()

    def rename_instance(self, instance_id, new_name):
        return self._gui.instance_manager.rename_instance(instance_id, new_name)

    def delete_instance(self, instance_id):
        result = self._gui.instance_manager.delete_instance(instance_id)
        if result.get("ok"):
            self._gui.instance_manager.notify_instances_changed()
        return result

    def launch_instance(self, instance_id):
        return self._gui.launch_manager.process_launch_instances(instance_id)

    def open_instance_window(self, instance_id, initial_page="overview"):
        return self._gui.instance_manager.open_instance_window(instance_id, initial_page)

    def get_instance_detail(self, instance_id):
        return self._gui.instance_manager.get_instance_detail(instance_id)

    def save_instance_detail(self, instance_id, values):
        result = self._gui.instance_manager.save_instance_detail(instance_id, values)
        if result.get("ok"):
            self._gui.instance_manager.notify_instances_changed()
        return result

    def save_instance_icon(self, instance_id, payload):
        result = self._gui.instance_manager.save_instance_icon(instance_id, payload)
        if result.get("ok"):
            self._gui.instance_manager.notify_instances_changed()
        return result

    def clear_instance_icon(self, instance_id):
        result = self._gui.instance_manager.clear_instance_icon(instance_id)
        if result.get("ok"):
            self._gui.instance_manager.notify_instances_changed()
        return result

    def get_instance_mods(self, instance_id):
        return self._gui.instance_manager.get_instance_mods(instance_id)

    def browse_instance_mods(self, instance_id):
        return self._gui.instance_manager.browse_instance_mods(instance_id)

    def import_instance_mod_files(self, instance_id, file_paths):
        return self._gui.instance_manager.add_instance_mods(instance_id, file_paths)

    def import_instance_mod_payloads(self, instance_id, payloads):
        return self._gui.instance_manager.import_instance_mod_payloads(instance_id, payloads)

    def remove_instance_mod(self, instance_id, file_name):
        return self._gui.instance_manager.remove_instance_mod(instance_id, file_name)

    def set_instance_mod_enabled(self, instance_id, file_name, enabled):
        return self._gui.instance_manager.set_instance_mod_enabled(instance_id, file_name, enabled)

    def get_instance_worlds(self, instance_id):
        return self._gui.instance_manager.get_instance_worlds(instance_id)

    def browse_import_instance_world(self, instance_id):
        return self._gui.instance_manager.browse_import_instance_world(instance_id)

    def delete_instance_world(self, instance_id, world_name):
        return self._gui.instance_manager.delete_instance_world(instance_id, world_name)

    def get_instance_resource_packs(self, instance_id):
        return self._gui.instance_manager.get_instance_resource_packs(instance_id)

    def browse_import_instance_resource_pack(self, instance_id):
        return self._gui.instance_manager.browse_import_instance_resource_pack(instance_id)

    def delete_instance_resource_pack(self, instance_id, pack_name):
        return self._gui.instance_manager.delete_instance_resource_pack(instance_id, pack_name)

    def get_instance_client_settings(self, instance_id):
        return self._gui.instance_manager.get_instance_client_settings(instance_id)

    def save_instance_client_settings(self, instance_id, values):
        result = self._gui.instance_manager.save_instance_client_settings(instance_id, values)
        if result.get("ok"):
            self._gui.instance_manager.notify_instances_changed()
        return result

    def browse_instance_client_jar(self, instance_id):
        return self._gui.instance_manager.browse_instance_client_jar(instance_id)

    def browse_instance_classpath_jar(self, instance_id):
        return self._gui.instance_manager.browse_instance_classpath_jar(instance_id)

    def set_instance_classpath_enabled(self, instance_id, classpath_id, enabled):
        return self._gui.instance_manager.set_instance_classpath_enabled(instance_id, classpath_id, enabled)

    def get_instance_jvm_settings(self, instance_id):
        return self._gui.instance_manager.get_instance_jvm_settings(instance_id)

    def save_instance_jvm_settings(self, instance_id, values):
        result = self._gui.instance_manager.save_instance_jvm_settings(instance_id, values)
        if result.get("ok"):
            self._gui.instance_manager.notify_instances_changed()
        return result

    # ======================== Java Virtual Machine ========================
    def get_jvms(self, force=False):
        return self._gui.instance_manager.get_jvms(force)

    def get_managed_jvms(self, force=False):
        return self._gui.jre_manager.get_managed_jvms(force)

    def download_jvm(self, java_major_version):
        java_major_version = str(java_major_version or "").strip()
        if not java_major_version.isdigit():
            return {"ok": False, "error": "Java version is required."}

        job_id = self._gui.launcher.background.add_worker(
            "Download Java {}".format(java_major_version),
            self.run_download_jvm_job,
            java_major_version,
        )
        return {"ok": True, "jobId": job_id}

    def run_download_jvm_job(self, job_id, update_job, java_major_version):
        install_dir = self._gui.runtimes_dir / "Java_{}".format(java_major_version)
        try:
            update_job(state="running", status="Downloading Java {}...".format(java_major_version), total=0, progress=0)
            self._gui.instance_creator.install_azul_java_runtime(update_job, java_major_version, install_dir)
            java_executable = runtime_java_executable(install_dir)
            if not java_executable.exists():
                raise RuntimeError("Downloaded Java runtime is missing executable: {}".format(java_executable))
            create_java_version_info(java_major_version, platform.machine().lower(), str(install_dir))
            self._gui.instance_manager.jvm_cache = None
            self._gui.jre_manager.scan_jvms()
            update_job(state="finished", status="Java {} installed.".format(java_major_version), progress=1, total=1, done=True)
        except Exception as exc:
            self._logger.exception("Failed to download JVM.")
            update_job(state="failed", status="Java download failed.", error=str(exc), done=True)

    def delete_jvm(self, runtime_id):
        result = self._gui.jre_manager.delete_runtime(runtime_id)
        self._gui.instance_manager.jvm_cache = None
        return result

    def check_jvm(self, runtime_id):
        result = self._gui.jre_manager.check_runtime(runtime_id)
        self._gui.instance_manager.jvm_cache = None
        return result

    # ======================== Instance Creator ========================
    def open_create_instance_window(self):
        return self._gui.instance_creator.open_create_instance_window()

    def create_instance(self, payload):
        result = self._gui.instance_creator.create_instance(payload)
        if result.get("ok") and not result.get("jobId"):
            self._gui.instance_manager.notify_instances_changed()
        return result

    def install_instance_mod_loader(self, instance_id, payload):
        return self._gui.instance_creator.install_instance_mod_loader(instance_id, payload)

    def get_minecraft_versions(self):
        return self._gui.instance_creator.get_minecraft_versions()

    def get_instance_job(self, job_id):
        return self._gui.launcher.background.get_job(job_id)

    def get_instance_log(self, instance_id, offset=0):
        return self._gui.launch_manager.get_instance_log(instance_id, offset)
