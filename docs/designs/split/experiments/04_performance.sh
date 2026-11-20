#!/bin/bash
# Experiment 4: Performance and Scalability Testing
# Purpose: Measure time and memory for various dataset sizes
# Expected: Identify performance bottlenecks and scaling characteristics

set -e

EXPERIMENT_DIR="/tmp/datalad-split-exp04"
echo "=== Experiment 4: Performance Testing ==="
echo "Working directory: $EXPERIMENT_DIR"

# Clean up from previous runs
rm -rf "$EXPERIMENT_DIR"
mkdir -p "$EXPERIMENT_DIR"
cd "$EXPERIMENT_DIR"

# Function to create dataset with N files
create_test_dataset() {
    local name=$1
    local num_files=$2
    local file_size_mb=$3

    echo -e "\nCreating dataset '$name' with $num_files files of ${file_size_mb}MB each..."
    datalad create "$name"
    cd "$name"

    mkdir -p data/keep data/discard

    # Create files to keep (will be filtered TO)
    for i in $(seq 1 $((num_files / 2))); do
        dd if=/dev/urandom of="data/keep/file${i}.dat" bs=1M count=$file_size_mb 2>/dev/null
    done

    # Create files to discard (will be filtered OUT)
    for i in $(seq 1 $((num_files / 2))); do
        dd if=/dev/urandom of="data/discard/file${i}.dat" bs=1M count=$file_size_mb 2>/dev/null
    done

    datalad save -m "Add $num_files files"
    cd ..
}

# Function to measure filtering performance
measure_filter_performance() {
    local source_ds=$1
    local filter_path=$2
    local test_name=$3

    echo -e "\n=== Testing: $test_name ==="

    # Clone
    echo "Cloning..."
    /usr/bin/time -v git clone "$source_ds" "filtered-${test_name}" 2>&1 | tee "time-clone-${test_name}.txt"

    cd "filtered-${test_name}"

    # Git-annex filter-branch
    echo "Running git-annex filter-branch..."
    /usr/bin/time -v git annex filter-branch "$filter_path" --include-all-key-information 2>&1 | tee "../time-annex-filter-${test_name}.txt" || echo "git-annex filter-branch failed"

    # Git filter-branch
    echo "Running git filter-branch..."
    /usr/bin/time -v git filter-branch --subdirectory-filter "$filter_path" --prune-empty HEAD 2>&1 | tee "../time-git-filter-${test_name}.txt"

    # Cleanup operations
    echo "Running cleanup operations..."
    /usr/bin/time -v sh -c "git annex dead origin 2>/dev/null; git remote rm origin; git annex forget --force --drop-dead" 2>&1 | tee "../time-cleanup-${test_name}.txt" || echo "Cleanup had issues"

    cd ..

    # Extract metrics
    echo -e "\n--- Performance Metrics ---"
    echo "Test: $test_name"

    # Parse time output (this is GNU time format)
    for phase in clone annex-filter git-filter cleanup; do
        if [ -f "time-${phase}-${test_name}.txt" ]; then
            echo "$phase:"
            grep "Elapsed (wall clock)" "time-${phase}-${test_name}.txt" || true
            grep "Maximum resident set size" "time-${phase}-${test_name}.txt" || true
        fi
    done

    # Repository sizes
    echo -e "\nRepository sizes:"
    echo "  Original: $(du -sh "$source_ds/.git" | cut -f1)"
    echo "  Filtered: $(du -sh "filtered-${test_name}/.git" | cut -f1)"
}

# Test 1: Small dataset (10 files, 1MB each)
echo -e "\n[Test 1] Small Dataset (10 files × 1MB)"
create_test_dataset "small-dataset" 10 1
measure_filter_performance "small-dataset" "data/keep" "small"

# Test 2: Medium dataset (100 files, 2MB each)
echo -e "\n[Test 2] Medium Dataset (100 files × 2MB)"
create_test_dataset "medium-dataset" 100 2
measure_filter_performance "medium-dataset" "data/keep" "medium"

# Test 3: Large dataset (500 files, 5MB each)
echo -e "\n[Test 3] Large Dataset (500 files × 5MB)"
create_test_dataset "large-dataset" 500 5
measure_filter_performance "large-dataset" "data/keep" "large"

# Generate summary report
echo -e "\n=== PERFORMANCE SUMMARY ==="
cat > performance_summary.txt <<'EOF'
# Performance Test Results

## Test Configurations
- Small:  10 files × 1MB = 10MB total
- Medium: 100 files × 2MB = 200MB total
- Large:  500 files × 5MB = 2.5GB total

## Timing Results
EOF

for size in small medium large; do
    echo -e "\n### $size Dataset" >> performance_summary.txt
    for phase in clone annex-filter git-filter cleanup; do
        if [ -f "time-${phase}-${size}.txt" ]; then
            echo "**$phase:**" >> performance_summary.txt
            grep "Elapsed (wall clock)" "time-${phase}-${size}.txt" | sed 's/^/  /' >> performance_summary.txt || true
            grep "Maximum resident set size" "time-${phase}-${size}.txt" | sed 's/^/  /' >> performance_summary.txt || true
        fi
    done
done

cat performance_summary.txt

echo -e "\n=== Experiment 4 Complete ==="
echo "Results available at: $EXPERIMENT_DIR/performance_summary.txt"
echo "Detailed timing logs: time-*.txt"

echo -e "\n=== KEY FINDINGS ==="
echo "1. Identify which operation is the bottleneck (clone, git-annex filter, git filter, cleanup)"
echo "2. Determine memory usage scaling"
echo "3. Calculate time complexity (linear, quadratic?)"
echo "4. Assess feasibility for large datasets (GB to TB scale)"
echo "5. Identify potential optimizations"
