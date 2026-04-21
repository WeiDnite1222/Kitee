"""
Kitee

Copyright (c) 2026 Kitee Contributors. All rights reserved.

Original repository:

Copyright (c) 2024~2025 Techarerm/TedKai
"""
import argparse
import base64
import html
import json
import logging
import threading
import time
import tomllib
import tomli_w
import uuid
from .front import FrontendAPI
from .managers.account_manager import AccountManager
from .managers.instance_manager import InstanceManager
from .managers.launch_manager import LaunchManager
from .managers.instance_creator import InstanceCreator
from .managers.jre_manager import JavaRuntimeManager
from .bk_core.utils.settings import FileSettings, required_section, required_value

DEFAULT_LANGUAGE = "en_US"

DEFAULT_TAB_ORDER = [
    "home_container",
    "instances_container",
    "accounts_container",
    "about_container",
    "settings_container",
]

DEFAULT_SETTINGS = {
    "main": {
        "language": DEFAULT_LANGUAGE,
    },
    "frontend": {
        "language": "zh-TW",
        "theme": "light",
        "tabs": {
            "order": DEFAULT_TAB_ORDER,
            "current": "home_container",
            "detached": [],
            "hidden": [],
        },
    },
    "instances": {
        "displayMode": "icon",
    },
    "background": {
        "imagePath": "",
        "blur": 10,
        "mediaOpacity": 100,
        "surfaceAlpha": 60,
        "childMode": "inherit",
        "childImagePath": "",
        "childBlur": 0,
    },
}

VALIDATION_RULES = {
    "main": required_section({
        "language": required_value(DEFAULT_LANGUAGE),
    }),
    "frontend": required_section({
        "language": required_value(DEFAULT_LANGUAGE),
        "theme": required_value("light"),
        "tabs": required_section({
            "order": required_value(DEFAULT_TAB_ORDER, recover_missing_items=True),
            "current": required_value("home_container"),
            "detached": required_value([]),
            "hidden": required_value([]),
        }),
    }),
    "instances": required_section({
        "displayMode": required_value("icon"),
    }),
    "background": required_section({
        "imagePath": required_value(None),
        "blur": required_value(10),
        "mediaOpacity": required_value(100),
        "surfaceAlpha": required_value(60),
        "childMode": required_value("inherit"),
        "childImagePath": required_value(None),
        "childBlur": required_value(0),
    }),
}

class KiteeGUIConfig(FileSettings):
    def __init__(self, settings_path, default_settings, validation_rules, dumps_func, load_func):
        FileSettings.__init__(self,
                              settings_path,
                              default_settings,
                              validation_rules=validation_rules,
                              dumps_func=dumps_func,
                              load_func=load_func)

        self.lock = threading.Lock()


