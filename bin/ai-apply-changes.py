import os
import json
import shutil
import difflib
import argparse

def create_backup(file_path, backup_dir):
    """Creates a backup of a file before modifying or deleting it."""
    try:
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(file_path, os.path.join(backup_dir, os.path.basename(file_path)))
    except Exception as e:
        print(f"Warning: Could not create backup for '{file_path}'. Error: {e}")

def show_diff(original_content, new_content, file_path):
    """Prints a side-by-side diff of the file changes."""
    diff = difflib.unified_diff(
        original_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f'a/{file_path}',
        tofile=f'b/{file_path}',
    )
    for line in diff:
        print(line.rstrip())

def apply_changes_from_json(json_file, dry_run=False, backup_enabled=True):
    """
    Reads a JSON file with project changes and applies them to the local
    filesystem, providing a summary of the actions taken.
    """
    if not os.path.exists(json_file):
        print(f"Error: JSON file not found at '{json_file}'.")
        return

    with open(json_file, 'r', encoding='utf-8') as f:
        try:
            changes = json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Could not parse '{json_file}'. Is it valid JSON?")
            return

    # Check for the expected structure
    if "files" not in changes or not isinstance(changes["files"], list):
        print("Error: JSON structure is not as expected. Missing 'files' key.")
        return

    print("--- Changes to be applied ---")
    
    actions_to_perform = []
    
    for file_entry in changes["files"]:
        file_path = file_entry.get("file_path")
        status = file_entry.get("status")
        original_content = file_entry.get("original_content", "")
        new_content = file_entry.get("new_content", "")

        if not file_path or not status:
            print("Warning: Skipping malformed file entry.")
            continue
        
        # We only care about files with an active status
        if status in ["modified", "new", "deleted"]:
            actions_to_perform.append((file_path, status, original_content, new_content))

    if not actions_to_perform:
        print("No changes to apply. All files are 'unchanged' or malformed.")
        return

    for file_path, status, original_content, new_content in actions_to_perform:
        if status == "modified":
            print(f"  - MODIFIED: {file_path}")
            # Show a diff for modified files
            show_diff(original_content, new_content, file_path)

        elif status == "new":
            print(f"  - CREATED: {file_path}")

        elif status == "deleted":
            print(f"  - DELETED: {file_path}")

    print("\n--- Summary ---")
    print(f"Files to be Modified: {sum(1 for _, s, _, _ in actions_to_perform if s == 'modified')}")
    print(f"Files to be Created: {sum(1 for _, s, _, _ in actions_to_perform if s == 'new')}")
    print(f"Files to be Deleted: {sum(1 for _, s, _, _ in actions_to_perform if s == 'deleted')}")

    if dry_run:
        print("\n--- Dry Run Complete ---")
        print("No files were changed. To apply these changes, run without the '--dry-run' flag.")
        return

    # Prompt for confirmation before applying changes
    user_input = input("\nDo you want to apply these changes to your project? (y/N): ")
    if user_input.lower() != 'y':
        print("Changes aborted by user.")
        return
    
    if backup_enabled:
        backup_dir = f"ai_backup_{changes['metadata']['timestamp']}"
        print(f"Creating a backup of affected files in '{backup_dir}'...")

    # Apply the changes
    for file_path, status, original_content, new_content in actions_to_perform:
        if status == "modified":
            if os.path.exists(file_path):
                if backup_enabled:
                    create_backup(file_path, backup_dir)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Applied modification to '{file_path}'.")
            else:
                print(f"Warning: File to be modified not found: '{file_path}'. Skipping.")
                
        elif status == "new":
            if not os.path.exists(file_path):
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Created new file '{file_path}'.")
            else:
                print(f"Warning: File to be created already exists: '{file_path}'. Skipping.")
        
        elif status == "deleted":
            if os.path.exists(file_path):
                if backup_enabled:
                    create_backup(file_path, backup_dir)
                os.remove(file_path)
                print(f"Deleted file '{file_path}'.")
            else:
                print(f"Warning: File to be deleted not found: '{file_path}'. Skipping.")

    print("\nAll requested changes have been applied.")
    print("Files with 'unchanged' status were not altered.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Applies a JSON manifest of project changes to the filesystem.")
    parser.add_argument("json_file", help="Path to the JSON file containing the changes.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them.")
    parser.add_argument("--no-backup", action="store_true", help="Disable the automatic backup of modified files.")
    
    args = parser.parse_args()

    apply_changes_from_json(args.json_file, dry_run=args.dry_run, backup_enabled=not args.no_backup)

