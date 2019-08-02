"""
Generate test-related data about pushes.

.. code-block:: bash

    adr push_data [--branch <branch>] [--from <date> [--to <date>]]
"""

from argparse import Namespace

from adr import config
from adr.query import run_query

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

    for push in pushes:
        data.append([
            push.rev,
            list(push.task_labels),
            list(push.possible_regressions),
            list(push.likely_regressions),
        ])

    return data
