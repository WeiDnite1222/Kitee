import re


MOD_LOADER_RULES = {
    "forge": {
        "display_name": "Forge",
        "metadata_url": "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
        "maven_base": "https://maven.minecraftforge.net/",
        "maven": {
            "group_id": "net.minecraftforge",
            "artifact_id": "forge",
            "group_path": "net/minecraftforge/forge",
        },
        "installer": {
            "file_name": "{artifact_id}-{loader_version}-installer.jar",
        },
        "java": {
            "client_version_rules": [
                {
                    "match": {"major": 1, "max_minor": 7},
                    "major_version": "7",
                },
                {
                    "match": {"major": 1, "max_minor": 16},
                    "major_version": "8",
                },
            ],
        },
        "launch": {
            "version_id_candidates": [
                "{base_client_version}-forge-{loader_version_without_base}",
                "forge-{mod_loader_version}",
                "{mod_loader_version}",
            ],
            "client_jar": "net/minecraftforge/forge/{mod_loader_version}/forge-{mod_loader_version}-client.jar",
        },
        "primary_artifact_names": [
            "{artifact_id}-{version}.jar",
            "{artifact_id}-{version}-client.jar",
            "{artifact_id}-{version}-universal.jar",
        ],
    },
    "neoforge": {
        "display_name": "NeoForge",
        "metadata_url": "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml",
        "maven_base": "https://maven.neoforged.net/releases/",
        "maven": {
            "group_id": "net.neoforged",
            "artifact_id": "neoforge",
            "group_path": "net/neoforged/neoforge",
        },
        "installer": {
            "file_name": "{artifact_id}-{loader_version}-installer.jar",
        },
        "java": {
            "client_version_rules": [],
        },
        "launch": {
            "version_id_candidates": [
                "{base_client_version}-neoforge-{mod_loader_version}",
                "neoforge-{mod_loader_version}",
                "{mod_loader_version}",
            ],
            "client_jar": "net/neoforged/neoforge/{mod_loader_version}/neoforge-{mod_loader_version}-client.jar",
        },
        "primary_artifact_names": [
            "{artifact_id}-{version}.jar",
            "{artifact_id}-{version}-client.jar",
            "{artifact_id}-{version}-universal.jar",
        ],
    },
    "fabric": {
        "display_name": "Fabric",
        "maven_base": "https://maven.fabricmc.net/",
        "launch": {
            "main_class": "net.fabricmc.loader.impl.launch.knot.KnotClient",
            "version_id_candidates": [
                "fabric-loader-{mod_loader_version}-{base_client_version}",
            ],
        },
    },
}


LAUNCH_RULES = {
    "classpath_java_compatibility": {
        "ignored_path_contains": [
            "/net/minecraftforge/nashorn-core-compat/",
        ],
    },
}


def normalize_loader_name(loader_name):
    return str(loader_name or "").strip().lower()


def get_loader_rule(loader_name):
    return MOD_LOADER_RULES.get(normalize_loader_name(loader_name), {})


def get_loader_display_name(loader_name):
    return get_loader_rule(loader_name).get("display_name") or str(loader_name or "").title()


def get_loader_maven_rule(loader_name):
    return get_loader_rule(loader_name).get("maven") or {}


def get_loader_maven_base(loader_name, default="https://maven.minecraftforge.net/"):
    return get_loader_rule(loader_name).get("maven_base") or default


def get_loader_metadata_url(loader_name):
    return get_loader_rule(loader_name).get("metadata_url") or ""


def is_primary_loader_maven_parts(loader_name, group_id, artifact_id):
    maven = get_loader_maven_rule(loader_name)
    return group_id == maven.get("group_id") and artifact_id == maven.get("artifact_id")


def is_primary_loader_maven_name(maven_name, loader_name):
    normalized = str(maven_name or "").strip("[]'\"")
    parts = normalized.split(":")
    if len(parts) < 3:
        return False
    # Primary forge library
    return is_primary_loader_maven_parts(loader_name, parts[0], parts[1])


def is_primary_loader_library(library, loader_name):
    if not isinstance(library, dict):
        return False
    return is_primary_loader_maven_name(library.get("name"), loader_name)


def loader_installer_metadata(loader_name, loader_version):
    rule = get_loader_rule(loader_name)
    maven = rule.get("maven") or {}
    artifact_id = maven.get("artifact_id") or normalize_loader_name(loader_name)
    group_path = maven.get("group_path") or ""
    maven_base = get_loader_maven_base(loader_name)
    file_template = (rule.get("installer") or {}).get("file_name") or "{artifact_id}-{loader_version}-installer.jar"
    installer_name = file_template.format(artifact_id=artifact_id, loader_version=loader_version)

    return {
        "artifact": artifact_id,
        "group_path": group_path,
        "maven_base": maven_base,
        "installer_url": "{}{}/{}/{}".format(maven_base, group_path, loader_version, installer_name),
    }


def resolve_mod_loader_java_major(client_version, loader_name):
    rules = (get_loader_rule(loader_name).get("java") or {}).get("client_version_rules") or []
    major, minor = parse_minecraft_major_minor(client_version)
    if major is None or minor is None:
        return ""

    for rule in rules:
        match = rule.get("match") or {}
        if "major" in match and major != match["major"]:
            continue
        if "min_minor" in match and minor < match["min_minor"]:
            continue
        if "max_minor" in match and minor > match["max_minor"]:
            continue
        return str(rule.get("major_version") or "")

    return ""


def parse_minecraft_major_minor(client_version):
    match = re.match(r"^(\d+)\.(\d+)", str(client_version or "").strip())
    if not match:
        return None, None

    try:
        return int(match.group(1)), int(match.group(2))
    except ValueError:
        return None, None


def build_loader_version_id_candidates(loader_name, mod_loader_version, base_client_version):
    rule = get_loader_rule(loader_name)
    templates = (rule.get("launch") or {}).get("version_id_candidates") or []
    loader_version_without_base = str(mod_loader_version or "")
    base_prefix = "{}-".format(base_client_version)
    if loader_version_without_base.startswith(base_prefix):
        loader_version_without_base = loader_version_without_base[len(base_prefix):]

    return [
        template.format(
            base_client_version=base_client_version,
            mod_loader_version=mod_loader_version,
            loader_version_without_base=loader_version_without_base,
        )
        for template in templates
    ]


def get_loader_client_jar_relative_path(loader_name, mod_loader_version):
    template = (get_loader_rule(loader_name).get("launch") or {}).get("client_jar")
    if not template:
        return ""
    return template.format(mod_loader_version=mod_loader_version)


def get_primary_artifact_file_names(loader_name, artifact_id, version):
    templates = get_loader_rule(loader_name).get("primary_artifact_names") or []
    return [
        template.format(artifact_id=artifact_id, version=version)
        for template in templates
    ]


def is_ignored_classpath_java_compatibility_jar(jar_path):
    normalized = str(jar_path or "").replace("\\", "/").lower()
    ignored = LAUNCH_RULES["classpath_java_compatibility"]["ignored_path_contains"]
    return any(pattern in normalized for pattern in ignored)
