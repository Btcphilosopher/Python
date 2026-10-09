"""
WINE FOUNTAIN CONTROL SYSTEM
============================

Purpose:
    Supervise circulation, flow stability, liquid levels,
    temperature, leakage, and cleaning operations.

Architecture:
    - Asynchronous control loop
    - Simulated sensor and actuator interfaces
    - Proportional flow controller
    - Reservoir and basin protection
    - Leak and sensor fault handling
    - Cleaning-cycle state machine
    - Operational telemetry

Python: 3.11+
Dependencies: Standard library only

IMPORTANT:
    This is a simulation and software prototype.
    It is not certified safety-control software.
    Real hardware requires independent electrical,
    mechanical, sanitation, and overflow protections.
"""

from __future__ import annotations

import asyncio
import logging
import random
import signal
import time

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


# ============================================================
# 1. CONFIGURATION
# ============================================================

@dataclass(frozen=True)
class FountainConfig:
    # Control loop
    control_interval: float = 0.5

    # Flow regulation
    target_flow_lpm: float = 4.0
    minimum_flow_lpm: float = 0.5
    maximum_flow_lpm: float = 8.0

    # Pump control
    minimum_pump_percent: float = 0.0
    maximum_pump_percent: float = 80.0
    pump_adjustment_limit: float = 5.0

    # Reservoir limits: percentages
    minimum_reservoir_level: float = 20.0
    maximum_reservoir_level: float = 95.0

    # Fountain basin limits: percentages
    minimum_basin_level: float = 10.0
    maximum_basin_level: float = 90.0

    # Temperature monitoring
    minimum_temperature_c: float = 8.0
    maximum_temperature_c: float = 20.0

    # Fault detection
    leak_detection_enabled: bool = True
    sensor_timeout_seconds: float = 3.0

    # Cleaning
    cleaning_duration_seconds: float = 60.0

    # Shutdown behaviour
    graceful_shutdown_timeout: float = 3.0


CONFIG = FountainConfig()


# ============================================================
# 2. LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)

logger = logging.getLogger("WineFountain")


# ============================================================
# 3. ENUMERATIONS
# ============================================================

class FountainState(Enum):
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    CLEANING = auto()
    FAULT = auto()
    SHUTTING_DOWN = auto()


class FaultCode(Enum):
    LOW_RESERVOIR = auto()
    HIGH_RESERVOIR = auto()
    LOW_BASIN = auto()
    HIGH_BASIN = auto()
    LEAK_DETECTED = auto()
    TEMPERATURE_OUT_OF_RANGE = auto()
    FLOW_TOO_LOW = auto()
    FLOW_TOO_HIGH = auto()
    SENSOR_FAILURE = auto()
    PUMP_FAILURE = auto()


# ============================================================
# 4. SENSOR DATA MODEL
# ============================================================

@dataclass
class SensorSnapshot:
    timestamp: float

    reservoir_level: float
    basin_level: float

    flow_lpm: float
    temperature_c: float

    leak_detected: bool
    pump_running: bool

    sensor_valid: bool = True


@dataclass
class FountainTelemetry:
    timestamp: float
    state: FountainState

    flow_lpm: float
    target_flow_lpm: float

    reservoir_level: float
    basin_level: float

    temperature_c: float
    pump_percent: float

    active_faults: tuple[str, ...]


# ============================================================
# 5. SIMULATED HARDWARE
# ============================================================

