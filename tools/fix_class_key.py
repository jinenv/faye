# tools/fix_class_key.py
import json
import os

# --- CONFIGURATION ---
# This path is relative to your project's root directory (e.g., C:\nyxa)
ESPRITS_JSON_PATH = os.path.join("data", "config", "esprits.json")
# ---------------------

def main():
    """
    Opens the esprits.json file, renames the 'class' key to 'class_name'
    for every entry, and saves the file.
    """
    try:
        with open(ESPRITS_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Could not find esprits.json at '{ESPRITS_JSON_PATH}'")
        return
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse esprits.json. Please check for syntax errors.")
        return

    renamed_count = 0
    for esprit_id, esprit_data in data.items():
        if "class" in esprit_data:
            # Copy the value and delete the old key
            class_value = esprit_data.pop("class")
            esprit_data["class_name"] = class_value
            renamed_count += 1

    if renamed_count > 0:
        # Save the modified data back to the same file
        with open(ESPRITS_JSON_PATH, 'w', encoding='utf-8') as f:
            # indent=2 makes the file readable
            json.dump(data, f, indent=2)
        print(f"Successfully renamed 'class' to 'class_name' for {renamed_count} Esprits.")
    else:
        print("No entries with the key 'class' were found to rename.")


if __name__ == "__main__":
    main()