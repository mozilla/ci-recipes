"""
Generate test-related data about pushes.

.. code-block:: bash

    adr push_data [--branch <branch>] [--from <date> [--to <date>]]
"""

from argparse import Namespace

from adr import config
from adr.query import run_query

from ci_info import Push


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
