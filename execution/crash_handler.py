import os
import sys
import json
import time
import signal
import traceback
import subprocess
import datetime

CRASH_LOG_DIR = ".tmp/crash_logs"
MASTER_CRASH_FILE = ".tmp/master_crash_report.json"

def ensure_dirs():
    os.makedirs(CRASH_LOG_DIR, exist_ok=True)
    os.makedirs(".tmp", exist_ok=True)

def log_crash_and_push(task_id, error_type, details, config_info=None):
    try:
        ensure_dirs()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        hostname = os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "unknown_host")
        
        crash_filename = f"crash_task_{task_id}_{timestamp}.log"
        crash_filepath = os.path.join(CRASH_LOG_DIR, crash_filename)
        
        crash_data = {
            "timestamp": timestamp,
            "task_id": task_id,
            "hostname": hostname,
            "error_type": str(error_type),
            "details": details,
            "config": config_info or {},
            "env_slurm_job_id": os.environ.get("SLURM_JOB_ID", "N/A"),
            "env_slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID", "N/A")
        }
        
        # 1. Write human-readable crash log file
        with open(crash_filepath, "w") as f:
            f.write("==================================================\n")
            f.write(f"CRASH REPORT - TASK {task_id} ON {hostname}\n")
            f.write("==================================================\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Error Type: {error_type}\n")
            f.write(f"Slurm Job ID: {os.environ.get('SLURM_JOB_ID', 'N/A')}\n")
            f.write(f"Slurm Array Task ID: {os.environ.get('SLURM_ARRAY_TASK_ID', 'N/A')}\n")
            f.write("--------------------------------------------------\n")
            f.write("DETAILS / TRACEBACK:\n")
            f.write(f"{details}\n")
            f.write("--------------------------------------------------\n")
            f.write("CONFIGURATION:\n")
            f.write(json.dumps(config_info or {}, indent=4))
            f.write("\n==================================================\n")
            
        print(f"\n[CRASH HANDLER] Logged crash details to '{crash_filepath}'.")

        # 2. Append to master JSON crash report
        master_data = []
        if os.path.exists(MASTER_CRASH_FILE):
            try:
                with open(MASTER_CRASH_FILE, "r") as f:
                    master_data = json.load(f)
            except Exception:
                master_data = []
                
        master_data.append(crash_data)
        with open(MASTER_CRASH_FILE, "w") as f:
            json.dump(master_data, f, indent=4)

        # 3. Auto-commit and push crash log to GitHub
        print(f"[CRASH HANDLER] Auto-syncing crash report to GitHub...")
        subprocess.run(["git", "add", crash_filepath, MASTER_CRASH_FILE], check=False)
        msg = f"CRASH LOG: Task {task_id} failed on {hostname} ({error_type})"
        subprocess.run(["git", "commit", "-m", msg], check=False)
        subprocess.run(["git", "push"], check=False)
        print(f"[CRASH HANDLER] Successfully pushed crash log to GitHub!")
        
    except Exception as e:
        print(f"[CRASH HANDLER ERROR] Failed to log/push crash: {e}")

def setup_global_exception_handler(task_id, config_info=None):
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(f"\nCRITICAL UNCAUGHT EXCEPTION IN TASK {task_id}:\n{err_msg}")
        log_crash_and_push(task_id, exc_type.__name__, err_msg, config_info)
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception

    def handle_signal(sig, frame):
        sig_name = signal.Signals(sig).name if hasattr(signal, "Signals") else f"Signal_{sig}"
        details = f"Process terminated by signal {sig_name} ({sig})"
        print(f"\nCRITICAL SIGNAL RECEIVED IN TASK {task_id}: {sig_name}")
        log_crash_and_push(task_id, sig_name, details, config_info)
        sys.exit(128 + sig)

    # Register termination signals (SIGTERM, SIGINT, SIGABRT)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGABRT):
        try:
            signal.signal(sig, handle_signal)
        except Exception:
            pass

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        t_id = sys.argv[1]
        e_type = sys.argv[2]
        det = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "Execution failure reported by wrapper script."
        log_crash_and_push(t_id, e_type, det)
