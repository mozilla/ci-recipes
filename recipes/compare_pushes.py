"""
Compare the tasks run by two different pushes.

.. code-block:: bash

    adr scheduler_analysis -r1 <rev1>  -r2 <rev2> [-B <branch>]
"""
import ntpath
import re
from collections import defaultdict
from difflib import unified_diff
from urllib.parse import urlparse

from loguru import logger
from mozci.push import Push

RUN_CONTEXTS = [
    {
        "push": {
            "flags": ["-p", "--push"],
            "help": "The push to inspect."
        },
        "push_compare": {
            "flags": ["-c", "--compare"],
            "default": None,
            "help": "The push to compare against. If not specified, push's "
                    "parent will be used.",
        },
        "task_filter": {
            "flags": ["--task-filter"],
            "help": "Only compare tasks that match this regex.",
        }
    }
]


def normalize(manifest):
    manifest = manifest.replace(ntpath.sep, '/')

    separators = (
        'tests/reftest/tests',
    )
    for sep in separators:
        if sep in manifest:
            manifest = manifest[manifest.index(sep)+len(sep)+1:]

    return manifest


def get_manifests_by_task(push):
    tasks = [t for t in push.tasks
             if t.label in push.scheduled_task_labels
             if t.label.startswith('test-')]

    manifests_by_task = defaultdict(set)
    for task in tasks:
        label, chunk = task.label.rsplit('-', 1)
        try:
            int(chunk)
        except ValueError:
            label = task.label

        manifests = task.groups
        if isinstance(manifests, str):
            manifests = [manifests]
        manifests_by_task[label].update(map(normalize, manifests))
    return manifests_by_task


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

    if args.push_compare:
        compare = get_push_object(args.push_compare)
    else:
        compare = push.parent

    push_manifests = get_manifests_by_task(push)
    compare_manifests = get_manifests_by_task(compare)

    labels = sorted(set(list(push_manifests.keys()) + list(compare_manifests.keys())))
    if args.task_filter:
        fltr = re.compile(args.task_filter)
        labels = filter(fltr.search, labels)

    for label in labels:
        logger.info(f"Processing {label}")

        if label not in push_manifests:
            logger.warning(f"{label} not run in rev1!")
            continue

        if label not in compare_manifests:
            logger.warning(f"{label} not run in rev2!")
            continue

        push_groups = sorted(push_manifests[label])
        compare_groups = sorted(compare_manifests[label])
        if push_groups == compare_groups:
            logger.info(f"{label} matches!")
            continue

        logger.warning(f"{label} doesn't match!")
        out = unified_diff(
            push_groups,
            compare_groups,
            fromfile=f'Rev 1: {push.rev}',
            tofile=f'Rev 2: {compare.rev}',
            n=8
        )
        diff = []
        for line in out:
            line = line.rstrip()
            if line.startswith('+'):
                line = f"<green>{line}</green>"

            elif line.startswith('-'):
                line = f"<red>{line}</red>"

            diff.append(line)

        diff = '\n'.join(diff)
        logger.opt(ansi=True).info("Diff:\n" + f"{diff}")

    return []
