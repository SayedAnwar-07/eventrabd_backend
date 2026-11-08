
from django.apps import AppConfig


class EventServicesConfig(AppConfig):

    default_auto_field = "django.db.models.BigAutoField"

    name = "apps.event_services"

    verbose_name = "Event Services"

    def ready(self):
        from . import signals
