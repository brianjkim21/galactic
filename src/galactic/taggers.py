import re
import pathlib
from typing import Sequence, Callable, Optional
import numpy as np
import huggingface_hub
from transformers import AutoTokenizer
import scrubadub
from .kenlm import KenlmModel
from .utils import byte_len

import logging

logger = logging.getLogger("galactic")


def tag_string(self, fields: Sequence[str], values: Sequence[str], tag: str):
    # make sure the tag hasn't already been used
    if f"__tag__{tag}" in self.dataset.column_names:
        logger.warning(
            f"Tag {tag} already exists. This will overwrite the existing tag."
        )

    regexp = re.compile("|".join([re.escape(val) for val in values]))

    def tag_(sample):
        for field in fields:
            if field in sample:
                if isinstance(sample[field], str):
                    if regexp.search(sample[field]):
                        return {f"__tag__{tag}": True}
                else:
                    if regexp.search(str(sample[field])):
                        return {f"__tag__{tag}": True}
        return {f"__tag__{tag}": False}

    self.dataset = self.dataset.map(tag_)
    logger.info(
        f"Tagged dataset in-place with exact string matching on fields: {fields}"
    )
    # return self for chaining
    return self


def tag_regex(self, fields: Sequence[str], regex: str, tag: str):
    # make sure the tag hasn't already been used
    if f"__tag__{tag}" in self.dataset.column_names:
        logger.warning(
            f"Tag already exists. This will overwrite the existing tag."
        )

    regexp = re.compile(regex)

    def tag_(sample):
        for field in fields:
            if field in sample:
                if isinstance(sample[field], str):
                    if regexp.search(sample[field]):
                        return {f"__tag__{tag}": True}
                else:
                    if regexp.search(str(sample[field])):
                        return {f"__tag__{tag}": True}
        return {f"__tag__{tag}": False}

    self.dataset = self.dataset.map(tag_)
    logger.info(
        f"Tagged dataset in-place with tag '__tag__{tag}', using regex matching on fields: {fields}"
    )
    return self


def detect_language(self, field: str):
    # make sure field exists
    if field not in self.dataset.features:
        raise ValueError(f"Field {field} not found in dataset.")
    import fasttext

    model_path = huggingface_hub.hf_hub_download(
        repo_id="TaylorAI/galactic-models", filename="lid.176.ftz"
    )
    model = fasttext.load_model(model_path)

    def detect_(sample):
        if isinstance(sample[field], str):
            return {
                "__language": model.predict(sample[field].replace("\n", " "))[
                    0
                ][0].split("__label__")[1]
            }
        else:
            return {
                "__language": model.predict(str(sample[field]))[0][0].split(
                    "__label__"
                )[1]
            }

    self.dataset = self.dataset.map(detect_)
    logger.info(
        f"Detected language in field {field}, added language metadata to '__language'."
    )
    return self


def calc_perplexity(
    self,
    field: str,
    model: str = "kenlm",  # other option is pythia
    language: Optional[str] = "en",
    dataset: Optional[str] = "wikipedia",
):
    # make sure field exists and is a string field
    if field not in self.dataset.features:
        raise ValueError(f"Field {field} not found in dataset.")
    elif self.dataset.features[field].dtype != "string":
        raise ValueError(
            f"Field {field} is not a string field, and so can't be used to calculate perplexity."
        )
    if model == "pythia":
        import ctranslate2

        repo_path = huggingface_hub.snapshot_download(
            "TaylorAI/galactic-models", allow_patterns="p70/*"
        )
        model_path = pathlib.Path(repo_path) / "p70"
        model = ctranslate2.Generator(str(model_path))
        tokenizer = AutoTokenizer.from_pretrained("EleutherAI/pythia-70m")

        def calc_(sample):
            token_ids = tokenizer(sample[field]).input_ids
            tokens = tokenizer.convert_ids_to_tokens(token_ids)
            log_probs = model.score_batch([tokens])[0].log_probs
            ppl = np.exp(-np.sum(log_probs) / byte_len(sample[field]))
            return {"__perplexity": ppl}

    elif model == "kenlm":
        if language is None or dataset is None:
            raise ValueError(
                "Must specify language (e.g. 'en') and dataset (e.g. 'wikipedia') for KenLM. See options here: https://huggingface.co/edugp/kenlm/tree/main"
            )
        model = KenlmModel.from_pretrained(dataset, language)

        def calc_(sample):
            ppl = model.get_perplexity(sample[field])
            return {"__perplexity": ppl}

    else:
        raise ValueError(
            f"Model {model} not supported. Supported models: 'kenlm', 'pythia'."
        )

    self.dataset = self.dataset.map(calc_)
    logger.info(
        f"Calculated perplexity-per-byte in field {field}, added perplexity metadata to '__perplexity'."
    )
    return self


