import random

from taskgraph.optimize import (
    Either,
    IndexSearch,
    OptimizationStrategy,
    SkipUnlessChanged,
    SkipUnlessSchedules,
)


class RandomOptimizer(OptimizationStrategy):
    probability = 0.1  # probability task is optimized away

    def should_remove_task(self, task, params, _):
        if random.random() < self.probability:
            return True
        return False


STRATEGIES = {
    'never': OptimizationStrategy(),  # "never" is the default behavior
    'index-search': IndexSearch(),
    'seta': RandomOptimizer(),
    'skip-unless-changed': SkipUnlessChanged(),
    'skip-unless-schedules': SkipUnlessSchedules(),
    'skip-unless-schedules-or-seta': Either(SkipUnlessSchedules(), RandomOptimizer()),
}
