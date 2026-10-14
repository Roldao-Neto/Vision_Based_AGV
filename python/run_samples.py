"""Reassembly of the sample notifications of one recorded run (step, ramp).

The MCU sends <name>(record_id, first_index, total, [values...]) in order, with a fixed
number of values per sample (step: t_us, counts_l, counts_r; ramp: t_us, duty,
counts_l, counts_r). Every notification carries the total, so a run is complete when
the samples received so far are exactly 0..total-1, and a gap in first_index means a
notification was lost (the run is then repeated instead of fitted).
"""

from dataclasses import dataclass, field


@dataclass
class RunSamples:
    record_id: int
    width: int
    samples: list[tuple[int, ...]] = field(default_factory=list)
    total: int | None = None
    lost: bool = False

    def add(self, first: int, total: int, flat: list[int]) -> None:
        if first != len(self.samples) or len(flat) % self.width != 0 or (self.total is not None and total != self.total):
            self.lost = True
        self.total = total
        self.samples.extend(tuple(flat[i : i + self.width]) for i in range(0, len(flat), self.width))

    @property
    def complete(self) -> bool:
        return not self.lost and self.total is not None and len(self.samples) == self.total
