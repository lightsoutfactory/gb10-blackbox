# gb10-blackbox

A flight recorder for NVIDIA GB10 machines: DGX Spark and the other boxes built around the same chip (ASUS Ascent GX10, Lenovo ThinkStation PGX, Dell Pro Max with GB10 and the rest). When the machine switches itself off, it tells you whether it was heat.

When a GB10 machine powers off on its own, the system journal simply ends mid-sentence: a hard power-off never gives journald time to write its last minutes. The hardware watchdog does nothing either, because nothing hung: the power was gone. And after a full power loss the clock can come back with an old date. So the one question you have, *why did it switch off?*, has no answer in the logs.

This keeps one line a minute, written through to disk with `fsync`, so the minute before a power-off survives it:

```
2026-11-19T08:43:21Z hot=95 zones=95,86,95,85,94,86,87 gpu=82C,49.5W,96%,2437MHz load=15.26,13.76,12.00 mem=113342/123970MB
```

Every thermal zone, the hottest of them, GPU temperature, power, utilisation and SM clock, load and memory. One Python file, standard library only, a systemd timer, nothing else.

## After a power-off: `gb10-blackbox why`

Every gap of more than five minutes in the record, the last readings before it, and a verdict. A restart someone asked for leaves a clean shutdown in `wtmp`, so it is told apart from a power-off:

```
$ gb10-blackbox why --show 3
191,624 readings from 2026-07-05 10:02 to 2026-11-18 18:15 UTC; 10 gap(s) of more than 5 minutes
...
2026-09-13 14:49 UTC  dark for 55 min
  CLEAN: a clean shutdown at 14:50 UTC is in wtmp: a restart someone asked for.
...
2026-11-14 10:28 UTC  dark for 31 min
  HEAT: the hottest sensor read 98 C in the last 10 minutes. The GPU was nearly idle (0% at 500 MHz), so the heat came from the CPU cores, not from GPU work.
    10:26 UTC  hottest  96 C  gpu  78 C   9.0 W   0%  500 MHz  load  5.05  mem 78,140/124,545 MB
    10:27 UTC  hottest  98 C  gpu  78 C   8.9 W   0%  500 MHz  load  2.54  mem 77,387/124,545 MB
    10:28 UTC  hottest  95 C  gpu  78 C   9.1 W   0%  500 MHz  load  8.46  mem 78,090/124,545 MB

CLEAN 3, COOL 1, HEAT 6
```

The verdicts: **HEAT** (the hottest sensor reached 93 °C or more in the ten minutes before; change it with `--hot`), **MEMORY** (less than 3% of memory free: a hang is likelier, and a hang is what a hardware watchdog reboots), **COOL** (look at the power supply and cable, or a hang) and **CLEAN** (a planned restart).

## How hot does it run: `gb10-blackbox bands`

```
$ gb10-blackbox bands
42,559 readings over the last 30 days (to 2026-11-18 18:15 UTC); hottest sensor:
  median 89 C, highest 98 C
   85 C or more:  73.5% of minutes
   90 C or more:  47.9% of minutes
   93 C or more:  29.8% of minutes
   95 C or more:  18.0% of minutes
   97 C or more:   8.8% of minutes
  100 C or more:   0.0% of minutes
  with the GPU busy (90% or more, 1,786 minutes): SM clock median 494 MHz, highest 1976 MHz; GPU power median 17 W
```

Set your alarms from these numbers, not from a guess: an alarm at this machine's average temperature rings all day.

## Install

```sh
git clone https://github.com/lightsoutfactory/gb10-blackbox
cd gb10-blackbox
sudo ./install.sh                      # the black box: a reading every minute to /var/log/gb10-blackbox.log
sudo ./install.sh --clock-cap 2000     # the same, and cap the GPU clock at 2000 MHz now and at every boot
```

Then `gb10-blackbox now` prints a reading, `gb10-blackbox why` and `gb10-blackbox bands` read the record. The record keeps itself under 64 MB, between six months and a year of minutes. `sudo ./uninstall.sh` removes everything and resets the GPU clock; `--purge` deletes the record too. Python 3.8 or newer, which DGX OS has.

## The clock cap

On GB10, `nvidia-smi -pl` cannot set a power limit (it answers N/A), but `nvidia-smi -lgc 0,2000` can lock the GPU clock range, and that is the one GPU knob that cut heat for us: on our hottest machine it took the hottest zone from 91 °C to 77 to 83 °C within seconds. Two details matter:

- **Apply it before the heavy services start.** Our first cap ran about 15 seconds after boot, when the model server was already loading at full power, which is the moment that had crashed the machine. `gb10-clock-cap.service` runs before Docker, containerd and Ollama, and waits until the driver answers.
- **Check it under load.** With the cap on, the GPU clock still reads about 2,400 MHz while the GPU is idle. Under load it holds at 1,976 MHz.

It costs speed in GPU-bound work, so measure your own tokens per second with and without it.

## What our machines taught us

One of our GB10 machines, the one with the worst cooling, recorded 10 gaps between July and November: 3 planned restarts, 1 unplanned stop at a cool 85 °C, and 6 power-offs with the hottest sensor at 95 to 98 °C in the minutes before.

- **It switched off well below the trip point it reports.** The ACPI critical trip point reads 104.8 °C, and the record never saw 100 °C. A reading a minute misses short peaks, but do not treat the reported trip point as the safe limit.
- **The GPU was not always the heater.** The three latest power-offs came with the GPU idle at 500 MHz, because a heat guard had already paused GPU work: the CPU cores alone kept the chip at 95 to 98 °C.
- **Software does not fix cooling.** The cap, the guard and the record kept this machine useful; the cause was physical. If a GB10 machine switches itself off under load, check its airflow and the space around it first.

The whole story, with the mistakes we made on the way: [Our GB10 machine kept switching itself off. The log blamed memory; it was heat](https://lightsoutfactory.ai/field-notes/gb10-switching-off-heat/).

## More than a record

The black box tells you why after the fact. [Factory Floor](https://lightsoutfactory.ai/kits/factory-floor/) acts before: it pauses the heavy jobs you name at a set temperature (92 °C by default) and resumes them below a lower one (84 °C), with memory and disk guards beside it, a health check that judges a busy vLLM server by its own counters instead of queueing a test request behind real work, a doctor for the failures you already know, and one readable email instead of a hundred. It is one of the kits of [LightsOut Factory](https://lightsoutfactory.ai/), built and tested on our own GB10 machines.

## Licence

MIT. Tests: `python3 -m unittest discover -s tests`.
