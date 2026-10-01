"""Clients for the two adapter processes (separate uv projects, separate lockfiles)."""

from __future__ import annotations

import json
import os
import subprocess

from wpbench import ROOT


class WorkerError(Exception):
    pass


class Worker:
    def __init__(self, project: str, timeout_s: float = 120.0):
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env.pop("ANTHROPIC_API_KEY", None)  # adapters never need it
        self.project = ROOT / "adapters" / project
        self.timeout_s = timeout_s
        self.proc = subprocess.Popen(
            ["uv", "run", "--frozen", "--project", str(self.project), "python", str(self.project / "worker.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(ROOT / "results" / "tmp" / f"{project}.stderr.log", "a"),
            text=True, env=env, cwd=self.project,
        )

    def call(self, **req) -> dict:
        import select

        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        ready, _, _ = select.select([self.proc.stdout], [], [], self.timeout_s)
        if not ready:
            raise WorkerError(f"{self.project.name}: timeout after {self.timeout_s}s on {req['cmd']}")
        line = self.proc.stdout.readline()
        if not line:
            raise WorkerError(f"{self.project.name}: worker exited (see results/tmp/{self.project.name}.stderr.log)")
        resp = json.loads(line)
        if not resp.pop("ok"):
            raise WorkerError(f"{self.project.name}: {resp['error']}\n{resp.get('trace', '')}")
        return resp

    def close(self) -> None:
        try:
            self.call(cmd="quit")
        except Exception:
            pass
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
