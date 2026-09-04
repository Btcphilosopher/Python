"""
RailBoost
=========
High-Speed Electric Train Performance Optimizer

Engineering simulation / digital-twin software.

This program does NOT override train protection systems,
speed limiters, signalling or certified vehicle limits.

It evaluates theoretical performance envelopes and identifies
which subsystem becomes the limiting factor.

Python 3.12+
"""

from dataclasses import dataclass
from enum import Enum
from math import sqrt, exp


# ============================================================
# ENUMERATIONS
# ============================================================

class LimitingFactor(Enum):
    NONE = "NONE"
    TRACK = "TRACK"
    VEHICLE = "VEHICLE"
    TRACTION = "TRACTION"
    ADHESION = "ADHESION"
    CATENARY = "CATENARY"
    MOTOR_THERMAL = "MOTOR_THERMAL"
    INVERTER_THERMAL = "INVERTER_THERMAL"
    AERODYNAMIC = "AERODYNAMIC"
    BRAKING = "BRAKING"


# ============================================================
# TRAIN
# ============================================================

@dataclass
class Train:

    name: str

    mass_kg: float

    frontal_area_m2: float

    drag_coefficient: float

    rolling_resistance: float

    max_certified_speed_mps: float

    motor_count: int

    motor_power_kw: float

    motor_efficiency: float

    inverter_efficiency: float

    wheel_rail_adhesion: float

    motor_max_temperature_c: float

    inverter_max_temperature_c: float

    motor_thermal_time_s: float

    inverter_thermal_time_s: float


# ============================================================
# ELECTRICAL SYSTEM
# ============================================================

@dataclass
class ElectricalSystem:

    voltage_v: float

    maximum_current_a: float

    maximum_power_kw: float

    transformer_efficiency: float

    catenary_margin: float


# ============================================================
# TRACK
# ============================================================

@dataclass
class Track:

    name: str

    length_m: float

    gradient: float

    curve_radius_m: float

    authorised_speed_mps: float

    maximum_vehicle_speed_mps: float

    cant_m: float

    cant_deficiency_m: float

    braking_margin: float


# ============================================================
# ATMOSPHERE
# ============================================================

@dataclass
class Atmosphere:

    temperature_k: float = 288.15

    pressure_pa: float = 101325.0

    wind_mps: float = 0.0


# ============================================================
# PERFORMANCE RESULT
# ============================================================

@dataclass
class PerformanceResult:

    speed_mps: float

    speed_kmh: float

    required_power_kw: float

    available_power_kw: float

    aerodynamic_drag_n: float

    rolling_force_n: float

    gradient_force_n: float

    adhesion_limit_n: float

    traction_force_n: float

    motor_temperature_c: float

    inverter_temperature_c: float

    limiting_factor: LimitingFactor

    feasible: bool


# ============================================================
# PHYSICS
# ============================================================

class TrainPhysics:

    G = 9.80665

    AIR_DENSITY = 1.225

    def __init__(
        self,
        train: Train,
        electrical: ElectricalSystem,
        atmosphere: Atmosphere,
    ):

        self.train = train
        self.electrical = electrical
        self.atmosphere = atmosphere


    # --------------------------------------------------------
    # AIR DENSITY
    # --------------------------------------------------------

    def air_density(self):

        R = 287.05

        return (
            self.atmosphere.pressure_pa /
            (
                R *
                self.atmosphere.temperature_k
            )
        )


    # --------------------------------------------------------
    # AERODYNAMIC DRAG
    # --------------------------------------------------------

    def aerodynamic_drag(self, speed):

        rho = self.air_density()

        apparent_speed = (
            speed +
            self.atmosphere.wind_mps
        )

        return (
            0.5 *
            rho *
            self.train.drag_coefficient *
            self.train.frontal_area_m2 *
            apparent_speed ** 2
        )


    # --------------------------------------------------------
    # ROLLING RESISTANCE
    # --------------------------------------------------------

    def rolling_force(self):

        return (
            self.train.mass_kg *
            self.G *
            self.train.rolling_resistance
        )


    # --------------------------------------------------------
    # GRADIENT
    # --------------------------------------------------------

    def gradient_force(self):

        return (
            self.train.mass_kg *
            self.G *
            0.01 *
            self._gradient
        )


    def set_gradient(self, gradient):

        self._gradient = gradient


    # --------------------------------------------------------
    # TOTAL RESISTANCE
    # --------------------------------------------------------

    def resistance(self, speed):

        return (
            self.aerodynamic_drag(speed) +
            self.rolling_force() +
            self.gradient_force()
        )


    # --------------------------------------------------------
    # POWER REQUIRED
    # --------------------------------------------------------

    def power_required(self, speed):

        mechanical_power = (
            self.resistance(speed) *
            speed
        )

        electrical_losses = (
            1.0 /
            (
                self.train.motor_efficiency *
                self.train.inverter_efficiency
            )
        )

        return mechanical_power * electrical_losses


