"""
bk_core

Copyright (c) 2024~2025 Techarerm/TedKai
Copyright (c) 2026 Kitee Contributors. All rights reserved.
"""
import datetime
import os
import platform
import subprocess
import tempfile
from .. import __version__
from ..game.version.version import get_version_data, get_version_data_from_exist_data


class Base:
    Platform = platform.system()
    FullArch = platform.machine().lower()


class client:
    """
    Client
    """
    def __init__(self, launch_command: str, client_name: str) -> None:
        self.client_name = client_name
        self.launch_command = launch_command

        # Process
        self.client_process: subprocess.Popen | None = None
        self.client_pid: int | None = None
        self.started_by_interface: bool = False

        # Logger
        self.logger = None

    def start_client_attached(self):
        """
        Start client in attached mode.
        """
        self.client_process = subprocess.Popen(
            self.launch_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.client_pid = self.client_process.pid
        print(f"[attached] Client pid: {self.client_pid}")
        return self.client_process

    # === 啟動 ===
    def start_client(self):
        """
        Start client (legacy method from BakeLauncher)
        This function will create a terminal(unix)/cmd(windows) for client
        """
        if os.name == "nt":
            # Create temp bat file
            with tempfile.NamedTemporaryFile(
                suffix=".bat",
                delete=False,
                mode="w",
                encoding="utf-8",
            ) as batch:
                batch_name = batch.name
                batch.write("@echo off\r\n")

                # Use utf-8
                batch.write("chcp 65001 >nul\r\n")
                batch.write(self.launch_command)
                batch.write("\r\n")

            # Open new console
            creationflags = subprocess.CREATE_NEW_CONSOLE
            self.client_process = subprocess.Popen(
                ["cmd", "/c", batch_name],
                creationflags=creationflags,
            )
        else:
            # Open new session on unix-like system
            self.client_process = subprocess.Popen(
                self.launch_command,
                shell=True,
                start_new_session=True,
            )

        self.client_pid = self.client_process.pid
        print(f"Client pid: {self.client_pid}")

        return None

    def start_client_by_interface(self, interface_starter):
        """
        Start client by interface starter.
        :param interface_starter:
        :return:
        """
        result = interface_starter(self)
        self.started_by_interface = True

        if isinstance(result, dict):
            process = result.get("process")
            pid = result.get("pid")

            if process is not None:
                self.client_process = process
            if pid is not None:
                self.client_pid = int(pid)
            elif process is not None:
                self.client_pid = self._extract_process_pid(process)

            self.logger = result.get("logger", self.logger)
            return self.logger

        if result is not None:
            self.client_process = result
            self.client_pid = self._extract_process_pid(result)

        return result

    @staticmethod
    def _extract_process_pid(process):
        pid = getattr(process, "pid", None)
        if pid is not None:
            return int(pid)

        process_id = getattr(process, "processId", None)
        if callable(process_id):
            process_id = process_id()
        if process_id is not None:
            return int(process_id)

        return None

    def stop(self):
        """
        Stop client.
        """
        if self.client_process is not None and self.is_alive():
            self.client_process.kill()

    def is_alive(self) -> bool:
        """
        Check if client is alive.
        """
        if self.client_process is None:
            return False

        return self.client_process.poll() is None


class clientLauncher:
    """
    clientLauncher
    Manage client, Generate arguments, Start game
    """
    def __init__(self) -> None:
        self.client_container: list[client] = []
        self.initialized: bool = False
        self.game_default_screen_height = 720
        self.game_default_screen_width = 1280
        self.jvm_ram_minimum_size = 2048
        self.jvm_ram_max_size = 4096

    def initialize(self, info: bool = True, custom_payload: str | None = None):
        """
        Initialize client
        wei comment: Not sure why original code has this function
        """
        print("clientLauncher > Initializing.")
        if info:
            print(f"Version {__version__}")
            print(f"Init date: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            print("")

        if custom_payload is not None:
            print(custom_payload)

        self.initialized = True

    @staticmethod
    def build_launch_command(
        java_executable,
        jvm_args,
        natives_path,
        classpath,
        main_class,
        game_args,
    ):
        if " " in java_executable and not java_executable.startswith('"'):
            java_executable = f'"{java_executable}"'

        return (
            f'{java_executable} {jvm_args} '
            f'-Djava.library.path="{natives_path}" -cp "{classpath}" '
            f'{main_class} {game_args}'
        )

    def _append_client(self, launch_command: str, client_name: str) -> client:
        """
        建立一個新的 client 物件並放進容器。
        """
        print("clientLauncher > Creating new client.")
        print(f"Name : {client_name}")
        print("Created Date: {}\n".format(datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')))

        new_client = client(launch_command, client_name)
        self.client_container.append(new_client)

        return new_client

    def create_client_instance(
        self,
        client_name,
        java_executable,
        jvm_args,
        natives_path,
        classpath,
        main_class,
        game_args,
    ) -> client:
        launch_command = self.build_launch_command(
            java_executable=java_executable,
            jvm_args=jvm_args,
            natives_path=natives_path,
            classpath=classpath,
            main_class=main_class,
            game_args=game_args,
        )
        return self._append_client(launch_command, client_name)

    def create_new_client(self, launch_command: str, client_name: str) -> client:
        return self._append_client(launch_command, client_name)

    def generate_jvm_args(
        self,
        client_version,
        versions_folder=None,
        without_ram_args=False,
        append_args=False,
    ):
        """
        Generate JVM arguments(Only generate require args)
        (About argument "-Djava.library.path=", check launch_client for more information :)
        """
        # Get version data
        version_data = None
        if versions_folder is not None:
            version_data = get_version_data_from_exist_data(client_version, versions_folder)
        if version_data is None:
            version_data = get_version_data(client_version)

        jvm_args_data = version_data.get("arguments", {}).get("jvm", None)

        # Set Java Virtual Machine use Memory Size
        ram_size_args = fr"-Xms{self.jvm_ram_minimum_size}m -Xmx{self.jvm_ram_max_size}m "

        other_args = " "

        # Set this to prevent the windows too small
        window_size_args = (f"-Dorg.lwjgl.opengl.Window.undecorated=false "
                            f"-Dorg.lwjgl.opengl.Display.width={self.game_default_screen_width} "
                            f"-Dorg.lwjgl.opengl.Display.height={self.game_default_screen_height} ")
        other_args += window_size_args

        if Base.Platform == "Windows":
            # JVM_Args_HeapDump(It will save heap dump when Minecraft Encountered OutOfMemoryError? "Only For Windows!")
            other_args += "-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump "
        elif Base.Platform == "Darwin":
            # Check whether the startup version of macOS requires the parameter "-XstartOnFirstThread" parameter In
            # LWJGL 3.x, macOS requires this args to make lwjgl running on the JVM starts with thread 0) (from wiki.vg)
            if jvm_args_data is not None:
                for arg in jvm_args_data:
                    if isinstance(arg, dict) and "rules" in arg:
                        for rule in arg["rules"]:
                            if rule.get("action") == "allow" and rule.get("os", {}).get("name") == "osx":
                                if "-XstartOnFirstThread" in arg["value"]:
                                    other_args += f" -XstartOnFirstThread"

        if append_args:
            other_args += f" {append_args}"

        if without_ram_args:
            return other_args
        else:
            return ram_size_args, other_args

    @staticmethod
    def _normalize_game_argument_template(minecraft_arguments):
        if isinstance(minecraft_arguments, list):
            parts = []
            for arg in minecraft_arguments:
                if isinstance(arg, str):
                    parts.append(arg)
                elif isinstance(arg, dict) and "value" in arg:
                    value = arg["value"]
                    if isinstance(value, list):
                        parts.extend(str(v) for v in value)
                    else:
                        parts.append(str(value))
            return " ".join(parts)

        return minecraft_arguments

    @staticmethod
    def _serialize_game_args(args_dict):
        args = []
        for arg_name, arg_value in args_dict.items():
            if arg_name == "__positional__":
                args.extend(str(value) for value in arg_value)
                continue

            if arg_value is None:
                continue

            args.append(arg_name)
            if arg_value is not True:
                args.append(str(arg_value))

        return " ".join(args)

    @staticmethod
    def generate_game_args(
        version_id,
        username,
        access_token,
        game_dir,
        assets_dir,
        assets_index,
        uuid,
        versions_folder=None,
        fetch_version_data_without_using_exist=False,
    ):
        # parameter stuff
        if fetch_version_data_without_using_exist:
            version_data = get_version_data(version_id)
        else:
            version_data = None
            if versions_folder is not None:
                version_data = get_version_data_from_exist_data(version_id, versions_folder)
            if version_data is None:
                return False, None

        minecraft_arguments = version_data.get("arguments", {}).get("game", None)
        if minecraft_arguments is None:
            minecraft_arguments = version_data.get("minecraftArguments", None)
            if minecraft_arguments is None:
                return False, None

        client_type = version_data.get("type", None)
        user_properties = "{}"
        user_type = "msa"

        minecraft_arguments = clientLauncher._normalize_game_argument_template(minecraft_arguments)

        if "--userProperties" in minecraft_arguments:
            minecraft_args_dict = {
                "--username": username,
                "--version": version_id,
                "--gameDir": game_dir,
                "--assetsDir": assets_dir,
                "--assetIndex": assets_index,
                "--accessToken": access_token,
                "--userProperties": user_properties,
            }

        elif client_type == "old-alpha":
            minecraft_args_dict = {
                "__positional__": [username, access_token],
                "--gameDir": game_dir,
                "--assetsDir": assets_dir,
            }

        # Handle special case where ${auth_player_name} and ${auth_session} are at the beginning
        elif minecraft_arguments.startswith("${auth_player_name} ${auth_session}"):
            # Prepend the username and access token as per the special case
            minecraft_args_dict = {
                "__positional__": [username, access_token],
                "--gameDir": game_dir,
                "--assetsDir": assets_dir,
                "--assetIndex": assets_index,
            }

        elif minecraft_arguments.endswith("${game_assets}"):
            minecraft_args_dict = {
                "--username": username,
                "--session": access_token,
                "--version": version_id,
                "--gameDir": game_dir,
                "--assetsDir": assets_dir,
                "--assetIndex": assets_index,
            }

        elif minecraft_arguments.startswith("--username") and minecraft_arguments.endswith("${auth_access_token}"):
            minecraft_args_dict = {
                "--username": username,
                "--version": version_id,
                "--gameDir": game_dir,
                "--assetsDir": assets_dir,
                "--assetIndex": assets_index,
                "--accessToken": access_token,
            }

        else:
            minecraft_args_dict = {
                "--username": username,
                "--version": version_id,
                "--gameDir": game_dir,
                "--assetsDir": assets_dir,
                "--assetIndex": assets_index,
                "--uuid": uuid,
                "--accessToken": access_token,
                "--userType": user_type,
            }

        if "AlphaVanillaTweaker" in minecraft_arguments or client_type in ["classic", "infdev", "indev", "alpha", "old"
                                                                                                                 "-alpha"]:
            minecraft_args_dict["--tweakClass"] = "net.minecraft.launchwrapper.AlphaVanillaTweaker"

        minecraft_args = clientLauncher._serialize_game_args(minecraft_args_dict)
        return True, minecraft_args

    @staticmethod
    def start_client(client_object: client, interface_starter=None):
        """
        啟動指定的 client。
        回傳格式維持原本：
            (Status: bool, ErrorMessage or None, client_object or None)
        """
        print("clientLauncher > Starting new client.")
        print(f"Name : {client_object.client_name}")
        print("Started Date: {}\n".format(datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')))

        try:
            if interface_starter is not None:
                logger = client_object.start_client_by_interface(interface_starter)
            else:
                logger = client_object.start_client()
            client_object.logger = logger
            return True, None, client_object
        except Exception as e:
            return False, f"Can't start client or client crash at running. ERR: {e}", None

    @staticmethod
    def stop_client(client_object: client):
        """
        嘗試停止指定的 client。
        現在啟動器沒在呼叫，但保留介面，以後要做「從啟動器關遊戲」就能直接用。
        """
        if not client_object.is_alive():
            return False, "Can't stop client. Because it is not alive."

        try:
            client_object.stop()
            return True, None
        except Exception as e:
            return False, f"Can't stop client. ERR: {e}"
