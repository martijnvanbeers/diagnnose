from typing import Any, Dict, List, Optional, Type

from transformers import PreTrainedTokenizer

from diagnnose.models import LanguageModel
from diagnnose.syntax.tasks import (
    LakretzTask,
    LinzenTask,
    MarvinTask,
    ResultsDict,
    SyntaxEvalTask,
    WarstadtTask,
    WinobiasTask,
)

task_constructors: Dict[str, Type[SyntaxEvalTask]] = {
    "lakretz": LakretzTask,
    "linzen": LinzenTask,
    "marvin": MarvinTask,
    "warstadt": WarstadtTask,
    "winobias": WinobiasTask,
}


class SyntacticEvaluator:
    """Suite that runs multiple syntactic evaluation tasks on a LM.

    Tasks can be run on already extracted activations, or on a new LM
    for which new activations will be extracted.

    Initialisation is performed separately from the tasks themselves,
    in order to allow multiple LMs to be ran on the same set of tasks.

    Parameters
    ----------
    tokenizer : PreTrainedTokenizer
        Tokenizer that converts tokens to their index within the LM.
    config : Dict[str, Any]
        Dictionary mapping a task name (`lakretz`, `linzen`, `marvin`,
        or `winobias`) to its configuration (`path`, `tasks`, and
        `task_activations`). `path` points to the corpus folder of the
        task, `tasks` is an optional list of subtasks, and
        `task_activations` an optional path to the folder containing
        the model activations.
    """

    def __init__(
        self,
        model: LanguageModel,
        tokenizer: PreTrainedTokenizer,
        config: Dict[str, Any],
        ignore_unk: bool = False,
        use_full_model_probs: bool = True,
        tasks: Optional[List[str]] = None,
    ) -> None:
        self.tasks: Dict[str, SyntaxEvalTask] = {}

        print("Initializing syntactic evaluation tasks...")

        for task_name in tasks or config.keys():
            constructor = task_constructors.get(task_name, SyntaxEvalTask)

            self.tasks[task_name] = constructor(
                model,
                tokenizer,
                ignore_unk=ignore_unk,
                use_full_model_probs=use_full_model_probs,
                **config[task_name],
            )

        print("Syntactic evaluation task initialization finished")

    def run(self) -> Dict[str, Any]:
        results: Dict[str, ResultsDict] = {}

        for task_name, task in self.tasks.items():
            print(f"\n--=={task_name.upper()}==--")

            results[task_name] = task.run()

        return results
