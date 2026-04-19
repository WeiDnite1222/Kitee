import os, json

source_path = str(input("Input source locals file: "))

if not os.path.exists(source_path) or os.path.isdir(source_path):
    print("File not found.")
    exit(1)

with open(source_path, "r", encoding="utf-8") as f:
    source_data = json.load(f)


target_path = str(input("Input target locals file: "))

if not os.path.exists(target_path) or os.path.isdir(target_path):
    print("File not found.")
    exit(1)

with open(target_path, "r", encoding="utf-8") as f:
    target_data = json.load(f)

def check_and_insert_new_keys(source_dict, target_dict, path=""):
    translations = source_dict.get("translations") or {}

    if not isinstance(translations, dict):
        raise ValueError(f"Invalid format for 'translations' at path '{path}'")
    
    for key, value in translations.items():
        if key not in target_dict.get("translations", {}):
            target_dict["translations"][key] = value
    
    return target_dict


print("Filling missing keys...")
new_target_data = check_and_insert_new_keys(source_data, target_data)

with open(target_path, "w", encoding="utf-8") as f:
    json.dump(new_target_data, f, ensure_ascii=False, indent=4)

print("Done.")
