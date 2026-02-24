# 🦅 Hummingbird Sim

**Wireless Power Transmission simulation platform for defense logistics**

Hummingbird Sim models laser and microwave power beaming over 1–5 km to reduce fuel convoy exposure for military forward operating bases (FOBs). It covers physics, hardware design, safety, operational scenarios, and financial modeling end-to-end.

---

## What It Does

| Module | File | What it models |
|---|---|---|
| **Laser physics** | `src/laser.py` | Gaussian beam propagation, atmospheric attenuation (Beer-Lambert), turbulence (Rytov/Fried), pointing jitter, PV conversion |
| **Microwave physics** | `src/microwave.py` | Friis transmission, phased array gain, rectenna conversion, rain/fog attenuation (ITU-R P.676) |
| **Hardware design** | `src/hardware.py` | Aperture sizing, BOM + costs, thermal model, weight/form factor |
| **Safety** | `src/safety.py` | Laser NOHD (ANSI Z136.1/IEC 60825), RF exposure (IEEE C95.1/ICNIRP), interlock modeling |
| **Scenarios** | `src/scenarios.py` | Operational impact: fuel saved, convoys eliminated, generator hours |
| **Financial** | `src/financial.py` | ROI, NPV/IRR, SBIR alignment, convoy economics, Wright's Law scaling |
| **Charts** | `src/charts.py` | Efficiency vs. range, link budget waterfall, safety zones, financial dashboard |

---

## Quick Start

```bash
# Set up virtual environment
python3 -m venv .venv && source .venv/bin/activate
pip install numpy scipy matplotlib pandas

# Compare laser vs microwave (MVP: 5 kW @ 2 km, clear sky)
python hummingbird.py

# Single modality
python hummingbird.py --mode laser
python hummingbird.py --mode microwave

# Range sweep (0.5–10 km, all weather conditions)
python hummingbird.py --mode sweep

# Safety analysis
python hummingbird.py --mode safety

# Hardware design + BOM
python hummingbird.py --mode hardware

# Financial model + SBIR alignment
python hummingbird.py --mode financial

# Everything + save charts
python hummingbird.py --mode all --charts --output output/
```

---

## MVP Results (5 kW target @ 2 km, clear sky)

### Laser (1070 nm Yb fiber)
- **DC delivered:** 2.3 kW (limited by 6 cm beam aperture × 50 cm PV receiver)
- **System efficiency:** ~6% (wall-plug → DC)
- **Electrical input needed:** 37.5 kW
- **Fuel saved:** 19 L/day (6,800 L/yr)
- **Convoys eliminated:** ~22/yr
- **Operational value:** ~$490k/yr

### Microwave (5.8 GHz, 1024-element phased array)
- **DC delivered:** ~1 W (beam footprint = 110m radius >> 5 m² receiver)
- **System efficiency:** ~0.004%
- **Verdict:** Microwave WPT is **not viable at km-scale** with practical apertures — beam divergence is the fundamental limit. Would need a 103m TX aperture for tight beam at 2 km.

**→ Laser is the clear winner at 1–5 km range.**

---

## Key Physics Insights

### Why laser wins at km-scale
A 7.5 cm laser aperture at 1070 nm has a Rayleigh range of ~13.8 km — it stays nearly collimated out to 2 km. The beam is only ~7.6 cm radius at the receiver, so a 50 cm PV aperture captures nearly 100% of the optical power.

A microwave phased array (1024 elements at 5.8 GHz) has a ~83 cm physical aperture and a 3.6° beam half-angle. At 2 km, the footprint is 110m radius. You'd need a stadium-sized receiver.

### Atmospheric sensitivity (laser)
| Condition | Efficiency @ 2 km |
|---|---|
| Clear | 8.2% |
| Haze | 1.4% |
| Smoke | 0.02% |
| Rain | 3.7% |

Smoke is the primary operational threat — attenuation is 10/km vs 0.1/km clear. This should drive energy buffer sizing and fail-safe design.

### Safety highlights
- **Laser NOHD:** >1,000 km (15 kW beam) — hard beam corridor and interlock mandatory
- **RF exclusion zone:** 135m occupational, 303m public — manageable with fixed installation
- **Laser path:** engineering controls (exclusion zone, tracking interlock, auto-shutoff <10ms) are the required mitigation strategy per MIL-STD-1425A

---

## Architecture

```
hummingbird-sim/
├── hummingbird.py          # CLI entrypoint
├── src/
│   ├── __init__.py
│   ├── laser.py            # Gaussian beam physics, PV conversion
│   ├── microwave.py        # Friis transmission, phased arrays, rectennas
│   ├── hardware.py         # System sizing, BOM, thermal model
│   ├── safety.py           # NOHD, RF limits, interlock scenarios
│   ├── scenarios.py        # Operational impact simulation
│   ├── financial.py        # ROI, NPV/IRR, SBIR, scaling curves
│   └── charts.py           # Matplotlib visualization
└── output/                 # Generated charts + reports
    ├── range_sweep.png
    ├── safety_zones.png
    └── financial_summary.png
```

---

## Financial Summary (default assumptions: $500k system, 10yr life)

| Metric | Value |
|---|---|
| Annual diesel saved | 6,900 L / $83k |
| Convoy cost saved | $716k/yr (38 convoys eliminated) |
| CAPEX | $575k (incl. install) |
| Simple payback | 9.9 years |
| NPV (10yr @ 8%) | -$160k (energy savings alone) |
| NPV w/ convoy value | +$5M+ |
| IRR | 1.7% energy only → >100% w/ convoy |
| Expected lives saved | 0.19/yr per system |

**SBIR alignment:** Phase I fits at $250k with a lean 3-person team (hardware BOM <$80k). Phase II is tight at $1.75M — requires careful scope control.

---

## Sources

Physics implementations cite:
- Saleh & Teich — *Fundamentals of Photonics* (Gaussian beams)
- Andrews & Phillips — *Laser Beam Propagation through Random Media* (turbulence)
- ITU-R P.676 (microwave atmospheric absorption)
- ANSI Z136.1 / IEC 60825-1 (laser safety)
- IEEE C95.1-2019 / ICNIRP (RF exposure)
- RAND Corp / Army studies (convoy cost: $400–800/mile)
- DoD fully-burdened fuel cost: ~$12/L at remote FOB
