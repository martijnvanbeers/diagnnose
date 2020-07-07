import os
from typing import Any, Dict, List, Optional

import torch

from diagnnose.corpus.create_iterator import create_iterator
from diagnnose.corpus import Corpus
from diagnnose.typedefs.models import LanguageModel

from torchtext.data import Example

from ..misc import calc_final_hidden, create_unk_sen_mask
from .preproc import ENVS, create_downstream_corpus, preproc_warstadt


def warstadt_init(
    vocab_path: str,
    path: str,
    subtasks: Optional[List[str]] = None,
    device: str = "cpu",
    **kwargs: Any,
) -> Dict[str, Dict[str, Any]]:
    """ Initializes the tasks described in Warstadt et al. (2019)

    Paper: https://arxiv.org/pdf/1901.03438.pdf
    Data: https://alexwarstadt.files.wordpress.com/2019/08/npi_lincensing_data.zip

    Parameters
    ----------
    vocab_path : str
        Path to vocabulary file of the Language Model.
    path : str
        Path to the original corpus.
    subtasks : List[str], optional
        The licensing environments that will be tested. If not provided
        this will default to the full set of environments.
    device : str, optional
        Torch device name on which model will be run. Defaults to cpu.

    Returns
    -------
    init_dict : Dict[str, Dict[str, Any]]
        Dictionary containing the initial env setup, mapping each env
        to to required fields.
    """
    if subtasks is None:
        subtasks = ENVS

    init_dict: Dict[str, Dict[str, Any]] = {}

    orig_corpus = preproc_warstadt(path)[0]

    for env in subtasks:
        assert env in ENVS, f"Provided env {env} is not recognised!"

        raw_corpus = create_downstream_corpus(orig_corpus, envs=[env])

        header = raw_corpus[0].split('\t')
        tokenize_columns = ["sen", "counter_sen"]
        fields = Corpus.create_fields(header, tokenize_columns=tokenize_columns)
        examples = [
            Example.fromlist(line.split("\t"), fields.items()) for line in raw_corpus
        ]
        corpus = Corpus(
            examples,
            fields,
            vocab_path=vocab_path,
            tokenize_columns=tokenize_columns,
        )

        iterator = create_iterator(
            corpus, batch_size=len(corpus), device=device, sort=True
        )

        init_dict[env] = {"corpus": corpus, "iterator": iterator}

    return init_dict


def warstadt_downstream(
    init_dict: Dict[str, Dict[str, Any]],
    model: LanguageModel,
    ignore_unk: bool = True,
    add_dec_bias: bool = False,
    **kwargs: Any,
) -> Dict[str, Dict[str, float]]:
    """ Performs the downstream tasks described in Warstadt et al. (2019)

    Paper: https://arxiv.org/pdf/1901.03438.pdf
    Data: https://alexwarstadt.files.wordpress.com/2019/08/npi_lincensing_data.zip

    Parameters
    ----------
    init_dict : Dict[str, Dict[str, Any]]
        Dictionary created using `warstadt_init` containing the initial
        task setup.
    model : LanguageModel
        Language model for which the accuracy is calculated.
    ignore_unk : bool, optional
        Ignore cases for which at least one of the cases of the verb
        is not part of the model vocabulary. Defaults to True.
    add_dec_bias : bool
        Toggle to add the decoder bias to the score that is compared.
        Defaults to False.

    Returns
    -------
    accs_dict : Dict[str, float]
        Dictionary mapping a licensing env to the model accuracy.
    """
    accuracies = {env: 0.0 for env in init_dict.keys()}
    for env, init_env in init_dict.items():
        print(f"\n{env}")
        corpus = init_env["corpus"]
        iterator = init_env["iterator"]

        skipped = 0

        for batch in iterator:
            all_sens = [ex.sen for ex in corpus.examples]
            final_hidden = calc_final_hidden(model, batch, all_sens)
            wfinal_hidden = calc_final_hidden(
                model, batch, all_sens, sort_sens=True, sen_column="counter_sen"
            )

            classes = torch.tensor(
                [corpus.vocab.stoi[npi] for npi in batch.npi]
            ).unsqueeze(1)

            if ignore_unk:
                # We base our mask on the correct sentences and apply that to both cases
                mask = create_unk_sen_mask(corpus.vocab, all_sens)
                skipped = int(torch.sum(mask))
                classes = classes[~mask]
                final_hidden = final_hidden[~mask]
                wfinal_hidden = wfinal_hidden[~mask]

            probs = torch.bmm(model.decoder_w[classes], final_hidden.unsqueeze(2))
            probs = probs[:, :, 0]
            wprobs = torch.bmm(model.decoder_w[classes], wfinal_hidden.unsqueeze(2))
            wprobs = wprobs[:, :, 0]
            if add_dec_bias:
                probs += model.decoder_b[classes]
                wprobs += model.decoder_b[classes]

            acc = torch.mean((probs > wprobs).to(torch.float)).item()
            accuracies[env] = acc

            print(f"{env}:\t{acc:.3f}")
            if skipped > 0:
                print(f"{skipped:.0f}/{batch.batch_size} items were skipped.\n")
                skipped = 0

    # shutil.rmtree(TMP_DIR)

    return accuracies
