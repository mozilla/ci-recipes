"""
Show information related to how "healthy" a push looks (autoland only)

.. code-block:: bash

    adr push_health -r <revision>
"""

from mozci.push import Push


def run(args):
    push = Push(args.rev)

    num_scheduled = len(push.scheduled_task_labels)
    num_total = len(push.target_task_labels)
    percentage = round(float(num_scheduled) / num_total * 100, 1)
    all_regressions = push.possible_regressions | push.likely_regressions

    return [[
        'Tasks Scheduled',
        'Tasks Total',
        'Percentage',
        'Total Hours (scheduled)',
        'Backed Out',
        'Regressions (possible)',
        'Regressions (likely)',
        'Caught',
        'Missed',
    ], [
        num_scheduled,
        num_total,
        percentage,
        push.scheduled_duration,
        push.backedout,
        len(push.possible_regressions),
        len(push.likely_regressions),
        len(all_regressions & push.scheduled_task_labels),
        len(all_regressions - push.scheduled_task_labels),
    ]]
