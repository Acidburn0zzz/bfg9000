from itertools import chain

from .iterutils import listify


def _get_prop(attr, desc):
    def inner(self, key):
        try:
            return getattr(self, attr)[key]
        except KeyError:
            raise ValueError('{} {!r} does not support {} {!r}'
                             .format(self._kind, self.name, desc, key))
    return inner


class _Info:
    _fields = ('vars',)

    def __init__(self, name, vars):
        self.name = name
        self._var = vars

    var = _get_prop('_var', 'var')


class _LanguageInfo(_Info):
    _kind = 'language'
    _fields = _Info._fields + ('exts', 'auxexts')

    def __init__(self, name, base, vars, exts, auxexts):
        super().__init__(name, vars)
        self._base = base

        allkeys = set(exts.keys()) | set(auxexts.keys())
        self._exts = {i: listify(exts.get(i)) for i in allkeys}
        self._auxexts = {i: listify(auxexts.get(i)) for i in allkeys}

    exts = _get_prop('_exts', 'file type')
    auxexts = _get_prop('_auxexts', 'file type')

    @property
    def src_lang(self):
        return self._base or self.name

    def allexts(self, key):
        return self.exts(key) + self.auxexts(key)

    def default_ext(self, key):
        exts = self.exts(key)
        if len(exts):
            return exts[0]
        return self.auxexts(key)[0]

    def extkind(self, ext):
        for k, v in chain(self._exts.items(), self._auxexts.items()):
            if ext in v:
                return k
        return None


class _FormatInfo(_Info):
    _kind = 'format'


class _Definer:
    def __init__(self, parent, type, name, **kwargs):
        self._parent = parent
        self._type = type
        self._name = name
        self._fields = set(type._fields)

        self._data = {i: {} for i in type._fields}
        for k, v in kwargs.items():
            assert k not in self._fields
            self._data[k] = v

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self._parent._add(self._type(self._name, **self._data))

    def __getattr__(self, attr):
        if attr not in self._fields:
            raise AttributeError(attr)

        def inner(**kwargs):
            self._data[attr] = kwargs

        return inner


class Languages:
    def __init__(self):
        self._langs = {}
        self._ext2lang = {}

    def __getitem__(self, name):
        try:
            return self._langs[name]
        except KeyError:
            raise ValueError('unrecognized language {!r}'.format(name))

    def __contains__(self, name):
        return name in self._langs

    def _add(self, info):
        self._langs[info.name] = info
        for kind, exts in info._exts.items():
            for ext in exts:
                if ext in self._ext2lang:
                    raise ValueError('{ext!r} already used by {lang!r}'.format(
                        ext=ext, lang=self._ext2lang[ext][0]
                    ))
                self._ext2lang[ext] = (info.name, kind)

    def fromext(self, ext, kind):
        lang, langkind = self.extinfo(ext)
        return lang if langkind == kind else None

    def extinfo(self, ext):
        return self._ext2lang.get(ext, (None, None))

    def make(self, name, base=None):
        return _Definer(self, _LanguageInfo, name, base=base)


class Formats:
    def __init__(self):
        self._formats = {}

    def __getitem__(self, name):
        try:
            return self._formats[name[0]][name[1]]
        except KeyError:
            raise ValueError("unrecognized format '{} ({})'"
                             .format(name[0], name[1]))

    def _add(self, info):
        name, mode = info.name
        if name not in self._formats:
            self._formats[name] = {}
        self._formats[name][mode] = info

    def make(self, name, mode):
        return _Definer(self, _FormatInfo, (name, mode))


known_langs = Languages()
known_formats = Formats()
