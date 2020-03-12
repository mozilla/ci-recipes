"""
Run an analysis of all the scheduling algorithms defined in the
'strategies' directory.

.. code-block:: bash

    adr scheduler_analysis --gecko-path <path> [--branch <branch>] [--from <date> [--to <date>]]
"""

import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from adr import config
from adr.errors import MissingDataError
from adr.util.memoize import memoized_property
from loguru import logger

from mozci.push import make_push_objects

here = Path(__file__).parent.resolve()


RUN_CONTEXTS = [
    {
        "strategies": {
            "nargs": "+",
            "default": [],
            "help": "Strategy names to analyze.",
        }
    }
]


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

    def get_tasks(self, push):
        key = f"scheduler.{push.rev}.{self.name}"

        if config.cache.has(key):
            logger.opt(ansi=True).info(f"<cyan>{self.name} loaded from cache</cyan>")
            return config.cache.get(key)

        # Download the shadow scheduler tasks
        tasks = push.get_shadow_scheduler_tasks(self.name)
        if tasks is not None:
            logger.opt(ansi=True).info(f"<cyan>{self.name} loaded from artifact</cyan>")
            config.cache.put(key, tasks, 43200)  # keep results for 30 days
            return tasks

        logger.warning(f"warning: shadow scheduler '{self.name}' not found!")
        raise MissingDataError

    def analyze(self, push):
        tasks = self.get_tasks(push)
        score = Score(tasks=len(tasks))

        if push.backedout:
            if push.get_likely_regressions("label") & tasks:
                score.primary_backouts += 1
            else:
                score.secondary_backouts += 1

        logger.debug(f"{score}")
        self.score.update(score)
        return score


def run(args):
    schedulers = []
    for s in args.strategies:
        logger.info(f"Creating scheduler using strategy {s}")
        schedulers.append(Scheduler(s))

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

            for s in schedulers:
                try:
                    scores[s.name].update(s.analyze(push))
                except MissingDataError:
                    logger.warning(f"MissingDataError: Skipping {push.rev}")

        config.cache.put(key, {k: v.as_dict() for k, v in scores.items()}, 43200)  # 30 days

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
