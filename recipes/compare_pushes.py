"""
Compare the tasks run by two different pushes.

.. code-block:: bash

    adr scheduler_analysis -r1 <rev1>  -r2 <rev2> [-B <branch>]
"""
import ntpath
import re
from collections import defaultdict
from difflib import unified_diff

from loguru import logger
from mozci.push import Push

RUN_CONTEXTS = [
    {
        "revA": {
            "flags": ["-r1", "--rev1"],
            "help": "First revision to compare.",
        },
        "revB": {
            "flags": ["-r2", "--rev2"],
            "help": "Second revision to compare.",
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


def run(args):
    manifestsA = get_manifests_by_task(Push(args.revA, branch=args.branch))
    manifestsB = get_manifests_by_task(Push(args.revB, branch=args.branch))

    labels = sorted(set(list(manifestsA.keys()) + list(manifestsB.keys())))
    if args.task_filter:
        fltr = re.compile(args.task_filter)
        labels = filter(fltr.search, labels)

    for label in labels:
        logger.info(f"Processing {label}")

        if label not in manifestsA:
            logger.warning(f"{label} not run in rev1!")
            continue

        if label not in manifestsB:
            logger.warning(f"{label} not run in rev2!")
            continue

        groupsA = sorted(manifestsA[label])
        groupsB = sorted(manifestsB[label])
        if groupsA == groupsB:
            logger.info(f"{label} matches!")
            continue

        logger.warning(f"{label} doesn't match!")
        out = unified_diff(
            groupsA,
            groupsB,
            fromfile=f'Rev 1: {args.revA}',
            tofile=f'Rev 2: {args.revB}',
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
