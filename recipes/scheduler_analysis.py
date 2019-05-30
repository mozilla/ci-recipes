"""
Run an analysis of all the scheduling algorithms defined in the
'strategies' directory.

.. code-block:: bash

    adr scheduler_analysis --gecko-path <path> [--branch <branch>] [--from <date> [--to <date>]]
"""

import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from adr import config
from adr.errors import MissingDataError
from adr.query import run_query
from icecream import ic
from loguru import logger

from ci_info import Push

here = Path(__file__).parent.resolve()


RUN_CONTEXTS = [
    {
        "gecko_path": {
            "flags": ["--gecko-path"],
            "dest": "gecko_path",
            "default": os.environ.get("GECKO_PATH"),
            "help": "Path to gecko (i.e mozilla-central).",
        }
    }
]

GECKO = None


class Scheduler:
    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.stem

        self.total_tasks = 0
        self.regressions_caught = 0
        self.regressions_missed = 0

    def get_target_tasks(self, push):
        if self.name == "baseline":
            return push.target_task_labels

        key = f"scheduler.{self.name}.{push.rev}"
        if config.cache.has(key):
            logger.debug(f"loading target tasks from cache")
            return config.cache.get(key)

        logger.info(f"generating target tasks for {self.name}")
        cmd = ["./mach", "taskgraph", "optimized"]
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": self.path.parent.as_posix(),
                "TASKGRAPH_OPTIMIZE_STRATEGIES": f"{self.name}:STRATEGIES",
            }
        )
        output = subprocess.check_output(
            cmd, env=env, cwd=GECKO, stderr=subprocess.DEVNULL
        )
        target_tasks = set(output.splitlines())

        config.cache.put(key, target_tasks, 43200)  # keep results for 30 days
        return target_tasks

    def analyze(self, push):
        target_tasks = self.get_target_tasks(push)

        self.total_tasks += len(target_tasks)
        self.regressions_caught += len(push.likely_regressions & target_tasks)
        self.regressions_missed += len(push.likely_regressions - target_tasks)


def hg(args):
    cmd = ["hg"] + args
    logger.debug(f"running command: {' '.join(cmd)}")
    return subprocess.check_output(cmd, cwd=GECKO).decode("utf8")


def make_push_objects(**kwargs):
    data = run_query("push_revisions", Namespace(**kwargs))["data"]

    pushes = []
    cur = prev = None
    for pushid, revs, parents in data:
        topmost = list(set(revs) - set(parents))[0]

        cur = Push(topmost)
        if prev:
            # avoids the need to query hgmo to find parent pushes
            cur._parent = prev

        pushes.append(cur)
        prev = cur

    return pushes


def run(args):
    global GECKO
    GECKO = args.gecko_path
    if not GECKO:
        logger.error("Must specify --gecko-path.")
        sys.exit(1)

    logger.debug("Starting scheduler analysis with:\n{args}", args=ic.format(args))

    # initialize schedulers to analyze
    cwd = os.getcwd()
    strategy_dir = here / "strategies"
    strategy_paths = [s for s in strategy_dir.glob("*.py") if s.name != "__init__.py"]

    schedulers = []
    for path in strategy_paths:
        logger.debug(f"Creating scheduler using strategy from {path.relative_to(cwd)}")
        schedulers.append(Scheduler(path))

    # use what was actually scheduled as a baseline comparison
    schedulers.append(Scheduler("baseline"))

    # compute pushes in range
    pushes = make_push_objects(
        from_date=args.from_date, to_date=args.to_date, branch=args.branch
    )
    orig_rev = hg(["log", "-r", ".", "-T", "{node}"])
    logger.debug(f"original revision: {orig_rev}")

    try:
        for i, push in enumerate(pushes):
            logger.info(f"analyzing {push.rev} ({i+1}/{len(pushes)})")
            hg(["update", push.rev])

            for scheduler in schedulers:
                logger.debug(f"analyzing scheduler '{scheduler.name}'")
                try:
                    scheduler.analyze(push)
                except MissingDataError:
                    logger.warning(f"MissingDataError: Skipping {push.rev}")
    finally:
        logger.debug("restoring repo")
        hg(["update", orig_rev])

    header = ["Scheduler", "Total Tasks", "Regressions Caught", "Regressions Missed"]
    data = [header]
    for s in schedulers:
        data.append([s.name, s.total_tasks, s.regressions_caught, s.regressions_missed])

    return data
