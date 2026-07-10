#!/bin/bash

# Usage: bash execution/resubmit_failed_no_subgroups.sh <sbatch_file>
# Example: bash execution/resubmit_failed_no_subgroups.sh execution/submit_twist_L_1.0_tuned_self.sbatch

SBATCH_FILE=$1
if [ -z "$SBATCH_FILE" ] || [ ! -f "$SBATCH_FILE" ]; then
    echo "Usage: $0 <sbatch_file>"
    exit 1
fi

# Create a temporary resubmit sbatch file name
RESUBMIT_FILE="${SBATCH_FILE%.sbatch}_resubmit.sbatch"

# Copy and modify the file:
# 1. Change time limit to 04:00:00 (more than enough for sequential mode, typically 30-50 mins)
# 2. Add --no-subgroups to the python run command to bypass split-communicator MPI overhead/deadlock
# 3. Change log output names to avoid overwriting original logs
sed -e 's/#SBATCH --time=.*/#SBATCH --time=04:00:00/' \
    -e 's/_%A_%a.out/_resubmit_%A_%a.out/' \
    -e 's/_%A_%a.err/_resubmit_%A_%a.err/' \
    -e 's/run_meep_simulation.py \\/run_meep_simulation.py --no-subgroups \\/' \
    -e 's/run_meep_simulation.py/run_meep_simulation.py --no-subgroups/' \
    "$SBATCH_FILE" > "$RESUBMIT_FILE"

echo "Created resubmit script: $RESUBMIT_FILE"
echo "Submitting to Slurm..."
JOB_ID=$(sbatch --parsable "$RESUBMIT_FILE")
echo "Submitted resubmit job. Job ID: $JOB_ID"
