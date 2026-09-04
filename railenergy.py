"""
RAILENERGYAI
============

Electric railway traction-energy optimisation and regenerative-braking
simulation engine.

PURPOSE
-------
Engineering / digital-twin / decision-support software.

Models:

    * train longitudinal dynamics
    * traction motors
    * inverter efficiency
    * transformer losses
    * catenary limits
    * aerodynamic drag
    * rolling resistance
    * gradients
    * acceleration
    * coasting
    * regenerative braking
    * friction braking
    * battery / wayside storage
    * auxiliary loads
    * energy accounting
    * timetable constraints
    * eco-driving optimisation

IMPORTANT
---------
This is not a safety-critical train controller.

It should not directly command a real train, override ETCS/ATP,
braking protection, signalling, traction interlocks or certified
operating limits.

The optimisation output is an engineering recommendation / energy
management envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional
import math
import statistics


# ============================================================
# ENUMERATIONS
# ============================================================

class OperatingMode(Enum):
    IDLE = "idle"
    ACCELERATING = "accelerating"
    CRUISING = "cruising"
    COASTING = "coasting"
    REGENERATIVE_BRAKING = "regenerative_braking"
    FRICTION_BRAKING = "friction_braking"
    STOPPED = "stopped"


class EnergyDestination(Enum):
    TRAIN_AUXILIARIES = "train_auxiliaries"
    OTHER_TRAIN = "other_train"
    GRID = "grid"
    ONBOARD_STORAGE = "onboard_storage"
    WAYSIDE_STORAGE = "wayside_storage"
    BRAKE_RESISTOR = "brake_resistor"


# ============================================================
# MOTOR
# ============================================================

@dataclass
class TractionMotor:

    rated_power_kw: float

    peak_power_kw: float

    efficiency: float

    regenerative_efficiency: float

    mass_kg: float = 400.0

    temperature_c: float = 40.0

    maximum_temperature_c: float = 150.0

    thermal_time_constant_s: float = 600.0

    maximum_regen_power_kw: float = 1000.0


# ============================================================
# INVERTER
# ============================================================

@dataclass
class Inverter:

    rated_power_kw: float

    efficiency: float

    regenerative_efficiency: float

    temperature_c: float = 35.0

    maximum_temperature_c: float = 120.0

    thermal_time_constant_s: float = 500.0


# ============================================================
# ELECTRICAL SUPPLY
# ============================================================

@dataclass
class ElectricalSupply:

    voltage_v: float

    maximum_current_a: float

    transformer_efficiency: float

    catenary_efficiency: float

    regenerative_grid_efficiency: float

    # Fraction of regenerative power that the infrastructure
    # can accept at the current instant.
    receptivity: float = 0.70

    # Optional onboard battery
    battery_capacity_kwh: float = 0.0

    battery_soc_kwh: float = 0.0

    battery_charge_power_kw: float = 0.0

    battery_discharge_power_kw: float = 0.0

    battery_efficiency: float = 0.95


# ============================================================
# TRAIN
# ============================================================

@dataclass
class ElectricTrain:

    mass_kg: float

    frontal_area_m2: float

    drag_coefficient: float

    rolling_resistance_coefficient: float

    maximum_speed_kmh: float

    maximum_acceleration_ms2: float

    maximum_service_deceleration_ms2: float

    number_of_motors: int

    motors: List[TractionMotor]

    inverters: List[Inverter]

    auxiliary_power_kw: float

    # Mechanical braking efficiency is represented separately
    # because friction braking dissipates kinetic energy as heat.

    service_brake_efficiency: float = 0.0


# ============================================================
# TRACK SEGMENT
# ============================================================

@dataclass
class TrackSegment:

    distance_m: float

    gradient_percent: float

    speed_limit_kmh: float

    station_stop: bool = False

    station_dwell_s: float = 0.0


# ============================================================
# ENVIRONMENT
# ============================================================

@dataclass
class Environment:

    temperature_c: float = 15.0

    pressure_pa: float = 101325.0

    headwind_ms: float = 0.0

    crosswind_ms: float = 0.0


# ============================================================
# ENERGY ACCOUNTING
# ============================================================

@dataclass
class EnergyLedger:

    traction_energy_kwh: float = 0.0

    regenerative_energy_kwh: float = 0.0

    recovered_energy_kwh: float = 0.0

    grid_return_energy_kwh: float = 0.0

    onboard_storage_energy_kwh: float = 0.0

    wayside_storage_energy_kwh: float = 0.0

    brake_resistor_energy_kwh: float = 0.0

    auxiliary_energy_kwh: float = 0.0

    friction_braking_energy_kwh: float = 0.0

    net_grid_energy_kwh: float = 0.0

    distance_km: float = 0.0

    def net_consumption(self):

        return max(
            0.0,
            self.traction_energy_kwh
            + self.auxiliary_energy_kwh
            - self.recovered_energy_kwh
        )

    def kwh_per_km(self):

        if self.distance_km <= 0:
            return 0.0

        return (
            self.net_consumption()
            / self.distance_km
        )


# ============================================================
# PHYSICS
# ============================================================

class RailwayPhysics:

    G = 9.80665

    AIR_R = 287.05

    @staticmethod
    def air_density(
        environment: Environment
    ):

        temperature_k = (
            environment.temperature_c
            + 273.15
        )

        return (
            environment.pressure_pa
            /
            (
                RailwayPhysics.AIR_R
                * temperature_k
            )
        )

    @staticmethod
    def relative_air_speed(
        speed_ms,
        environment
    ):

        return max(
            0.0,
            speed_ms
            + environment.headwind_ms
        )

    @staticmethod
    def aerodynamic_drag(
        train,
        speed_ms,
        environment
    ):

        rho = RailwayPhysics.air_density(
            environment
        )

        v = RailwayPhysics.relative_air_speed(
            speed_ms,
            environment
        )

        return (
            0.5
            * rho
            * train.drag_coefficient
            * train.frontal_area_m2
            * v ** 2
        )

    @staticmethod
    def rolling_resistance(
        train
    ):

        return (
            train.mass_kg
            * RailwayPhysics.G
            * train.rolling_resistance_coefficient
        )

    @staticmethod
    def gradient_resistance(
        train,
        gradient_percent
    ):

        gradient = (
            gradient_percent
            / 100.0
        )

        return (
            train.mass_kg
            * RailwayPhysics.G
            * gradient
        )

    @staticmethod
    def total_resistance(
        train,
        speed_ms,
        gradient_percent,
        environment
    ):

        return (
            RailwayPhysics.aerodynamic_drag(
                train,
                speed_ms,
                environment
            )
            +
            RailwayPhysics.rolling_resistance(
                train
            )
            +
            RailwayPhysics.gradient_resistance(
                train,
                gradient_percent
            )
        )


# ============================================================
# TRACTION POWER
# ============================================================

class TractionModel:

    def __init__(
        self,
        train: ElectricTrain,
        supply: ElectricalSupply
    ):

        self.train = train

        self.supply = supply

    def maximum_motor_power_kw(self):

        return min(
            sum(
                min(
                    motor.rated_power_kw,
                    motor.peak_power_kw
                )
                for motor in self.train.motors
            ),

            sum(
                inverter.rated_power_kw
                for inverter in self.train.inverters
            )
        )

    def maximum_catenary_power_kw(self):

        return (
            self.supply.voltage_v
            * self.supply.maximum_current_a
            / 1000.0
        )

    def available_power_kw(self):

        return min(
            self.maximum_motor_power_kw(),
            self.maximum_catenary_power_kw()
        )

    def electrical_input_power(
        self,
        mechanical_power_kw
    ):

        if mechanical_power_kw <= 0:
            return 0.0

        motor_efficiency = statistics.mean(
            m.efficiency
            for m in self.train.motors
        )

        inverter_efficiency = statistics.mean(
            i.efficiency
            for i in self.train.inverters
        )

        return (
            mechanical_power_kw
            /
            (
                motor_efficiency
                * inverter_efficiency
                * self.supply.transformer_efficiency
            )
        )


# ============================================================
# REGENERATIVE BRAKING
# ============================================================

class RegenerativeBraking:

    def __init__(
        self,
        train,
        supply
    ):

        self.train = train

        self.supply = supply

    def maximum_regenerative_power_kw(self):

        motor_limit = sum(
            motor.maximum_regen_power_kw
            for motor in self.train.motors
        )

        inverter_limit = sum(
            inverter.rated_power_kw
            for inverter in self.train.inverters
        )

        return min(
            motor_limit,
            inverter_limit
        )

    def generated_power_kw(
        self,
        braking_force_n,
        speed_ms
    ):

        mechanical_power_kw = (
            braking_force_n
            * speed_ms
            / 1000.0
        )

        return min(
            mechanical_power_kw,
            self.maximum_regenerative_power_kw()
        )

    def recover_energy(
        self,
        power_kw,
        dt_s,
        ledger
    ):

        if power_kw <= 0:
            return 0.0

        energy_kwh = (
            power_kw
            * dt_s
            / 3600.0
        )

        ledger.regenerative_energy_kwh += (
            energy_kwh
        )

        remaining = energy_kwh

        # ----------------------------------------------------
        # 1. Onboard storage
        # ----------------------------------------------------

        if (
            self.supply.battery_capacity_kwh
            > 0
        ):

            available_capacity = (
                self.supply.battery_capacity_kwh
                - self.supply.battery_soc_kwh
            )

            battery_acceptance = min(
                remaining,
                available_capacity,
                self.supply.battery_charge_power_kw
                * dt_s
                / 3600.0
            )

            stored = (
                battery_acceptance
                * self.supply.battery_efficiency
            )

            self.supply.battery_soc_kwh += stored

            ledger.onboard_storage_energy_kwh += stored

            remaining -= battery_acceptance

        # ----------------------------------------------------
        # 2. Other trains / catenary
        # ----------------------------------------------------

        if remaining > 0:

            grid_acceptance = (
                remaining
                * self.supply.receptivity
            )

            grid_acceptance = min(
                grid_acceptance,
                self.supply.maximum_current_a
                * self.supply.voltage_v
                / 1000.0
                * dt_s
                / 3600.0
            )

            ledger.grid_return_energy_kwh += (
                grid_acceptance
            )

            ledger.recovered_energy_kwh += (
                grid_acceptance
            )

            remaining -= grid_acceptance

        # ----------------------------------------------------
        # 3. Unrecoverable energy
        # ----------------------------------------------------

        if remaining > 0:

            ledger.brake_resistor_energy_kwh += (
                remaining
            )

        return energy_kwh


# ============================================================
# ENERGY MANAGER
# ============================================================

class EnergyManager:

    def __init__(
        self,
        train,
        supply
    ):

        self.train = train

        self.supply = supply

        self.traction = TractionModel(
            train,
            supply
        )

        self.regen = RegenerativeBraking(
            train,
            supply
        )

    def acceleration_power(
        self,
        acceleration_ms2,
        speed_ms,
        gradient_percent,
        environment
    ):

        resistance = (
            RailwayPhysics.total_resistance(
                self.train,
                speed_ms,
                gradient_percent,
                environment
            )
        )

        inertial_force = (
            self.train.mass_kg
            * acceleration_ms2
        )

        total_force = (
            resistance
            + inertial_force
        )

        mechanical_power_kw = (
            total_force
            * speed_ms
            / 1000.0
        )

        return min(
            mechanical_power_kw,
            self.traction.available_power_kw()
        )

    def braking_power(
        self,
        deceleration_ms2,
        speed_ms,
        gradient_percent,
        environment
    ):

        resistance = (
            RailwayPhysics.total_resistance(
                self.train,
                speed_ms,
                gradient_percent,
                environment
            )
        )

        inertial_force = (
            self.train.mass_kg
            * deceleration_ms2
        )

        braking_force = max(
            0.0,
            inertial_force
            + resistance
        )

        regenerative_power = (
            self.regen.generated_power_kw(
                braking_force,
                speed_ms
            )
        )

        return regenerative_power


# ============================================================
# TRAIN SIMULATION
# ============================================================

class TrainSimulator:

    def __init__(
        self,
        train,
        supply,
        environment
    ):

        self.train = train

        self.supply = supply

        self.environment = environment

        self.energy = EnergyLedger()

        self.manager = EnergyManager(
            train,
            supply
        )

        self.speed_ms = 0.0

        self.position_m = 0.0

        self.time_s = 0.0

        self.mode = OperatingMode.STOPPED

    def step(
        self,
        acceleration_ms2,
        gradient_percent,
        dt_s
    ):

        old_speed = self.speed_ms

        # ----------------------------------------------------
        # Determine operating mode
        # ----------------------------------------------------

        if acceleration_ms2 > 0.01:
            self.mode = OperatingMode.ACCELERATING

        elif acceleration_ms2 < -0.01:
            self.mode = OperatingMode.REGENERATIVE_BRAKING

        elif self.speed_ms > 0.1:
            self.mode = OperatingMode.COASTING

        else:
            self.mode = OperatingMode.STOPPED

        # ----------------------------------------------------
        # Speed update
        # ----------------------------------------------------

        self.speed_ms += (
            acceleration_ms2
            * dt_s
        )

        self.speed_ms = max(
            0.0,
            self.speed_ms
        )

        # ----------------------------------------------------
        # Distance
        # ----------------------------------------------------

        self.position_m += (
            0.5
            * (old_speed + self.speed_ms)
            * dt_s
        )

        # ----------------------------------------------------
        # Energy
        # ----------------------------------------------------

        if acceleration_ms2 > 0:

            mechanical_power = (
                self.manager.acceleration_power(
                    acceleration_ms2,
                    self.speed_ms,
                    gradient_percent,
                    self.environment
                )
            )

            electrical_power = (
                self.manager.traction
                .electrical_input_power(
                    mechanical_power
                )
            )

            energy = (
                electrical_power
                * dt_s
                / 3600.0
            )

            self.energy.traction_energy_kwh += (
                energy
            )

        elif acceleration_ms2 < 0:

            regen_power = (
                self.manager.braking_power(
                    abs(acceleration_ms2),
                    self.speed_ms,
                    gradient_percent,
                    self.environment
                )
            )

            self.manager.regen.recover_energy(
                regen_power,
                dt_s,
                self.energy
            )

            # Energy not captured regeneratively
            # becomes friction braking.

            mechanical_braking_power = (
                self.train.mass_kg
                * abs(acceleration_ms2)
                * self.speed_ms
                / 1000.0
            )

            friction_power = max(
                0.0,
                mechanical_braking_power
                - regen_power
            )

            self.energy.friction_braking_energy_kwh += (
                friction_power
                * dt_s
                / 3600.0
            )

        # ----------------------------------------------------
        # Auxiliary consumption
        # ----------------------------------------------------

        auxiliary_energy = (
            self.train.auxiliary_power_kw
            * dt_s
            / 3600.0
        )

        self.energy.auxiliary_energy_kwh += (
            auxiliary_energy
        )

        self.time_s += dt_s

        self.energy.distance_km = (
            self.position_m / 1000.0
        )

    def run(
        self,
        duration_s,
        acceleration_profile,
        gradient_percent=0.0,
        dt_s=0.1
    ):

        steps = int(
            duration_s / dt_s
        )

        for i in range(steps):

            acceleration = (
                acceleration_profile(
                    self.time_s,
                    self.speed_ms
                )
            )

            self.step(
                acceleration,
                gradient_percent,
                dt_s
            )

        return self.energy


# ============================================================
# ECO-DRIVING OPTIMIZER
# ============================================================

@dataclass
class DrivingStrategy:

    acceleration_ms2: float

    cruise_speed_kmh: float

    braking_deceleration_ms2: float

    coasting_fraction: float


@dataclass
class StrategyResult:

    strategy: DrivingStrategy

    journey_time_s: float

    energy_kwh: float

    regenerative_energy_kwh: float

    recovered_energy_kwh: float

    friction_braking_energy_kwh: float

    distance_km: float

    kwh_per_km: float


class EcoDrivingOptimizer:

    def __init__(
        self,
        train,
        supply,
        environment
    ):

        self.train = train

        self.supply = supply

        self.environment = environment

    def simulate_strategy(
        self,
        strategy,
        distance_m,
        gradient_percent=0.0,
        dt_s=0.2
    ):

        simulator = TrainSimulator(
            self.train,
            self.supply,
            self.environment
        )

        target_speed = (
            strategy.cruise_speed_kmh
            / 3.6
        )

        # ----------------------------------------------------
        # Simple closed-loop eco-driving policy
        # ----------------------------------------------------

        def profile(
            time_s,
            speed_ms
        ):

            if speed_ms < target_speed:

                return strategy.acceleration_ms2

            # Cruise/coast
            #
            # Coasting avoids spending electrical
            # energy merely to maintain speed when
            # resistance is sufficiently low.

            return 0.0

        maximum_time = 3600.0

        while (
            simulator.position_m
            < distance_m
            and simulator.time_s
            < maximum_time
        ):

            remaining_distance = (
                distance_m
                - simulator.position_m
            )

            # Calculate braking distance
            if strategy.braking_deceleration_ms2 > 0:

                braking_distance = (
                    simulator.speed_ms ** 2
                    /
                    (
                        2.0
                        * strategy.braking_deceleration_ms2
                    )
                )

            else:

                braking_distance = float("inf")

            # Begin braking near destination
            if (
                remaining_distance
                <= braking_distance
                + 50.0
            ):

                acceleration = (
                    -strategy.braking_deceleration_ms2
                )

            else:

                acceleration = profile(
                    simulator.time_s,
                    simulator.speed_ms
                )

            simulator.step(
                acceleration,
                gradient_percent,
                dt_s
            )

        energy = simulator.energy

        return StrategyResult(
            strategy=strategy,

            journey_time_s=simulator.time_s,

            energy_kwh=energy.net_consumption(),

            regenerative_energy_kwh=
                energy.regenerative_energy_kwh,

            recovered_energy_kwh=
                energy.recovered_energy_kwh,

            friction_braking_energy_kwh=
                energy.friction_braking_energy_kwh,

            distance_km=
                energy.distance_km,

            kwh_per_km=
                energy.kwh_per_km()
        )

    def optimise(
        self,
        distance_m,
        minimum_speed_kmh,
        maximum_speed_kmh,
        minimum_journey_time_s,
        gradient_percent=0.0
    ):

        candidates = []

        speed = minimum_speed_kmh

        while speed <= maximum_speed_kmh:

            strategy = DrivingStrategy(

                acceleration_ms2=0.55,

                cruise_speed_kmh=speed,

                braking_deceleration_ms2=0.55,

                coasting_fraction=0.20
            )

            result = self.simulate_strategy(
                strategy,
                distance_m,
                gradient_percent
            )

            if (
                result.journey_time_s
                <= minimum_journey_time_s * 1.05
            ):

                candidates.append(result)

            speed += 5.0

        if not candidates:

            raise RuntimeError(
                "No strategy satisfied timetable constraint."
            )

        return min(
            candidates,
            key=lambda x: x.energy_kwh
        )


# ============================================================
# REGENERATIVE ENERGY UTILISATION STUDY
# ============================================================

@dataclass
class RecoveryScenario:

    name: str

    receptivity: float

    battery_capacity_kwh: float

    battery_charge_power_kw: float


class RecoveryStudy:

    def __init__(
        self,
        train,
        base_supply,
        environment
    ):

        self.train = train

        self.base_supply = base_supply

        self.environment = environment

    def evaluate(
        self,
        scenario,
        distance_m
    ):

        supply = ElectricalSupply(
            voltage_v=self.base_supply.voltage_v,

            maximum_current_a=
                self.base_supply.maximum_current_a,

            transformer_efficiency=
                self.base_supply.transformer_efficiency,

            catenary_efficiency=
                self.base_supply.catenary_efficiency,

            regenerative_grid_efficiency=
                self.base_supply.regenerative_grid_efficiency,

            receptivity=scenario.receptivity,

            battery_capacity_kwh=
                scenario.battery_capacity_kwh,

            battery_soc_kwh=0.0,

            battery_charge_power_kw=
                scenario.battery_charge_power_kw
        )

        optimizer = EcoDrivingOptimizer(
            self.train,
            supply,
            self.environment
        )

        result = optimizer.simulate_strategy(
            DrivingStrategy(
                acceleration_ms2=0.55,

                cruise_speed_kmh=120.0,

                braking_deceleration_ms2=0.55,

                coasting_fraction=0.2
            ),

            distance_m
        )

        return result


# ============================================================
# REPORTING
# ============================================================

class EnergyReport:

    @staticmethod
    def print_result(
        result: StrategyResult
    ):

        print()
        print("=" * 78)
        print("RAILENERGYAI RESULT")
        print("=" * 78)

        print(
            f"Cruise speed:          "
            f"{result.strategy.cruise_speed_kmh:.1f} km/h"
        )

        print(
            f"Journey time:           "
            f"{result.journey_time_s:.1f} s"
        )

        print(
            f"Distance:               "
            f"{result.distance_km:.2f} km"
        )

        print(
            f"Gross traction energy:  "
            f"{result.energy_kwh:.2f} kWh"
        )

        print(
            f"Regenerative energy:    "
            f"{result.regenerative_energy_kwh:.2f} kWh"
        )

        print(
            f"Recovered energy:       "
            f"{result.recovered_energy_kwh:.2f} kWh"
        )

        print(
            f"Friction braking:       "
            f"{result.friction_braking_energy_kwh:.2f} kWh"
        )

        print(
            f"Net energy:             "
            f"{result.energy_kwh:.2f} kWh"
        )

        print(
            f"Energy intensity:       "
            f"{result.kwh_per_km:.2f} kWh/km"
        )

        print("=" * 78)


# ============================================================
# DEMONSTRATION
# ============================================================

def create_train():

    motors = [

        TractionMotor(
            rated_power_kw=1000.0,
            peak_power_kw=1200.0,
            efficiency=0.96,
            regenerative_efficiency=0.94,
            maximum_regen_power_kw=900.0
        )

        for _ in range(8)
    ]

    inverters = [

        Inverter(
            rated_power_kw=1100.0,
            efficiency=0.985,
            regenerative_efficiency=0.975
        )

        for _ in range(8)
    ]

    train = ElectricTrain(

        mass_kg=450_000,

        frontal_area_m2=11.5,

        drag_coefficient=0.20,

        rolling_resistance_coefficient=0.0015,

        maximum_speed_kmh=320,

        maximum_acceleration_ms2=0.60,

        maximum_service_deceleration_ms2=0.70,

        number_of_motors=8,

        motors=motors,

        inverters=inverters,

        auxiliary_power_kw=350
    )

    return train


def create_supply():

    return ElectricalSupply(

        voltage_v=25_000,

        maximum_current_a=700,

        transformer_efficiency=0.985,

        catenary_efficiency=0.98,

        regenerative_grid_efficiency=0.95,

        receptivity=0.75,

        battery_capacity_kwh=0.0,

        battery_soc_kwh=0.0,

        battery_charge_power_kw=0.0,

        battery_discharge_power_kw=0.0
    )


# ============================================================
# MAIN
# ============================================================

def main():

    train = create_train()

    supply = create_supply()

    environment = Environment(
        temperature_c=15.0,
        pressure_pa=101325.0,
        headwind_ms=2.0,
        crosswind_ms=1.0
    )

    optimizer = EcoDrivingOptimizer(
        train,
        supply,
        environment
    )

    # --------------------------------------------------------
    # Optimise a 50 km section
    # --------------------------------------------------------

    best = optimizer.optimise(

        distance_m=50_000,

        minimum_speed_kmh=100,

        maximum_speed_kmh=200,

        minimum_journey_time_s=1500
    )

    EnergyReport.print_result(best)

    # --------------------------------------------------------
    # Regenerative-energy scenarios
    # --------------------------------------------------------

    scenarios = [

        RecoveryScenario(
            name="Low network receptivity",
            receptivity=0.25,
            battery_capacity_kwh=0.0,
            battery_charge_power_kw=0.0
        ),

        RecoveryScenario(
            name="Normal network",
            receptivity=0.70,
            battery_capacity_kwh=0.0,
            battery_charge_power_kw=0.0
        ),

        RecoveryScenario(
            name="High network receptivity",
            receptivity=0.95,
            battery_capacity_kwh=0.0,
            battery_charge_power_kw=0.0
        ),

        RecoveryScenario(
            name="Onboard battery",
            receptivity=0.50,
            battery_capacity_kwh=500,
            battery_charge_power_kw=1000
        )
    ]

    print()
    print("=" * 78)
    print("REGENERATIVE ENERGY STUDY")
    print("=" * 78)

    study = RecoveryStudy(
        train,
        supply,
        environment
    )

    for scenario in scenarios:

        result = study.evaluate(
            scenario,
            50_000
        )

        print()

        print(
            f"{scenario.name:30s}"
        )

        print(
            f"  Regenerated: "
            f"{result.regenerative_energy_kwh:8.1f} kWh"
        )

        print(
            f"  Recovered:   "
            f"{result.recovered_energy_kwh:8.1f} kWh"
        )

        print(
            f"  Net energy:  "
            f"{result.energy_kwh:8.1f} kWh"
        )


if __name__ == "__main__":
    main()
