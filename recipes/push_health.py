"""
Show information related to how "healthy" a push looks. Only works with
autoland for now.

.. code-block:: bash

    adr push_health -r <revision>
"""

from argparse import Namespace
from collections import defaultdict, namedtuple
from enum import Enum

import requests

from adr.query import run_query
from adr.util import memoize


class Status(Enum):
    PASS = 0
    FAIL = 1
    INTERMITTENT = 2


Task = namedtuple('Task', ['label', 'duration', 'result', 'classification'])


@memoize
def get_decision_artifact_urls(rev):
    """Return all artifact urls from the Decision task of the given revision.

    This function is memoized, so it will only run the 'decision_artifacts'
    query a single time for any given revision.

    Args:
        rev (str): Revision associated with the push on treeherder.

    Returns:
        list: List of artifact urls.
    """
    return run_query('decision_artifacts', Namespace(rev=rev))['data'][0]['artifacts']


def get_decision_artifact(rev, name):
    """Get an artifact from Decision task of the given revision.

    Args:
        rev (str): Revision associated with the push on treeherder.
        name (str): Name of the artifact fetch.

    Returns:
        dict: JSON representation of the artifact.
    """
    for url in get_decision_artifact_urls(rev):
        if url.rsplit('/', 1)[1] == name:
            return requests.get(url).json()


def run(args):
    target_task_set = set(get_decision_artifact(args.rev, 'target-tasks.json'))
    task_set = set([v['label'] for v in get_decision_artifact(args.rev, 'task-graph.json').values()])

    data = run_query('push_results', args)['data']
    tasks = [Task(**kwargs) for kwargs in data]

    labels = defaultdict(lambda: {'status': None, 'classifications': set()})
    duration = reg_caught = reg_missed = 0
    for task in tasks:
        label = labels[task.label]
        s = Status.FAIL if task.result in ('busted', 'exception', 'testfailed') else Status.PASS

        if label['status'] is None:
            label['status'] = s
            # Don't count retriggers in total duration as it is beyond the
            # scheduler's control.
            duration += task.duration
        elif label['status'] != s:
            label['status'] = Status.INTERMITTENT

        label['classifications'].add(task.classification)


    for label, value in labels.items():
        status = value['status']
        classifications = value['classifications']

        if status == Status.PASS:
            continue

        if any(c in ('not classified', 'fixed by commit') for c in classifications):
            if label in task_set:
                reg_caught += 1
            else:
                reg_missed += 1


    header = [
        'Tasks Scheduled',
        'Tasks Total',
        'Percentage',
        'Total Hours',
        'Regressions Caught',
        'Regressions Missed',
    ]
    num_scheduled = len(task_set)
    num_total = len(target_task_set)
    percentage = round(float(num_scheduled) / num_total * 100, 1)
    hours = int(duration / 3600)

    result = [[num_scheduled, num_total, percentage, hours, reg_caught, reg_missed]]
    result.insert(0, header)
    return result