def detect_pii(self, fields: Sequence[str]):
    """
    Detect personally identifiable information in the specified fields.
    Args:
        fields (List[str]): List of fields to detect PII in.
        Currently only supports "email", "phone", and "credential".
    """

    def detect_(sample):
        filth = []
        for field in fields:
            if field in sample:
                if isinstance(sample[field], str):
                    filth.extend(scrubadub.list_filth(sample[field]))
                else:
                    filth.extend(scrubadub.list_filth(str(sample[field])))
        filth_types = [f.detector_name for f in filth]
        return {
            **{
                f"__pii__{f}": f in filth_types
                for f in ["email", "phone", "credential"]
            },
            "__pii__any": len(filth) > 0,
        }

    self.dataset = self.dataset.map(detect_)
    logger.info(
        f"Detected PII in fields: {fields}; added __pii__email, __pii__phone, __pii__credential, and __pii__any metadata."
    )
    # no option to do out-of-place as this operation is not destructive
    return self


def detect_seo_spam(self, field: str):
    """
    Uses a FastText model distilled from GPT-3.5-turbo to flag documents likely to be SEO spam or otherwise
    repetitive, machine-generated, or worthless. Trained on web documents from Falcon RefinedWeb, unlikely to
    perform well out-of-distribution. Preprocessing is built-in, we just lowercase -> replace \n with space.
    """
    # make sure field exists in dataset and are strings
    if field not in self.dataset.features:
        raise ValueError(f"Field {field} not found in dataset.")
    elif self.dataset.features[field].dtype != "string":
        raise ValueError(
            f"Field {field} is not a string field, and so can't be used to detect SEO spam."
        )

    import fasttext

    model_path = huggingface_hub.hf_hub_download(
        repo_id="TaylorAI/galactic-models", filename="seo_spam.ftz"
    )
    model = fasttext.load_model(model_path)

    def detect_(sample):
        result = model.predict(
            sample[field].replace("\n", " ").lower()
        )  # [0][0].split("__label__")[1]
        label, prob = result[0][0].split("__label__")[1], result[1][0]
        if label == "discard":
            return {
                f"__seo_spam__{field}": True,
                f"__seo_spam_prob__{field}": prob,
            }
        return {
            f"__seo_spam__{field}": False,
            f"__seo_spam_prob__{field}": 1 - prob,
        }

    self.dataset = self.dataset.map(detect_)
    logger.info(
        f"Detected SEO spam in fields '{field}'; added __seo_spam metadata."
    )
    # no option to do out-of-place as this operation is not destructive
    return self


def count_tokens(self, fields: Sequence[str], tokenizer: Optional[str] = None):
    """
    Count the number of tokens in the specified fields.
    Args:
        fields (List[str]): List of fields to count tokens in.
        tokenizer (Callable): Tokenizer function to use. Defaults to None, which uses bytes.
    """
    if tokenizer is None:
        # count bytes in string
        count_fn = lambda x: byte_len(str(x))
        field_name = "__byte_count__"
    else:
        tokenizer = AutoTokenizer.from_pretrained(tokenizer)
        count_fn = lambda x: len(tokenizer(str(x)).input_ids)
        field_name = "__token_count__"
    self.dataset = self.dataset.map(
        lambda x: {
            f"{field_name}{field}": count_fn(x[field]) for field in fields
        }
    )
    logger.info(
        f"Counted tokens in fields: {fields}, added metadata to {field_name}"
    )

    # no option to do out-of-place as this operation is not destructive
    return self
