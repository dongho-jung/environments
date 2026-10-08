#!/usr/bin/env python3
"""Exercise the real collector entry point without touching the live GPU/journal."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "gpu-xid-capture"


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="gpu-xid-test-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.output = self.root / "captures"
        self.proc = self.root / "nvidia"
        self.gpu = self.proc / "gpus" / "0000:01:00.0"
        self.gpu.mkdir(parents=True)
        (self.proc / "params").write_text("EnableGpuFirmwareLogs: 1\n")
        (self.gpu / "information").write_text("Model: fixture GPU\n")
        (self.gpu / "power").write_text("fixture power state\n")
        self.runtime = self.root / "run"
        log = self.runtime / "1000/hypr/test-session/hyprland.log"
        log.parent.mkdir(parents=True)
        log.write_text("volatile compositor evidence\n")
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        GPU_XID_OUT_ROOT=str(self.output),
                        GPU_XID_PROC_ROOT=str(self.proc),
                        GPU_XID_RUNTIME_ROOT=str(self.runtime),
                        FIXTURE_ROOT=str(self.root))
        self.env.pop("JOURNAL_STREAM", None)
        self.env.pop("GPU_XID_DEBOUNCE", None)
        self.env.pop("GPU_XID_KEEP", None)
        self.env.pop("HANG_POWER", None)
        self.env.pop("HANG_REPORT", None)
        self.stub("logger", 'printf "%s\\n" "$*" >> "$FIXTURE_ROOT/events"\n')
        self.stub("sync", 'printf "sync\\n" >> "$FIXTURE_ROOT/events"\n')
        self.stub("journalctl", '''
case " $* " in
    *" -f "*)
        touch "$FIXTURE_ROOT/watching"
        exec /usr/bin/cat "$FIXTURE_ROOT/journal-stream" ;;
esac
printf 'fixture journal evidence\\n'
''')
        for name in ("coredumpctl", "lspci", "sensors", "nvidia-smi"):
            self.stub(name, f"printf '{name} evidence\\n'\n")
        self.stub("nvidia-bug-report.sh", '''
if [ "${HANG_REPORT:-0}" = 1 ]; then
    printf '%s\\n' "$$" > "$FIXTURE_ROOT/report-pid"
    exec sleep 60
fi
printf 'fixture report complete\\n'
''')
        # Both the old cp and the fixed cat must encounter the same blocked
        # procfs read. Ignore TERM to exercise timeout's SIGKILL escalation.
        for name in ("cat", "cp"):
            self.stub(name, f'''
case "$*" in
    *"$GPU_XID_PROC_ROOT/gpus/0000:01:00.0/power"*)
        if [ "${{HANG_POWER:-0}}" = 1 ]; then
            printf '%s\\n' "$$" > "$FIXTURE_ROOT/power-pid"
            trap '' TERM
            exec sleep 60
        fi ;;
esac
exec /usr/bin/{name} "$@"
''')

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\nset -eu\n" + body)
        path.chmod(0o755)

    def start(self, mode="capture", **env):
        log = open(self.root / "process.log", "ab")
        self.addCleanup(log.close)
        proc = subprocess.Popen(["/bin/bash", str(SCRIPT), mode], env=dict(self.env, **env),
                                stdout=log, stderr=log, start_new_session=True)
        self.addCleanup(self.stop, proc)
        return proc

    def stop(self, proc):
        # timeout creates additional process groups. Kill any surviving fixture
        # workers too, so even a regression failure cannot leave test sleepers.
        for path in self.root.glob("*-pid"):
            try:
                group = os.getpgid(int(path.read_text()))
                if group != os.getpgrp():
                    os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=3)

    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail("condition timed out; collector output:\n" +
                  (self.root / "process.log").read_text())

    def capture_dir(self):
        self.wait_for(lambda: self.output.exists() and any(self.output.iterdir()))
        return next(self.output.iterdir())

    def test_wedged_power_read_preserves_fast_evidence(self):
        proc = self.start(HANG_POWER="1")
        directory = self.capture_dir()
        self.wait_for(lambda: (self.root / "power-pid").exists())
        self.assertEqual((directory / "hyprland-test-session.log").read_text(),
                         "volatile compositor evidence\n")
        self.assertIn("sync", (self.root / "events").read_text())
        self.assertTrue((directory / "journal-15min.txt").is_file())
        self.assertTrue((directory / "processes.txt").is_file())
        # A wedged power query must not serialize other collectors behind it.
        self.wait_for(lambda: (directory / "sensors.txt.status").exists())
        self.assertEqual(proc.wait(timeout=12), 0)
        self.assertIn((directory / "nvidia-proc/0000:01:00.0/power.status").read_text().strip(),
                      ("124", "137"))
        self.assertEqual((directory / "capture-status.txt").read_text().strip(), "complete")

    def test_normal_capture_and_collector_failure(self):
        self.stub("sensors", "printf 'fixture sensor failure\\n' >&2\nexit 7\n")
        proc = self.start()
        directory = self.capture_dir()
        self.assertEqual(proc.wait(timeout=8), 0)
        self.assertEqual((directory / "sensors.txt.status").read_text(), "7\n")
        self.assertEqual((directory / "nvidia-smi-q.txt.status").read_text(), "0\n")
        self.assertEqual((directory / "nvidia-proc/0000:01:00.0/power").read_text(),
                         "fixture power state\n")

    def test_shutdown_preserves_evidence_with_report_pending(self):
        proc = self.start(HANG_REPORT="1")
        directory = self.capture_dir()
        self.wait_for(lambda: (self.root / "report-pid").exists())
        self.assertTrue((directory / "hyprland-test-session.log").is_file())
        self.assertIn("sync", (self.root / "events").read_text())
        # Equivalent TERM for the service's control group, including timeout's
        # separate process group. No GPU reset or live service is involved.
        report_pid = int((self.root / "report-pid").read_text())
        os.killpg(os.getpgid(report_pid), signal.SIGTERM)
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=3)
        self.assertTrue((directory / "journal-15min.txt").is_file())
        self.assertFalse((directory / "capture-status.txt").exists())

    def test_watch_debounces_and_exits_when_stream_disconnects(self):
        fifo = self.root / "journal-stream"
        os.mkfifo(fifo)
        proc = self.start("watch")
        self.wait_for(lambda: (self.root / "watching").exists())
        with open(fifo, "w") as stream:
            stream.write("fixture kernel: NVRM: Xid 62\n" * 2)
            stream.flush()
            directory = self.capture_dir()
            self.wait_for(lambda: "within debounce window" in
                          (self.root / "events").read_text(), timeout=8)
            self.assertTrue((directory / "capture-status.txt").exists())
            self.assertEqual(len(list(self.output.iterdir())), 1)
        self.assertEqual(proc.wait(timeout=3), 1)
        self.assertIn("kernel log stream ended", (self.root / "events").read_text())


if __name__ == "__main__":
    unittest.main()
