"""Fon vazifalari: deploy / yangilash / rollback / AI tahlil uchun umumiy progress kuzatuvchisi.
Bot ham, web ham bir xil Job ni o'qiydi — mantiq ikki marta yozilmaydi."""
import asyncio, time, uuid

JOBS: dict[str, "Job"] = {}
KEEP_SECS = 3600  # tugagan job'lar bir soatdan keyin xotiradan o'chadi


class Job:
    def __init__(self, kind: str, title: str, est: float = 30, **meta):
        self.id = uuid.uuid4().hex[:10]
        self.kind, self.title, self.est = kind, title, max(est, 5)
        self.meta = meta
        self.t0 = time.time()
        self.t_end = self.t0
        self.cur, self.cur_t = "", self.t0
        self.steps: list[dict] = []
        self.state = "run"          # run | ok | bad | cancel
        self.error = ""
        self.result: dict = {}
        self.log = ""
        self.task: asyncio.Task | None = None
        JOBS[self.id] = self
        self._gc()

    def _gc(self):
        now = time.time()
        for k, j in list(JOBS.items()):
            if j.state != "run" and now - j.t_end > KEEP_SECS:
                JOBS.pop(k, None)

    # ── progress ──
    def step(self, text: str):
        now = time.time()
        if self.cur:
            self.steps.append({"text": self.cur, "secs": round(now - self.cur_t, 1)})
        self.cur, self.cur_t = text, now
        self.touch()

    def touch(self):  # heartbeat — osilib qolganini aniqlash uchun
        self.t_end = time.time()

    def finish(self, state: str = "ok", error: str = "", **result):
        if self.cur:
            self.steps.append({"text": self.cur, "secs": round(time.time() - self.cur_t, 1)})
            self.cur = ""
        self.state, self.error = state, error
        self.result.update(result)
        self.t_end = time.time()

    # ── ko'rinish ──
    @property
    def elapsed(self) -> float:
        return (self.t_end if self.state != "run" else time.time()) - self.t0

    def snap(self) -> dict:
        el, rem = self.elapsed, 0.0
        pct = 0
        if self.state == "run":
            rem = max(self.est - el, 0)
            pct = min(int(el / self.est * 100), 95)
        else:
            pct = 100
        return {"id": self.id, "kind": self.kind, "title": self.title, "state": self.state,
                "steps": self.steps, "cur": self.cur, "error": self.error, "result": self.result,
                "elapsed": round(el, 1), "remain": round(rem), "pct": pct,
                "log": self.log[-6000:], "meta": self.meta}


def spawn(kind: str, title: str, coro_fn, est: float = 30, **meta) -> Job:
    """Job yaratib, korutinani fonda ishga tushiradi. coro_fn(job) bo'lishi kerak."""
    j = Job(kind, title, est, **meta)

    async def runner():
        try:
            await coro_fn(j)
            if j.state == "run":
                j.finish("ok")
        except asyncio.CancelledError:
            j.finish("cancel", "Bekor qilindi")
        except Exception as e:
            j.finish("bad", str(e)[:800])
            j.log = str(e)[-3000:]

    j.t_end = time.time()
    j.task = asyncio.create_task(runner())
    return j


def get(jid: str) -> Job | None:
    return JOBS.get(jid)


def cancel(jid: str) -> bool:
    j = JOBS.get(jid)
    if j and j.task and not j.task.done():
        j.task.cancel()
        return True
    return False


async def wait(jid: str, timeout: float = 900) -> Job | None:
    j = JOBS.get(jid)
    if not j or not j.task:
        return j
    try:
        await asyncio.wait_for(asyncio.shield(j.task), timeout)
    except Exception:
        pass
    return j
