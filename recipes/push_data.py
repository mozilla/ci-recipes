"""
Generate test-related data about pushes.

.. code-block:: bash

    adr push_data [--branch <branch>] [--from <date> [--to <date>]] [--runnable <runnable>]
"""

import traceback

from adr import config
from adr.errors import MissingDataError
from loguru import logger
from tqdm import tqdm

from mozci.push import make_push_objects


def run(args):
    # compute pushes in range
    pushes = make_push_objects(
        from_date=args.from_date, to_date=args.to_date, branch=args.branch
    )

    header = [
        'Revisions',
        'All Runnables',
        'Regressions (possible)',
        'Regressions (likely)',
    ]

    data = [
        header
    ]

    num_cached = 0

    for push in tqdm(pushes):
        key = f"push_data.{args.runnable}.{push.rev}"

        logger.info(f"Analyzing {push.rev} at the {args.runnable} level...")

        if config.cache.has(key):
            num_cached += 1
            data.append(config.cache.get(key))
        else:
            try:
                if args.runnable == "label":
                    runnables = push.task_labels
                elif args.runnable == "group":
                    runnables = push.group_summaries.keys()

                value = [
                    push.revs,
                    list(runnables),
                    list(push.get_possible_regressions(args.runnable)),
                    list(push.get_likely_regressions(args.runnable)),
                ]
                data.append(value)
                config.cache.forever(key, value)
            except MissingDataError:
                logger.warning(f"Tasks for push {push.rev} can't be found on ActiveData")
            except Exception:
                traceback.print_exc()

    logger.info(f"{num_cached} pushes were already cached out of {len(pushes)}")

    return data
