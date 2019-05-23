"""
Show information related to how "healthy" a push looks (autoland only).

.. code-block:: bash

    adr push_health -r <revision>
"""

from ci_info import Push


def run(args):
    push = Push(args.rev)

    num_scheduled = len(push.scheduled_task_labels)
    num_total = len(push.target_task_labels)
    percentage = round(float(num_scheduled) / num_total * 100, 1)

    return [[
        'Tasks Scheduled',
        'Tasks Total',
        'Percentage',
        'Total Hours',
        'Backed Out',
        'Regressions Caught',
        'Regressions Missed',
    ], [
        num_scheduled,
        num_total,
        percentage,
        push.scheduled_duration,
        push.backedout,
        len(push.regressions_caught),
        len(push.regressions_missed),
    ]]
