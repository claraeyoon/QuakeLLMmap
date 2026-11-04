#!/usr/bin/env bash

# ==============================================================================
# Script: batch_test_pipeline.sh
# Purpose: Iterates through files in an input directory, runs 'test_pipeline.py'
#          on each file, and saves the output to a specified output directory
#          with the file's extension replaced by '.txt'.
# ==============================================================================

set -u

# Display usage instructions
usage() {
    echo "Usage: $0 <input_directory> <output_directory> [output_csv_file]"
    echo ""
    echo "Arguments:"
    echo "  <input_directory>   Directory containing media files to process (e.g. images, PDFs, videos)"
    echo "  <output_directory>  Directory where .txt output files will be saved"
    echo "  [output_csv_file]   Optional CSV file to output (longitude, latitude, mmi_estimation, confidence)"
    echo "                      Default: <output_directory>/records_mmi_gemini_ai.csv"
    echo ""
    echo "Example:"
    echo "  $0 ../data/events/us7000pn9s/test_inbound/ ../data/events/us7000pn9s/out_test/ ../data/events/us7000pn9s/records_mmi_gemini_ai.csv"
    echo ""
    echo "Environment Variables (Optional):"
    echo "  CSV_OUT             Output CSV filename (e.g. CSV_OUT=my_records.csv)"
    echo "  PYTHON              Path to specific python interpreter (e.g. PYTHON=/path/to/python)"
    exit 1
}

# Ensure required arguments are provided
if [ $# -lt 2 ]; then
    usage
fi

INPUT_DIR="$1"
OUTPUT_DIR="$2"
CSV_FILE="${3:-${CSV_OUT:-$OUTPUT_DIR/records_mmi_gemini_ai.csv}}"

# Validate input directory
if [ ! -d "$INPUT_DIR" ]; then
    echo "❌ Error: Input directory '$INPUT_DIR' does not exist."
    exit 1
fi

# Resolve absolute paths before changing directories
ABS_INPUT_DIR="$(cd "$INPUT_DIR" && pwd)"

# Ensure output directory exists and resolve its absolute path
mkdir -p "$OUTPUT_DIR" || {
    echo "❌ Error: Failed to create output directory '$OUTPUT_DIR'."
    exit 1
}
ABS_OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

# Ensure CSV directory exists and resolve absolute CSV file path
CSV_DIR="$(dirname "$CSV_FILE")"
mkdir -p "$CSV_DIR" 2>/dev/null || true
ABS_CSV_FILE="$(cd "$CSV_DIR" 2>/dev/null && pwd)/$(basename "$CSV_FILE")"

# Switch to the directory containing this script (QuakemapMyanmar/server)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Verify test_pipeline.py exists
if [ ! -f "test_pipeline.py" ]; then
    echo "❌ Error: 'test_pipeline.py' not found in '$SCRIPT_DIR'."
    exit 1
fi

# Determine Python executable
if [ -n "${PYTHON:-}" ]; then
    PYTHON_CMD="$PYTHON"
elif [ -n "${VIRTUAL_ENV:-}" ] && command -v python &>/dev/null; then
    PYTHON_CMD="python"
elif [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

# Verify Python command
if ! command -v "$PYTHON_CMD" &>/dev/null && [ ! -x "$PYTHON_CMD" ]; then
    echo "❌ Error: Python interpreter '$PYTHON_CMD' not found."
    echo "   Please activate your virtual environment: source .venv/bin/activate"
    exit 1
fi

# Collect all non-hidden regular files from input directory
files=()
for f in "$ABS_INPUT_DIR"/*; do
    [ -f "$f" ] || continue
    fname="$(basename "$f")"
    # Skip hidden files (like .DS_Store)
    [[ "$fname" == .* ]] && continue
    files+=("$f")
done

total_files=${#files[@]}
if [ "$total_files" -eq 0 ]; then
    echo "⚠️  No files found to process in '$ABS_INPUT_DIR'."
    exit 0
fi

echo "============================================================"
echo "🚀 Starting Batch Pipeline Processing"
echo "  Input directory:  $ABS_INPUT_DIR"
echo "  Output directory: $ABS_OUTPUT_DIR"
echo "  Output CSV file:  $ABS_CSV_FILE"
echo "  Total files:      $total_files"
echo "  Python runtime:   $PYTHON_CMD"
echo "============================================================"

current=1
success_count=0
failed_count=0

for file_path in "${files[@]}"; do
    filename="$(basename "$file_path")"
    stem="${filename%.*}"
    out_file="$ABS_OUTPUT_DIR/${stem}.txt"

    echo ""
    echo "------------------------------------------------------------"
    echo "[$current/$total_files] Processing: $filename"
    echo "  Input:  $file_path"
    echo "  Output: $out_file"

    start_time=$(date +%s)

    # Execute test_pipeline.py and append results to CSV and stdout text file
    "$PYTHON_CMD" test_pipeline.py "$file_path" "$ABS_CSV_FILE" > "$out_file" 2>&1
    exit_code=$?

    end_time=$(date +%s)
    elapsed=$(( end_time - start_time ))

    if [ $exit_code -eq 0 ]; then
        mmi_line=$(grep -m 1 "🎯 MMI Estimation:" "$out_file" 2>/dev/null || true)
        conf_line=$(grep -m 1 "🎯 Confidence:" "$out_file" 2>/dev/null || true)
        loc_line=$(grep -m 1 "📍 Location:" "$out_file" 2>/dev/null || true)
        if [ -n "$mmi_line" ]; then
            echo "  ✅ Done in ${elapsed}s -> $mmi_line ${conf_line:+($conf_line)}"
            if [ -n "$loc_line" ]; then
                echo "     $loc_line"
            fi
        else
            echo "  ✅ Done in ${elapsed}s"
        fi
        ((success_count++))
    else
        echo "  ❌ Failed with exit code $exit_code in ${elapsed}s"
        echo "     See '$out_file' for error details."
        ((failed_count++))
    fi

    ((current++))
done

echo ""
echo "============================================================"
echo "🏁 Batch processing finished!"
echo "  Total processed:  $total_files"
echo "  Successful:       $success_count"
echo "  Failed:           $failed_count"
echo "  Text logs saved:  $ABS_OUTPUT_DIR"
echo "  CSV summary file: $ABS_CSV_FILE"
echo "============================================================"