class SimulatedHardware:
    """
    Simulates sensors and a pump.

    Replace this class with real hardware drivers when
    integrating a physical fountain.

    No GPIO pins or physical devices are controlled here.
    """

    def __init__(self):
        self.reservoir_level = 80.0
        self.basin_level = 45.0
        self.temperature_c = 14.0

        self.flow_lpm = 0.0
        self.pump_percent = 0.0

        self.leak_detected = False
        self.sensor_valid = True

        self.pump_running = False

        self.last_update = time.monotonic()

    async def set_pump(self, percent: float) -> None:
        """Set simulated pump command."""

        self.pump_percent = max(0.0, min(80.0, percent))
        self.pump_running = self.pump_percent > 0.0

    async def read_sensors(self) -> SensorSnapshot:
        """
        Advance the physical simulation and return
        a coherent sensor snapshot.
        """

        now = time.monotonic()
        dt = max(0.0, now - self.last_update)
        self.last_update = now

        # Simulated pump response.
        #
        # The pump approaches its commanded flow gradually,
        # rather than responding instantaneously.

        desired_flow = self.pump_percent / 80.0 * 8.0

        response_factor = min(1.0, dt / 2.0)

        self.flow_lpm += (
            desired_flow - self.flow_lpm
        ) * response_factor

        # Small simulated measurement disturbances.
        measured_flow = max(
            0.0,
            self.flow_lpm + random.uniform(-0.03, 0.03),
        )

        # Estimate circulation and return.
        #
        # This model assumes a closed loop in which most
        # wine pumped to the fountain returns to the basin.
        #
        # Real systems need their own hydraulic model.

        if self.pump_running:
            circulation = self.flow_lpm * dt / 60.0

            self.reservoir_level -= circulation * 0.03
            self.basin_level += circulation * 0.02

        # Slow environmental temperature drift.
        self.temperature_c += random.uniform(-0.002, 0.002)

        return SensorSnapshot(
            timestamp=now,
            reservoir_level=self.reservoir_level,
            basin_level=self.basin_level,
            flow_lpm=measured_flow,
            temperature_c=self.temperature_c,
            leak_detected=self.leak_detected,
            pump_running=self.pump_running,
            sensor_valid=self.sensor_valid,
        )

    async def emergency_stop(self) -> None:
        """Immediately command the simulated pump to stop."""

        self.pump_percent = 0.0
        self.pump_running = False

        logger.critical("Pump emergency stop commanded.")


# ============================================================
# 6. FLOW CONTROLLER
# ============================================================

class FlowController:
    """
    Proportional controller with bounded adjustments.

    The controller changes the pump command gradually
    to reduce the difference between measured and target flow.

    This is a starting point for simulation, not a tuned
    controller for an actual pump.
    """

    def __init__(self, config: FountainConfig):
        self.config = config

        self.target = config.target_flow_lpm
        self.command_percent = 0.0

        self.kp = 5.0

    def reset(self) -> None:
        self.command_percent = 0.0

    def update(self, measured_flow: float) -> float:
        error = self.target - measured_flow

        adjustment = self.kp * error

        # Bound the change to avoid abrupt commands.
        adjustment = max(
            -self.config.pump_adjustment_limit,
            min(
                self.config.pump_adjustment_limit,
                adjustment,
            ),
        )

        self.command_percent += adjustment

        self.command_percent = max(
            self.config.minimum_pump_percent,
            min(
                self.config.maximum_pump_percent,
                self.command_percent,
            ),
        )

        return self.command_percent


# ============================================================
# 7. SAFETY SUPERVISOR
# ============================================================

