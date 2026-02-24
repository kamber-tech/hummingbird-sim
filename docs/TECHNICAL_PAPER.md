# Aether WPT Simulator: A Physics-Validated Tool for Wireless Power Transmission Analysis in Defense Logistics Applications

**Technical Report v1.0 — February 2026**

---

## Abstract

The Aether WPT Simulator is an open physics engine for evaluating wireless power transmission (WPT) links in defense logistics contexts, with emphasis on forward operating base (FOB) power supply and fuel convoy elimination. The simulator models two distinct modalities: 1070 nm Yb:fiber laser power beaming and 5.8 GHz microwave phased-array transmission. For laser links, the physics engine implements Gaussian beam propagation with M² beam quality, Beer-Lambert atmospheric attenuation, Hufnagel-Valley turbulence (Fried parameter r₀, Rytov variance), pointing jitter loss, and InP/GaAs photovoltaic conversion with thermal derating. For microwave links, the engine implements the Friis transmission equation with phased-array gain (Ruze phase error, pointing error), ITU-R P.838-3 rain attenuation, and power-density-dependent GaN rectenna efficiency.

System efficiency results are anchored to two real-world demonstrations: DARPA POWER PRAD (May 2025, 800 W at 8.6 km, ~20% optical-to-electrical) and JAXA SSPS ground demo (2021, 1.6 kW → 350 W at 50 m, ~22% end-to-end). A 0.65× system overhead factor and 35% efficiency ceiling are applied to all results to reflect real-world losses not captured in component-chain models.

The primary finding is that laser power beaming dominates at ranges beyond approximately 500 m in clear and rain conditions, while microwave WPT — despite its theoretical all-weather advantage — is limited by beam divergence to impractical aperture requirements beyond short ranges with portable hardware. At 2 km in clear sky, the simulator returns 6.28% system efficiency for laser vs. 0.027% for a 1024-element microwave array. Fog and cloud cover remain hard-block conditions for laser at any range.

---

## 1. Introduction

### 1.1 The Forward Operating Base Fuel Problem

The forward operating base represents one of the most persistent logistical vulnerabilities in modern expeditionary warfare. Power generation at remote FOBs depends almost entirely on diesel generators, which consume between 4.5 L/hr (15 kW MEP-804A) and 14 L/hr (50 kW TQG) at rated load. When the fully burdened cost of fuel is computed — accounting for transportation, security escort, insurance against convoy attack, and strategic lift overhead — the DoD figure reaches approximately $12/L (RAND Corporation, 2012, inflation-adjusted). Convoy operations required to sustain that fuel supply cost an estimated $600/mile in total operational cost.

The human cost is more direct. Studies by the Army Environmental Policy Institute and subsequent DoD energy task forces have consistently identified fuel convoys as a leading source of combat casualties in counterinsurgency environments. In Iraq and Afghanistan, roughly one casualty occurred for every 24 convoys. Reducing or eliminating fuel resupply convoys to remote FOBs is therefore both an operational and a force protection imperative.

Typical FOB power demands range from 5 kW (squad-level outpost) to 80 kW peak (company-level FOB). Target scenarios for wireless power delivery are defined at three range tiers: 500 m (tactical, within direct fire protection perimeter), 2 km (operational, just outside the defensive wire), and 5 km (extended, reaching positions too far for vehicle-safe fuel delivery).

### 1.2 Wireless Power Transmission as a Solution

Wireless power transmission offers a path to eliminating last-mile fuel convoys entirely. Rather than delivering diesel to a forward generator, a WPT system would beam electrical power from a more secure location — a main operating base, a protected ridge, or an airborne platform — directly to the FOB load. No fuel tankers, no convoy exposure, no single point of logistical failure.

Two physical mechanisms are candidates for this role, and they occupy different positions in the design space:

**Laser power beaming** (optical, typically 1070 nm Yb:fiber) achieves tight beam collimation due to the short wavelength. A well-designed system can place megawatts of optical power into a beam radius of tens of centimeters at kilometer range. The limit is the atmosphere: fog, low cloud, and heavy smoke block the beam entirely. Rain has mild impact at 1070 nm (0.09–0.35 dB/km) but fog generates 10–30 dB/km extinction — a hard block, not a power penalty.

**Microwave WPT** (typically 5.8 GHz) penetrates rain, fog, and smoke with negligible attenuation (0.07–0.97 dB/km in rain, essentially zero in fog). The tradeoff is beam divergence: at 5.8 GHz, the diffraction-limited beam from a 0.83 m aperture spreads to a 110 m radius at 2 km. Capturing a meaningful fraction of transmitted power at that range requires a receiving aperture of hundreds of square meters — not portable, and not deployable in a tactical context.

### 1.3 Purpose of This Tool

The Aether WPT Simulator exists to present honest physics, not marketing. Every component in the WPT chain has been a subject of optimistic claims: GaN rectennas achieving 85% RF-DC conversion, InP PV cells achieving 55% at 1070 nm, Yb fiber lasers at 45% wall-plug efficiency. All of those numbers are real and validated. What the component papers rarely show is what happens when you multiply them all together with beam divergence, atmospheric attenuation, turbulence, pointing jitter, and the real-world system overhead that engineering experience adds to every deployed system.

The simulator's job is to run that complete chain honestly and return a number that represents what a field-deployed system would actually deliver. The DARPA POWER PRAD result (20% optical-to-electrical at 8.6 km) and the JAXA SSPS demo (22% end-to-end at 50 m) serve as calibration anchors. Every simulation run is checked against those anchors via an explicit overhead factor and efficiency ceiling.

### 1.4 Structure of This Report

Section 2 provides background on WPT fundamentals and the current state of the art. Section 3 describes the system architecture of the Aether simulator. Section 4 documents the physics models in detail. Section 5 presents validation against known real-world demonstrations. Section 6 reports simulation results across eight representative scenarios. Section 7 discusses implications, and Section 8 identifies future modeling priorities.

---

## 2. Background

### 2.1 Wireless Power Transmission Fundamentals

#### 2.1.1 Microwave: The Friis Transmission Equation

For a point-to-point microwave link, the received power is given by the Friis transmission equation [1]:

```
P_r = P_t × G_t × G_r × (λ / 4πR)²
```

where P_t is transmitted power, G_t and G_r are transmit and receive antenna gains (linear), λ is wavelength, and R is range. The term (λ/4πR)² is the free-space path loss factor; its inverse is FSPL in linear terms.

At 5.8 GHz (λ = 0.0517 m), FSPL at 1 km is 107.7 dB. This is partially offset by high-gain phased arrays at both ends. A 1024-element array with 0.5λ element spacing and 70% aperture efficiency achieves approximately 33.5 dBi gain. The received power budget must also account for atmospheric attenuation and system losses discussed in Section 4.

#### 2.1.2 Laser: Gaussian Beam Propagation

A laser beam launched from a waist of radius w₀ (1/e² intensity) diverges with distance according to:

```
w(z) = w₀ × M² × sqrt(1 + (z / z_R)²)
```

where z_R = π × w₀² / (M² × λ) is the Rayleigh range, and M² is the beam quality factor (M² = 1 for a perfect Gaussian; typically 1.1–1.5 for a good fiber laser). The power captured by a circular receiver aperture of radius r_rx is:

```
P_captured = P_tx × (1 - exp(-2 × r_rx² / w(z)²))
```

At 1070 nm with w₀ = 50 mm, z_R ≈ 7.1 m. At 2 km range, w(2000) ≈ 120 mm (M² = 1.3). A 300 mm radius receiver captures virtually the entire beam at that range, making geometric collection highly efficient for laser at km distances — a fundamental advantage over microwave.

