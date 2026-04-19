"""
Kitee

Copyright (c) 2026 Kitee Contributors. All rights reserved.

Original repository:

Copyright (c) 2024~2025 Techarerm/TedKai
"""
import logging
import queue
import threading
import time
from queue import Queue
from typing import Callable


class Background(threading.Thread):
    def __init__(self, launcher, callback: Callable):
        threading.Thread.__init__(self, daemon=True, name="BackgroundThread")
        # Logger
        self.logger = logging.getLogger(f'Launcher/Background')
        self.launcher = launcher
        self.callback = callback

        # Workers & Jobs
        self.workers: Queue = queue.Queue()
        self.worker_threads = set()
        self.worker_lock = threading.Lock()

        self.jobs: dict = {}
        self.job_lock = threading.Lock()
        self.job_count = 0

        # Event
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            try:
                job_id, func, args, kwargs = self.workers.get(timeout=0.2)
            except queue.Empty:
                continue

            # Create worker thread
            w_thread = threading.Thread(
                target=self.run_job,
                args=(job_id, func, args, kwargs),
                name="BackgroundWorker-{}".format(job_id),
                daemon=True,
            )

            with self.worker_lock:
                self.worker_threads.add(w_thread)

            w_thread.start()

        self.callback()

    def run_job(self, job_id, func, args, kwargs):
        self.update_job(job_id, state="running", status="Running.")
        try:
            self.logger.debug("Starting background job: [id: {}, name: {}]".format(job_id, self.get_job(job_id).get("name")))
            func(job_id, self.make_job_updater(job_id), *args, **kwargs)
            job = self.get_job(job_id)
            if job.get("state") not in {"failed", "finished"}:
                self.update_job(job_id, state="finished", status="Finished.", done=True)
        except Exception as exc:
            self.logger.exception("Background job failed.")
            self.update_job(job_id, state="failed", status="Failed.", error=str(exc), done=True)
        finally:
            try:
                self.workers.task_done()
            finally:
                with self.worker_lock:
                    self.worker_threads.discard(threading.current_thread())

    def add_worker(self, name, func, *args, **kwargs):
        with self.job_lock:
            self.job_count += 1
            job_id = "{}-{}".format(int(time.time() * 1000), self.job_count)
            self.jobs[job_id] = {
                "ok": True,
                "id": job_id,
                "name": name,
                "state": "queued",
                "status": "Queued.",
                "progress": 0,
                "total": 0,
                "done": False,
                "error": "",
            }

        self.workers.put((job_id, func, args, kwargs))
        return job_id

    def get_job(self, job_id):
        with self.job_lock:
            if job_id not in self.jobs:
                return {"status": False, "message": "No such job"}

            return dict(self.jobs[job_id])

    def update_job(self, job_id, **values):
        with self.job_lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(values)

    def make_job_updater(self, job_id):
        def update(**values):
            self.update_job(job_id, **values)

        return update

    def stop(self):
        self.stop_event.set()

    def remove_worker(self, job_id):
        self.update_job(job_id, state="removed", status="Removed.", done=True)
