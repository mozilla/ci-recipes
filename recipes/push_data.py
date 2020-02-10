"""
Generate test-related data about pushes.

.. code-block:: bash

    adr push_data [--branch <branch>] [--from <date> [--to <date>]]
"""

import json
import os
import traceback

from adr import config
from adr.errors import MissingDataError
from adr.query import run_query
from loguru import logger
from tqdm import tqdm

from mozci.push import Push, make_push_objects


def run(args):
    # compute pushes in range
    pushes = make_push_objects(
        from_date=args.from_date, to_date=args.to_date, branch=args.branch
    )

    header = [
        'Revisions',
        'All Tasks',
        'Task Regressions (possible)',
        'Task Regressions (likely)',
        'All Groups',
        'Group Regressions (possible)',
        'Group Regressions (likely)',
    ]

    data = [
        header
    ]

    num_cached = 0

    for push in tqdm(pushes):
        key = f"push_data.{push.rev}"

        if config.cache.has(key):
            num_cached += 1
            data.append(config.cache.get(key))
        else:
            try:
                value = [
                    push.revs,
                    list(push.task_labels),
                    list(push.get_possible_regressions("label")),
                    list(push.get_likely_regressions("label")),
                    list(push.group_summaries.keys()),
                    list(push.get_possible_regressions("group")),
                    list(push.get_likely_regressions("group")),
                ]
                data.append(value)
                config.cache.forever(key, value)
            except MissingDataError:
                logger.warning(f"Tasks for push {push.rev} can't be found on ActiveData")
            except Exception as e:
                traceback.print_exc()

    logger.info(f"{num_cached} pushes were already cached out of {len(pushes)}")

    return data