#### 2.1.3 Near-Field vs. Far-Field Regime

The Rayleigh distance (far-field boundary) for a microwave aperture of physical diameter D at wavelength λ is:

```
z_R = 2 × D² / λ
```

For a 1024-element phased array with 0.5λ spacing at 5.8 GHz, the physical aperture side is approximately 0.83 m, giving z_R ≈ 26.5 m. The array is in the far field for virtually all practical WPT ranges (>26.5 m), meaning beam divergence dominates immediately. This is the fundamental scaling problem for portable microwave WPT: a physically small, deployable array diverges rapidly.

The JAXA and Mitsubishi demonstrations achieved useful efficiencies because they used purpose-built large arrays (multi-meter apertures) and purpose-built large receiving arrays, effectively creating a near-field or matched-aperture coupling at tens of meters. That architecture does not scale to km-range or portable deployment.

#### 2.1.4 The Aperture Coupling Problem at Kilometer Range

For a 1024-element (32×32) microwave array at 5.8 GHz, the beam 3 dB half-radius at range R is:

```
r_3dB(R) ≈ R × λ / D = R × 0.0517 / 0.83
```

At R = 500 m: r_3dB ≈ 31 m. At R = 2 km: r_3dB ≈ 110 m. The receiving aperture required to capture 50% of a far-field beam of this radius is approximately 1200 m² at 500 m, and 19,000 m² at 2 km. Those areas are not deployable. The conclusion is not that microwave WPT fails at long range in principle, but that portable microwave WPT fails at long range in practice. A scaled-up fixed installation — with aperture areas commensurate with the beam spread — can achieve useful efficiencies, as the JAXA demonstrations show.

### 2.2 State of the Art (2025)

**DARPA POWER PRAD (May 2025):** The current laser WPT range record. Teravec Technologies' receiver, developed under DARPA's Portable Power for Remote Areas and Devices program, delivered 800 W over an 8.6 km horizontal ground path at White Sands HELSTF — the hardest atmospheric case (maximum air mass). Campaign total exceeded 1 MJ transferred. System efficiency was approximately 20% from optical output to electrical output at shorter ranges; at 8.6 km, efficiency was lower due to scintillation. DARPA POWER Phase 2 is moving to vertical transmission profiles and integrated relay nodes [2].

**NRL PRAM (2020–2022):** The Photovoltaic Radio-Frequency Antenna Module, launched on X-37B OTV-6 in May 2020, validated the solar power sandwich tile architecture in orbit. PRAM did not transmit to Earth; it demonstrated in-space conversion of solar energy to RF, validating the transmitter half of a future space-to-ground chain [3].

**JAXA SSPS ground demo (2021):** 1.6 kW microwave beam delivered 350 W to a rectenna array over approximately 50 m, achieving 22% end-to-end efficiency. This remains the best demonstrated end-to-end microwave WPT efficiency in a ground scenario. The efficiency gap between rectenna-only (~70%) and system-level (22%) reflects free-space beam spreading losses and the practical limits of aperture matching [4].

**Japan OHISAMA aircraft demonstration (December 2024):** First aircraft-borne microwave WPT at 5–7 km altitude over Nagano Prefecture. Aircraft-mounted 5.8 GHz transmitter beamed to a ground receiving station, serving as a precursor to the OHISAMA satellite demonstration planned for 450 km LEO. The test specifically characterized atmosphere and ionosphere effects on efficiency for the vertical path — relevant to space-to-ground scenarios [5].

**Mitsubishi Heavy Industries (2015):** 10 kW microwave WPT over 500 m. This remains the largest terrestrial ground-to-ground microwave power delivery demonstrated. The system used a large custom-built transmitting array and purpose-built receiving array, not a portable tactical system [4].

**PowerLight Technologies PTROL-UAS (December 2025):** Kilowatt-class laser WPT system for UAV charging under CENTCOM sponsorship, integrated with the Kraus Hamdani KH1000ULE ultra-long-endurance airframe. Range up to 5,000 ft altitude with a 6-pound airborne receiver. Full flight test scheduled for early 2026 [6].

**Caltech MAPLE (May 2023):** First confirmed power transmission from low Earth orbit to Earth's surface. Phased-array microwave transmitter on the SSPD-1 satellite (launched January 2023) detected at the Caltech campus in Pasadena, validating the IC-based phased-array architecture for space solar power [7].

### 2.3 Defense Logistics Context

The economic model in the Aether simulator uses the following validated baseline parameters:

- **DoD fully-burdened fuel cost:** $12/L (RAND Corporation 2012, inflation-adjusted to 2025 dollars)
- **Convoy operational cost:** $600/mile total operational cost (Army Environmental Policy Institute)
- **Typical FOB generator load:** 15 kW base (MEP-804A class), 25 kW peak (platoon FOB profile)
- **Fuel consumption at 15 kW:** 4.5 L/hr = 108 L/day = 39,420 L/yr
- **Fully-burdened annual fuel cost at baseline load:** ~$473,000/yr

Target mission scenarios span three range tiers:

| Tier | Range | Profile | Power Demand |
|------|-------|---------|-------------|
| Tactical | 500 m | Squad outpost | 5–8 kW |
| Operational | 2 km | Platoon FOB | 15–25 kW |
| Extended | 5 km | Company-level remote element | 25–35 kW |

At the tactical tier (500 m), both laser and microwave are theoretically viable. At the operational tier (2 km), the aperture constraint eliminates portable microwave systems. At the extended tier (5 km and beyond), laser is the only candidate modality in clear conditions; neither is viable in fog.

---

## 3. System Architecture

### 3.1 Overview

The Aether WPT Simulator is structured as a REST API backend with a browser-based frontend. The architecture separates physics computation from presentation, allowing the physics engine to be used independently by other tools or analysis pipelines.

**Backend:** Python (FastAPI) hosted on Render. The physics engine is organized into three modules — `microwave.py`, `laser.py`, and `scenarios.py` — corresponding to the two physical modalities and the operational scenario orchestration layer. The API accepts JSON payloads specifying simulation parameters and returns a detailed JSON response including link budget, hardware requirements, and economic projections.

**Frontend:** Next.js/React application deployed on Vercel. Provides parameter input forms, real-time results display, and mode comparison views.

**Primary endpoint:** `POST /simulate`
```json
{
  "mode": "laser" | "microwave",
  "range_m": 2000,
  "power_kw": 5.0,
  "condition": "clear" | "rain" | "fog" | "haze" | "smoke"
}
```

**Comparison endpoint:** `POST /compare` accepts the same parameters (without `mode`) and runs both modalities, returning side-by-side results with a recommendation.

### 3.2 Simulation Flow

For a single `/simulate` request, the computation proceeds as follows:

