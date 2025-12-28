import os
import glob
import yaml
import json
import time
import io
from contextlib import redirect_stdout
from tools import tools
import tests.debug.tool_calls as tool_log
tools.tool_log = tool_log
# import debug.tool_calls as tool_log

# Make project root importable
import sys
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

# Import ATOM runtime
from core import main   # we will access main.cli AFTER initialize() #UNCOMMENT THIS BEFORE RUNNING TESTS

VERBOSE = False      # set True for super chatty logging
SAVE_REPORT = True   # saves report to disk

REPORT_FOLDER = "tests/reports"
os.makedirs(REPORT_FOLDER, exist_ok=True)

# ===============================
# Atom Runner (Single Turn)
# ===============================
def atom_run_single_turn(user_text: str):
    """
    Runs ONE turn of ATOM, captures printed logs,
    returns (reply_text, logs_list)
    """

    buffer = io.StringIO()
    reply = ""

    try:
        # Capture ALL prints happening inside ATOM
        with redirect_stdout(buffer):
            for chunk in main.cli.stream_to_console_basic(user_text):
                reply += chunk

    except Exception as e:
        pass

    # Get all printed runtime logs
    printed_output = buffer.getvalue().splitlines()
    return reply, printed_output

# ===============================
# Scenario Helpers
# ===============================
def load_scenario(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def run_atom_conversation(steps):
    from tests.debug.tool_calls import TOOL_CALL_LOG
    TOOL_CALL_LOG.clear()

    logs = []
    reply = None

    history = []
    all_logs = []
    per_step_tool_logs = []

    reply = None

    for step in steps:
        if "user" in step:
            user_msg = step["user"]
            history.append({"role": "user", "content": user_msg})

            reply, logs = atom_run_single_turn(user_msg)

            all_logs.extend(logs)
            called = [t["tool"] for t in tool_log.TOOL_CALL_LOG]
            per_step_tool_logs.append(called)

    return reply, all_logs, per_step_tool_logs

# ===============================
# Assertions
# ===============================

def assert_expectations(expect, logs):
    if not expect:
        return

    # =====================
    # WAIT FOR TOOL CALLS
    # =====================
    if "tools_called_contain" in expect:
        deadline = time.time() + 3.0   # wait up to 3 sec for async tools
        required = expect["tools_called_contain"] or []

        while time.time() < deadline:
            called = [t["tool"] for t in tool_log.TOOL_CALL_LOG]
            if all(r in called for r in required):
                break
            time.sleep(0.1)

    # =====================
    # ERROR CHECK
    # =====================
    if expect.get("no_errors", False):
        for l in logs:
            if (
                "ERROR" in l
                or "Traceback" in l
                or "Exception" in l
            ):
                raise AssertionError(f"Unexpected error log found:\n{l}")

    # =====================
    # LOG TEXT ASSERTIONS
    # =====================
    logs_expected = expect.get("logs_contain") or []
    for key in logs_expected:
        if not any(key in l for l in logs):
            raise AssertionError(
                f"Expected log entry '{key}' not found.\nLogs:\n" +
                "\n".join(logs)
            )

    # =====================
    # TOOL ASSERTIONS
    # =====================
    if "tools_called_contain" in expect:
        called = [t["tool"] for t in tool_log.TOOL_CALL_LOG]

        for required in expect["tools_called_contain"]:
            if required not in called:
                raise AssertionError(
                    f"Expected tool '{required}' to be called.\n"
                    f"Tools actually called: {called}"
                )

def format_logs(logs, max_lines=25):
    if not logs:
        return "  (no logs captured)"

    if len(logs) <= max_lines:
        return "\n".join("  " + l for l in logs)

    head = "\n".join("  " + l for l in logs[:max_lines//2])
    tail = "\n".join("  " + l for l in logs[-max_lines//2:])
    return f"{head}\n  ... ({len(logs)-max_lines} more lines) ...\n{tail}"


def save_report(results, total_time):
    if not SAVE_REPORT:
        return

    ts = time.strftime("%Y-%m-%d_%H-%M-%S")
    summary_path = os.path.join(REPORT_FOLDER, f"report_{ts}.txt")
    json_path = os.path.join(REPORT_FOLDER, f"report_{ts}.json")

    failed = [r for r in results if r["failed"]]
    passed = [r for r in results if not r["failed"]]

    # ---------- TXT REPORT ----------
    with open(summary_path, "w") as f:
        f.write("ATOM Test Report\n")
        f.write("====================================\n")
        f.write(f"Total tests: {len(results)}\n")
        f.write(f"Passed     : {len(passed)}\n")
        f.write(f"Failed     : {len(failed)}\n")
        f.write(f"Duration   : {total_time}s\n")
        f.write("====================================\n\n")

        if failed:
            f.write("FAILURE DETAILS\n\n")
            for r in failed:
                f.write(f"❌ {r['name']}\n")
                f.write(f"Reason     : {r['reason']}\n")
                f.write(f"Duration   : {r['duration']}s\n")

                f.write("\nTools Called:\n")
                if r["tools"]:
                    for t in r["tools"]:
                        f.write(f"  • {t}\n")
                else:
                    f.write("  (no tools called)\n")

                f.write("\nLogs:\n")
                f.write(format_logs(r["logs"]) + "\n")
                f.write("\n" + ("-" * 60) + "\n\n")

        else:
            f.write("ALL TESTS PASSED CLEANLY 🎉\n")

    # ---------- JSON REPORT ----------
    with open(json_path, "w") as f:
        json.dump({
            "summary": {
                "total": len(results),
                "passed": len(passed),
                "failed": len(failed),
                "duration": total_time
            },
            "results": results
        }, f, indent=2)

    # also write latest aliases
    latest_txt = os.path.join(REPORT_FOLDER, "latest_report.txt")
    latest_json = os.path.join(REPORT_FOLDER, "latest_report.json")
    os.system(f"cp '{summary_path}' '{latest_txt}'")
    os.system(f"cp '{json_path}' '{latest_json}'")

# ===============================
# Main Test Runner
# ===============================

def run_all_tests():
    print("Booting ATOM once...")
    main.initialize()

    scenario_files = glob.glob(
        os.path.join(ROOT, "tests", "scenarios", "*.yaml")
        # os.path.join(ROOT, "tests", "other_scenarios", "*.yaml")
    )

    if not scenario_files:
        print("⚠️ No scenarios found in tests/scenarios/")
        # print("⚠️ No scenarios found in tests/other_scenarios/")
        return

    results = []
    total_start = time.time()

    for path in scenario_files:
        scenario = load_scenario(path)
        name = scenario["name"]

        print(f"\n▶ Running: {name}")
        tool_log.TOOL_CALL_LOG.clear()

        start = time.time()
        failed = False
        fail_reason = ""
        logs = []
        called_tools = []

        try:
            _, logs = run_atom_conversation(scenario["steps"])
            called_tools = [t["tool"] for t in tool_log.TOOL_CALL_LOG]

            last = scenario["steps"][-1]
            assert_expectations(last.get("expect"), logs)

            duration = round(time.time() - start, 2)
            print(f"✅ PASS ({duration}s)")

            if VERBOSE:
                print("Tools:", called_tools)
                print("Logs:")
                print(format_logs(logs))

        except Exception as e:
            failed = True
            duration = round(time.time() - start, 2)
            fail_reason = str(e)

            print(f"❌ FAIL ({duration}s)")
            print(e)

            if VERBOSE:
                print("\nTools Called:")
                print(called_tools or "(none)")
                print("\nLogs:")
                print(format_logs(logs))

        results.append({
            "name": name,
            "failed": failed,
            "reason": fail_reason,
            "duration": duration,
            "tools": called_tools,
            "logs": logs
        })

    total_time = round(time.time() - total_start, 2)

    # ---------- FINAL SUMMARY ----------
    failed = [r for r in results if r["failed"]]
    passed = [r for r in results if not r["failed"]]

    print("\n\n====================================")
    print("            TEST REPORT")
    print("====================================")
    print(f"Total tests: {len(results)}")
    print(f"Passed     : {len(passed)}")
    print(f"Failed     : {len(failed)}")
    print(f"Duration   : {total_time}s")
    print("====================================\n")

    if failed and not VERBOSE:
        print("🔍 FAILURE DETAILS:")
        for r in failed:
            print(f"\n❌ {r['name']}")
            print(f"Reason   : {r['reason']}")
            print(f"Tools    : {r['tools'] or '(none)'}")
            print("Logs:")
            print(format_logs(r["logs"]))
            print("\n" + ("-" * 50))

        # try:
        #     main.graceful_exit()
        # except Exception as e:
        #     print(f"[WARN] Failed to unload model: {e}")

    elif not failed:
        print("🎉 ALL TESTS PASSED CLEANLY — BEAUTIFUL")
        # try:
        #     main.graceful_exit()
        # except Exception as e:
        #     print(f"[WARN] Failed to unload model: {e}")

    save_report(results, total_time)
    print("\n📁 Report saved in tests/reports/")

if __name__ == "__main__":
    run_all_tests()
