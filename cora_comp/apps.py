from django.apps import AppConfig


class CoraCompConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cora_comp"
    label = "cora_comp"
    verbose_name = "CORA-COMP"

    def ready(self):
        from comp_eval_platform.competitions import register

        from . import steps  # noqa: F401  (registers step handlers)
        from .competition import CoraCompetition

        register(CoraCompetition)
