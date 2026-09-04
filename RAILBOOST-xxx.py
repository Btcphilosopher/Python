"""
RAILBOOST-X
Experimental Railway High-Speed Test & Performance Optimizer

PURPOSE
-------
Engineering / simulation / test-planning software.

It estimates:
    - longitudinal train performance
    - aerodynamic resistance
    - rolling resistance
    - gradient resistance
    - traction power
    - adhesion limits
    - motor thermal loading
    - inverter thermal loading
    - braking distance
    - wind effects
    - test-track speed envelope
    - incremental experimental speed steps
    - subsystem limiting factors

IMPORTANT
---------
This is NOT a safety-critical train-control system.

It must NOT:
    - override ETCS/ATP/PTC
    - disable speed supervision
    - command traction directly on a live railway
    - replace certified braking systems
    - bypass infrastructure speed limits
    - determine operational authority

The output is an engineering/test-planning envelope.
Actual test operation requires the relevant railway operator,
infrastructure manager, test authority and safety/authorisation process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import pi, sqrt
from typing import List, Dict


# ============================================================
# ENUMERATIONS
# ============================================================

class LimitingFactor(Enum):
    NONE = "none"
    TRACK = "track"
    VEHICLE_CERTIFICATION = "vehicle certification"
    TRACTION_POWER = "traction power"
    ADHESION = "adhesion"
    MOTOR_THERMAL = "motor thermal"
    INVERTER_THERMAL = "inverter thermal"
    TRANSFORMER = "transformer"
    CATENARY = "catenary"
    AERODYNAMICS = "aerodynamics"
    BRAKING = "braking"
    WIND = "wind"
    UNKNOWN = "unknown"


class TestStatus(Enum):
    PASS = "PASS"
    CAUTION = "CAUTION"
    HOLD = "HOLD"


# ============================================================
# TRAIN
# ============================================================

@dataclass
class Motor:
    rated_power_kw: float
    max_power_kw: float
    efficiency: float

    temperature_c: float = 25.0
    maximum_temperature_c: float = 150.0

    thermal_time_constant_s: float = 900.0


@dataclass
class Inverter:
    rated_power_kw: float
    maximum_power_kw: float
    efficiency: float

    temperature_c: float = 30.0
    maximum_temperature_c: float = 120.0

    thermal_time_constant_s: float = 600.0


@dataclass
class Train:
    mass_kg: float

    frontal_area_m2: float
    drag_coefficient: float

    rolling_resistance_coefficient: float

    wheel_diameter_m: float

    motors: List[Motor]
    inverters: List[Inverter]

    maximum_certified_speed_kmh: float

    adhesion_coefficient: float

    axle_load_kg: float

    # Mechanical braking
    service_brake_deceleration_ms2: float
    emergency_brake_deceleration_ms2: float

    # Mechanical / aerodynamic limits
    maximum_body_speed_kmh: float

    # Current configuration
    gear_efficiency: float = 0.97


# ============================================================
# ELECTRICAL SYSTEM
# ============================================================

@dataclass
class ElectricalSystem:

    nominal_voltage_v: float

    maximum_current_a: float

    transformer_efficiency: float

    maximum_transformer_power_kw: float

    maximum_catenary_power_kw: float

    minimum_voltage_v: float

    voltage_drop_factor: float = 0.02


# ============================================================
# TEST TRACK
# ============================================================

@dataclass
class TestTrack:

    name: str

    length_km: float

    authorised_test_speed_kmh: float

    minimum_curve_radius_m: float

    maximum_gradient_percent: float

    track_quality_factor: float

    braking_margin_factor: float

    maximum_wind_crosswind_ms: float

    maximum_wind_headwind_ms: float

    safety_margin_percent: float = 10.0


# ============================================================
# ENVIRONMENT
# ============================================================

@dataclass
class Environment:

    temperature_c: float = 15.0
    pressure_pa: float = 101325.0

    headwind_ms: float = 0.0
    crosswind_ms: float = 0.0

    gradient_percent: float = 0.0

    rail_adhesion_factor: float = 1.0


# ============================================================
# TEST RESULT
# ============================================================

@dataclass
class PerformanceResult:

    speed_kmh: float

    speed_ms: float

    aerodynamic_force_n: float
    rolling_force_n: float
    gradient_force_n: float

    total_resistance_n: float

    required_power_kw: float
    available_power_kw: float

    adhesion_force_n: float

    motor_temperature_c: float
    inverter_temperature_c: float

    braking_distance_m: float

    limiting_factor: LimitingFactor

    status: TestStatus

    margin_percent: float


# ============================================================
# PHYSICS ENGINE
# ============================================================

class TrainPhysics:

    G = 9.80665
    AIR_R = 287.05

    @staticmethod
    def air_density(environment: Environment) -> float:

        temperature_k = environment.temperature_c + 273.15

        return environment.pressure_pa / (
            TrainPhysics.AIR_R * temperature_k
        )

    @staticmethod
    def effective_air_speed(
        speed_ms: float,
        environment: Environment
    ) -> float:

        # Headwind increases relative airspeed.
        return max(
            0.0,
            speed_ms + environment.headwind_ms
        )

    @staticmethod
    def aerodynamic_force(
        train: Train,
        speed_ms: float,
        environment: Environment
    ) -> float:

        rho = TrainPhysics.air_density(environment)

        relative_speed = TrainPhysics.effective_air_speed(
            speed_ms,
            environment
        )

        return (
            0.5
            * rho
            * train.drag_coefficient
            * train.frontal_area_m2
            * relative_speed ** 2
        )

    @staticmethod
    def rolling_force(
        train: Train
    ) -> float:

        return (
            train.mass_kg
            * TrainPhysics.G
            * train.rolling_resistance_coefficient
        )

    @staticmethod
    def gradient_force(
        train: Train,
        environment: Environment
    ) -> float:

        gradient = environment.gradient_percent / 100.0

        return (
            train.mass_kg
            * TrainPhysics.G
            * gradient
        )

    @staticmethod
    def total_resistance(
        train: Train,
        speed_ms: float,
        environment: Environment
    ) -> float:

        aero = TrainPhysics.aerodynamic_force(
            train,
            speed_ms,
            environment
        )

        rolling = TrainPhysics.rolling_force(train)

        gradient = TrainPhysics.gradient_force(
            train,
            environment
        )

        return aero + rolling + gradient


# ============================================================
# POWERTRAIN
# ============================================================

class PowertrainModel:

    def __init__(
        self,
        train: Train,
        electrical: ElectricalSystem
    ):

        self.train = train
        self.electrical = electrical

    def motor_power_limit_kw(self) -> float:

        if not self.train.motors:
            return 0.0

        return sum(
            min(
                motor.rated_power_kw,
                motor.max_power_kw
            )
            for motor in self.train.motors
        )

    def inverter_power_limit_kw(self) -> float:

        if not self.train.inverters:
            return 0.0

        return sum(
            min(
                inverter.rated_power_kw,
                inverter.maximum_power_kw
            )
            for inverter in self.train.inverters
        )

    def electrical_power_limit_kw(self) -> float:

        return min(
            self.electrical.maximum_transformer_power_kw,
            self.electrical.maximum_catenary_power_kw
        )

    def available_power_kw(self) -> float:

        motor_limit = self.motor_power_limit_kw()

        inverter_limit = self.inverter_power_limit_kw()

        electrical_limit = self.electrical_power_limit_kw()

        return min(
            motor_limit,
            inverter_limit,
            electrical_limit
        )


# ============================================================
# ADHESION
# ============================================================

class AdhesionModel:

    @staticmethod
    def maximum_tractive_force(
        train: Train,
        environment: Environment
    ) -> float:

        effective_mu = (
            train.adhesion_coefficient
            * environment.rail_adhesion_factor
        )

        return (
            effective_mu
            * train.mass_kg
            * TrainPhysics.G
        )

    @staticmethod
    def force_from_power(
        power_kw: float,
        speed_ms: float
    ) -> float:

        if speed_ms <= 0:
            return float("inf")

        return (
            power_kw * 1000.0
        ) / speed_ms


# ============================================================
# THERMAL MODEL
# ============================================================

class ThermalModel:

    @staticmethod
    def update_motor_temperature(
        motor: Motor,
        power_kw: float,
        dt_s: float
    ) -> float:

        heat_loss_kw = (
            power_kw
            * (1.0 - motor.efficiency)
        )

        temperature_target = (
            25.0
            + heat_loss_kw * 1.8
        )

        alpha = min(
            1.0,
            dt_s / motor.thermal_time_constant_s
        )

        motor.temperature_c += (
            temperature_target
            - motor.temperature_c
        ) * alpha

        return motor.temperature_c

    @staticmethod
    def update_inverter_temperature(
        inverter: Inverter,
        power_kw: float,
        dt_s: float
    ) -> float:

        heat_loss_kw = (
            power_kw
            * (1.0 - inverter.efficiency)
        )

        temperature_target = (
            30.0
            + heat_loss_kw * 2.0
        )

        alpha = min(
            1.0,
            dt_s / inverter.thermal_time_constant_s
        )

        inverter.temperature_c += (
            temperature_target
            - inverter.temperature_c
        ) * alpha

        return inverter.temperature_c


# ============================================================
# BRAKING
# ============================================================

class BrakingModel:

    @staticmethod
    def stopping_distance(
        speed_ms: float,
        deceleration_ms2: float
    ) -> float:

        if deceleration_ms2 <= 0:
            return float("inf")

        return (
            speed_ms ** 2
        ) / (
            2.0 * deceleration_ms2
        )

    @staticmethod
    def braking_distance(
        train: Train,
        speed_kmh: float
    ) -> float:

        speed_ms = speed_kmh / 3.6

        return BrakingModel.stopping_distance(
            speed_ms,
            train.service_brake_deceleration_ms2
        )


# ============================================================
# MAIN OPTIMIZER
# ============================================================

class ExperimentalOptimizer:

    def __init__(
        self,
        train: Train,
        electrical: ElectricalSystem,
        track: TestTrack,
        environment: Environment
    ):

        self.train = train
        self.electrical = electrical
        self.track = track
        self.environment = environment

        self.powertrain = PowertrainModel(
            train,
            electrical
        )

    # --------------------------------------------------------
    # PERFORMANCE EVALUATION
    # --------------------------------------------------------

    def evaluate(
        self,
        speed_kmh: float
    ) -> PerformanceResult:

        speed_ms = speed_kmh / 3.6

        resistance = TrainPhysics.total_resistance(
            self.train,
            speed_ms,
            self.environment
        )

        aero = TrainPhysics.aerodynamic_force(
            self.train,
            speed_ms,
            self.environment
        )

        rolling = TrainPhysics.rolling_force(
            self.train
        )

        gradient = TrainPhysics.gradient_force(
            self.train,
            self.environment
        )

        required_power_kw = (
            resistance
            * speed_ms
            / 1000.0
        )

        available_power_kw = (
            self.powertrain.available_power_kw()
        )

        adhesion_force = (
            AdhesionModel.maximum_tractive_force(
                self.train,
                self.environment
            )
        )

        traction_force = AdhesionModel.force_from_power(
            available_power_kw,
            speed_ms
        )

        motor_temps = []

        for motor in self.train.motors:

            temp = ThermalModel.update_motor_temperature(
                motor,
                available_power_kw / max(
                    1,
                    len(self.train.motors)
                ),
                10.0
            )

            motor_temps.append(temp)

        inverter_temps = []

        for inverter in self.train.inverters:

            temp = ThermalModel.update_inverter_temperature(
                inverter,
                available_power_kw / max(
                    1,
                    len(self.train.inverters)
                ),
                10.0
            )

            inverter_temps.append(temp)

        max_motor_temperature = (
            max(motor_temps)
            if motor_temps
            else 0.0
        )

        max_inverter_temperature = (
            max(inverter_temps)
            if inverter_temps
            else 0.0
        )

        braking_distance = (
            BrakingModel.braking_distance(
                self.train,
                speed_kmh
            )
        )

        # ----------------------------------------------------
        # LIMIT DETECTION
        # ----------------------------------------------------

        factor = LimitingFactor.NONE
        margin = 100.0

        if speed_kmh > self.track.authorised_test_speed_kmh:
            factor = LimitingFactor.TRACK
            margin = 0.0

        elif speed_kmh > self.train.maximum_certified_speed_kmh:
            factor = LimitingFactor.VEHICLE_CERTIFICATION
            margin = 0.0

        elif required_power_kw > available_power_kw:

            factor = LimitingFactor.TRACTION_POWER

            margin = (
                available_power_kw
                / max(required_power_kw, 1.0)
            ) * 100.0

        elif traction_force > adhesion_force:

            factor = LimitingFactor.ADHESION

            margin = (
                adhesion_force
                / max(traction_force, 1.0)
            ) * 100.0

        elif max_motor_temperature >= (
            0.95 * max(
                m.maximum_temperature_c
                for m in self.train.motors
            )
            if self.train.motors
            else False
        ):

            factor = LimitingFactor.MOTOR_THERMAL
            margin = 5.0

        elif max_inverter_temperature >= (
            0.95 * max(
                i.maximum_temperature_c
                for i in self.train.inverters
            )
            if self.train.inverters
            else False
        ):

            factor = LimitingFactor.INVERTER_THERMAL
            margin = 5.0

        elif (
            abs(self.environment.crosswind_ms)
            > self.track.maximum_wind_crosswind_ms
        ):

            factor = LimitingFactor.WIND
            margin = 0.0

        elif (
            abs(self.environment.headwind_ms)
            > self.track.maximum_wind_headwind_ms
        ):

            factor = LimitingFactor.WIND
            margin = 0.0

        else:

            # Power margin
            if required_power_kw > 0:

                margin = (
                    1.0
                    - required_power_kw
                    / available_power_kw
                ) * 100.0

            factor = LimitingFactor.NONE

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        if factor in (
            LimitingFactor.TRACK,
            LimitingFactor.VEHICLE_CERTIFICATION,
            LimitingFactor.WIND
        ):

            status = TestStatus.HOLD

        elif margin < self.track.safety_margin_percent:

            status = TestStatus.CAUTION

        else:

            status = TestStatus.PASS

        return PerformanceResult(
            speed_kmh=speed_kmh,
            speed_ms=speed_ms,

            aerodynamic_force_n=aero,
            rolling_force_n=rolling,
            gradient_force_n=gradient,

            total_resistance_n=resistance,

            required_power_kw=required_power_kw,
            available_power_kw=available_power_kw,

            adhesion_force_n=adhesion_force,

            motor_temperature_c=max_motor_temperature,
            inverter_temperature_c=max_inverter_temperature,

            braking_distance_m=braking_distance,

            limiting_factor=factor,

            status=status,

            margin_percent=margin
        )

    # --------------------------------------------------------
    # SEARCH PERFORMANCE ENVELOPE
    # --------------------------------------------------------

    def speed_envelope(
        self,
        minimum_kmh: float,
        maximum_kmh: float,
        increment_kmh: float
    ) -> List[PerformanceResult]:

        results = []

        speed = minimum_kmh

        while speed <= maximum_kmh:

            results.append(
                self.evaluate(speed)
            )

            speed += increment_kmh

        return results

    # --------------------------------------------------------
    # FIND THEORETICAL PERFORMANCE LIMIT
    # --------------------------------------------------------

    def theoretical_limit(
        self,
        minimum_kmh: float,
        maximum_kmh: float,
        increment_kmh: float = 1.0
    ) -> PerformanceResult:

        best = None

        for result in self.speed_envelope(
            minimum_kmh,
            maximum_kmh,
            increment_kmh
        ):

            if result.status == TestStatus.PASS:

                best = result

        if best is None:

            return self.evaluate(
                minimum_kmh
            )

        return best

    # --------------------------------------------------------
    # EXPERIMENTAL SPEED STEPS
    # --------------------------------------------------------

    def experimental_steps(
        self,
        current_validated_speed_kmh: float,
        target_speed_kmh: float,
        step_kmh: float = 10.0
    ) -> List[PerformanceResult]:

        results = []

        speed = (
            current_validated_speed_kmh
            + step_kmh
        )

        while speed <= target_speed_kmh:

            result = self.evaluate(speed)

            results.append(result)

            # Stop generating higher steps if an
            # engineering constraint is encountered.

            if result.status == TestStatus.HOLD:

                break

            speed += step_kmh

        return results

    # --------------------------------------------------------
    # MARGINAL SPEED BENEFIT
    # --------------------------------------------------------

    def marginal_power_cost(
        self,
        speed_a_kmh: float,
        speed_b_kmh: float
    ) -> float:

        a = self.evaluate(speed_a_kmh)
        b = self.evaluate(speed_b_kmh)

        return (
            b.required_power_kw
            - a.required_power_kw
        )

    # --------------------------------------------------------
    # UPGRADE SIMULATION
    # --------------------------------------------------------

    def simulate_upgrade(
        self,
        drag_reduction: float = 0.0,
        power_increase: float = 0.0,
        mass_reduction: float = 0.0
    ) -> Dict[str, float]:

        original_cd = self.train.drag_coefficient
        original_mass = self.train.mass_kg

        original_motor_limits = [
            m.max_power_kw
            for m in self.train.motors
        ]

        # Apply hypothetical modifications

        self.train.drag_coefficient *= (
            1.0 - drag_reduction
        )

        self.train.mass_kg *= (
            1.0 - mass_reduction
        )

        for motor in self.train.motors:

            motor.max_power_kw *= (
                1.0 + power_increase
            )

        baseline = self.theoretical_limit(
            200,
            self.track.authorised_test_speed_kmh,
            1
        )

        # Restore configuration

        self.train.drag_coefficient = original_cd
        self.train.mass_kg = original_mass

        for motor, original in zip(
            self.train.motors,
            original_motor_limits
        ):

            motor.max_power_kw = original

        return {
            "baseline_speed_kmh":
                baseline.speed_kmh,

            "drag_reduction":
                drag_reduction,

            "power_increase":
                power_increase,

            "mass_reduction":
                mass_reduction
        }


# ============================================================
# TEST REPORT
# ============================================================

class TestReport:

    @staticmethod
    def print_result(
        result: PerformanceResult
    ):

        print()
        print("=" * 72)
        print(
            f"TEST SPEED: {result.speed_kmh:.1f} km/h"
        )
        print("=" * 72)

        print(
            f"Required power:       "
            f"{result.required_power_kw:,.1f} kW"
        )

        print(
            f"Available power:      "
            f"{result.available_power_kw:,.1f} kW"
        )

        print(
            f"Aerodynamic force:    "
            f"{result.aerodynamic_force_n:,.0f} N"
        )

        print(
            f"Rolling force:        "
            f"{result.rolling_force_n:,.0f} N"
        )

        print(
            f"Gradient force:       "
            f"{result.gradient_force_n:,.0f} N"
        )

        print(
            f"Total resistance:     "
            f"{result.total_resistance_n:,.0f} N"
        )

        print(
            f"Motor temperature:    "
            f"{result.motor_temperature_c:.1f} °C"
        )

        print(
            f"Inverter temperature: "
            f"{result.inverter_temperature_c:.1f} °C"
        )

        print(
            f"Braking distance:     "
            f"{result.braking_distance_m:,.0f} m"
        )

        print(
            f"Performance margin:   "
            f"{result.margin_percent:.1f}%"
        )

        print(
            f"Limiting factor:      "
            f"{result.limiting_factor.value}"
        )

        print(
            f"Test status:          "
            f"{result.status.value}"
        )

    @staticmethod
    def print_steps(
        results: List[PerformanceResult]
    ):

        print()
        print("=" * 90)
        print("EXPERIMENTAL SPEED ENVELOPE")
        print("=" * 90)

        print(
            f"{'Speed':>10}"
            f"{'Power':>12}"
            f"{'Margin':>12}"
            f"{'Motor °C':>12}"
            f"{'Brake m':>12}"
            f"{'Limit':>22}"
        )

        print("-" * 90)

        for r in results:

            print(
                f"{r.speed_kmh:>10.0f}"
                f"{r.required_power_kw:>12.0f}"
                f"{r.margin_percent:>11.1f}%"
                f"{r.motor_temperature_c:>12.1f}"
                f"{r.braking_distance_m:>12.0f}"
                f"{r.limiting_factor.value:>22}"
            )


# ============================================================
# EXAMPLE TEST TRAIN
# ============================================================

def create_test_train():

    motors = [
        Motor(
            rated_power_kw=1500,
            max_power_kw=1650,
            efficiency=0.96
        )
        for _ in range(8)
    ]

    inverters = [
        Inverter(
            rated_power_kw=1600,
            maximum_power_kw=1750,
            efficiency=0.985
        )
        for _ in range(8)
    ]

    train = Train(

        mass_kg=450_000,

        frontal_area_m2=11.5,

        drag_coefficient=0.18,

        rolling_resistance_coefficient=0.0015,

        wheel_diameter_m=0.92,

        motors=motors,

        inverters=inverters,

        maximum_certified_speed_kmh=350,

        adhesion_coefficient=0.18,

        axle_load_kg=18_000,

        service_brake_deceleration_ms2=0.65,

        emergency_brake_deceleration_ms2=1.0,

        maximum_body_speed_kmh=380
    )

    electrical = ElectricalSystem(

        nominal_voltage_v=25_000,

        maximum_current_a=700,

        transformer_efficiency=0.985,

        maximum_transformer_power_kw=17_000,

        maximum_catenary_power_kw=17_500,

        minimum_voltage_v=21_000
    )

    track = TestTrack(

        name="High-Speed Experimental Test Track",

        length_km=50,

        authorised_test_speed_kmh=400,

        minimum_curve_radius_m=7000,

        maximum_gradient_percent=1.5,

        track_quality_factor=1.0,

        braking_margin_factor=1.20,

        maximum_wind_crosswind_ms=10,

        maximum_wind_headwind_ms=15,

        safety_margin_percent=10
    )

    environment = Environment(

        temperature_c=15,

        pressure_pa=101325,

        headwind_ms=2,

        crosswind_ms=3,

        gradient_percent=0,

        rail_adhesion_factor=1.0
    )

    return train, electrical, track, environment


# ============================================================
# DEMONSTRATION
# ============================================================

def main():

    train, electrical, track, environment = (
        create_test_train()
    )

    optimizer = ExperimentalOptimizer(
        train,
        electrical,
        track,
        environment
    )

    print()
    print("RAILBOOST-X")
    print("Experimental High-Speed Test Optimizer")
    print()

    # --------------------------------------------------------
    # Current validated speed
    # --------------------------------------------------------

    current_speed = 300.0

    print(
        f"Current validated speed: "
        f"{current_speed:.0f} km/h"
    )

    # --------------------------------------------------------
    # Evaluate candidate speeds
    # --------------------------------------------------------

    candidates = [
        300,
        310,
        320,
        330,
        340,
        350,
        360,
        370,
        380,
        390,
        400
    ]

    results = [
        optimizer.evaluate(speed)
        for speed in candidates
    ]

    TestReport.print_steps(results)

    # --------------------------------------------------------
    # Experimental increments
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("INCREMENTAL TEST PROGRAM")
    print("=" * 72)

    steps = optimizer.experimental_steps(
        current_validated_speed_kmh=300,
        target_speed_kmh=400,
        step_kmh=10
    )

    TestReport.print_steps(steps)

    # --------------------------------------------------------
    # Theoretical envelope
    # --------------------------------------------------------

    limit = optimizer.theoretical_limit(
        minimum_kmh=250,
        maximum_kmh=400,
        increment_kmh=1
    )

    print()
    print("=" * 72)
    print("THEORETICAL PERFORMANCE ENVELOPE")
    print("=" * 72)

    print(
        f"Highest simulated PASS speed: "
        f"{limit.speed_kmh:.0f} km/h"
    )

    print(
        f"Limiting factor: "
        f"{limit.limiting_factor.value}"
    )

    # --------------------------------------------------------
    # Marginal power
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("MARGINAL SPEED COST")
    print("=" * 72)

    for speed in [300, 320, 340, 360, 380]:

        next_speed = speed + 10

        delta_power = optimizer.marginal_power_cost(
            speed,
            next_speed
        )

        print(
            f"{speed:3.0f} -> {next_speed:3.0f} km/h : "
            f"+{delta_power:,.0f} kW"
        )

    # --------------------------------------------------------
    # Upgrade study
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("HYPOTHETICAL PERFORMANCE STUDIES")
    print("=" * 72)

    studies = [

        (
            "Aerodynamic optimisation",
            {
                "drag_reduction": 0.10,
                "power_increase": 0.0,
                "mass_reduction": 0.0
            }
        ),

        (
            "Traction upgrade",
            {
                "drag_reduction": 0.0,
                "power_increase": 0.10,
                "mass_reduction": 0.0
            }
        ),

        (
            "Mass reduction",
            {
                "drag_reduction": 0.0,
                "power_increase": 0.0,
                "mass_reduction": 0.05
            }
        ),

        (
            "Combined optimisation",
            {
                "drag_reduction": 0.08,
                "power_increase": 0.08,
                "mass_reduction": 0.03
            }
        )
    ]

    for name, parameters in studies:

        result = optimizer.simulate_upgrade(
            **parameters
        )

        print(
            f"{name:30s} "
            f"{result['baseline_speed_kmh']:.0f} km/h"
        )


if __name__ == "__main__":
    main()
