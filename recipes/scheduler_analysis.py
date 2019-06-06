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
from collections import defaultdict
from dataclasses import dataclass
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


@dataclass
class Score:
    primary_backouts: int = 0
    secondary_backouts: int = 0
    tasks: int = 0

    @property
    def secondary_backout_rate(self):
        total_backouts = self.primary_backouts + self.secondary_backouts
        if not total_backouts:
            return 0

        return float(self.secondary_backouts) / total_backouts

    @property
    def scheduler_efficiency(self):
        return round(100000 / (self.secondary_backout_rate * self.tasks), 2)


class Scheduler:
    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.stem
        self.score = Score()

    def get_target_tasks(self, push):
        if self.name == "baseline":
            return push.target_task_labels

        with open(self.path, "r") as fh:
            scheduler_hash = config.cache._hash(fh.read())

        key = f"scheduler.{push.rev}.{scheduler_hash}"
        if config.cache.has(key):
            logger.debug(f"Loading target tasks from cache")
            return config.cache.get(key)

        logger.debug(f"Generating target tasks for {self.name}")
        cmd = ["./mach", "taskgraph", "optimized", "--fast"]
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": self.path.parent.as_posix(),
                "TASKGRAPH_OPTIMIZE_STRATEGIES": f"{self.name}:STRATEGIES",
            }
        )
        output = subprocess.check_output(
            cmd, env=env, cwd=GECKO, stderr=subprocess.DEVNULL
        ).decode("utf8")
        target_tasks = set(output.splitlines())

        config.cache.put(key, target_tasks, 43200)  # keep results for 30 days
        return target_tasks

    def analyze(self, push):
        target_tasks = self.get_target_tasks(push)
        self.score.tasks += len(target_tasks)

        if push.backedout:
            if push.likely_regressions & target_tasks:
                self.score.primary_backouts += 1
            else:
                self.score.secondary_backouts += 1


def hg(args):
    cmd = ["hg"] + args
    logger.debug(f"Running: {' '.join(cmd)}")
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
    global GECKO, logger
    GECKO = args.gecko_path
    if not GECKO:
        logger.error("Must specify --gecko-path.")
        sys.exit(1)

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
    logger.debug(f"Found previous revision: {orig_rev}")

    try:
        for i, push in enumerate(pushes):
            logger.info(f"Analyzing https://treeherder.mozilla.org/#/jobs?repo=autoland&revision={push.rev} ({i+1}/{len(pushes)})")  # noqa

            hg(["update", push.rev])

            for scheduler in schedulers:
                logger.debug(f"Scheduler {scheduler.name}")
                try:
                    scheduler.analyze(push)
                except MissingDataError:
                    logger.warning(f"MissingDataError: Skipping {push.rev}")

    finally:
        logger.debug("restoring repo")
        hg(["update", orig_rev])

    header = [
        "Scheduler",
        "Total Tasks",
        "Primary Backouts",
        "Secondary Backouts",
        "Secondary Backout Rate",
        "Scheduler Efficiency",
    ]

    data = []
    for sched in schedulers:
        s = sched.score
        data.append([
            sched.name,
            s.tasks,
            s.primary_backouts,
            s.secondary_backouts,
            s.secondary_backout_rate,
            s.scheduler_efficiency,
        ])

    data.sort(key=lambda x: x[-1], reverse=True)
    data.insert(0, header)
    return data
