#!/bin/bash

# A script to find all text files in a directory and its subdirectories,
# and concatenate their content into a single output file with clear separators.
# The format is designed to be easily parsed by an AI model.
# This updated version now respects rules from a .gitignore file, and is more efficient.

# --- SCRIPT USAGE AND CONFIGURATION ---
#
# Usage: ./aggregate_text_files.sh [directory] [output_file]
#
# If no arguments are provided, the script will use the current directory
# and a default output file name.

# Set the starting directory. Defaults to the current directory if not provided.
START_DIR="${1:-.}"

# Set the output file path. Defaults to "aggregated_text_content.txt" if not provided.
OUTPUT_FILE="${2:-aggregated_text_content.txt}"

# A unique separator string to clearly mark the beginning of each file's content.
# This format (e.g., "--- FILE: /path/to/file.txt ---") is ideal for AI consumption.
SEPARATOR_START="### --- START OF FILE: "
SEPARATOR_END="### --- END OF FILE: "

# An array to hold the patterns from .gitignore
declare -a IGNORE_PATTERNS

# --- SCRIPT LOGIC ---

# Check if the starting directory exists.
if [ ! -d "$START_DIR" ]; then
    echo "Error: Directory '$START_DIR' not found."
    exit 1
fi

# Check for a .gitignore file and read patterns if it exists
GITIGNORE_FILE="$START_DIR/.gitignore"
if [ -f "$GITIGNORE_FILE" ]; then
    echo "Found .gitignore file. Reading patterns..."
    # Read each line, skipping comments (#) and empty lines
    while read -r line || [[ -n "$line" ]]; do
        line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//') # Trim leading/trailing whitespace
        if [[ ! -z "$line" && "$line" != \#* ]]; then
            IGNORE_PATTERNS+=("$line")
        fi
    done < "$GITIGNORE_FILE"
fi

# Clear the output file before starting, or create a new one.
> "$OUTPUT_FILE"

echo "Scanning for text files in '$START_DIR'..."
echo "Aggregating content into '$OUTPUT_FILE'..."

# Build the dynamic 'find' command with exclusion rules from .gitignore
# We use a combined approach with -path for directories and -name for files.
FIND_COMMAND="find \"$START_DIR\""
if [ ${#IGNORE_PATTERNS[@]} -gt 0 ]; then
    # Start the exclusion group
    FIND_COMMAND+=" -path \"$OUTPUT_FILE\"" # Always exclude the output file
    # Build a list of exclusion expressions for 'find'
    for pattern in "${IGNORE_PATTERNS[@]}"; do
        # Use -o (OR) to combine multiple exclusion patterns
        # The -prune action tells find not to descend into directories that match
        # We also use '!' to negate the match for files
        FIND_COMMAND+=" -o -path \"$START_DIR/$pattern\" -prune"
    done
    # Add a final -o to separate the exclusion rules from the primary action
    FIND_COMMAND+=" -o"
fi

# Add the final actions for 'find': find only files, not directories, and print them safely
FIND_COMMAND+=" -type f -print0"

# Execute the dynamic 'find' command and pipe the results to the while loop
eval "$FIND_COMMAND" | while read -d '' -r file; do
    # Check if the file is a text file using its MIME type
    if [[ $(file --mime-type -b "$file") == "text/plain" ]]; then
        # Append the start separator line with the full path to the output file
        echo "${SEPARATOR_START}$file ---" >> "$OUTPUT_FILE"
        
        # Append the content of the file
        cat "$file" >> "$OUTPUT_FILE"
        
        # Append the end separator line
        echo "${SEPARATOR_END}$file ---" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
        
        echo "  - Added: $file"
    fi
done

echo "Done! All text files have been aggregated into '$OUTPUT_FILE'."

