# The held-out month

`config/heldout.yaml` (H1) was written before any held-out run, and run once at commit `ac3b827`
(`config/heldout.lock`), with the code and the gate that dev ended on. The numbers below are from
`reports/heldout.json`.

## What it changed

March 2026 instead of October: colder (mean 5 °C), the start of summer time on 29 March (a 92-quarter-hour day), more
heat pumps, EVs and smart charging (421 devices instead of 346), and roughly twice every fault: 6 stuck registers,
71 counter resets, 867 register-days sent first as substitute values, 25 files delivered twice, half the meters on the
operator without UTC offsets, a third of the other operator's days in UTC with a `Z`, more trade amendments and
cancellations, and more imbalance price revisions.

## What came out

All 13 gate lines passed.

| | first version | this warehouse |
|---|---|---|
| portfolio energy off from the truth | 34.6 MWh (8.9%) | 0.15 MWh (0.04%) |
| quarter hours within 0.5% of the true net load | 0% | 100% |
| imbalance cost for the month (truth €131) | -€4,723 | €127 |
| days with procurement cost within 1% | 3% | 100% |
| attribution off from the truth | €20,443 | €238 |

The first version got much worse than on dev, because more meters send local times without an offset and more trades
are amended. The warehouse's error went down, most likely because its only estimates are the values behind stuck registers, which weigh
less in a colder month with twice the load.

## What it showed

1. **The split between household base load and EV charging is the weak spot.** The class errors for base (19.7 MWh)
   and EV (17.4 MWh) are almost equal and opposite, on dev as well (13.6 and 11.8 MWh). Base load is metered load minus
   the devices. When a charger's HEMS goes offline for hours, its counter is interpolated linearly over the gap, so
   the energy lands in the wrong quarter hours, and base absorbs the difference. Totals stay right, but the imbalance
   cost attributed to EVs was -€48 against a true -€156. The fix belongs in `int_device_qh`: spread a gap's energy
   along the charger's own schedule (smart chargers follow the cheapest day-ahead quarter hours) instead of linearly.
   It has to be measured on dev, by the class errors in `reports/dev.json`. Not done yet.
2. **The leaking feature set was worse even in its own backtest** (20.2 kWh against 17.9 kWh per quarter hour), and
   still 1.1 kWh more optimistic than in production. In a month where the weather moves load more, the newest weather
   run is less like the run the desk had at the gate. The honest features backtested at exactly what production got,
   as on dev.
3. **The desk's own forecast still beats the model** (13.3 against 17.9 kWh). The model shows the features are safe;
   it does not replace the desk's class-by-class forecast.
4. **A counting error in the report, not in the warehouse.** The held-out report says 856 of 867 substitute
   register-days were "seen". The world counted import and export registers separately and the report counted meter
   days. The count was fixed in `ftd/eval/run.py` and checked on dev (325 of 325). The gate line it backs,
   no substitute value left once a measured one arrived, was 0 in both months.

The held-out month is not run again, and `config/gate.yaml` was not moved.
