"""A deliberately hostile agent used ONLY by the Tier A adapter tests (D-010, section 7).

It reads one JSON object from stdin; ``mode`` picks the misbehaviour. It is never imported and
never run by AgentProof itself, only by the test-suite through the adapter under test.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import time


def main() -> None:
    if "--no-stdin" in sys.argv:
        time.sleep(0.2)  # never reads the (possibly huge) input; must not deadlock the parent
        print(json.dumps({"status": "ok"}))
        return
    if "--no-stdin-hang" in sys.argv:
        time.sleep(600)  # never reads stdin and never exits: a blocking writer would hang
        return
    request = json.loads(sys.stdin.read() or "{}")
    mode = request.get("mode", "ok")
    out = sys.stdout

    if mode == "ok":
        print(json.dumps({"echo": request, "status": "ok"}))
    elif mode == "loop":
        while True:
            pass
    elif mode == "sleep":
        time.sleep(600)
    elif mode == "ignore_sigterm":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(600)
    elif mode == "term_handler":
        def on_term(_signum, _frame):
            with open(request["marker"], "w") as handle:
                handle.write("got SIGTERM")
            os._exit(0)

        signal.signal(signal.SIGTERM, on_term)
        time.sleep(600)
    elif mode == "fork_children":
        pids = [subprocess.Popen(["sleep", "600"]).pid for _ in range(int(request.get("n", 5)))]
        with open(request["pid_file"], "w") as handle:
            handle.write("\n".join(map(str, pids)))
        time.sleep(600)
    elif mode == "orphan_then_exit":
        # Leaves a child running in the same process group and exits normally with valid JSON.
        child = subprocess.Popen(["sleep", "600"])
        with open(request["pid_file"], "w") as handle:
            handle.write(str(child.pid))
        print(json.dumps({"status": "ok"}))
    elif mode == "stdout_flood":
        chunk = "x" * 65536
        while True:
            out.write(chunk)
            out.flush()
    elif mode == "stderr_flood":
        chunk = "e" * 65536
        while True:
            sys.stderr.write(chunk)
            sys.stderr.flush()
    elif mode == "endless_no_newline":
        while True:
            out.write("a")
            out.flush()
    elif mode == "trickle":
        while True:
            out.write(" ")
            out.flush()
            time.sleep(0.05)
    elif mode == "invalid_utf8":
        sys.stdout.buffer.write(b'{"a": "\xff\xfe"}')
    elif mode == "non_json":
        print("hello, this is not json")
    elif mode == "empty":
        pass
    elif mode == "json_array":
        print("[1, 2, 3]")
    elif mode == "json_scalar":
        print("42")
    elif mode == "deep_json":
        depth = int(request.get("depth", 5000))
        print("[" * depth + "]" * depth)
    elif mode == "deep_object":
        depth = int(request.get("depth", 200))
        print('{"a":' * depth + "1" + "}" * depth)
    elif mode == "nan":
        print('{"x": NaN}')
    elif mode == "huge_int":
        print('{"x": ' + "9" * 5000 + "}")
    elif mode == "huge_string":
        print(json.dumps({"s": "A" * int(request.get("size", 2_000_000))}))
    elif mode == "exit_nonzero":
        print(json.dumps({"status": "looks fine"}))
        sys.exit(3)
    elif mode == "crash":
        os.kill(os.getpid(), signal.SIGSEGV)
    elif mode == "print_env":
        print(json.dumps({"env": dict(os.environ)}))
    elif mode == "info":
        print(json.dumps({
            "cwd": os.getcwd(),
            "stdin_tty": sys.stdin.isatty(),
            "pgid_is_own": os.getpgid(0) == os.getpid(),
            "argv": sys.argv,
        }))
    elif mode == "limits":
        with open("/proc/self/limits") as handle:
            print(json.dumps({"limits": handle.read()}))
    elif mode == "alloc":
        try:
            blob = bytearray(int(request.get("bytes", 1 << 30)))
            print(json.dumps({"alloc": "succeeded", "n": len(blob)}))
        except MemoryError:
            print(json.dumps({"alloc": "denied"}))
    elif mode == "write_big_file":
        try:
            with open("big.bin", "wb") as handle:
                handle.write(b"\0" * int(request.get("bytes", 64 * 1024 * 1024)))
                handle.flush()
            print(json.dumps({"write": "succeeded"}))
        except OSError:
            print(json.dumps({"write": "denied"}))
    elif mode == "write_outside":
        # Tier A does NOT block this (documented); the test asserts exactly that.
        with open(request["path"], "w") as handle:
            handle.write("written by the agent")
        print(json.dumps({"status": "wrote"}))
    elif mode == "symlink_trick":
        # Plant symlinks to a directory outside the temp cwd; cleanup must not follow them.
        os.symlink(request["victim"], "link_to_victim")
        os.mkdir("sub")
        os.symlink(request["victim"], "sub/link2")
        os.chmod("sub", 0o000)  # makes naive cleanup fail
        print(json.dumps({"status": "planted"}))
    elif mode == "read_home":
        # Tier A does NOT block this (documented); the test asserts exactly that.
        print(json.dumps({"can_read": os.path.exists(request["path"])}))
    elif mode == "network":
        # Tier A does NOT block this (documented); the test asserts exactly that.
        try:
            sock = socket.create_connection(("127.0.0.1", int(request["port"])), timeout=2)
            sock.close()
            print(json.dumps({"connected": True}))
        except OSError:
            print(json.dumps({"connected": False}))
    else:
        print(json.dumps({"error": "unknown mode"}))


if __name__ == "__main__":
    main()