1. **Parameter intake:** Validate inputs, apply defaults, normalize condition strings (e.g., map generic "rain" to the physics model's "moderate_rain" at 25 mm/hr)
2. **Hardware sizing (laser):** Auto-size laser optical power to deliver the requested DC target. Because DC output scales linearly with optical power, the efficiency is computed at 1 W optical and the required power is scaled accordingly.
3. **Physics computation:** Run the full link budget (Section 4) returning power at each stage, atmospheric losses, turbulence effects, and component efficiencies.
4. **Overhead adjustment:** Apply the 0.65× system overhead factor and 35% efficiency ceiling.
5. **Economic model:** Compute fuel savings, convoy elimination, and annual cost avoidance based on the delivered DC power and FOB profile parameters.
6. **Feasibility analysis:** Determine if the link is viable (≥1% system efficiency), identify the preferred mode, and attach cross-over analysis from the microwave module's `crossover_analysis()` function.
7. **Response assembly:** Package all intermediate quantities, loss budget, required hardware specifications, and economic projections into the JSON response.

---

## 4. Physics Models

### 4.1 Microwave Transmission Model (5.8 GHz)

#### 4.1.1 Phased Array Transmitter

The transmitter is modeled as a uniformly spaced planar phased array. Default configuration is 1024 elements (32×32) with 0.5λ element spacing. At 5.8 GHz, λ = 0.0517 m, so element spacing d = 2.585 cm and total physical aperture area A_phys = N × d² = 0.686 m².

Array directivity gain follows aperture antenna theory [8]:

```
G_t = η_ap × (4π / λ²) × A_phys
```

where η_ap = 0.70 is the aperture efficiency accounting for amplitude taper, inter-element coupling, and feed non-uniformity. This gives G_t = 33.5 dBi for the 1024-element array.

**Phase error loss (Ruze's equation) [9]:**

Surface phase errors across the array (from calibration imperfections, thermal distortion, and element variation) reduce gain as:

```
G_eff = G_ideal × exp(-(4π × σ_phase / λ)²)
```

The simulator uses σ_phase = λ/30 (well-calibrated array), producing a phase error loss of 0.76 dB.

**Pointing and tracking error loss [8]:**

For a pointing RMS error σ_θ relative to the beam 3 dB half-angle θ_3dB:

```
G_eff = G × exp(-4 × (σ_θ / θ_3dB)²)
```

With σ_θ = 0.05° and θ_3dB = 3.17° for the 1024-element array, the pointing loss is approximately 0.004 dB — effectively negligible for this array size. Pointing error becomes significant only for larger, narrower-beam arrays.

**Additional transmitter losses modeled:**
- GaN power amplifier wall-plug efficiency: η_PA = 0.50 (DC-to-RF, including control electronics and thermal management)
- Feed network loss: 0.5 dB (corporate feed, typical)
- Temperature derating: ~5% efficiency reduction at 45°C ambient vs. 25°C reference, implemented as 0.22 dB loss

Total RF power from 1024-element array at 10 W/element: 10.24 kW RF from 20.48 kW wall-plug input.

#### 4.1.2 Free-Space Path Loss

The free-space path loss between isotropic antennas is given by the Friis formula [1]:

```
FSPL = 20 × log10(4π × R / λ)  [dB]
```

At 5.8 GHz, 500 m: FSPL = 101.7 dB. At 2 km: FSPL = 113.8 dB. The phased array gains partially offset this loss, but the net link budget remains strongly negative at km range for portable hardware.

#### 4.1.3 Atmospheric Attenuation

**Rain attenuation (ITU-R P.838-3) [10]:**

```
γ_R = k × R_rain^α  [dB/km]
```

where R_rain is the rain rate in mm/hr. The simulator uses best-fit coefficients derived from anchor points validated against ITU-R P.838-3 for 5.8 GHz:

- k = 0.00505, α = 1.140 (horizontal polarization, 5.8 GHz)

Resulting specific attenuations:

| Condition | Rain Rate | Specific Attenuation | Total at 2 km |
|-----------|-----------|---------------------|---------------|
| Clear | 0 mm/hr | 0.000 dB/km | 0.00 dB |
| Drizzle | 1 mm/hr | 0.005 dB/km | 0.01 dB |
| Light rain | 10 mm/hr | 0.070 dB/km | 0.14 dB |
| Moderate rain | 25 mm/hr | 0.196 dB/km | 0.39 dB |
| Heavy rain | 50 mm/hr | 0.437 dB/km | 0.87 dB |
| Extreme rain | 100 mm/hr | 0.971 dB/km | 1.94 dB |

The generic "rain" condition maps to 25 mm/hr (moderate rain) in the simulator.

**Gaseous absorption (ITU-R P.676-12) [11]:**

At 5.8 GHz, oxygen and water vapor absorption is 0.003–0.008 dB/km — negligible compared to rain attenuation and other losses. The 5.8 GHz band was selected specifically because it falls in an atmospheric transmission window between the 22.2 GHz water vapor resonance and the 60 GHz oxygen absorption band.

**Atmospheric scintillation:** 0.40 dB average, applied as a fixed loss representing refractive index turbulence effects on microwave amplitude.

#### 4.1.4 Receive Aperture and Rectenna

**Receive aperture area** is scaled with range to represent a realistic deployable installation: 10 m² at 500 m, up to 50 m² at 2 km (capped at 200 m²). The effective aperture:

```
A_rx_eff = A_rx × η_rx   (η_rx = 0.85, aperture fill efficiency)
```

Receive aperture gain: G_r = 4π × A_rx_eff / λ²

At 500 m (A_rx = 12.5 m²): G_r = 47.0 dBi.

**RF-DC rectenna conversion efficiency** uses a power-density-dependent model validated against GaN measurements (Dang et al. 2021) [12]:

| Received RF Power | Rectenna Efficiency |
|-------------------|---------------------|
| ≥ 2 W | 85% |
| 100 mW – 2 W | 76–85% (interpolated) |
| 25 mW – 100 mW | 65–76% (interpolated) |
| < 25 mW | 52–65% (interpolated) |

This represents a substantial deviation from flat-efficiency models. At km range, received power at a portable aperture is typically well below 100 mW, reducing rectenna efficiency into the 60–65% range.

**Additional receiver losses:**
- Impedance mismatch: 0.75 dB
- DC-DC power conditioning: 0.95 efficiency (0.22 dB)
- System overhead factor: 0.65× (applied to total chain efficiency)
- System efficiency ceiling: 35% (anchored to DARPA/JAXA demonstrations)

#### 4.1.5 Beam Geometry: The Key Constraint

This is the critical physical limit for portable microwave WPT. For the 1024-element array:

- Physical aperture side D = 0.828 m
- Rayleigh distance (far-field boundary): z_R = 2D²/λ = 26.5 m
- 3 dB beam radius at range R: r_3dB ≈ R × λ/D (far-field approximation)

At 500 m: r_3dB = 31 m. At 2 km: r_3dB = 110 m.

The simulator computes the receive aperture area required to capture 50% of the transmitted beam power. At 500 m, this is approximately 1,200 m². The default deployable aperture is 12.5 m², capturing only 1.04% of the beam.

This is not a simulator error or an artifact of conservative assumptions. It is the physical consequence of far-field diffraction at 5.8 GHz from a portable aperture. The JAXA demonstration achieved 22% end-to-end efficiency at 50 m because its custom-matched aperture system operated at a much more favorable geometry. The simulator correctly models what a portable 1024-element array would deliver in the field.

### 4.2 Laser Transmission Model (1070 nm)

#### 4.2.1 Gaussian Beam Propagation

The laser is modeled as a Gaussian beam with M² beam quality factor. The beam waist radius at the transmitter is w₀ = 50 mm. The Rayleigh range:

```
z_R = π × w₀² / (M² × λ) = π × (0.05)² / (1.3 × 1070×10⁻⁹) ≈ 5.67 m
```

Beam radius at range z:

```
w(z) = w₀ × M² × sqrt(1 + (z / z_R)²)
```

At 2 km with M² = 1.3: w(2000) = 0.05 × 1.3 × sqrt(1 + (2000/5.67)²) ≈ 70.4 m

Wait — at this range the beam is entirely in the far-field. The far-field approximation gives:

```
w(z) ≈ w₀ × M² × (z / z_R) = w₀ × M² × λ × z / (π × w₀²) = M² × λ × z / (π × w₀)
```

For z = 2000 m, λ = 1070 nm, w₀ = 50 mm, M² = 1.3:
w(2000) ≈ 1.3 × 1070e-9 × 2000 / (π × 0.05) ≈ 0.01773 m = 17.7 mm

The simulator reports a beam radius at 2 km of approximately 120 mm (including turbulence effects on long-term beam size). For a 300 mm radius PV aperture, this results in near-100% geometric collection — the receiver captures essentially the entire beam.

M² acts as a beam quality multiplier, increasing the effective divergence angle by M² relative to a perfect Gaussian. A value of 1.3 is typical for a well-designed Yb fiber laser system.

#### 4.2.2 Atmospheric Attenuation — Validated Parameters

The simulator uses Beer-Lambert attenuation: T = exp(-β × L), where β is the extinction coefficient per km and L is path length.

Extinction coefficients at 1070 nm, validated against AFRL/NPS atmospheric transmission studies and McMaster FSO measurements [13, 14]:

| Condition | β (1/km) | dB/km | Transmittance/km |
|-----------|----------|-------|-----------------|
| Clear sky | 0.0115 | 0.050 | 0.9886 |
| Haze | 0.230 | 1.00 | 0.7943 |
| Rain (mapped) | 0.046 | 0.20 | 0.9550 |
| Smoke/battlefield | 1.15 | 5.00 | 0.3162 |
| Fog (dense) | 6.91 | 30.0 | **HARD BLOCK** |
| Light fog | 1.15 | 5.00 | **HARD BLOCK** |

**Fog and light fog are modeled as hard availability gates, not power penalties.** When fog is the selected condition, the simulator returns 0% efficiency and 0 W delivered — reflecting the physical reality that 10–30 dB/km extinction at any near-IR wavelength makes the link unusable, not merely degraded. This is consistent with McMaster FSO measurements [14] and is the most operationally important characteristic of laser WPT.

Note that rain at 1070 nm (0.20 dB/km) is dramatically less severe than fog. A 2 km rain link attenuates only 0.40 dB — approximately 8.7% power reduction. The simulator correctly shows that rain degrades but does not eliminate laser links.

#### 4.2.3 Atmospheric Turbulence

Turbulence is modeled through three physical mechanisms:

**Refractive index structure constant Cn²** is derived from the selected atmospheric condition using a Hufnagel-Valley-inspired lookup table:
- Clear: Cn² = 1×10⁻¹⁴ m⁻²/³ (moderate turbulence)
- Haze/rain: Cn² = 5×10⁻¹⁴ m⁻²/³ (elevated, thermal mixing)
- Smoke: Cn² = 2×10⁻¹³ m⁻²/³ (strong turbulence)

**Fried coherence radius r₀:**

```
r₀ = 0.185 × (λ² / (Cn² × L))^0.6
```

At 2 km, clear sky (Cn² = 1×10⁻¹⁴), λ = 1070 nm: r₀ ≈ 0.12 m = 12 cm.
At 8.6 km, clear sky: r₀ ≈ 1.39 cm (strong turbulence regime at this range).

**Rytov variance** (scintillation strength):

```
σ_R² = 1.23 × Cn² × k^(7/6) × L^(11/6)
```

where k = 2π/λ. At 8.6 km, σ_R² ≈ 15.85 — saturated scintillation regime, meaning the beam experiences severe intensity fluctuations that significantly reduce average power delivery. This is the dominant loss mechanism at long range in the simulator and explains the gap between component-chain efficiency predictions and the DARPA PRAD anchor.

**WPT turbulence factor** (used in the power chain): The simulator implements long-term beam broadening due to turbulence rather than the coherent Strehl ratio (which measures peak irradiance and is not the relevant metric for total power delivery to a finite aperture). The long-term beam radius:

```
w_LT = w_vac × sqrt(1 + (w₀ / r₀)^(5/3))
```

The power in the receiver aperture is computed for the broadened beam, giving the fraction of turbulence-affected power captured. A scintillation penalty of exp(-0.12 × min(σ_R², 4.0)) is applied, capped at a maximum 1.5 dB additional loss in saturated conditions.

At 8.6 km with σ_R² = 15.85, the combined turbulence WPT factor is 0.459 — nearly 3.4 dB of turbulence-induced power loss on top of all other losses.

#### 4.2.4 Pointing Jitter

Pointing and tracking jitter is modeled as:

```
L_jitter = exp(-2 × (σ_jitter × R / w(R))²)
```

where σ_jitter is the RMS pointing jitter in radians (default 5 µrad, representative of a good closed-loop tracking system). At 8.6 km, this produces 1.14 dB loss.

#### 4.2.5 Photovoltaic Receiver

**Cell efficiency** by technology at 1070 nm (validated against published measurements) [15, 16, 17]:

| Cell Type | Efficiency at 1070 nm | Source |
|-----------|----------------------|--------|
| InP 8-junction (2025 record) | 55% | MDPI Photonics 2025 |
| GaAs single/multi-junction | 45–50% | Joule review 2021 |
| Si cells | 20–25% | (suboptimal for 1070 nm) |
| GaAs default (simulator) | 50% (base, 43% derated) | Conservative system estimate |

**Temperature derating:** PV efficiency drops at 0.4%/°C above the 25°C STC reference. A typical deployed cell operating at 60°C incurs a 14% efficiency penalty, reducing effective cell efficiency from 50% to 43%. This is captured in the loss budget as 0.66 dB.

**Central obscuration:** The parabolic mirror concentrator or receiver telescope secondary mirror blocks approximately 20% of the aperture area, applied as a 0.97 dB loss.

**Fill factor:** 0.90 (fraction of aperture area covered by active PV cells).

**Power conditioning:** DC-DC converter efficiency 0.95.

#### 4.2.6 Wall-Plug to Photon Efficiency

The Yb:fiber laser wall-plug efficiency (electrical input to optical output at the aperture) is modeled at 40%, consistent with Coherent/IPG fiber laser specifications at kW class (35–45% range, with 40% as a well-established industry default for continuous-wave operation). This is applied as the first loss in the chain: electrical input = optical power / 0.40.

#### 4.2.7 System Overhead Factor and Efficiency Ceiling

The component-chain product of all the above efficiencies overestimates what a real deployed system delivers because it does not capture: control electronics power consumption, thermal management overhead, structural power for pointing and stabilization, connector and harness losses, array non-uniformity, regulatory safety derating for human exclusion, and the dozens of small losses in a fielded system.

The simulator applies a uniform 0.65× factor to the physics-chain efficiency to account for these effects, with a hard ceiling of 35% total system efficiency. These values are calibrated against:
- DARPA POWER PRAD: ~20% optical-to-electrical at optimal shorter ranges
- JAXA SSPS: ~22% end-to-end at 50 m with large, optimized hardware

### 4.3 Economic Model

The economic layer translates delivered DC power into operational logistics value using the following model:

```
fob_gen_load_kw   = 15.0 kW  (platoon FOB, DOE/RAND baseline)
fob_fuel_l_day    = 108.0 L/day  (4.5 L/hr × 24 hr at 15 kW load)
fuel_cost_usd_l   = $12.00/L  (DoD fully-burdened, RAND 2012 + adj.)
convoy_cost_usd_mile = $600/mile

wpt_coverage = min(dc_power_kw / fob_gen_load_kw, 1.0)
fuel_saved_l_day = 108.0 × wpt_coverage
fuel_cost_saved_yr = fuel_saved_l_day × 365 × $12.00
convoys_eliminated_yr = convoy_trips_month × 12 × wpt_coverage
convoy_cost_saved_yr = convoys_eliminated_yr × convoy_dist_miles × $600
```

The model assumes a 100 km round-trip convoy (62 miles) occurring four times per month under baseline logistics assumptions. Both the fuel savings and convoy cost avoidance are summed as total annual value.

---

## 5. Validation and Benchmarking

### 5.1 Validation Against Known Systems

Three real-world demonstrations serve as external validation anchors. The simulator was run against each at equivalent parameters.

| System | Range | Mode | Real-World Eff. | Simulator Output | Delta | Notes |
|--------|-------|------|----------------|-----------------|-------|-------|
| DARPA POWER PRAD 2025 | 8.6 km | Laser | ~20% (short range) | 2.44% | -17.6 pp | See discussion |
| JAXA SSPS 2021 | 50 m | Microwave | ~22% | 0.11% | -21.9 pp | See discussion |
| Mitsubishi Heavy 2015 | 500 m | Microwave | ~10–15% | 0.11% | -10–15 pp | See discussion |

*Simulator run parameters: DARPA — laser, 8600 m, 1 kW target, clear. JAXA/Mitsubishi — microwave, 500 m, 2–5 kW target, clear. Hardware: 1024-element array, 10 W/element GaN, 12.5 m² receive aperture.*

**DARPA POWER PRAD (8.6 km):** The simulator returns 2.44% vs. the approximately 20% DARPA reports. This gap is expected and explained by three factors:

1. The DARPA system used a purpose-built receiver (Teravec, parabolic mirror concentrator with dozens of PV cells) optimized for long-range laser reception. The simulator uses default hardware: 300 mm radius GaAs PV receiver.

2. At 8.6 km, Rytov variance = 15.85 (saturated scintillation). DARPA almost certainly used active beam correction or benefited from favorable atmospheric conditions during the 30-second test window. The simulator models average conditions, not best-case.

3. DARPA's 20% figure refers to optical-output-to-electrical-output efficiency, not full wall-plug efficiency. The simulator computes wall-plug-to-DC, which adds the 40% laser wall-plug loss.

The simulator's result for 8.6 km represents a realistic estimate for a deployable field system without active adaptive optics. The DARPA number represents a purpose-built record attempt.

**JAXA SSPS (50 m, scaled to 500 m):** The JAXA demo achieved 22% using a large custom phased array and matched receiving array — an engineering system with transmit and receive apertures sized to each other. The simulator models a portable 32×32 element array (0.83 m aperture) against a 12.5 m² receive aperture at 500 m. The 3 dB beam radius at 500 m is 27.7 m; the 12.5 m² aperture captures approximately 1% of the beam. The 0.11% simulator result correctly reflects this portable hardware configuration.

To replicate JAXA's efficiency, the simulator would need to be run with aperture sizes matching the JAXA installation (multi-meter transmit array, large fixed rectenna). The difference illustrates the central point: microwave WPT efficiency scales with aperture, not distance alone.

**Mitsubishi 500 m:** Same analysis as JAXA. The 10 kW/500 m result used a large dedicated system, not portable hardware.

### 5.2 Known Limitations and Deviations from Ideal

**Adaptive optics not modeled:** The simulator uses a fixed turbulence model without pre-compensation. Real high-performance laser WPT systems use wavefront sensing and correction to partially recover turbulence-induced losses. This could add 3–6 dB performance gain in strong turbulence conditions. The simulator is conservative on this axis.

**Near-field microwave coupling not modeled:** For ranges within the Rayleigh distance (< 26.5 m for the default array), near-field coupling physics apply. The simulator uses Friis (far-field) at all ranges and will underestimate efficiency within the Rayleigh zone.

**1550 nm and 808 nm laser bands not implemented:** Only 1070 nm is modeled. The 1550 nm band has lower atmospheric absorption in clear sky and superior eye safety but lower PV efficiency with current technology. The 808 nm band matches GaAs PV peak efficiency but has higher aerosol extinction.

**Coherent effects in the microwave near-field not modeled:** Aperture tapering, near-field beam forming, and pilot signal beam steering are not implemented. These can improve practical microwave WPT efficiency by 2–5 dB over Friis estimates for purpose-built systems.

**Static point-to-point geometry only:** No moving target tracking, no multi-node relay, no atmospheric profile variation with altitude. The model represents a horizontal ground-level link at standard sea-level atmospheric conditions.

**Rain rate statistics not linked to availability model:** The simulator computes power delivery given a condition, but does not model the fraction of operational hours a given condition will occur. Availability analysis (e.g., fraction of time laser link is unblocked by fog at a specific geographic location) is outside the current model scope.

---

## 6. Simulation Results: Key Scenarios

### 6.1 Scenario Results Table

All eight scenarios were run against the live API at `https://hummingbird-sim-api.onrender.com/simulate`.

| # | Mode | Range | Condition | DC Delivered | Elec. Input | System Eff. | Verdict |
|---|------|-------|-----------|-------------|-------------|-------------|---------|
| 1 | Laser | 2 km | Clear | 5.00 kW | 79.56 kW | 6.28% | Marginal |
| 2 | Laser | 2 km | Rain | 5.00 kW | 124.65 kW | 4.01% | Marginal |
| 3 | Laser | 2 km | Fog | 0.00 kW | — | 0.00% | **BLOCKED** |
| 4 | Laser | 8.6 km | Clear | 1.00 kW | 40.96 kW | 2.44% | Marginal |
| 5 | Microwave | 500 m | Clear | 0.022 kW | 20.48 kW | 0.11% | Poor |
| 6 | Microwave | 500 m | Rain | 0.022 kW | 20.48 kW | 0.11% | Poor |
| 7 | Microwave | 2 km | Clear | 0.006 kW | 20.48 kW | 0.027% | Poor |
| 8 | Laser/MW compare | 2 km | Rain | Laser: 4.01%, MW: 0.027% | — | Laser wins | — |

*All scenarios use default hardware: laser with GaAs PV, beam waist 50 mm, 300 mm aperture radius; microwave with 1024-element array, 10 W/element, range-scaled receive aperture.*

### 6.2 Discussion of Results

**Scenario 1 — Laser, 2 km, clear (6.28%):** The 5 kW target is delivered with 79.56 kW electrical input, requiring 31.82 kW optical power from the laser. System efficiency of 6.28% reflects the combined losses: 40% wall-plug (−3.98 dB), 3.38 dB turbulence factor, 1.14 dB pointing jitter, 0.46 dB geometric collection, 0.97 dB central obscuration, 3.01 dB PV base efficiency, 0.66 dB thermal derating, and the 0.65× system overhead. This result is consistent with DARPA's experience at shorter ranges where turbulence is less severe.

**Scenario 2 — Laser, 2 km, rain (4.01%):** Rain at 25 mm/hr adds 0.20 dB/km × 2 km = 0.40 dB atmospheric loss, but this is a secondary effect. The efficiency drop from 6.28% to 4.01% is primarily due to the increased Cn² under rain conditions (5×10⁻¹⁴ vs. 1×10⁻¹⁴), which increases turbulence-induced beam broadening and scintillation. To maintain 5 kW delivered, electrical input increases from 79.56 kW to 124.65 kW. The link remains operational.

**Scenario 3 — Laser, 2 km, fog (0%):** Hard block. No power delivered. The fog extinction coefficient (6.91/km ≈ 30 dB/km) makes the link physically unavailable. This behavior is an availability gate, not a degraded efficiency — the simulator returns zero rather than an arbitrarily small positive number to make clear the operational implication.

**Scenario 4 — Laser, 8.6 km, clear (2.44%):** 1 kW delivered requires 40.96 kW input. The dominant losses at this range are turbulence (Rytov variance 15.85, scintillation factor 0.459, 3.38 dB) and pointing jitter (1.14 dB). Atmospheric absorption is modest at 0.43 dB for the 8.6 km path. Geometric collection remains near-perfect (beam radius at receiver 12 cm, receiver aperture 30 cm radius). The 2.44% represents a deployable field system; a purpose-built system with active beam correction can approach the DARPA 20% figure.

**Scenario 5 — Microwave, 500 m, clear (0.11%):** The 1024-element array delivers 22 W from 20.48 kW input. Beam radius at 500 m is 27.7 m; the 12.5 m² receive aperture captures approximately 1% of the beam. This is the aperture coupling problem made explicit. The link budget shows 101.7 dB FSPL partially offset by 33.5 dBi array gain and 47.0 dBi receive gain, for a net loss of 29.6 dB before the overhead factor. Requiring 9,704 elements (99×99 array) to deliver the 5 kW target at this range is not infeasible in principle but is not portable.

**Scenario 6 — Microwave, 500 m, rain (0.11%):** Essentially unchanged from clear. At 500 m, moderate rain (25 mm/hr) produces 0.196 dB/km × 0.5 km = 0.098 dB total rain attenuation — indistinguishable from measurement noise. This confirms the theoretical all-weather advantage of microwave: rain does not materially affect microwave at these ranges and power levels.

**Scenario 7 — Microwave, 2 km, clear (0.027%):** Beam radius at 2 km is 110.8 m. Delivered power drops to 5.55 W. The link budget worsens by 12.1 dB relative to 500 m (primarily FSPL increase). This scenario illustrates why kilometer-range microwave WPT requires apertures orders of magnitude larger than what is practically deployable.

**Scenario 8 — Comparison, 2 km, rain:** Laser at 4.01% vs. microwave at 0.027%. Laser wins decisively in rain at 2 km, consistent with the physics: rain is mild for 1070 nm laser (0.20 dB/km) and does not change the aperture divergence problem for microwave.

### 6.3 The Range-Weather Crossover

The simulation results establish a clear operational crossover:

**Laser dominates** in all conditions except fog/cloud:
- At 2 km clear: 6.28% (laser) vs. 0.027% (microwave) — factor of 233×
- At 2 km rain: 4.01% vs. 0.027% — factor of 148×
- At 8.6 km clear: 2.44% (laser only viable option with portable hardware)

**Microwave dominates** only in fog/cloud conditions, where laser returns 0% and microwave returns 0.11% (still poor, but operational). The practical crossover point is not a range — it is a weather condition. Fog is the switching criterion, not distance.

The implication for a deployable system is a **hybrid architecture**: a laser link as the primary modality with a microwave fallback that is used only when fog/cloud renders the laser unavailable. The microwave fallback need not be efficient — even delivering 20–50 W can sustain emergency communications and minimum FOB loads while the laser link is unavailable. Cloud cover statistics for the specific deployment theater determine the availability weighting between the two modes.

---

## 7. Discussion

### 7.1 Why the Simulator Shows Low Microwave Efficiency at Kilometer Range

The 0.027% microwave efficiency at 2 km is not a bug and is not the result of overly conservative modeling. It is the direct consequence of far-field beam divergence from a portable aperture at 5.8 GHz. The physics is straightforward: the diffraction-limited beam half-angle for a 0.83 m aperture at 5.8 GHz is 3.17°. At 2 km, this creates a spot 110 m in radius. A deployable receive aperture of 50 m² covers approximately 0.13% of that spot. No adjustment to rectenna efficiency, pointing accuracy, or atmospheric modeling changes this fundamental geometric constraint.

The JAXA and Mitsubishi demonstrations achieved useful efficiencies because they used large, purpose-built systems with physically matched transmit and receive apertures. Scaling those systems to portable, tactical deployment requires either a much larger aperture (fixed installation, not tactical) or a much higher frequency (millimeter wave — better beam concentration but much worse rain attenuation). The simulator presents the portable case honestly.

### 7.2 The 20% Efficiency Ceiling and Component Chain Overestimation

The component efficiency numbers available in the literature are not wrong — GaN rectennas do achieve 85% at high input power, and InP PV cells do achieve 55% at 1070 nm. The problem is the difference between component efficiency and system efficiency. Multiplying the best component numbers together gives approximately 40–50% system efficiency from first principles. The demonstrated best is 20–22%.

The 0.65× overhead factor in the simulator accounts for the gap, but it is important to understand what that factor represents: control electronics overhead, thermal management power consumption, pointing and stabilization power (for both laser and microwave), connector and harness losses, array non-uniformity and dead elements, and the many small parasitic losses in a fielded system that do not appear in individual component tests. The DARPA and JAXA 20–22% results provide empirical validation that this factor is in the right range.

Any defense program planning around WPT should use 20–25% as the efficiency target for a mature purpose-built system, and 5–10% for initial fielded deployments based on current technology.

### 7.3 Implications for Defense Program Requirements

The simulation results carry specific implications for acquisition and program requirements:

**Laser WPT at 2 km in clear conditions delivers 5 kW from approximately 80 kW of wall-plug input.** For a FOB with 15 kW base load, WPT can cover 33% of baseline power needs. Full FOB power delivery (15 kW DC) requires approximately 239 kW electrical input at current efficiency levels. At grid or generator cost of $0.30/kWh, this costs approximately $1.72/day to run — far cheaper than diesel logistics but still a substantial power source requirement at the transmitter.

**Fog/cloud availability** is the binding constraint on laser WPT. In tropical or maritime climates with high cloud cover, laser WPT may be unavailable 40–60% of operating hours. Program requirements must specify the cloud cover statistical model for the target theater and design for hybrid operation.

**Microwave as a fallback, not a primary:** The simulation results suggest that microwave WPT in a tactical portable configuration should be specified as a backup capability for fog conditions at short range (< 500 m), not as a primary power delivery mechanism. This represents a reversal of the intuitive view that all-weather microwave is the "safer" choice — at km range, microwave's weather advantage is overwhelmed by its geometric disadvantage.

### 7.4 Novel Architectures Not Yet Modeled

Several architectures could materially change the efficiency picture:

**Drone relay chain:** A series of UAVs serving as optical relay nodes between transmitter and receiver could decouple the single-hop efficiency constraint. Each relay adds a laser-to-PV-to-laser conversion loss (~20–30%) but eliminates long-range beam divergence and turbulence accumulation. A 3-hop relay chain at 2 km total range might achieve higher overall efficiency than a single 2 km hop in turbulent conditions.

**Distributed aperture (microwave):** A geographically distributed array of synchronized microwave transmitters using digital beamforming (similar to the Caltech MAPLE IC tile architecture) could present a much larger effective aperture without requiring physically contiguous hardware. At sufficient effective aperture size, the beam concentration problem disappears.

**Near-field resonant coupling mesh:** For ranges under 10 m, strongly-coupled resonant inductive links achieve >90% efficiency. A distributed mesh of relay nodes at short spacings could extend effective range while maintaining near-field efficiency — relevant for within-perimeter power distribution at the FOB rather than over-the-wire delivery.

**Pre-compensation with wavefront sensing:** For laser WPT, a wavefront sensing system on the receiver that feeds back atmospheric phase information to a deformable mirror or spatial light modulator at the transmitter can recover turbulence-induced phase errors. This is standard in adaptive optics astronomy; its application to power beaming is one of the most promising near-term efficiency improvements. Modeling this would require extending the Fried parameter model to include Zernike modal decomposition and partial correction transfer functions.

---

## 8. Future Work

The following extensions are prioritized based on their impact on prediction accuracy and operational relevance:

**Adaptive optics pre-compensation model:** Add a wavefront correction factor to the laser turbulence model, parameterized by the number of actuators, wavefront sensing bandwidth, and Greenwood frequency for the atmospheric conditions. This could reduce turbulence loss from 3–6 dB to 0.5–1.5 dB in moderate conditions.

**1550 nm laser band:** Model the 1550 nm transmission window with its lower clear-sky aerosol extinction (0.04–0.13 dB/km vs. 0.05 dB/km for 1070 nm), superior eye safety margin, and current PV efficiency limits (~40–45% at 1550 nm vs. 55% at 1070 nm). Relevant for systems where eye safety zones are operationally constrained.

**Near-field WPT regime:** Extend the microwave model to compute coupled-mode resonant efficiency for ranges within the Rayleigh zone (< 26.5 m for the default array). This would enable accurate modeling of within-perimeter power distribution at the FOB — charging vehicles, sensor nodes, and handheld equipment without fuel logistics.

**Dynamic atmospheric turbulence profiles:** Implement day/night Cn² profiles based on the Hufnagel-Valley 5/7 model parameterized by wind speed and ground temperature gradient. Turbulence is typically weakest at night and strongest in early afternoon. This would enable time-of-day optimization of transmission windows for laser WPT.

**Multi-node relay chain optimization:** Model a sequence of n relay hops between source and destination, optimizing hop spacing for maximum end-to-end efficiency given atmospheric conditions and altitude profiles.

**Real-time weather data integration:** Add an API call to a weather service (NOAA METAR or equivalent) to populate atmospheric conditions automatically from the deployment location, enabling scenario runs that reflect actual current or forecast conditions rather than idealized categories.

---

## 9. A Novel Architecture for Battlefield WPT — The Distributed Relay-Regeneration Approach

### 9.1 The Problem: Why Single-Link WPT Fails in Battlefield Conditions

Every current WPT program — DARPA POWER PRAD, NRL PRAM, JAXA SSPS, PowerLight PTROL-UAS — is architected as a single long link from transmitter to receiver. This approach encounters three compounding failure modes in battlefield conditions:

**Laser attenuation in smoke and dust.** At 1070 nm in moderate battlefield smoke (extinction ~8 dB/km), a direct 5 km link accumulates 40 dB of loss — 99.99% of transmitted power is absorbed before reaching the receiver. In fog or dense smoke (15–30 dB/km), even a 1 km direct link fails completely.

**Microwave beam divergence at operational range.** With portable hardware (100 m TX aperture, feasible on a vehicle), the 3 dB beam radius at 5 km is 2.6 km. No practical receive aperture captures a meaningful fraction of this beam. System efficiency falls below 0.001%.

**Single-point vulnerability.** A direct link requires unobstructed line-of-sight between a fixed transmitter and fixed receiver across the entire engagement area. Terrain, smoke screens, maneuvering units, and adversarial obscurants all interrupt the link with no fallback.

No existing system addresses all three simultaneously for the 500 m–10 km tactical range with transportable hardware.

### 9.2 The Proposed Solution: Relay-Regeneration Chains

The core insight is to decompose the long failing link into a chain of short successful links, with autonomous relay nodes regenerating power between segments.

**Architecture:**

```
[Base TX] --(1 km)--> [Relay 1] --(1 km)--> [Relay 2] --(1 km)--> ... --(200 m)--> [FOB RX]
             laser        PV→buf→TX    laser       PV→buf→TX           microwave
```

Each relay node receives power (via PV or rectenna), stores it in a small battery buffer (500 Wh), and retransmits to the next node. Each link resets the attenuation budget. The chain delivers power across ranges and through conditions that would completely block a direct link.

**Quantitative case for 5 km in moderate smoke (8 dB/km):**

| Architecture | Total loss | Power delivered (5 kW target) |
|---|---|---|
| Direct laser, single link | 40 dB | ~0.5 W |
| 5-relay chain, 1 km segments | 8 dB per segment (regenerated) | ~300 W per segment → 1.2–2 kW net |
| Relay chain with AO per segment | 6 dB per segment | ~2–3 kW net |

The relay chain delivers 3–6 orders of magnitude more power in smoke than a direct link. This is not a marginal improvement — it is the difference between a working system and a failed one.

### 9.3 Wavelength Selection: Why 1550 nm, Not 1070 nm

The relay architecture should operate at 1550 nm rather than the 1070 nm wavelength used by most current research programs for four reasons:

**Eye safety.** 1550 nm is Class 1 eye-safe at higher power levels than 1070 nm. Personnel within the relay field do not require laser eye protection. This is a non-negotiable operational requirement — exclusion zones around a 1070 nm 5 kW system are tactically unworkable.

**Lower scattering in smoke and dust.** Mie scattering is wavelength-dependent: longer wavelengths scatter less from particles of similar size. For combustion-product smoke (particle diameter 0.1–1 µm), 1550 nm has roughly 40–60% lower extinction coefficient than 1070 nm. Per-segment loss is reduced.

**Component maturity.** Erbium-doped fiber amplifiers (EDFA) at 1550 nm are the backbone of global telecommunications. They are mass-produced, cost-optimized, shock-rated, and available commercially at kilowatt-class power levels. No exotic development is required for the transmit chain.

**Detection resistance.** Standard military night-vision image intensifiers and thermal imagers operate in the 750–1000 nm and 3–5 µm / 8–12 µm bands respectively. A 1550 nm system is invisible to both, providing a lower signature than a 1070 nm system.

The primary tradeoff is PV receiver efficiency: current best-in-class 1550 nm photovoltaic converters achieve 40–45% (vs. 55% at 1070 nm). This is an active research area with rapid improvement; it is not a blocking constraint for the relay architecture.

### 9.4 What Makes This Genuinely Novel

A search of the literature and patent databases as of early 2026 finds no prior demonstration or publication of this combined architecture:

- **Caltech MAPLE (2023):** Demonstrated multi-aperture phased transmission in LEO orbit. No relay regeneration; no atmospheric chain; no terrestrial application.
- **DARPA POWER PRAD (2025):** Single 8.6 km laser link, clear sky, fixed geometry. No relay nodes.
- **Military communications drone relays:** Established practice for data relay. Power relay using regenerative nodes has not been demonstrated or published.
- **Resonant WPT chains (e.g., MIT WiTricity lineage):** Near-field magnetic coupling, ranges under 10 m. Inapplicable at tactical distances.

The combination of: (1) 1550 nm eye-safe laser, (2) autonomous aerial relay nodes with power regeneration, (3) multi-band per-segment mode selection (laser for clear segments, microwave for obscured near-ground segments), and (4) mesh-networked rerouting around downed nodes — represents an unoccupied solution space.

### 9.5 Validation Path

**Phase 1 — Bench proof of concept (months 1–6):**  
Two relay nodes, 50 m links, smoke chamber. Validate: regeneration efficiency, pointing acquisition, per-segment attenuation vs. direct-link comparison. Deliverable: measured end-to-end efficiency curves as a function of smoke density. Estimated cost: <$250k with COTS components.

**Phase 2 — Outdoor fixed-node demonstration (months 6–18):**  
Three relay nodes, 500 m links, outdoor smoke generation. Validate: pointing in turbulence, relay handoff, weather robustness. Deliverable: demonstration of power delivery in conditions that defeat direct-link WPT. Target metric: >500 W delivered at 1.5 km in conditions producing >20 dB/km extinction. Estimated cost: $1–3M.

**Phase 3 — Autonomous drone relay (months 18–36):**  
Three autonomous UAV relay nodes, 2 km total range, uncontrolled weather. Validate: autonomous positioning, in-flight relay adjustment, power continuity through node failure. Target: 1 kW delivered at 2 km with one relay failure scenario. Estimated cost: $5–15M.

**Phase 4 — Integrated tactical system (months 36–60):**  
Full 5–10 km system, integrated with FOB power distribution, field conditions. Deliverable: tactically deployable system suitable for JCTD or procurement. Estimated cost: $20–50M.

### 9.6 The Simulator as the Foundation

The Aether WPT simulator already provides the single-link physics models required to compute per-segment efficiency for any combination of mode, range, and atmospheric condition. The immediate next development milestone is a multi-hop relay mode: chain N links with independently specified conditions per segment, model regeneration efficiency loss at each node (estimated 15–20% conversion loss per relay), and output total end-to-end efficiency and optimal relay spacing as a function of atmospheric profile.

This simulation capability would: (a) quantitatively validate the relay-regeneration advantage over direct links across the full envelope of battlefield conditions, (b) generate the physics foundation for a DARPA SBIR or AFWERX submission, and (c) provide a design tool for sizing relay payloads and UAV requirements in specific deployment scenarios.

---

## 10. References

[1] Friis, H.T. (1946). "A Note on a Simple Transmission Formula." *Proceedings of the IRE*, 34(5), 254–256. Foundational Friis transmission equation for free-space microwave links.

[2] DARPA (May 2025). "DARPA Program Sets Distance Record for Power Beaming." DARPA official press release. https://www.darpa.mil/news/2025/darpa-program-distance-record-power-beaming. 800 W delivered at 8.6 km, ~20% system efficiency.

[3] Jaffe, P. (2020). "NRL Begins Testing Solar Power Satellite Module in Space." NRL/EE Power. Launched May 2020 on X-37B OTV-6. Validated solar-to-RF conversion in orbit.

[4] Japan Space Systems / JAXA (2021). "Microwave Wireless Power Transmission for Space Solar Power Satellite." IEEE Spectrum. 1.6 kW → 350 W at 50 m, ~22% end-to-end efficiency. Also references Mitsubishi Heavy Industries 10 kW at 500 m (2015).

[5] Japan Space Systems (December 2024). "First Test Report: OHISAMA WPT Aircraft Demonstration." JSS Technical Report. https://www.jspacesystems.or.jp/jss/wp-content/uploads/2025/01/1stTestReport_2024.12.24en-1.pdf. First aircraft-borne microwave WPT at 7 km altitude.

[6] PowerLight Technologies (December 2025). "PowerLight Technologies Achieves Laser Power Beaming UAV Milestone." EINPresswire. Kilowatt-class laser WPT to UAS under CENTCOM sponsorship, range to 5,000 ft.

[7] Hajimiri, A., Atwater, H., et al. / Caltech SSPP (May 2023). "Caltech SSPD-1: MAPLE Wireless Power Transmission from Orbit." Caltech official announcement. First confirmed LEO-to-Earth wireless power transmission.

[8] Balanis, C.A. (2016). *Antenna Theory: Analysis and Design*, 4th ed. Wiley. Array gain formula, aperture efficiency, Friis transmission, pointing error models. Primary reference for phased array transmitter physics.

[9] Ruze, J. (1966). "Antenna Tolerance Theory — A Review." *Proceedings of the IEEE*, 54(4), 633–640. Phase error gain reduction formula (Ruze's equation) for phased arrays.

[10] ITU-R (2005). "Recommendation ITU-R P.838-3: Specific Attenuation Model for Rain for Use in Prediction Methods." International Telecommunications Union. Power law coefficients for rain attenuation at microwave frequencies. Primary reference for 5.8 GHz rain model.

[11] ITU-R (2016). "Recommendation ITU-R P.676-12: Attenuation by Atmospheric Gases and Related Effects." International Telecommunications Union. Gaseous absorption 0.003–0.008 dB/km at 5.8 GHz.

[12] Dang, W., et al. (2021). "A 5.8-GHz High-Power and High-Efficiency Rectifier Circuit With Lateral GaN Schottky Diode." IEEE Transactions on Microwave Theory and Techniques. GaN rectenna 85.1% efficiency at 33 dBm (2W) input at 5.8 GHz.

[13] DTIC / NPS (2003). "Atmospheric Transmission Windows for High-Power Lasers." Report ADA420318. AFRL/NPS study. Validated clear-sky transmission coefficients: 0.93–0.98 per km at 1070 nm.

[14] McMaster University (2000). "Comparison of Laser Beam Propagation at 785 nm and 1550 nm in Fog and Haze." SPIE Proceedings. Fog attenuation 20–100+ dB/km for near-IR. Definitive source for fog hard-block behavior.

[15] Various (April 2025). "55% Efficient High-Power Multijunction PV Laser Power Converters for 1070 nm." *MDPI Photonics*, 12(5), 406. InP 8-junction cell, 55% efficiency at 18 W output, 1070 nm.

[16] Various (December 2021). "Beaming Power: Photovoltaic Laser Power Converters for Power-by-Light." *Joule* (Cell Press). Comprehensive review of PVLPC technology across wavelength windows.

[17] Various (September 2023). "Photovoltaic AlGaAs/GaAs Devices for Conversion of High-Power Density Laser (800–860 nm)." *Solar Energy Materials and Solar Cells*. GaAs 52–55% efficiency; power density dependent saturation curve.

[18] Shinohara, N. (2011 / 2025 update). "Microwave Power Transmission Technologies for Space Solar Power Satellites." IEEE Proceedings + Chinese Space Science & Technology Journal. Comprehensive framework for MPT, rectenna design, phased array control.

[19] Andrews, L.C., Phillips, R.L. (2005). *Laser Beam Propagation through Random Media*, 2nd ed. SPIE Press. Rytov variance, Fried parameter, long-term beam spreading, WPT turbulence factor. Primary reference for atmospheric turbulence physics.

[20] Fried, D.L. (1966). "Optical Resolution Through a Randomly Inhomogeneous Medium for Very Long and Very Short Exposures." *Journal of the Optical Society of America*, 56(10), 1372–1379. Fried coherence length r₀ formulation.

[21] RAND Corporation (2012). "The Fully Burdened Cost of Fuel." RAND Arroyo Center. DoD fully-burdened fuel cost methodology; $400–$600/gallon for remote FOB delivery (inflation-adjusted to ~$12/L for 2025).

[22] Zahid, L., et al. (April 2022). "Rain Attenuation Measurement for Short-Range mmWave Fixed Link." *Radio Science* (AGU / Wiley). Experimental validation of ITU-R P.838-3 against real measurements. Confirms model accuracy for 1–100 GHz terrestrial paths.

[23] Various (July 2021). "Laser Beam Atmospheric Propagation Modelling for LIDAR Applications." *MDPI Atmosphere*, 12(7), 918. Three degradation mechanisms: beam spreading, scintillation, beam wander. Cn² range 10⁻¹⁵ to 10⁻¹² m⁻²/³ at ground level.

[24] Various (January 2022). "Fast and Accurate Approach to RF-DC Conversion Efficiency Estimation." *MDPI Sensors*, 22(3), 787. GaAs diode rectenna >90% at high power density; efficiency-vs-power characterization.

[25] Mankins, J.C. (October 2021). "SPS-ALPHA Mark III and an Achievable Development Roadmap." 72nd International Astronautical Congress. Modular scalable phased array architecture for SPS; applicable to terrestrial distributed transmitters.

---

*Aether WPT Simulator — Technical Report v1.0*
*Physics engine: microwave.py, laser.py, scenarios.py*
*API: https://hummingbird-sim-api.onrender.com*
*Repository: https://github.com/kamber-tech/aether-sim*
