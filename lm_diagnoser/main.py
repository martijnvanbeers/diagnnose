from collections import namedtuple

from models.lstm import ForwardLSTM
from extractors.init_extractor import Extractor
# from classifiers.logreg import run_experiments

MODEL_DIR = './models'
OUTPUT_EMBS_DIR = './data/extracted_embs'
PRETRAINED_EMBS_DIR = './data/pretrained_embs'
PARSED_DATA_DIR = './data/parsed'

GapSentence = namedtuple('GapSentence', ['sen', 'raw', 'labels', 'filler', 'gap_start', 'gap_end', 'dep_len'])
LM = namedtuple('LM', ['model_type', 'model_path', 'vocab_path', 'init_embs', 'vocab_size', 'hidden_size'])

models = {
    'gulordava': ForwardLSTM(
        MODEL_DIR + '/gulordava/model.pt',
        MODEL_DIR + '/gulordava/vocab.txt',
    ),
}

if __name__ == '__main__':
    extractor = Extractor(
        models['gulordava'],
        PARSED_DATA_DIR + '/gapsens.pickle',
        [(1, 'hx'), (1, 'cx')]
    )
    extractor.extract(OUTPUT_EMBS_DIR)