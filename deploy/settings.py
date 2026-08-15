"""CORA-COMP deployment settings: select the competition + install its plugin."""
from comp_eval_platform.settings import *  # noqa: F401,F403

ACTIVE_COMPETITION = "cora"
INSTALLED_APPS += ["cora_comp"]  # noqa: F405