class KiteeMainGUI:
    """
    Kitee Main GUI Window (webview)
    """

    def __init__(self, launcher, args, callback=None):
        self.launcher = launcher
        self.background = self.launcher.background
        self.callback = callback

        # Logger
        self.logger = logging.getLogger("MainGUI")
        self.logger.setLevel(logging.DEBUG if self.launcher.debug else logging.INFO)

        if self.launcher.debug:
            self.logger.addHandler(launcher.handler)

        # Directories
        # ProgramDir/resources/*
        self.resource_dir = self.launcher.get_program_path("resources")
        self.template_dir = self.resource_dir / "templates"
        self.style_dir = self.resource_dir / "styles"
        self.templates_dir = self.resource_dir / "templates"
        self.script_dir = self.resource_dir / "scripts"
        self.locale_dir = self.resource_dir / "locales"
        self.icons_dir = self.resource_dir / "icons"

        # Path
        self.icon_path = self.icons_dir / "icon.ico"

        # WorkDir
        self.work_dir = self.launcher.work_dir
        self.settings_dir = self.launcher.get_work_path("settings")
        self.data_dir = self.launcher.get_work_path("data")
        self.runtimes_dir = self.launcher.get_work_path("runtimes")
        self.instances_dir = self.launcher.get_work_path("instances")

        # Vars & Flags
        self.auto_reload = False
        self.renderer = None

        if self.launcher.platform.lower() == "linux":
            self.renderer = "gtk"

        # Settings
        self.settings_path = self.settings_dir / "gui" / "settings.toml"
        self.settings = KiteeGUIConfig(
            self.settings_path,
            DEFAULT_SETTINGS,
            VALIDATION_RULES,
            dumps_func=tomli_w.dumps,
            load_func=tomllib.load
        )


        # FrontAPI
        self.api = FrontendAPI(
            self.launcher,
            self,
            self.settings,
            self.logger,
        )

        # Managers
        self.account_manager = AccountManager(
            self,
            self.data_dir,
            self.logger,
        )
        self.jre_manager = JavaRuntimeManager(
            self,
            self.runtimes_dir,
            self.data_dir,
        )
        self.instance_manager = InstanceManager(
            self,
            self.jre_manager,
            self.instances_dir,
            self.logger,
        )
        self.instance_creator = InstanceCreator(
            self,
            self.work_dir,
            self.instance_manager,
            self.launcher.version,
            self.background,
            self.logger,
        )
        self.launch_manager = LaunchManager(
            self,
            self.launcher,
            self.background,
            self.instance_manager,
            self.jre_manager,
            self.account_manager,
            self.instances_dir,
            self.logger,
        )

        # International
        self.languages = {}

        # Arguments
        self.args = args
        self.arguments_parser()

        # Event & Lock
        self.in_mainloop = threading.Event()

        # Window
        self.window = None
        self.detached_windows = {}
        self.overlay_callbacks = {}
        self.overlay_callbacks_lock = threading.Lock()

        # Debug
        self.resource_snapshot = {}

    def initialize(self):
        self.arguments_parser()

        # Ensure settings file exists
        if not self.settings.exists():
            self.settings.create(exist_ok=True)
        else:
            self.settings.read_from_exist()

        self.load_available_languages()

    def mainloop(self):
        webview = self.get_webview()

        if webview:
            try:
                self.window = webview.create_window(
                    "KiteeLauncher",
                    html=self.build_home_html(),
                    js_api=self.api,
                    width=1100,
                    height=700,
                    min_size=(800, 500),
                )
                self.in_mainloop.set()
                self.start_resource_watcher()
                webview.start(debug=self.launcher.debug,
                              gui=self.renderer,
                              icon=str(self.ensure_icon_is_exist()))
            except Exception as exc:
                self.logger.exception("GUI stopped unexpectedly.")
                self.in_mainloop.clear()
                if self.callback:
                    self.callback(exc)
                return

    def arguments_parser(self):
        parser = argparse.ArgumentParser(description="Kitee GUI Arguments List")
        parser.add_argument("-al", "--auto-reload",
                            help="Enable GUI debug mode and reload resources when they change",
                            action="store_true")
        parser.add_argument("-r", "--renderer",
                            help="Set the GUI renderer (e.g., \"cef\" Chromium, \"edge\" WebView2, \"qt\" QtWebEngine, \"gtk\" WebKitGTK,"
                                 " \"cocoa\" WebKit on macOS)")
        parser.add_argument("-lang", "--language",
                            help="Set launcher language resource (currently only \"en\" is bundled)")

        args, unknown_args = parser.parse_known_args(self.args[1:])

        if args.auto_reload:
            self.auto_reload = True

        if args.renderer:
            self.renderer = args.renderer

        if args.language:
            self.language = args.language

        self.logger.warning("Unknown GUI arguments: {}".format(unknown_args)) if len(unknown_args) > 0 else None

        return args

    def load_available_languages(self):
        self.logger.debug("Searching available languages...")

        try:
            locale_files = sorted(self.locale_dir.glob("*.json"))
        except Exception as e:
            self.logger.exception(f"Failed to list locale resources. Got exception: {e}")
            locale_files = []

        for locale_file in locale_files:
            try:
                with open(locale_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                self.logger.error("Failed to read locale resources file: {}, Got exception: {}".format(locale_file, e))
                continue

            lang_id = data.get("language", None)

            if lang_id is None:
                self.logger.warning("Locale file {} lang_id undefined.".format(locale_file))
                continue

            translations = data.get("translations", [])

            self.languages[lang_id] = translations

    def get_available_languages(self):
        return self.languages.keys()

    def get_webview(self):
        try:
            import webview
            return webview
        except ImportError:
            self.logger.error("pywebview is not installed. Install it with: pip install pywebview")

    def create_detached_tab(self, target_id, title, body_html):
        try:
            import webview

            if target_id in self.detached_windows:
                self.focus_detached_tab(target_id)
                return {"ok": True, "alreadyDetached": True}

            window = webview.create_window(
                title,
                html=self.build_detached_tab_html(target_id, title, body_html),
                js_api=self.api,
                width=720,
                height=520,
                min_size=(420, 280),
            )
            self.detached_windows[target_id] = window

            def on_closed():
                if self.detached_windows.get(target_id) is window:
                    self.detached_windows.pop(target_id, None)
                    self.notify_tab_docked(target_id)

            window.events.closed += on_closed
            return {"ok": True}
        except Exception as exc:
            self.logger.exception("Failed to create detached tab window.")
            return {"ok": False, "error": str(exc)}

    def dock_detached_tab(self, target_id):
        window = self.detached_windows.pop(target_id, None)

        try:
            if window:
                window.destroy()
        except Exception as e:
            self.logger.exception("Failed to close detached tab window. Exception: {}".format(e))

        self.notify_tab_docked(target_id)
        return {"ok": True}

    def focus_detached_tab(self, target_id):
        window = self.detached_windows.get(target_id)

        self.logger.debug("Focusing detached tab for target id: {}".format(target_id))

        if not window:
            self.logger.error("Target id not found: {}".format(target_id))
            return {"ok": False, "error": "Detached window not found."}

        try:
            window.show()
            return {"ok": True}
        except Exception as exc:
            self.logger.exception("Failed to focus detached tab window.")
            return {"ok": False, "error": str(exc)}

    def notify_tab_docked(self, target_id):
        self.evaluate_main_js("window.__bakeDockTab && window.__bakeDockTab({});".format(json.dumps(target_id)))

    def show_error_overlay(self, message, window=None, callback=None, actions=None):
        if callable(window):
            if actions is None and isinstance(callback, (list, tuple)):
                actions = callback
            callback = window
            window = None
        elif isinstance(window, (list, tuple)) and actions is None:
            actions = window
            window = None

        self.show_overlay(
            "error",
            message,
            window=window,
            callback=callback,
            actions=actions,
            default_message="Unknown error.",
        )

    def show_warning_overlay(self, message, window=None, callback=None, actions=None):
        if callable(window):
            if actions is None and isinstance(callback, (list, tuple)):
                actions = callback
            callback = window
            window = None
        elif isinstance(window, (list, tuple)) and actions is None:
            actions = window
            window = None

        self.show_overlay(
            "warning",
            message,
            window=window,
            callback=callback,
            actions=actions,
            default_message="Oh no! Warning message is missing.",
        )

    def show_overlay(self, level, message, window=None, callback=None, actions=None, default_message=""):
        target_window = window or self.window
        if not target_window:
            return

        overlay_id = ""
        if callable(callback):
            overlay_id = uuid.uuid4().hex
            with self.overlay_callbacks_lock:
                self.overlay_callbacks[overlay_id] = callback

        payload = {
            "level": level,
            "title": "Warning" if level == "warning" else "Error",
            "message": str(message or default_message),
            "actions": self.normalize_overlay_actions(actions),
            "overlayId": overlay_id,
        }
        function_name = "__bakeShowWarningOverlay" if level == "warning" else "__bakeShowErrorOverlay"
        script = "window.{name} && window.{name}({payload});".format(
            name=function_name,
            payload=json.dumps(payload),
        )
        try:
            target_window.evaluate_js(script)
        except Exception as e:
            if overlay_id:
                with self.overlay_callbacks_lock:
                    self.overlay_callbacks.pop(overlay_id, None)
            self.logger.exception("Failed to show {} overlay. Exception: {}".format(level, e))

    def handle_overlay_action(self, overlay_id, action_id):
        if not overlay_id:
            return {"ok": False, "error": "Overlay id is required."}

        with self.overlay_callbacks_lock:
            callback = self.overlay_callbacks.pop(str(overlay_id), None)

        if not callable(callback):
            return {"ok": False, "error": "Overlay callback not found."}

        try:
            callback(str(action_id or ""))
        except Exception as exc:
            self.logger.exception("Failed to run overlay callback.")
            return {"ok": False, "error": str(exc)}

        return {"ok": True}

    @staticmethod
    def normalize_overlay_actions(actions):
        if not actions:
            actions = [{"id": "close", "label": "Close"}]

        normalized = []
        for index, action in enumerate(actions):
            if isinstance(action, str):
                normalized.append({"id": action, "label": action})
                continue

            if not isinstance(action, dict):
                continue

            action_id = action.get("id") or action.get("value") or "action_{}".format(index + 1)
            label = action.get("label") or action.get("text") or str(action_id)
            normalized.append({
                "id": str(action_id),
                "label": str(label),
                "kind": str(action.get("kind") or action.get("type") or ""),
                "closes": action.get("closes", True),
            })

        if not normalized:
            normalized.append({"id": "close", "label": "Close"})

        return normalized

    # ======================== Resource Watcher ========================

    def start_resource_watcher(self):
        if not self.auto_reload:
            return

        self.resource_snapshot = self.get_resource_snapshot()
        watcher = threading.Thread(target=self.watch_resources, name="ResourceWatcher")
        watcher.daemon = True
        watcher.start()
        self.logger.debug("GUI resource hot reload enabled.")

    def watch_resources(self):
        while self.in_mainloop.is_set():
            time.sleep(1)

            snapshot = self.get_resource_snapshot()
            if snapshot == self.resource_snapshot:
                continue

            self.resource_snapshot = snapshot
            self.reload_window()

    def get_resource_snapshot(self):
        snapshot = {}

        if not self.resource_dir.exists():
            return snapshot

        for path in self.resource_dir.rglob("*"):
            if path.is_file():
                snapshot[str(path)] = path.stat().st_mtime_ns

        return snapshot

    # ======================== Utils ========================

    def reload_window(self):
        if not self.window:
            return

        try:
            self.window.load_html(self.build_home_html())
            self.logger.debug("GUI resources reloaded.")
        except Exception:
            self.logger.exception("Failed to reload GUI resources.")

    def get_resource(self, relative_path):
        path = self.resource_dir / relative_path

        if not path.exists() or not path.is_file():
            raise FileNotFoundError("Resource {} not found".format(relative_path))

    def get_styles(self, relative_path):
        path = self.style_dir / relative_path

        if not path.exists() or not path.is_file():
            raise FileNotFoundError("Style file {} not found".format(relative_path))

        return path.read_text(encoding="utf-8")

    def get_scripts(self, relative_path):
        path = self.script_dir / relative_path

        if not path.exists() or not path.is_file():
            raise FileNotFoundError("Failed to find script file: {}".format(path))

        return path.read_text(encoding="utf-8")

    def get_templates(self, relative_path):
        path = self.template_dir / relative_path

        if not path.exists() or not path.is_file():
            raise FileNotFoundError("Failed to find template file: {}".format(path))

        return path.read_text(encoding="utf-8")

    def image_to_base64_data_url(self, path):
        try:
            data = path.read_bytes()
        except Exception as e:
            self.logger.warning("Failed to read image resource: {}, Got {}".format(path, e))
            return ""

        suffix = path.suffix.lower().lstrip(".") or "png"
        mime_types = {
            "bmp": "image/bmp",
            "gif": "image/gif",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webm": "video/webm",
            "webp": "image/webp",
        }
        mime = mime_types.get(suffix, "application/octet-stream")

        if mime == "application/octet-stream":
            self.logger.warning("Image resource file {} may not supported.".format(path))

        return "data:{};base64,{}".format(mime, base64.b64encode(data).decode("ascii"))

    def ensure_icon_is_exist(self):
        if not self.icon_path.exists() or not self.icon_path.is_file():
            raise FileNotFoundError("Icon file {} not found".format(self.icon_path))

        return self.icon_path

    @staticmethod
    def focus_window(window):
        for method_name in ("restore", "show"):
            method = getattr(window, method_name, None)
            if not method:
                continue

            try:
                method()
            except Exception:
                pass

        try:
            window.evaluate_js("window.focus();")
        except Exception:
            pass

    def evaluate_main_js(self, script):
        if not self.window:
            return

        try:
            self.window.evaluate_js(script)
        except Exception as e:
            self.logger.exception("Failed to evaluate JavaScript in main window. Error: {}".format(e))

    # ======================== Templates ========================
    def render(self, template_relative_path, replacements):
        template = self.get_templates(template_relative_path)
        return self.render_text(template, replacements)

    def render_text(self, text, replacements):
        for key, value in replacements.items():
            for placeholder in self.placeholders(key):
                text = text.replace(placeholder, str(value))

        return text

    @staticmethod
    def placeholders(name):
        return [
            "<!-- BK_{} -->".format(name.upper()),  # html
            "/* BK_{} */".format(name.upper()),  # css
            "__BK_{}__".format(name.upper()),  # js
        ]

    # ======================== HTML ========================
    def build_home_html(self):
        version = getattr(self.launcher, "version", "development")
        grass_icon = json.dumps(self.image_to_base64_data_url(self.resource_dir / "icons" / "instances" / "grass.png"))
        grass_modded_icon = json.dumps(
            self.image_to_base64_data_url(self.resource_dir / "icons" / "instances" / "grass_modded.png"))
        home_js = self.render_text(self.get_scripts("home.js"), {
            "grass_icon": grass_icon,
            "grass_modded_icon": grass_modded_icon,
        })

        return self.render("home.html", {
            "style": self.get_styles("home.css"),
            "i18n": self.build_i18n_script(),
            "shared_js": self.get_scripts("shared.js"),
            "version": version,
            "bk_core_version": self.launcher.bk_core_version,
            "home_js": home_js,
        })

    def build_detached_tab_html(self, target_id, title, body_html):
        return self.render("detached_tab.html", {
            "style": self.get_styles("home.css"),
            "i18n": self.build_i18n_script(),
            "target_id": html.escape(target_id, quote=True),
            "title": html.escape(title, quote=True),
            "body": body_html,
            "shared_js": self.get_scripts("shared.js"),
            "detached_js": self.get_scripts("detached.js"),
        })

    def build_create_instance_html(self):
        return self.render("create_instance.html", {
            "style": self.get_styles(self.style_dir / "home.css"),
            "i18n": self.build_i18n_script(),
            "shared_js": self.get_scripts("shared.js"),
            "instance_creator_js": self.get_scripts("instance_creator.js"),
        })

    def build_instance_window_html(self, instance_id, initial_page="overview", initial_detail=None):
        grass_icon = json.dumps(self.image_to_base64_data_url(self.resource_dir / "icons" / "instances" / "grass.png"))
        grass_modded_icon = json.dumps(
            self.image_to_base64_data_url(self.resource_dir / "icons" / "instances" / "grass_modded.png"))
        instance_js = self.render_text(self.get_scripts("instance.js"), {
            "instance_id": json.dumps(instance_id),
            "initial_page": json.dumps(initial_page),
            "initial_detail": json.dumps(initial_detail),
            "grass_icon": grass_icon,
            "grass_modded_icon": grass_modded_icon,
        })

        return self.render("instance_window.html", {
            "style": self.get_styles(self.style_dir / "home.css"),
            "i18n": self.build_i18n_script(),
            "shared_js": self.get_scripts("shared.js"),
            "instance_js": instance_js,
        })

    def build_i18n_script(self):
        frontend = self.settings.get("frontend", {})
        main = self.settings.get("main", {})
        language = frontend.get("language") or main.get("language") or DEFAULT_LANGUAGE
        translations = self.languages.get(language) or self.languages.get(DEFAULT_LANGUAGE) or {}

        if not translations:
            self.logger.warning("No translations found for language {}, using default language: {}".format(
                language, DEFAULT_LANGUAGE))

        payload = {
            "language": language,
            "availableLanguages": list(self.languages.keys()),
            "translations": translations,
        }

        return """
        window.KiteeLauncherI18n = {payload};
        (function () {{
            const i18n = window.KiteeLauncherI18n || {{}};
            const translations = i18n.translations || {{}};
            const attrs = ["aria-label", "placeholder", "title"];
            let translating = false;

            function translateText(value) {{
                return translations[value] || value;
            }}

            window.t = function (key, params) {{
                let text = translateText(String(key || ""));
                if (params && typeof params === "object") {{
                    Object.entries(params).forEach(([name, value]) => {{
                        text = text.replaceAll(`{{${{name}}}}`, String(value));
                    }});
                }}
                return text;
            }};

            function translateElement(element) {{
                if (!element || element.nodeType !== Node.ELEMENT_NODE) {{
                    return;
                }}

                if (element.matches("[data-i18n]")) {{
                    const translated = window.t(element.getAttribute("data-i18n"));
                    if (element.textContent !== translated) {{
                        element.textContent = translated;
                    }}
                }}

                attrs.forEach(attr => {{
                    const explicitKey = element.getAttribute(`data-i18n-${{attr}}`);
                    if (explicitKey) {{
                        const translated = window.t(explicitKey);
                        if (element.getAttribute(attr) !== translated) {{
                            element.setAttribute(attr, translated);
                        }}
                        return;
                    }}

                    const value = element.getAttribute(attr);
                    if (value && translations[value] && translations[value] !== value) {{
                        element.setAttribute(attr, translations[value]);
                    }}
                }});
            }}

            function translateTextNode(node) {{
                if (!node || node.nodeType !== Node.TEXT_NODE) {{
                    return;
                }}

                const parent = node.parentElement;
                if (!parent || ["SCRIPT", "STYLE", "TEXTAREA"].includes(parent.tagName)) {{
                    return;
                }}

                const original = node.nodeValue;
                const trimmed = original.trim();
                if (!trimmed || !translations[trimmed] || translations[trimmed] === trimmed) {{
                    return;
                }}

                node.nodeValue = original.replace(trimmed, translations[trimmed]);
            }}

            function translate(root) {{
                if (translating) {{
                    return;
                }}

                translating = true;
                try {{
                    document.documentElement.lang = i18n.language || "en_US";
                    const scope = root && root.nodeType === Node.ELEMENT_NODE ? root : document.body;
                    if (!scope) {{
                        return;
                    }}

                    translateElement(scope);
                    scope.querySelectorAll("*").forEach(translateElement);

                    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
                    let node = walker.nextNode();
                    while (node) {{
                        translateTextNode(node);
                        node = walker.nextNode();
                    }}
                }} finally {{
                    translating = false;
                }}
            }}

            window.translateKiteeLauncher = translate;
            translate(document.body);

            const observer = new MutationObserver(records => {{
                if (translating) {{
                    return;
                }}

                records.forEach(record => {{
                    record.addedNodes.forEach(node => {{
                        if (node.nodeType === Node.ELEMENT_NODE) {{
                            translate(node);
                        }} else if (node.nodeType === Node.TEXT_NODE) {{
                            translateTextNode(node);
                        }}
                    }});

                    if (record.type === "characterData") {{
                        translateTextNode(record.target);
                    }}
                }});
            }});

            if (document.body) {{
                observer.observe(document.body, {{
                    childList: true,
                    subtree: true,
                    characterData: true,
                }});
            }}
        }})();
    """.format(payload=json.dumps(payload, ensure_ascii=False))
