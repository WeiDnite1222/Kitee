import os

from .instance import _parse_bool, _strip_config_value, LEGACY_INSTANCE_PROFILE_PATH

def _parse_legacy_key_value_file(file_path, defaults, bool_keys):
    data = defaults.copy()
    try:
        with open(file_path, "r") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.split("#", 1)[0].strip()

                if key not in data:
                    continue

                if key in bool_keys:
                    data[key] = _parse_bool(value)
                else:
                    data[key] = _strip_config_value(value)
        return True, data
    except Exception as e:
        raise Exception("Failed to parse legacy key value file: {}\n"
                        "Exception: {}".format(file_path, e))


def get_legacy_instance_profile_path(instance_dir):
    return os.path.join(instance_dir, LEGACY_INSTANCE_PROFILE_PATH)