# Alt modülleri burada eager import etmek, yalnızca `vertex_client` isteyen ETL işlerinde
# dahi katalog/GCS/DB yüklemesini tetikliyordu. Geriye uyumlu isimler gerektiğinde lazy yüklenir.
from importlib import import_module

__all__ = [
    "feature_extractor",
    "FeatureExtractor",
    "rag_engine",
    "RAGEngine",
]

_LAZY_EXPORTS = {
    "feature_extractor": (".feature_extractor", "feature_extractor"),
    "FeatureExtractor": (".feature_extractor", "FeatureExtractor"),
    "rag_engine": (".rag_engine", "rag_engine"),
    "RAGEngine": (".rag_engine", "RAGEngine"),
}


def __getattr__(name):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(name)
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
