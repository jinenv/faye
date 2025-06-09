# replace_currency.py
import os
import re
from pathlib import Path

# Define replacements
replacements = [
    (r'\bgold\b', 'nyxies'),
    (r'\bdust\b', 'moonglow'),
    (r'\bfragments\b', 'azurite_shards'),
    (r'\bGold\b', 'Nyxies'),
    (r'\bDust\b', 'Moonglow'),
    (r'\bFragments\b', 'Azurite Shards'),
]

# Directories to skip
skip_dirs = {'.git', '__pycache__', '.venv', 'logs', 'alembic/versions'}

# Files to skip
skip_files = {'esprits.json', 'items.json', 'npcs.json'}

# Extensions to process
valid_extensions = {'.py', '.yml', '.yaml', '.txt', '.md'}

def should_process_file(filepath):
    """Check if file should be processed."""
    path = Path(filepath)
    
    # Skip if in excluded directory
    for parent in path.parents:
        if parent.name in skip_dirs:
            return False
    
    # Skip if filename matches exclusion
    if path.name in skip_files:
        return False
    
    # Skip test files
    if path.name.startswith('test_'):
        return False
    
    # Only process valid extensions
    return path.suffix in valid_extensions

def replace_in_file(filepath):
    """Replace currency names in a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)
        
        if content != original:
            # Create backup
            backup_path = f"{filepath}.backup"
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original)
            
            # Write updated content
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ Updated: {filepath}")
            return True
    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}")
    
    return False

# Run the replacer
updated_count = 0
for root, dirs, files in os.walk('.'):
    # Remove excluded directories from traversal
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    
    for file in files:
        filepath = os.path.join(root, file)
        if should_process_file(filepath):
            if replace_in_file(filepath):
                updated_count += 1

print(f"\n✨ Updated {updated_count} files!")
print("💾 Backup files created with .backup extension")
print("🔄 To undo: rename all .backup files back to original names")