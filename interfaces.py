# interfaces.py
from abc import ABC, abstractmethod
from typing import TypeVar, Generic

I = TypeVar('I')
O = TypeVar('O')
T = TypeVar('T')

class Emitter(Generic[T], ABC):
    @abstractmethod
    def emit(self, item: T) -> None:
        pass

class Stage(Generic[I, O], ABC):
    @abstractmethod
    def process(self, input_item: I, out: Emitter[O]) -> None:
        pass

    def open(self) -> None:
        """Lifecycle hook: Başlangıç işlemleri için."""
        pass

    def close(self) -> None:
        """Lifecycle hook: Kaynakları serbest bırakmak için."""
        pass

class Source(Generic[T], ABC):
    @abstractmethod
    def produce(self, out: Emitter[T]) -> None:
        pass

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

class Sink(Generic[I], ABC):
    @abstractmethod
    def consume(self, item: I) -> None:
        pass

    # v3: Sink'e de yaşam döngüsü kancaları eklendi (FileSink buna muhtaçtır).
    def open(self) -> None:
        """Lifecycle hook: çıktı kaynağını (dosya, bağlantı...) açmak için."""
        pass

    def close(self) -> None:
        """Lifecycle hook: arabelleği boşaltıp kaynağı serbest bırakmak için."""
        pass
