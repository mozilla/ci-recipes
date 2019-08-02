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

from ci_info import Push, make_push_objects


def run(args):
    # compute pushes in range
    pushes = make_push_objects(
        from_date=args.from_date, to_date=args.to_date, branch=args.branch
    )

    if config.output_file is not None and os.path.exists(config.output_file):
        with open(config.output_file, "r") as f:
            data = json.load(f)
    else:
        header = [
            'Revision',
            'All Tasks',
            'Regressions (possible)',
            'Regressions (likely)',
        ]

        data = [
            header
        ]

    already_done = set(row[0] for row in data[1:])

    for push in pushes:
        if push.rev in already_done:
            continue

        try:
            data.append([
                push.rev,
                list(push.task_labels),
                list(push.possible_regressions),
                list(push.likely_regressions),
            ])
        except MissingDataError:
            logger.warning(f"Tasks for push {push.rev} can't be found on ActiveData")
            continue
        except Exception as e:
            logger.error(e)
            continue

    return data
