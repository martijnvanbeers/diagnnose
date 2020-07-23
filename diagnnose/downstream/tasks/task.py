import warnings
from typing import Dict, Optional, Union

import torch
from torch import Tensor
from torch.nn.functional import log_softmax
from torchtext.data import Example

from diagnnose.activations.selection_funcs import final_token
from diagnnose.corpus import Corpus
from diagnnose.extract import simple_extract
from diagnnose.typedefs.activations import SelectionFunc
from diagnnose.typedefs.models import LanguageModel

# subtask -> Corpus | (condition -> Corpus)
DownstreamCorpora = Dict[str, Union[Corpus, Dict[str, Corpus]]]
# subtask -> accuracy | (condition -> accuracy)
ResultsDict = Dict[str, Union[float, Dict[str, float]]]


# TODO: allow already extracted activations to be read from file
# TODO: allow downstream task based on decomposed state
class DownstreamTask:
    """

    Parameters
    ----------
    model : LanguageModel
        Language model for which the accuracy is calculated.
    vocab_path : str
        Path to vocabulary file of the Language Model.
    device : str, optional
        Torch device name on which model will be run. Defaults to cpu.
    """

    def __init__(self, model: LanguageModel, vocab_path: str, *args, **kwargs):
        model.eval()
        self.model = model
        self.vocab_path = vocab_path

        self.corpora: DownstreamCorpora = self.initialize(*args, **kwargs)

    def initialize(self, *args, **kwargs) -> DownstreamCorpora:
        raise NotImplementedError

    def run(
        self, ignore_unk: bool = False, use_full_model_probs: bool = True
    ) -> ResultsDict:
        """ Performs the downstream task that has been initialised.

        Parameters
        ----------
        ignore_unk : bool, optional
            Ignore cases for which at least one of the cases of the verb
            is not part of the model vocabulary. Defaults to False.
        use_full_model_probs : bool, optional
            Toggle to calculate the full model probs for the NPI sentences.
            If set to False only the NPI logits will be compared, instead
            of their Softmax probabilities. Defaults to True.

        Returns
        -------
        results : ResultsDict
            Dictionary mapping a downstream task to a task condition to
            the model accuracy.
        """
        results: ResultsDict = {}

        for subtask, subtask_corpora in self.corpora.items():
            if isinstance(subtask_corpora, Corpus):
                accuracy = self.run_single_corpus(
                    subtask_corpora, subtask, ignore_unk, use_full_model_probs
                )
                results[subtask] = accuracy
                continue

            for condition, corpus in subtask_corpora.items():
                accuracy = self.run_single_corpus(
                    corpus, subtask, ignore_unk, use_full_model_probs
                )

                results.setdefault(subtask, {})[condition] = accuracy

        return results

    def run_single_corpus(
        self, corpus: Corpus, subtask: str, ignore_unk: bool, use_full_model_probs: bool
    ) -> float:
        activations = self.calc_final_hidden(corpus)
        counter_activations = None

        if self.calc_counter_sen(subtask):

            def selection_func(w_idx: int, item: Example) -> bool:
                return len(item.counter_sen) == (w_idx + 1)

            counter_activations = self.calc_final_hidden(
                corpus, sen_column="counter_sen", selection_func=selection_func
            )

        accuracy = self.calc_accuracy(
            corpus,
            activations,
            counter_activations=counter_activations,
            use_full_model_probs=use_full_model_probs,
            ignore_unk=ignore_unk,
        )

        return accuracy

    def calc_final_hidden(
        self,
        corpus: Corpus,
        sen_column: str = "sen",
        selection_func: SelectionFunc = final_token,
    ) -> Tensor:
        activation_name = (self.model.top_layer, "hx")

        activation_reader, _ = simple_extract(
            self.model,
            corpus,
            [activation_name],
            batch_size=len(corpus),
            selection_func=selection_func,
            sen_column=sen_column,
        )

        activations = torch.cat(activation_reader[:, activation_name], dim=0)

        return activations

    @staticmethod
    def calc_counter_sen(*args, **kwargs) -> bool:
        """ Specify conditions when the activations of a second
        sentence should be computed, for a P(w|h1) > P(w|h2) test.
        Defaults to False, and should be overridden if necessary.
        """
        return False

    def calc_accuracy(
        self,
        corpus: Corpus,
        activations: Tensor,
        counter_activations: Optional[Tensor] = None,
        use_full_model_probs: bool = True,
        ignore_unk: bool = False,
    ) -> float:
        mask = self.create_unk_sen_mask(corpus, ignore_unk)

        activations = activations[mask]

        token_ids = torch.tensor([corpus.vocab.stoi[ex.token] for ex in corpus])
        token_ids = token_ids[mask]

        if counter_activations is None:
            counter_token_ids = torch.tensor(
                [corpus.vocab.stoi[ex.counter_token] for ex in corpus]
            )
            counter_token_ids = counter_token_ids[mask]

            accuracy = self.single_context_accuracy(
                activations, token_ids, counter_token_ids
            )
        else:
            accuracy = self.dual_context_accuracy(
                activations, counter_activations[mask], token_ids, use_full_model_probs
            )

        return accuracy

    @staticmethod
    def create_unk_sen_mask(corpus: Corpus, ignore_unk: bool) -> Tensor:
        """
        Creates a tensor mask for sentences that contain at least one
        token that is not part of the model vocabulary.
        """
        mask = torch.ones(len(corpus), dtype=torch.uint8)
        if not ignore_unk:
            return mask

        for idx, ex in enumerate(corpus):
            for w in ex.sen:
                if w not in corpus.vocab.stoi:
                    mask[idx] = False
                    warnings.warn(f"'{w}' is not part of model vocab!")

        return mask

    def single_context_accuracy(
        self, activations: Tensor, token_ids: Tensor, counter_token_ids: Tensor
    ) -> float:
        """ Computes activations for comparing P(w1|h) > P(w2|h). """
        activations = activations.unsqueeze(2)

        decoder_w = self.model.decoder_w[token_ids].unsqueeze(1)
        decoder_b = self.model.decoder_b[token_ids]
        counter_decoder_w = self.model.decoder_w[counter_token_ids].unsqueeze(1)
        counter_decoder_b = self.model.decoder_b[counter_token_ids]

        logits = torch.bmm(decoder_w, activations).squeeze()
        logits += decoder_b

        counter_logits = torch.bmm(counter_decoder_w, activations).squeeze()
        counter_logits += counter_decoder_b

        return torch.mean((logits >= counter_logits).to(torch.float)).item()

    def dual_context_accuracy(
        self,
        activations: Tensor,
        counter_activations: Tensor,
        token_ids: Tensor,
        use_full_model_probs: bool,
    ) -> float:
        """ Computes activations for comparing P(w|h1) > P(w|h2). """
        decoder_w = self.model.decoder_w
        decoder_b = self.model.decoder_b

        if use_full_model_probs:
            logits = activations @ decoder_w.t() + decoder_b
            counter_logits = counter_activations @ decoder_w.t() + decoder_b

            probs: Tensor = log_softmax(logits, dim=1)
            counter_probs: Tensor = log_softmax(counter_logits, dim=1)

            batch_size = logits.shape[0]
            probs = probs[range(batch_size), token_ids]
            counter_probs = counter_probs[range(batch_size), token_ids]

            return torch.mean((probs >= counter_probs).to(torch.float)).item()

        decoder_w = decoder_w[token_ids].unsqueeze(1)

        logits = torch.bmm(decoder_w, activations.unsqueeze(2))
        counter_logits = torch.bmm(decoder_w, counter_activations.unsqueeze(2))

        return torch.mean((logits >= counter_logits).to(torch.float)).item()