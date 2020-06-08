"""
Compare the manifests that ran vs what bugbug said.

.. code-block:: bash

    adr inspect_bugbug --push <push>
"""
import ntpath
from collections import defaultdict
from itertools import chain
from urllib.parse import urlparse

from loguru import logger
from mozci.push import Push

RUN_CONTEXTS = [
    {
        "push": {
            "flags": ["-p", "--push"],
            "help": "The push to inspect. Either a treeherder URL to a single push, "
                    "or of the form '<branch>:<rev>'.",
        },
    }
]

SUITES_SKIP_LIST = (
    "jsreftest",
)


def is_skip_suite(label):
    return any(f"-{s}-" in label for s in SUITES_SKIP_LIST)


def normalize(group):
    group = group.replace(ntpath.sep, '/')

    separators = (
        'tests/reftest/tests',
    )
    for sep in separators:
        if sep in group:
            group = group[group.index(sep)+len(sep)+1:]

    if ":" in group:
        group = group.split(":")[0]
    return group


def get_groups_by_task(push):
    tasks = [t for t in push.tasks
             if t.label in push.scheduled_task_labels
             if t.label.startswith('test-')
             if not is_skip_suite(t.label)]

    groups_by_task = defaultdict(set)
    for task in tasks:
        label, chunk = task.label.rsplit('-', 1)
        try:
            int(chunk)
        except ValueError:
            label = task.label

        groups = task.groups
        if isinstance(groups, str):
            groups = [groups]
        groups_by_task[label].update(map(normalize, groups))
    return groups_by_task


def get_push_object(spec):
    rev = branch = None

    if "://" in spec:
        # Likely a URL, try to parse out branch and rev.
        o = urlparse(spec)
        if "treeherder.mozilla.org" in o.netloc:
            query = o.fragment[o.fragment.index('?') + 1:]
            params = {p[0]: p[1] for p in [i.split("=") for i in query.split("&")]}
            rev = params.get("revision")
            branch = params.get("repo")

    elif ":" in spec:
        branch, rev = spec.split(":", 1)

    if not branch or not rev:
        raise TypeError(f"Could not parse a branch and revision from {spec}! " +
                        "Expected a treeherder url or the format '<branch>:<revision>'.")

    return Push(rev, branch=branch)


def run(args):
    push = get_push_object(args.push)
    groups_by_task = get_groups_by_task(push)
    bugbug_data = push.decision_task.get_artifact("public/bugbug-push-schedules.json")

    scheduled_groups = [(g, bugbug_data["groups"].get(g, 0))
                        for g in set(chain(*groups_by_task.values()))]

    print("Scheduled groups:")
    for group, confidence in sorted(scheduled_groups, reverse=True, key=lambda x: (x[1], x[0])):
        print(f"{group}: {confidence}")
