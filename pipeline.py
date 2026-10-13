# pipeline.py
from contextlib import ExitStack
from typing import Any, Callable, List
from interfaces import Source, Sink, Stage, Emitter

class PipelineEmitter(Emitter[Any]):
    def __init__(self, target_callback: Callable[[Any], None]):
        self.target_callback = target_callback

    def emit(self, item: Any) -> None:
        self.target_callback(item)


class Pipeline:
    def __init__(self, source: Source[Any], sink: Sink[Any]):
        self.source = source
        self.sink = sink
        self.stages: List[Stage[Any, Any]] = []

    def add_stage(self, stage: Stage[Any, Any]) -> 'Pipeline':
        self.stages.append(stage)
        return self

    def run(self) -> None:
        # Yaşam döngüsü (LIFO): kaynak -> aşamalar -> sink sırasıyla açılır,
        # tam ters sırada kapanır. ExitStack, bir aşama hata verse bile
        # açılmış olan HER bileşenin close() çağrılmasını garanti eder
        # (aksi halde FileSink arabellekteki çıktıyı sessizce kaybeder).
        with ExitStack() as opened:
            for component in [self.source, *self.stages, self.sink]:
                component.open()
                opened.callback(component.close)

            # Akış zincirini kuruyoruz (Sink'ten geriye doğru)
            current_emitter: Emitter[Any] = PipelineEmitter(lambda item: self.sink.consume(item))

            for stage in reversed(self.stages):
                nxt = current_emitter
                def make_closure(stg=stage, n=nxt):
                    return PipelineEmitter(lambda item: stg.process(item, n))
                current_emitter = make_closure()

            # Kaynaktan üretilen verileri akışa ver
            self.source.produce(current_emitter)