# ============================================================
# PERFORMANCE OPTIMIZER
# ============================================================

class RailBoostOptimizer:

    def __init__(
        self,
        train: Train,
        electrical: ElectricalSystem,
        track: Track,
        atmosphere: Atmosphere,
    ):

        self.train = train
        self.electrical = electrical
        self.track = track
        self.atmosphere = atmosphere

        self.physics = TrainPhysics(
            train,
            electrical,
            atmosphere
        )

        self.physics.set_gradient(
            track.gradient
        )


    # ========================================================
    # ELECTRICAL POWER
    # ========================================================

    def available_electrical_power(self):

        catenary_power = (
            self.electrical.voltage_v *
            self.electrical.maximum_current_a
        ) / 1000.0

        catenary_power *= (
            1.0 -
            self.electrical.catenary_margin
        )

        return min(
            catenary_power,
            self.electrical.maximum_power_kw
        )


    # ========================================================
    # MOTOR POWER
    # ========================================================

    def available_motor_power(self):

        return (
            self.train.motor_count *
            self.train.motor_power_kw
        )


    # ========================================================
    # COMPLETE POWER LIMIT
    # ========================================================

    def available_power(self):

        return min(
            self.available_electrical_power(),
            self.available_motor_power()
        )


    # ========================================================
    # ADHESION
    # ========================================================

    def adhesion_limit(self):

        normal_force = (
            self.train.mass_kg *
            self.physics.G
        )

        return (
            self.train.wheel_rail_adhesion *
            normal_force
        )


    # ========================================================
    # TRACTIVE FORCE
    # ========================================================

    def available_tractive_force(self, speed):

        if speed <= 0:

            return self.adhesion_limit()

        power_force = (
            self.available_power() *
            1000.0 /
            speed
        )

        adhesion_force = (
            self.adhesion_limit()
        )

        return min(
            power_force,
            adhesion_force
        )


    # ========================================================
    # CURVE SPEED
    # ========================================================

    def curve_speed_limit(self):

        if self.track.curve_radius_m <= 0:

            return float("inf")

        g = self.physics.G

        effective_cant =
            self.track.cant_m +
            self.track.cant_deficiency_m

        # Simplified engineering approximation.

        speed_squared = (
            g *
            self.track.curve_radius_m *
            (
                effective_cant /
                1.435
            )
        )

        if speed_squared <= 0:

            return float("inf")

        return sqrt(speed_squared)


    # ========================================================
    # THERMAL MODEL
    # ========================================================

    def thermal_temperature(
        self,
        speed,
        power_kw,
        base_temp=25.0
    ):

        load_fraction = (
            power_kw /
            max(
                self.available_power(),
                1.0
            )
        )

        aerodynamic_load = (
            self.physics.aerodynamic_drag(speed) /
            max(
                self.train.mass_kg *
                self.physics.G,
                1.0
            )
        )

        motor_temp = (
            base_temp +
            75.0 *
            load_fraction +
            20.0 *
            aerodynamic_load
        )

        inverter_temp = (
            base_temp +
            50.0 *
            load_fraction
        )

        return (
            motor_temp,
            inverter_temp
        )


    # ========================================================
    # BRAKING CHECK
    # ========================================================

    def braking_distance(
        self,
        speed,
        deceleration_mps2=1.0
    ):

        if deceleration_mps2 <= 0:

            return float("inf")

        return (
            speed ** 2 /
            (
                2.0 *
                deceleration_mps2
            )
        )


    # ========================================================
    # LIMIT IDENTIFICATION
    # ========================================================

    def identify_limit(
        self,
        speed,
        power_required
    ):

        if speed > self.track.authorised_speed_mps:

            return LimitingFactor.TRACK


        if speed > self.track.maximum_vehicle_speed_mps:

            return LimitingFactor.VEHICLE


        if speed > self.train.max_certified_speed_mps:

            return LimitingFactor.VEHICLE


        if power_required >
           self.available_power() * 1000.0:

            return LimitingFactor.TRACTION


        required_force = (
            self.physics.resistance(speed)
        )

        if required_force >
           self.available_tractive_force(speed):

            return LimitingFactor.ADHESION


        motor_temp, inverter_temp = (
            self.thermal_temperature(
                speed,
                power_required / 1000.0
            )
        )


        if (
            motor_temp >
            self.train.motor_max_temperature_c
        ):

            return LimitingFactor.MOTOR_THERMAL


        if (
            inverter_temp >
            self.train.inverter_max_temperature_c
        ):

            return LimitingFactor.INVERTER_THERMAL


        curve_limit = (
            self.curve_speed_limit()
        )

        if speed > curve_limit:

            return LimitingFactor.TRACK


        return LimitingFactor.NONE


    # ========================================================
    # SINGLE SPEED EVALUATION
    # ========================================================

    def evaluate(self, speed):

        required_power_w = (
            self.physics.power_required(speed)
        )

        required_force = (
            self.physics.resistance(speed)
        )

        traction_force = min(
            required_force,
            self.available_tractive_force(speed)
        )

        motor_temp, inverter_temp = (
            self.thermal_temperature(
                speed,
                required_power_w / 1000.0
            )
        )

        limit = self.identify_limit(
            speed,
            required_power_w
        )

        feasible = (
            limit ==
            LimitingFactor.NONE
        )

        return PerformanceResult(

            speed_mps=speed,

            speed_kmh=speed * 3.6,

            required_power_kw=
                required_power_w / 1000.0,

            available_power_kw=
                self.available_power(),

            aerodynamic_drag_n=
                self.physics.aerodynamic_drag(speed),

            rolling_force_n=
                self.physics.rolling_force(),

            gradient_force_n=
                self.physics.gradient_force(),

            adhesion_limit_n=
                self.adhesion_limit(),

            traction_force_n=
                traction_force,

            motor_temperature_c=
                motor_temp,

            inverter_temperature_c=
                inverter_temp,

            limiting_factor=limit,

            feasible=feasible
        )


    # ========================================================
    # SEARCH FOR MAXIMUM SPEED
    # ========================================================

    def find_maximum_speed(
        self,
        lower_kmh=100.0,
        upper_kmh=500.0,
        step_kmh=1.0
    ):

        best = None

        speed = lower_kmh

        while speed <= upper_kmh:

            result = self.evaluate(
                speed / 3.6
            )

            if result.feasible:

                best = result

            speed += step_kmh


        return best


    # ========================================================
    # SPEED ENVELOPE
    # ========================================================

    def generate_envelope(
        self,
        start_kmh=100.0,
        end_kmh=500.0,
        increment_kmh=10.0
    ):

        results = []

        speed = start_kmh

        while speed <= end_kmh:

            results.append(
                self.evaluate(
                    speed / 3.6
                )
            )

            speed += increment_kmh

        return results


