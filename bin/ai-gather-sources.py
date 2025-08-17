import os
import json
import subprocess
import argparse
import time

def gather_project_files(output_filename, verbose=False):
    """
    Gathers all relevant project files from the current directory
    into a JSON object for AI analysis.
    """
    # List of file extensions, files, and directories to ignore for AI analysis
    # This list is manually maintained.
    IGNORE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.bmp',
        '.bin', '.lock', '.log', '.zip', '.tar', '.gz', '.rar',
        '.mp4', '.mov', '.avi', '.mp3', '.wav', '.ogg', '.flac',
        '.min.js', '.min.css', '.map'
    }

    IGNORE_DIRECTORIES = {
        '.git', '__pycache__', 'node_modules', 'venv', 'env', 'dist', 'build', 'bin', 'instance'
    }

    IGNORE_FILES = {
        'LICENSE', 'README.md', 'CONTRIBUTING.md', 'gemini_payload.json', 'ai_backup'
    }

    project_data = {
        "metadata": {
            "project_name": os.path.basename(os.getcwd()),
            "timestamp": time.time(),
            "description": "Project files for AI analysis and modification."
        },
        "files": []
    }

    file_list = []
    for root, dirs, files in os.walk('.'):
        # Remove ignored directories from the traversal
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRECTORIES]

        for file_name in files:
            file_path = os.path.join(root, file_name)
            file_list.append(file_path)

    print(f"Scanning {len(file_list)} files in the project directory...")

    processed_count = 0
    for file_path in file_list:
        processed_count += 1

        # Simple progress indicator
        if verbose and processed_count % 50 == 0:
            print(f"Processed {processed_count}/{len(file_list)} files...")

        # Check for ignored files and extensions
        if os.path.basename(file_path) in IGNORE_FILES:
            continue
        if any(file_path.endswith(ext) for ext in IGNORE_EXTENSIONS):
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            file_entry = {
                "file_path": file_path,
                "status": "unchanged",
                "original_content": content,
                "new_content": content  # Initially, new_content is the same as original
            }
            project_data["files"].append(file_entry)

        except UnicodeDecodeError:
            if verbose:
                print(f"Warning: Skipping binary file '{file_path}'.")
            continue
        except Exception as e:
            if verbose:
                print(f"Warning: Could not read file '{file_path}'. Skipping. Error: {e}")
            continue

    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(project_data, f, indent=2)
    print(f"\nSuccessfully created '{output_filename}' with project data.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gathers project files for AI analysis.")
    parser.add_argument(
        "output_file",
        nargs='?',
        default="gemini_payload.json",
        help="Path to the output JSON file. Defaults to gemini_payload.json."
    )
    parser.add_argument(
        "--timestamp",
        action="store_true",
        help="Appends a timestamp to the output filename (e.g., gemini_payload_1672531200.json)."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enables detailed logging for file processing and warnings."
    )
    args = parser.parse_args()

    output_file = args.output_file
    if args.timestamp:
        base, ext = os.path.splitext(output_file)
        timestamp_str = str(int(time.time()))
        output_file = f"{base}_{timestamp_str}{ext}"

    gather_project_files(output_file, verbose=args.verbose)
