from typing import List, Optional, Union

from torchtext.data import Field, Pipeline, RawField, TabularDataset

from diagnnose.vocab import attach_vocab


def import_corpus(
    path: str,
    header: Optional[List[str]] = None,
    header_from_first_line: bool = False,
    to_lower: bool = False,
    vocab_path: Optional[str] = None,
    vocab_from_corpus: bool = False,
    sen_column: str = "sen",
    labels_column: str = "labels",
    tokenize_columns: Optional[List[str]] = None,
) -> TabularDataset:
    """ Imports a corpus from a path.

    The corpus can either be a raw string or a pickled dictionary.
    Outputs a `Corpus` type, that is used throughout the library.

    The raw sentence is assumed to be labeled `sen`.
    Sentences can optionally be labeled, which are assumed to be labeled
    by a `labels` tag.

    Parameters
    ----------
    path : str
        Path to corpus file
    header : List[str], optional
        Optional list of attribute names of each column. If not provided
        all lines will be considered to be sentences, with the
        attribute name "sen". In case the corpus file contains 2 columns
        the header ["sen", "labels"] will be assumed.
    to_lower : bool, optional
        Transform entire corpus to lower case, defaults to False.
    header_from_first_line : bool, optional
        Use the first line of the corpus as the attribute names of the
        corpus.
    vocab_path : str, optional
        Path to the model vocabulary, which should a file containing a
        vocab entry at each line.
    vocab_from_corpus : bool, optional
        Create a new vocabulary from the tokens of the corpus itself.
        If set to True `vocab_path` does not need to be provided.
        Defaults to False.
    sen_column : str, optional
        Name of the corpus column containing the raw sentences.
        Defaults to `sen`.
    labels_column : str, optional
        Name of the corpus column containing the sentence labels.
        Defaults to `labels`.
    tokenize_columns : List[str], optional
        List of column names that should be tokenized according to the
        provided vocabulary.

    Returns
    -------
    corpus : TabularDataset
        A TabularDataset containing the parsed sentences and optional labels
    """
    if tokenize_columns is None:
        tokenize_columns = []

    if header is None:
        if header_from_first_line:
            with open(path) as f:
                header = next(f).strip().split("\t")
        else:
            with open(path) as f:
                first_line = next(f).strip().split("\t")
            if len(first_line) == 2:
                header = [sen_column, labels_column]
            else:
                header = [sen_column]

    assert sen_column in header, "`sen` should be part of corpus_header!"

    def preprocess(s: str) -> Union[str, int]:
        return int(s) if s.isdigit() else s

    pipeline = Pipeline(convert_token=preprocess)
    fields = {}
    for field in header:
        if field == sen_column or field in tokenize_columns:
            fields[field] = Field(
                batch_first=True, include_lengths=True, lower=to_lower
            )
        elif field == labels_column:
            fields[field] = Field(
                use_vocab=True, pad_token=None, unk_token=None, is_target=True
            )
        else:
            fields[field] = RawField(preprocessing=pipeline)
            fields[field].is_target = False

    corpus = TabularDataset(
        fields=fields.items(),
        format="tsv",
        path=path,
        skip_header=header_from_first_line,
        csv_reader_params={"quotechar": None},
    )

    # The current torchtext Vocab does not allow a fixed vocab order so should be attached manually.
    if vocab_path is not None or vocab_from_corpus:
        for column in tokenize_columns + [sen_column]:
            attach_vocab(corpus, vocab_path or path, sen_column=column)
    if labels_column in corpus.fields:
        corpus.fields[labels_column].build_vocab(corpus)

    return corpus
