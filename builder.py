# builder.py
"""Akıcı (fluent) PipelineBuilder.

    pipeline = (PipelineBuilder.from_(FileLineSource(girdi))
                .via(ParserStage())
                .via(PredicateFilterStage(min_status(400)))
                .via(ProjectionStage("timestamp", "clientIp", "status", "path"))
                .to(FileSink(cikti)))

Not: Python'da `from` ayrılmış bir sözcüktür, bu yüzden başlangıç metodu `from_`.
4. haftada bu birleştirme işini yapılandırma (configuration) devralacak;
builder o zaman da aynen kullanılabilir.
"""
from typing import List

from interfaces import Sink, Source, Stage
from pipeline import Pipeline


class PipelineBuilder:

    def __init__(self, source: Source):
        if not isinstance(source, Source):
            raise TypeError(f"Source bekleniyordu, gelen: {type(source).__name__}")
        self._source = source
        self._stages: List[Stage] = []
        self._built = False

    @classmethod
    def from_(cls, source: Source) -> "PipelineBuilder":
        return cls(source)

    def via(self, stage: Stage) -> "PipelineBuilder":
        """Hatta bir aşama ekler. Aşamalar eklenme sırasıyla çalışır."""
        self._ensure_not_built()
        if not isinstance(stage, Stage):
            raise TypeError(f"Stage bekleniyordu, gelen: {type(stage).__name__}")
        self._stages.append(stage)
        return self

    def to(self, sink: Sink) -> Pipeline:
        """Hattı bir Sink ile bitirir ve çalıştırılabilir Pipeline döndürür."""
        self._ensure_not_built()
        if not isinstance(sink, Sink):
            raise TypeError(f"Sink bekleniyordu, gelen: {type(sink).__name__}")
        pipeline = Pipeline(self._source, sink)
        for stage in self._stages:
            pipeline.add_stage(stage)
        self._built = True
        return pipeline

    def _ensure_not_built(self) -> None:
        if self._built:
            raise RuntimeError("Bu builder zaten bir Pipeline üretti; yeni bir builder kullanın")
