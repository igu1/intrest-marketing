def apply():
    from copy import copy as _copy
    from django.template import context as _ctx

    old = _ctx.BaseContext.__copy__

    def _safe_copy(self):
        duplicate = self.__class__.__new__(self.__class__)
        if hasattr(self, "__dict__"):
            duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    _ctx.BaseContext.__copy__ = _safe_copy
