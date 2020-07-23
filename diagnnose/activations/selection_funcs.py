from typing import List

from torchtext.data import Example

from diagnnose.typedefs.activations import SelectionFunc


def return_all(_w_idx: int, _item: Example) -> bool:
    """ Always returns True for every token. """
    return True


def final_token(w_idx: int, item: Example) -> bool:
    """ Only returns the final token of a sentence. """
    return len(item.sen) == (w_idx + 1)


def first_n(n: int) -> SelectionFunc:
    """ Wrapper that creates a selection_func that only returns True for
    the first `n` items of a corpus.
    """

    def selection_func(_w_idx: int, item: Example) -> bool:
        return item.sen_idx < n

    return selection_func


def nth_token(n: int) -> SelectionFunc:
    """ Wrapper that creates a selection_func that only returns True for
    the `n^{th}` token of a sentence.
    """

    def selection_func(w_idx: int, _item: Example) -> bool:
        return w_idx == n

    return selection_func


def in_sen_ids(sen_ids: List[int]) -> SelectionFunc:
    """ Wrapper that creates a selection_func that only returns True for
    a `sen_id` if it is part of the provided list of `sen_ids`.
    """

    def selection_func(_w_idx: int, item: Example) -> bool:
        return item.sen_idx in sen_ids

    return selection_func