class SafetySupervisor:
    """
    Evaluates operating conditions and returns active faults.

    Any detected safety fault causes the supervisory
    controller to stop normal operation.
    """

    def __init__(self, config: FountainConfig):
        self.config = config

    def evaluate(
        self,
        sensors: SensorSnapshot,
    ) -> list[FaultCode]:

        faults: list[FaultCode] = []

        if not sensors.sensor_valid:
            faults.append(FaultCode.SENSOR_FAILURE)
            return faults

        if (
            sensors.reservoir_level
            < self.config.minimum_reservoir_level
        ):
            faults.append(FaultCode.LOW_RESERVOIR)

        if (
            sensors.reservoir_level
            > self.config.maximum_reservoir_level
        ):
            faults.append(FaultCode.HIGH_RESERVOIR)

        if (
            sensors.basin_level
            < self.config.minimum_basin_level
        ):
            faults.append(FaultCode.LOW_BASIN)

        if (
            sensors.basin_level
            > self.config.maximum_basin_level
        ):
            faults.append(FaultCode.HIGH_BASIN)

        if (
            self.config.leak_detection_enabled
            and sensors.leak_detected
        ):
            faults.append(FaultCode.LEAK_DETECTED)

        if (
            sensors.temperature_c
            < self.config.minimum_temperature_c
            or sensors.temperature_c
            > self.config.maximum_temperature_c
        ):
            faults.append(FaultCode.TEMPERATURE_OUT_OF_RANGE)

        # A pump command with no measurable flow may indicate
        # a blockage, disconnected pipe, failed pump, or sensor fault.

        if sensors.pump_running and (
            sensors.flow_lpm < self.config.minimum_flow_lpm
        ):
            faults.append(FaultCode.FLOW_TOO_LOW)

        if (
            sensors.flow_lpm > self.config.maximum_flow_lpm
        ):
            faults.append(FaultCode.FLOW_TOO_HIGH)

        return faults


# ============================================================
# 8. CLEANING CYCLE
# ============================================================

class CleaningController:
    """
    Coordinates a timed cleaning state.

    This module does not itself operate cleaning valves,
    dosing pumps, or hot-water equipment.

    A real cleaning sequence needs explicit valve interlocks,
    compatible cleaning agents, rinse verification, and
    food-contact sanitation procedures.
    """

    def __init__(self, config: FountainConfig):
        self.config = config
        self.started_at: Optional[float] = None

    def start(self) -> None:
        self.started_at = time.monotonic()

        logger.info("Cleaning cycle started.")

    def is_complete(self) -> bool:
        if self.started_at is None:
            return False

        elapsed = time.monotonic() - self.started_at

        return elapsed >= self.config.cleaning_duration_seconds

    def reset(self) -> None:
        self.started_at = None


# ============================================================
# 9. MAIN FOUNTAIN CONTROLLER
# ============================================================

