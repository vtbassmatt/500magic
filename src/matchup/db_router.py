MTGJSON_MODELS = {'card', 'cardidentifiers'}


class MtgjsonRouter:
    """Route unmanaged mtgjson models to the mtgjson database."""

    def db_for_read(self, model, **hints):
        if model._meta.model_name in MTGJSON_MODELS:
            return 'mtgjson'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.model_name in MTGJSON_MODELS:
            return 'mtgjson'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if model_name in MTGJSON_MODELS:
            return False
        if db == 'mtgjson':
            return False
        return None
