"""
The script generates predictions of the level of functioning that is described in a clinical note in Dutch. The predictions are made for 9 WHO-ICF domains: 'ADM', 'ATT', 'BER', 'ENR', 'ETN', 'FAC', 'INS', 'MBW', 'STM'.

The script can be customized with the following parameters:
    --in_csv: path to input csv file
    --text_col: name of the column containing the text

To change the default values of a parameter, pass it in the command line, e.g.:

$ python main.py --in_csv myfile.csv --text_col notitie_tekst
"""


import spacy
import argparse
import warnings
import pandas as pd
from pathlib import Path
from shutil import ReadError
from src.text_processing import anonymize
from src.icf_classifiers import predict_domains, predict_levels


def add_level_predictions(
    sents,
    domains,
):
    """
    For each domain, select the sentences in `sents` that were predicted as discussing this domain. Apply the relevant levels regression model to get level predictions and join them back to `sents`.

    Parameters
    ----------
    sents: pd DataFrame
        df with sentences and `predictions` of the domains classifier
    domains: list
        list of all the domains, in the order in which they appear in the multi-label

    Returns
    -------
    sents: pd DataFrame
        the input df with additional columns containing levels predictions
    """
    for i, dom in enumerate(domains):
        boolean = sents['predictions'].apply(lambda x: bool(x[i]))
        results = sents[boolean]
        if results.empty:
            print(f'There are no sentences for which {dom} was predicted.')
        else:
            print(f'Generating levels predictions for {dom}.')
        lvl_model = f'CLTL/icf-levels-{dom.lower()}'
        predictions = predict_levels(results['text'], 'roberta', lvl_model).rename(f"{dom}_lvl")
        sents = sents.join(predictions)
    return sents


def main(
    in_csv,
    text_col,
):
    """
    Read the `in_csv` file, process the text by row (anonymize, split to sentences), predict domains and levels per sentence, aggregate the results back to note-level, write the results to the output file.

    Parameters
    ----------
    in_csv: str
        path to csv file with the text to process; the csv must follow the following specs: sep=';', quotechar='"', encoding='utf-8', first row is the header
    text_col: str
        name of the column containing the text

    Returns
    -------
    None
    """

    domains=['ADM', 'ATT', 'BER', 'ENR', 'ETN', 'FAC', 'INS', 'MBW', 'STM']
    levels = [f"{domain}_lvl" for domain in domains]

    # check path
    in_csv = Path(in_csv)
    msg = f'The csv file cannot be found in this location: "{in_csv}"'
    assert in_csv.exists(), msg

    # read csv
    print(f'Loading input csv file: {in_csv}')
    try:
        df = pd.read_csv(
            in_csv,
            sep=';',
            header=0,
            quotechar='"',
            encoding='utf-8',
            low_memory=False,
        )
        print(f'Input csv file ({in_csv}) is successfuly loaded!')
    except:
        raise ReadError('The input csv file cannot be read. Please check that it conforms with the required specifications (separator, header, quotechar, encoding).')

    if len(df) > 3000:
        warnings.warn('The csv file contains more than 3,000 rows. This is not recommended since it might cause problems when generating predictions; consider splitting to several smaller files.')

    # anonymize
    print(f'Anonymizing the text in "{text_col}" column. This might take a while.')
    nlp = spacy.load('nl_core_news_lg')
    anonym_notes = df[text_col].apply(lambda i: anonymize(i, nlp)).rename('anonym_text')

    # split to sentences
    print(f'Splitting the text in "{text_col}" column to sentences. This might take a while.')
    to_sentence = lambda txt: [str(sent) for sent in list(nlp(txt).sents)]
    sents = anonym_notes.apply(to_sentence).explode().rename('text').reset_index().rename(columns={'index': 'note_index'})

    # predict domains
    print('Generating domains predictions. This might take a while.')
    sents['predictions'] = predict_domains(
        sents['text'],
        'roberta',
        'CLTL/icf-domains',
    )

    # predict levels
    print('Processing domains predictions.')
    sents = add_level_predictions(sents, domains)

    # aggregate to note-level
    note_predictions = sents.groupby('note_index')[levels].mean()
    df = df.merge(
        note_predictions,
        how='left',
        left_index=True,
        right_index=True,
    )

    # save output file
    out_csv = in_csv.parent / (in_csv.stem + '_output.csv')
    df.to_csv(out_csv, sep='\t', index=False)
    print(f'The output file is saved: {out_csv}')


if __name__ == '__main__':

    argparser = argparse.ArgumentParser()
    argparser.add_argument('--in_csv', default='./example/input.csv')
    argparser.add_argument('--text_col', default='text')
    args = argparser.parse_args()

    main(
        args.in_csv,
        args.text_col,
    )