# ============================================================
# PERFORMANCE IMPROVEMENT ANALYSIS
# ============================================================

class UpgradeAnalyzer:

    def __init__(
        self,
        optimizer
    ):

        self.optimizer = optimizer


    def aerodynamic_upgrade(
        self,
        drag_reduction
    ):

        original = (
            self.optimizer.train.drag_coefficient
        )

        self.optimizer.train.drag_coefficient *= (
            1.0 -
            drag_reduction
        )

        result = (
            self.optimizer.find_maximum_speed()
        )

        self.optimizer.train.drag_coefficient = (
            original
        )

        return result


    def power_upgrade(
        self,
        power_multiplier
    ):

        original_motor_power = (
            self.optimizer.train.motor_power_kw
        )

        original_max_power = (
            self.optimizer.electrical.maximum_power_kw
        )

        self.optimizer.train.motor_power_kw *= (
            power_multiplier
        )

        self.optimizer.electrical.maximum_power_kw *= (
            power_multiplier
        )

        result = (
            self.optimizer.find_maximum_speed()
        )

        self.optimizer.train.motor_power_kw = (
            original_motor_power
        )

        self.optimizer.electrical.maximum_power_kw = (
            original_max_power
        )

        return result


    def mass_reduction(
        self,
        reduction_fraction
    ):

        original_mass = (
            self.optimizer.train.mass_kg
        )

        self.optimizer.train.mass_kg *= (
            1.0 -
            reduction_fraction
        )

        result = (
            self.optimizer.find_maximum_speed()
        )

        self.optimizer.train.mass_kg = (
            original_mass
        )

        return result


    def compare_upgrades(self):

        baseline = (
            self.optimizer.find_maximum_speed()
        )

        aero = (
            self.aerodynamic_upgrade(0.10)
        )

        power = (
            self.power_upgrade(0.10)
        )

        mass = (
            self.mass_reduction(0.10)
        )

        return {
            "baseline": baseline,
            "aerodynamics_-10%_Cd":
                aero,
            "power_+10%":
                power,
            "mass_-10%":
                mass
        }


