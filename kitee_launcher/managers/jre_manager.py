import os
import re
import json
import shutil
import subprocess
from pathlib import Path


class JavaRuntimeManager:
    def __init__(self, gui, runtimes_dir, data_dir):
        self.gui = gui

        # Directories
        self.runtimes_dir = runtimes_dir
        self.data_dir = data_dir

        # Path
        self.registry_path = self.data_dir / "jvms.json"

    def find_specified_java_version_executable_from_runtimes(self, java_major_version):
        """
        Find specified java version executable file in runtimes dir.
        :param java_major_version:
        :return:
        """
        java_name = "java.exe" if os.name == "nt" else "java"
        fallback_name = "javaw.exe" if os.name == "nt" else "java" # Window ver

        if java_major_version:
            runtime_dir = self.runtimes_dir / "Java_{}".format(java_major_version)
            java_path = runtime_dir / "bin" / java_name

            if java_path.exists() and self.java_executable_matches_major(java_path, java_major_version):
                return str(java_path)

            fallback_path = runtime_dir / "bin" / fallback_name
            if fallback_path.exists() and self.java_executable_matches_major(fallback_path, java_major_version):
                return str(fallback_path)

            for runtime in self.scan_jvms():
                if str(runtime.get("majorVersion") or "") == str(java_major_version):
                    return str(runtime.get("path") or "")

        return None

    def scan_jvms(self):
        """
        Scan jvms in runtimes dir or system dirs.
        :return:
        """
        candidates = {}

        def add_runtime(path, source, major_version=""):
            if not path:
                return

            path = str(path)
            key = os.path.normcase(os.path.abspath(path))
            if key in candidates:
                return

            home = self.java_home_from_executable(path)
            version_info = self.detect_java_version(path, execute=False)
            runtime_major = str(version_info.get("majorVersion") or major_version or self.guess_java_major_version(path) or "")
            managed = self.is_launcher_runtime_home(home)
            candidates[key] = {
                "id": key,
                "path": path,
                "home": home,
                "source": source,
                "majorVersion": runtime_major,
                "version": version_info.get("version") or "",
                "managed": managed,
                "canDelete": managed,
                "validationMethod": version_info.get("method") or "",
            }

        java_names = ("javaw.exe", "java.exe") if os.name == "nt" else ("java",)
        if self.runtimes_dir.exists():
            # Search in runtimes dir
            for runtime_dir in sorted(self.runtimes_dir.iterdir(), key=lambda path: path.name.lower()):
                if not runtime_dir.is_dir():
                    continue

                for java_name in java_names:
                    executable = runtime_dir / "bin" / java_name
                    if executable.exists():
                        add_runtime(executable, "Launcher-Installed", self.major_version_from_runtime_dir(runtime_dir))
                        break

        # Search in system
        for executable in self.find_system_java_executables(java_names):
            add_runtime(executable, "System-Installed")

        path_java = shutil.which("javaw" if os.name == "nt" else "java") or shutil.which("java")
        if path_java:
            add_runtime(path_java, "PATH")

        runtimes = sorted(candidates.values(), key=lambda item: (item["source"], item["majorVersion"], item["path"]))
        self.write_registry(runtimes)
        return runtimes

    def get_managed_jvms(self, force=False):
        runtimes = self.scan_jvms()
        return {
            "ok": True,
            "runtimesDir": str(self.runtimes_dir),
            "registryPath": str(self.registry_path),
            "jvms": runtimes,
            "downloadOptions": self.get_download_options(runtimes),
        }

    @staticmethod
    def get_download_options(runtimes=None):
        installed = {str(item.get("majorVersion") or "") for item in (runtimes or []) if item.get("managed")}
        options = []
        majors = sorted({"8", "16", "17", "21", *installed}, key=lambda value: int(value) if value.isdigit() else 999)
        for major in majors:
            options.append({
                "majorVersion": major,
                "installed": major in installed,
                "name": "Java {}".format(major),
            })
        return options

    def write_registry(self, runtimes):
        """
        Write registry file (for launcher next use)
        :param runtimes:
        :return:
        """
        payload = {
            "runtimesDir": str(self.runtimes_dir),
            "jvms": runtimes,
        }
        try:
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            self.registry_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger = getattr(self.gui, "logger", None)
            if logger:
                logger.exception("Failed to write JVM registry.")

    def is_launcher_runtime_home(self, home):
        """
        Check if a JVM runtime is created by launcher.
        :param home:
        :return:
        """
        try:
            home_path = Path(str(home)).resolve()
            runtimes_path = self.runtimes_dir.resolve()
        except OSError:
            return False

        return home_path.parent == runtimes_path and home_path.name.lower().startswith("java_")

    def check_runtime(self, runtime_id):
        """
        Check runtime information
        :param runtime_id:
        :return:
        """
        runtime_id = str(runtime_id or "").strip()
        if not runtime_id:
            return {"ok": False, "error": "JVM id is required."}

        runtime = next((item for item in self.scan_jvms() if item.get("id") == runtime_id or item.get("path") == runtime_id), None)
        if not runtime:
            return {"ok": False, "error": "JVM was not found."}

        version_info = self.detect_java_version(runtime.get("path"), execute=True)
        runtime.update({
            "majorVersion": version_info.get("majorVersion") or runtime.get("majorVersion") or "",
            "version": version_info.get("version") or runtime.get("version") or "",
            "validationMethod": version_info.get("method") or runtime.get("validationMethod") or "",
            "checked": True,
        })

        runtimes = []
        for item in self.scan_jvms():
            if item.get("id") == runtime.get("id"):
                runtimes.append(runtime)
            else:
                runtimes.append(item)
        self.write_registry(runtimes)

        return {
            "ok": True,
            "runtime": runtime,
            "runtimesDir": str(self.runtimes_dir),
            "registryPath": str(self.registry_path),
            "jvms": runtimes,
            "downloadOptions": self.get_download_options(runtimes),
        }

    def delete_runtime(self, runtime_id):
        """
        Delete runtime (Only works for launcher-installed JVMs)
        :param runtime_id:
        :return:
        """
        runtime_id = str(runtime_id or "").strip()
        if not runtime_id:
            return {"ok": False, "error": "JVM id is required."}

        runtime = next((item for item in self.scan_jvms() if item.get("id") == runtime_id or item.get("path") == runtime_id), None)
        if not runtime:
            return {"ok": False, "error": "JVM was not found."}

        home = Path(str(runtime.get("home") or ""))
        # Ensure only launcher-installed jvms can be deleted
        if not self.is_launcher_runtime_home(home):
            return {"ok": False, "error": "Only launcher-installed JVMs can be deleted."}

        try:
            shutil.rmtree(home)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        return self.get_managed_jvms(force=True)

    @staticmethod
    def find_system_java_executables(java_names):
        """
        Find system Java executables
        :param java_names:
        :return:
        """
        roots = []
        if os.name == "nt":
            for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
                root = os.environ.get(env_name)
                if root:
                    roots.append(os.path.join(root, "Java"))
        elif os.name == "posix":
            roots.extend(("/Library/Java/JavaVirtualMachines", "/opt/java", "/usr/lib/jvm", "/usr/local/java"))

        found = []
        for root in roots:
            if not os.path.isdir(root):
                continue

            for current_root, _, files in os.walk(root):
                for java_name in java_names:
                    if java_name in files and os.path.basename(current_root).lower() == "bin":
                        found.append(os.path.join(current_root, java_name))
                        break

        return found

    @staticmethod
    def java_home_from_executable(executable_path):
        bin_dir = os.path.dirname(str(executable_path))
        if os.path.basename(bin_dir).lower() == "bin":
            return os.path.dirname(bin_dir)
        return bin_dir

    @staticmethod
    def major_version_from_runtime_dir(runtime_dir):
        """
        Get major version from target runtime directory
        (Only works if this runtime is created by launcher)
        :param runtime_dir:
        :return:
        """
        name = runtime_dir.name
        if name.lower().startswith("java_"):
            return name.split("_", 1)[1]

        info_path = runtime_dir / "java.version.info"
        if info_path.exists():
            try:
                for line in info_path.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("JavaMajorVersion") and "=" in line:
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                return ""

        return ""

    def guess_java_major_version(self, executable_path):
        """
        Get major version from target runtime directory
        (Only works if this runtime is created by launcher or use official installer, custom install path may not work)
        :param executable_path:
        :return:
        """
        home = self.java_home_from_executable(executable_path)
        name = os.path.basename(home)
        for prefix in ("jdk-", "jre-", "java-", "Java_"):
            if name.startswith(prefix):
                version = name.split(prefix, 1)[1].split(".", 1)[0].split("_", 1)[0]
                if version.isdigit():
                    return version

        if name.startswith(("jdk1.", "jre1.")):
            parts = name.split(".", 2)
            if len(parts) > 1 and parts[1].isdigit():
                return parts[1]

        return ""

    def java_executable_matches_major(self, executable_path, java_major_version):
        """
        Check if Java major version matches runtime's major version
        :param executable_path:
        :param java_major_version:
        :return:
        """
        actual_major = self.detect_java_major_version(executable_path, execute=False)
        if actual_major:
            return str(actual_major) == str(java_major_version)

        # Failback to guess version
        guessed_major = self.guess_java_major_version(executable_path)
        return str(guessed_major or "") == str(java_major_version)

    def detect_java_major_version(self, executable_path, execute=False):
        return self.detect_java_version(executable_path, execute=execute).get("majorVersion") or ""

    def detect_java_version(self, executable_path, execute=False):
        release_version = self.detect_java_version_from_release_file(executable_path)
        if release_version:
            return {
                "version": release_version,
                "majorVersion": self.parse_java_version_major(release_version),
                "method": "release",
            }

        if not execute:
            return {"version": "", "majorVersion": "", "method": "not checked"}

        # Use checkMyDuke.jar to detect java version
        duke_version = self.detect_java_version_from_checkmyduke(executable_path)
        if duke_version:
            return {
                "version": duke_version,
                "majorVersion": self.parse_java_version_major(duke_version),
                "method": "CheckMyDuke",
            }

        # Use "java -version" to detect java version (legacy method from BakeLauncher's DukeExplorer)
        command_version = self.detect_java_version_from_command(executable_path)
        if command_version:
            return {
                "version": command_version,
                "majorVersion": self.parse_java_version_major(command_version),
                "method": "-version",
            }

        return {"version": "", "majorVersion": "", "method": ""}

    def detect_java_major_version_from_release_file(self, executable_path):
        version = self.detect_java_version_from_release_file(executable_path)
        return self.parse_java_version_major(version)

    def detect_java_version_from_release_file(self, executable_path):
        """
        Detect Java major version from release file (For newer java versions such as java 8)
        :param executable_path:
        :return:
        """
        release_path = os.path.join(self.java_home_from_executable(executable_path), "release")
        if not os.path.exists(release_path):
            return ""

        try:
            with open(release_path, "r", encoding="utf-8", errors="ignore") as release_file:
                for line in release_file:
                    if line.startswith("JAVA_VERSION="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            return ""

        return ""

    def detect_java_major_version_from_command(self, executable_path):
        version = self.detect_java_version_from_command(executable_path)
        return self.parse_java_version_major(version)

    @staticmethod
    def detect_java_version_from_command(executable_path):
        """
        Detect Java major version yse "java -version" command
        (Not working if regex pattern not support target java version)
        :param executable_path:
        :return:
        """
        try:
            result = subprocess.run(
                [str(executable_path), "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception:
            return ""

        output = "{}\n{}".format(result.stdout or "", result.stderr or "")
        match = re.search(r'version\s+"([^"]+)"', output)
        if not match:
            return ""

        return match.group(1)

    @staticmethod
    def detect_java_version_from_checkmyduke(executable_path):
        """
        Detect Java major version yse CheckMyDuke.jar
        (Not working for old java versions. Maybe java major less 8 are not supported)
        :param executable_path:
        :return:
        """
        checkmyduke_jar = Path(__file__).resolve().parents[1] / "bk_core" / "duke" / "CheckMyDuke.jar"
        if not checkmyduke_jar.exists():
            return ""

        try:
            result = subprocess.run(
                [str(executable_path), "-jar", str(checkmyduke_jar)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception:
            return ""

        output = (result.stdout or "").strip()
        return output if output and re.search(r"\d", output) else ""

    @staticmethod
    def parse_java_version_major(version):
        """
        Split java major version from full java version string
        :param version:
        :return:
        """
        value = str(version or "").strip()
        if not value:
            return ""

        if value.startswith("1."):
            parts = value.split(".", 2)
            return parts[1] if len(parts) > 1 and parts[1].isdigit() else ""

        major = value.split(".", 1)[0].split("+", 1)[0].split("-", 1)[0]
        return major if major.isdigit() else ""
