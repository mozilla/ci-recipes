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
    all_regressions = push.get_possible_regressions("label") | push.get_likely_regressions("label")

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
        len(push.get_possible_regressions("label")),
        len(push.get_likely_regressions("label")),
        len(all_regressions & push.scheduled_task_labels),
        len(all_regressions - push.scheduled_task_labels),
    ]]