# ============================================================
# REPORTING
# ============================================================

def print_result(
    title,
    result
):

    print()
    print("=" * 65)
    print(title)
    print("=" * 65)

    if result is None:

        print("No feasible operating point found.")

        return

    print(
        f"Speed:             "
        f"{result.speed_kmh:8.1f} km/h"
    )

    print(
        f"Required power:    "
        f"{result.required_power_kw:8.1f} kW"
    )

    print(
        f"Available power:   "
        f"{result.available_power_kw:8.1f} kW"
    )

    print(
        f"Aero drag:         "
        f"{result.aerodynamic_drag_n / 1000:8.1f} kN"
    )

    print(
        f"Rolling resistance:"
        f"{result.rolling_force_n / 1000:8.1f} kN"
    )

    print(
        f"Gradient force:    "
        f"{result.gradient_force_n / 1000:8.1f} kN"
    )

    print(
        f"Adhesion limit:    "
        f"{result.adhesion_limit_n / 1000:8.1f} kN"
    )

    print(
        f"Motor temperature: "
        f"{result.motor_temperature_c:8.1f} °C"
    )

    print(
        f"Inverter temp:     "
        f"{result.inverter_temperature_c:8.1f} °C"
    )

    print(
        f"Limiting factor:   "
        f"{result.limiting_factor.value}"
    )


# ============================================================
# DEMONSTRATION
# ============================================================

def main():

    train = Train(

        name="Existing HST",

        mass_kg=450_000.0,

        frontal_area_m2=11.0,

        drag_coefficient=0.15,

        rolling_resistance=0.0015,

        max_certified_speed_mps=
            360.0 / 3.6,

        motor_count=8,

        motor_power_kw=1500.0,

        motor_efficiency=0.96,

        inverter_efficiency=0.98,

        wheel_rail_adhesion=0.20,

        motor_max_temperature_c=120.0,

        inverter_max_temperature_c=90.0,

        motor_thermal_time_s=300.0,

        inverter_thermal_time_s=120.0
    )


    electrical = ElectricalSystem(

        voltage_v=25_000.0,

        maximum_current_a=600.0,

        maximum_power_kw=15_000.0,

        transformer_efficiency=0.98,

        catenary_margin=0.10
    )


    track = Track(

        name="High Speed Test Section",

        length_m=100_000.0,

        gradient=0.0,

        curve_radius_m=20_000.0,

        authorised_speed_mps=
            360.0 / 3.6,

        maximum_vehicle_speed_mps=
            360.0 / 3.6,

        cant_m=0.18,

        cant_deficiency_m=0.10,

        braking_margin=0.20
    )


    atmosphere = Atmosphere(

        temperature_k=288.15,

        pressure_pa=101325.0,

        wind_mps=0.0
    )


    optimizer = RailBoostOptimizer(

        train,
        electrical,
        track,
        atmosphere
    )


    baseline = (
        optimizer.find_maximum_speed(
            lower_kmh=100,
            upper_kmh=500
        )
    )


    print_result(
        "BASELINE TRAIN",
        baseline
    )


    analyzer = UpgradeAnalyzer(
        optimizer
    )


    upgrades = (
        analyzer.compare_upgrades()
    )


    print_result(
        "10% AERODYNAMIC IMPROVEMENT",
        upgrades[
            "aerodynamics_-10%_Cd"
        ]
    )


    print_result(
        "10% TRACTION POWER IMPROVEMENT",
        upgrades[
            "power_+10%"
        ]
    )


    print_result(
        "10% MASS REDUCTION",
        upgrades[
            "mass_-10%"
        ]
    )


if __name__ == "__main__":

    main()