class WineFountainController:

    def __init__(
        self,
        hardware: SimulatedHardware,
        config: FountainConfig,
    ):
        self.hardware = hardware
        self.config = config

        self.state = FountainState.STOPPED

        self.flow_controller = FlowController(config)
        self.safety = SafetySupervisor(config)
        self.cleaning = CleaningController(config)

        self.active_faults: list[FaultCode] = []

        self.last_snapshot: Optional[SensorSnapshot] = None

        self.running = False

        self.last_valid_sensor_time = time.monotonic()

    async def start(self) -> None:
        if self.state not in (
            FountainState.STOPPED,
        ):
            raise RuntimeError(
                f"Cannot start from state {self.state.name}"
            )

        logger.info("Initialising wine fountain.")

        self.state = FountainState.STARTING

        await self.hardware.set_pump(0.0)

        sensors = await self.hardware.read_sensors()

        faults = self.safety.evaluate(sensors)

        if faults:
            await self.enter_fault_state(faults)
            return

        self.flow_controller.reset()

        self.state = FountainState.RUNNING
        self.running = True

        logger.info("Wine fountain running.")

    async def enter_fault_state(
        self,
        faults: list[FaultCode],
    ) -> None:

        self.active_faults = list(set(faults))

        self.state = FountainState.FAULT

        await self.hardware.emergency_stop()

        logger.critical(
            "Fountain fault: %s",
            ", ".join(fault.name for fault in self.active_faults),
        )

    async def control_step(self) -> None:
        """
        Execute one complete supervisory control cycle.
        """

        if self.state in (
            FountainState.FAULT,
            FountainState.SHUTTING_DOWN,
            FountainState.STOPPED,
        ):
            return

        sensors = await self.hardware.read_sensors()

        self.last_snapshot = sensors

        # Validate sensor communication freshness.
        now = time.monotonic()

        if sensors.sensor_valid:
            self.last_valid_sensor_time = now

        elif (
            now - self.last_valid_sensor_time
            > self.config.sensor_timeout_seconds
        ):
            await self.enter_fault_state(
                [FaultCode.SENSOR_FAILURE]
            )
            return

        # Evaluate hard operating limits.
        faults = self.safety.evaluate(sensors)

        if faults:
            await self.enter_fault_state(faults)
            return

        # Normal fountain operation.
        if self.state == FountainState.RUNNING:

            pump_command = self.flow_controller.update(
                sensors.flow_lpm
            )

            await self.hardware.set_pump(pump_command)

        # Cleaning is represented as a timed state.
        # The pump remains off in this prototype.
        elif self.state == FountainState.CLEANING:

            await self.hardware.set_pump(0.0)

            if self.cleaning.is_complete():

                self.cleaning.reset()

                self.state = FountainState.STOPPED

                logger.info(
                    "Cleaning timer complete. "
                    "Manual inspection and rinse verification required."
                )

        self.publish_telemetry(sensors)

    def publish_telemetry(
        self,
        sensors: SensorSnapshot,
    ) -> None:

        telemetry = FountainTelemetry(
            timestamp=sensors.timestamp,
            state=self.state,
            flow_lpm=sensors.flow_lpm,
            target_flow_lpm=self.config.target_flow_lpm,
            reservoir_level=sensors.reservoir_level,
            basin_level=sensors.basin_level,
            temperature_c=sensors.temperature_c,
            pump_percent=self.hardware.pump_percent,
            active_faults=tuple(
                fault.name for fault in self.active_faults
            ),
        )

        logger.info(
            "STATE=%s | FLOW=%.2f L/min | TARGET=%.2f L/min | "
            "RESERVOIR=%.1f%% | BASIN=%.1f%% | "
            "TEMP=%.1f°C | PUMP=%.1f%%",
            telemetry.state.name,
            telemetry.flow_lpm,
            telemetry.target_flow_lpm,
            telemetry.reservoir_level,
            telemetry.basin_level,
            telemetry.temperature_c,
            telemetry.pump_percent,
        )

    async def begin_cleaning(self) -> None:
        if self.state != FountainState.STOPPED:
            raise RuntimeError(
                "Cleaning may only begin when the fountain is stopped."
            )

        await self.hardware.set_pump(0.0)

        self.cleaning.start()

        self.state = FountainState.CLEANING

    async def shutdown(self) -> None:
        logger.info("Shutting down fountain.")

        self.state = FountainState.SHUTTING_DOWN
        self.running = False

        await self.hardware.emergency_stop()

        self.flow_controller.reset()

        self.state = FountainState.STOPPED

        logger.info("Fountain stopped.")

    async def run(self) -> None:
        await self.start()

        if self.state == FountainState.FAULT:
            return

        try:
            while self.running:

                cycle_started = time.monotonic()

                await self.control_step()

                if self.state == FountainState.FAULT:
                    self.running = False
                    break

                elapsed = time.monotonic() - cycle_started

                await asyncio.sleep(
                    max(
                        0.0,
                        self.config.control_interval - elapsed,
                    )
                )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception("Unexpected controller failure.")

            await self.enter_fault_state(
                [FaultCode.SENSOR_FAILURE]
            )

        finally:
            await self.shutdown()


# ============================================================
# 10. APPLICATION ENTRY POINT
# ============================================================

async def main() -> None:

    hardware = SimulatedHardware()

    controller = WineFountainController(
        hardware=hardware,
        config=CONFIG,
    )

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                stop_event.set,
            )
        except NotImplementedError:
            pass

    task = asyncio.create_task(controller.run())

    stop_task = asyncio.create_task(stop_event.wait())

    done, pending = await asyncio.wait(
        [task, stop_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    if stop_task in done:
        controller.running = False

        await controller.shutdown()

        task.cancel()

        await asyncio.gather(
            task,
            return_exceptions=True,
        )

    for pending_task in pending:
        pending_task.cancel()

    await asyncio.gather(
        *pending,
        return_exceptions=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
    
    
    
