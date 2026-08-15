"""Test settings for the CORA variant: core's sqlite test settings + this plugin."""
from comp_eval_platform.settings_test import *  # noqa: F401,F403

ACTIVE_COMPETITION = "cora"
INSTALLED_APPS += ["cora_comp"]  # noqa: F405
ROOT_URLCONF = "deploy.urls"
