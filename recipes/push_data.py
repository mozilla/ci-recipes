"""
Generate test-related data about pushes.

.. code-block:: bash

    adr push_data [--branch <branch>] [--from <date> [--to <date>]]
"""

import json
import os

from adr import config
from adr.errors import MissingDataError
from adr.query import run_query
from loguru import logger
from tqdm import tqdm

from ci_info import Push, make_push_objects


def run(args):
    # compute pushes in range
    pushes = make_push_objects(
        from_date=args.from_date, to_date=args.to_date, branch=args.branch
    )

    header = [
        'Revision',
        'All Tasks',
        'Regressions (possible)',
        'Regressions (likely)',
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
                    push.rev,
                    list(push.task_labels),
                    list(push.possible_regressions),
                    list(push.likely_regressions),
                ]
                data.append(value)
                config.cache.forever(key, value)
            except MissingDataError:
                logger.warning(f"Tasks for push {push.rev} can't be found on ActiveData")
                continue
            except Exception as e:
                logger.error(e)
                continue

    logger.info(f"{num_cached} pushes were already cached out of {len(pushes)}")

    return data
