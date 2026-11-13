"""Classification service: label a topic's posts with the scheme its topic file defines.

Two workflows: one model (docs/07-classify.md), or tiers that settle easy
posts cheaply and send only the hard ones to a stronger model
(docs/08-escalating-labels.md). A model is sent a position number and text,
never a uri.

Command: python -m bluesky_bots.classify --help
"""
from .scheme import BASE_INSTRUCTION, Item, build_instruction, build_label_model, is_unsure, label_rows
from .tiers import build_tiered_workflow, classifier_path, load_classifiers
from .train import save_classifier, threshold_table, train_classifier, training_set
from .workflow import build_workflow, run_workflow

__all__ = ["BASE_INSTRUCTION", "Item", "build_label_model", "build_instruction", "is_unsure",
           "label_rows", "build_workflow", "run_workflow", "build_tiered_workflow",
           "classifier_path", "load_classifiers", "training_set", "train_classifier",
           "threshold_table", "save_classifier"]
