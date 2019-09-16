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
from datetime import datetime
from pathlib import Path

from adr import config
from adr.errors import MissingDataError
from adr.query import run_query
from adr.util.memoize import memoized_property
from icecream import ic
from loguru import logger

from ci_info import Push, make_push_objects

here = Path(__file__).parent.resolve()


RUN_CONTEXTS = [
    {
        "gecko_path": {
            "flags": ["--gecko-path"],
            "dest": "gecko_path",
            "default": os.environ.get("GECKO_PATH"),
            "help": "Path to gecko (i.e mozilla-central).",
        },
        "clone": {
            "flags": ["--clone"],
            "dest": "clone",
            "action": "store_true",
            "default": False,
            "help": "Clone Gecko if the specified path does not exist.",
        },
        "strategies": {
            "nargs": "+",
            "default": [],
            "help": "Strategy names to analyze.",
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

        return round(float(self.secondary_backouts) / total_backouts, 2)

    @property
    def scheduler_efficiency(self):
        rate = self.secondary_backout_rate * self.tasks
        if rate == 0:
            return 0
        return round(float(100000) / rate, 2)

    def update(self, other):
        self.primary_backouts += other.primary_backouts
        self.secondary_backouts += other.secondary_backouts
        self.tasks += other.tasks

    def as_dict(self):
        return {
            'primary_backouts': self.primary_backouts,
            'secondary_backouts': self.secondary_backouts,
            'tasks': self.tasks
        }


class Scheduler:
    def __init__(self, name):
        self.name = name
        self.score = Score()

    @memoized_property
    def path(self):
        # initialize schedulers to analyze
        cwd = os.getcwd()
        strategy_dir = here / "strategies"
        for s in strategy_dir.glob("*.py"):
            if s.stem == self.name:
                return s

    def get_tasks(self, push):
        key = f"scheduler.{push.rev}.{self.name}"
        if self.path:
            with open(self.path, "r") as fh:
                scheduler_hash = config.cache._hash(fh.read())
            key += f".{scheduler_hash}"

        if config.cache.has(key):
            logger.opt(ansi=True).info(f"<cyan>{self.name} loaded from cache</cyan>")
            return config.cache.get(key)

        # If we're baseline simply use the scheduled_task_labels.
        if self.name == "baseline":
            tasks = push.scheduled_task_labels
            logger.opt(ansi=True).info(f"<cyan>{self.name} loaded from artifact</cyan>")
            config.cache.put(key, tasks, 43200)  # keep results for 30 days
            return tasks

        # Next check if a shadow scheduler matching our name ran on the push.
        tasks = push.get_shadow_scheduler_tasks(self.name)
        if tasks is not None:
            logger.opt(ansi=True).info(f"<cyan>{self.name} loaded from artifact</cyan>")
            config.cache.put(key, tasks, 43200)  # keep results for 30 days
            return tasks

        # Finally fallback to generating the tasks locally.
        if not GECKO or not self.path:
            logger.warning(f"warning: shadow scheduler '{self.name}' not found!")
            raise MissingDataError

        logger.info(f"Generating target tasks")
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
        tasks = set(output.splitlines())

        logger.opt(ansi=True).info(f"<cyan>{self.name} loaded from local repository</cyan>")
        config.cache.put(key, tasks, 43200)  # keep results for 30 days
        return tasks

    def analyze(self, push):
        tasks = self.get_tasks(push)
        score = Score(tasks=len(tasks))

        if push.backedout:
            if push.likely_regressions & tasks:
                score.primary_backouts += 1
            else:
                score.secondary_backouts += 1

        logger.debug(f"{score}")
        self.score.update(score)
        return score


def hg(args):
    cmd = ["hg"] + args
    logger.debug(f"Running: {' '.join(cmd)}")
    return subprocess.check_output(cmd, cwd=GECKO).decode("utf8")


def clone_gecko():
    cmd = ['hg', 'clone', 'https://hg.mozilla.org/mozilla-unified', GECKO]
    logger.debug(f"Running: {' '.join(cmd)}")
    subprocess.call(cmd)


def run(args):
    global GECKO, logger
    if args.gecko_path:
        GECKO = args.gecko_path

    if GECKO and not Path(GECKO).is_dir():
        if args.clone:
            clone_gecko()
        else:
            logger.error(f"Gecko path '{GECKO}' does not exist! Pass --clone to clone it to this location.")
            sys.exit(1)

    schedulers = []
    for s in args.strategies:
        logger.info(f"Creating scheduler using strategy {s}")
        schedulers.append(Scheduler(s))

    # use what was actually scheduled as a baseline comparison
    schedulers.append(Scheduler('baseline'))

    # compute dates in range
    pushes = make_push_objects(
        from_date=args.from_date, to_date=args.to_date, branch=args.branch
    )

    total_pushes = len(pushes)
    logger.info(f"Found {total_pushes} pushes in specified range.")
    pushes_by_date = defaultdict(list)
    for push in pushes:
        date = datetime.utcfromtimestamp(push.date).strftime('%Y-%m-%d')
        pushes_by_date[date].append(push)

    if GECKO:
        orig_rev = hg(["log", "-r", ".", "-T", "{node}"])
        logger.info(f"Found previous revision: {orig_rev}")

    try:
        i = 0
        for date in sorted(pushes_by_date):
            pushes = pushes_by_date[date]
            logger.info(f"Analyzing pushes from {date} ({len(pushes)} pushes)")

            _hash = config.cache._hash(''.join([p.rev for p in pushes]) +
                                       ''.join([s.name for s in schedulers]))
            key = f"scheduler_analysis.{date}.{_hash}"
            if config.cache.has(key):
                logger.info(f"Loading results for {date} from cache")
                data = config.cache.get(key)

                for s in schedulers:
                    s.score.update(Score(**data[s.name]))
                i += len(pushes)
                continue

            scores = defaultdict(Score)
            for push in sorted(pushes, key=lambda p: p.id):
                i += 1
                logger.info(f"Analyzing https://treeherder.mozilla.org/#/jobs?repo=autoland&revision={push.rev} ({i}/{total_pushes})")  # noqa

                if GECKO:
                    hg(["update", push.rev])

                for s in schedulers:
                    try:
                        scores[s.name].update(s.analyze(push))
                    except MissingDataError:
                        logger.warning(f"MissingDataError: Skipping {push.rev}")

            config.cache.put(key, {k: v.as_dict() for k, v in scores.items()}, 43200)  # 30 days


    finally:
        if GECKO:
            logger.info("restoring repo")
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
