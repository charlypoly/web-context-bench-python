"""Everything a run needs, started and stopped together.

- the local servers (no live sites)
- the benchmark Chromium, launched by Playwright with a CDP port that the
  Browser Use adapter attaches to
- the Browser Use adapter process
- the Stagehand adapter process, which launches its own Chromium (same
  Chrome for Testing binary, same offline flags); Playwright attaches to it
  over CDP only to resolve ground truth
"""

from __future__ import annotations

import asyncio

from wpbench.browser import launch
from wpbench.capture import PageSession, capture_page_session
from wpbench.pages import OFFLINE_ARGS, load_pages
from wpbench.server import LocalServers
from wpbench.workers import Worker



def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Harness:
    def __init__(self, playwright):
        self.p = playwright
        self.pages = {pg.id: pg for pg in load_pages()}
        self.versions: dict[str, str] = {}

    async def __aenter__(self) -> "Harness":
        self.servers = self.browser = self.bu = self.sh = None
        try:
            await self._start()
        except BaseException:
            await self.__aexit__(None, None, None)
            raise
        return self

    async def _start(self) -> None:
        (__import__("wpbench").RESULTS_DIR / "tmp").mkdir(parents=True, exist_ok=True)
        self.servers = LocalServers().__enter__()
        main_port, stagehand_port = _free_port(), _free_port()
        self.browser = await launch(self.p, cdp_port=main_port)
        self.cdp_url = f"http://127.0.0.1:{main_port}"
        self.versions["chromium"] = self.browser.version
        self.bu = Worker("browser_use")
        self.sh = Worker("stagehand")
        out = await asyncio.to_thread(
            self.sh.call, cmd="launch", executable_path=self.p.chromium.executable_path,
            port=stagehand_port, args=OFFLINE_ARGS)
        self.versions["stagehand"] = out["stagehand_version"]
        self.sh_browser = await self.p.chromium.connect_over_cdp(out["cdp_url"])
        self.versions["stagehand_chromium"] = self.sh_browser.version

    async def capture(self, page_id: str, act_tasks: list[dict]) -> PageSession:
        return await capture_page_session(
            page_id, self.pages[page_id].url, act_tasks, self.browser, self.cdp_url,
            self.bu, self.sh, self.sh_browser)

    async def __aexit__(self, *exc) -> None:
        for worker in (self.bu, self.sh):
            if worker is not None:
                try:
                    await asyncio.to_thread(worker.close)
                except Exception:
                    pass
        try:
            if self.browser is not None:
                await self.browser.close()
        finally:
            if self.servers is not None:
                self.servers.__exit__(None, None, None)
