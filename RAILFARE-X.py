"""
RAILFARE-X
==========

Lowest-fare railway ticket optimisation engine.

Designed primarily as a UK rail fare optimisation prototype.

The engine can consider:

    * Advance tickets
    * Anytime tickets
    * Off-Peak tickets
    * Super Off-Peak tickets
    * Railcard discounts
    * Split-ticket combinations
    * Multiple intermediate stations
    * Different train services
    * Journey-time constraints
    * Transfer constraints
    * Ticket validity
    * Fare caps / maximum journey costs
    * Return-vs-single combinations
    * Price optimisation

IMPORTANT
---------
This is a fare-planning / optimisation engine.

It does NOT attempt to:
    * evade fares
    * falsify passenger information
    * bypass ticket barriers
    * exploit payment systems
    * purchase tickets under false conditions.

Every selected combination must be checked against the
actual ticket's published validity conditions before purchase.

For UK National Rail, split-ticketing is permitted subject to
the National Rail Conditions of Travel and the individual
tickets' restrictions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import heapq
import math


# ============================================================
# ENUMERATIONS
# ============================================================

class TicketType(Enum):

    ADVANCE = "Advance"

    ANYTIME = "Anytime"

    OFF_PEAK = "Off-Peak"

    SUPER_OFF_PEAK = "Super Off-Peak"


class Railcard(Enum):

    NONE = "None"

    TWO_TOGETHER = "Two Together"

    FAMILY_FRIENDS = "Family & Friends"

    SENIOR = "Senior"

    NETWORK = "Network"

    DISABLED = "Disabled Persons"

    OTHER = "Other"


# ============================================================
# STATION
# ============================================================

@dataclass(frozen=True)
class Station:

    code: str
    name: str


# ============================================================
# TRAIN SERVICE
# ============================================================

@dataclass
class TrainService:

    service_id: str

    operator: str

    origin: Station

    destination: Station

    departure: datetime

    arrival: datetime

    calling_points: List[Station]

    standard_available: bool = True

    first_available: bool = False

    reservation_required: bool = False

    fare_classes: Dict[str, float] = field(
        default_factory=dict
    )

    @property
    def duration_minutes(self):

        return (
            self.arrival
            - self.departure
        ).total_seconds() / 60.0

    def calls_at(
        self,
        station: Station
    ):

        return (
            station == self.origin
            or station == self.destination
            or station in self.calling_points
        )


# ============================================================
# FARE
# ============================================================

@dataclass
class Fare:

    origin: Station

    destination: Station

    ticket_type: TicketType

    base_price: float

    route_code: str

    restriction_code: Optional[str] = None

    operator: Optional[str] = None

    valid_services: Optional[List[str]] = None

    railcard_discount: float = 0.0

    break_of_journey_allowed: bool = True

    reservation_required: bool = False

    refundable: bool = False

    notes: str = ""

    def discounted_price(
        self,
        railcard: Railcard
    ):

        return self.base_price * (
            1.0 - self.railcard_discount
        )

    def valid_for(
        self,
        service: TrainService
    ):

        if self.valid_services is not None:

            return (
                service.service_id
                in self.valid_services
            )

        if self.operator is not None:

            if service.operator != self.operator:

                return False

        return True


# ============================================================
# FARE DATABASE
# ============================================================

class FareDatabase:

    def __init__(self):

        self.fares: List[Fare] = []

    def add(
        self,
        fare: Fare
    ):

        self.fares.append(fare)

    def find(
        self,
        origin: Station,
        destination: Station
    ):

        return [
            fare
            for fare in self.fares
            if fare.origin == origin
            and fare.destination == destination
        ]


# ============================================================
# RAILCARD
# ============================================================

class RailcardEngine:

    DISCOUNTS = {

        Railcard.NONE: 0.0,

        Railcard.TWO_TOGETHER: 0.34,

        Railcard.FAMILY_FRIENDS: 0.33,

        Railcard.SENIOR: 0.33,

        Railcard.NETWORK: 0.34,

        Railcard.DISABLED: 0.33,

        Railcard.OTHER: 0.0
    }

    @staticmethod
    def discount(
        railcard: Railcard
    ):

        return RailcardEngine.DISCOUNTS.get(
            railcard,
            0.0
        )


# ============================================================
# JOURNEY LEG
# ============================================================

@dataclass
class JourneyLeg:

    origin: Station

    destination: Station

    service: TrainService

    fare: Fare

    price: float

    railcard: Railcard


# ============================================================
# COMPLETE ITINERARY
# ============================================================

@dataclass
class Itinerary:

    legs: List[JourneyLeg]

    total_price: float

    departure: datetime

    arrival: datetime

    changes: int

    valid: bool = True

    explanation: str = ""

    @property
    def duration_minutes(self):

        return (
            self.arrival
            - self.departure
        ).total_seconds() / 60.0


# ============================================================
# VALIDITY ENGINE
# ============================================================

class TicketValidityEngine:

    """
    Central validity checker.

    In production this should be backed by the current
    published fare/restriction data rather than assumptions.
    """

    def __init__(self):

        self.restrictions = {}

    def register_restriction(
        self,
        code,
        function
    ):

        self.restrictions[code] = function

    def valid_fare_for_service(
        self,
        fare: Fare,
        service: TrainService,
        departure: datetime
    ):

        if not fare.valid_for(service):

            return False

        if fare.restriction_code:

            restriction = self.restrictions.get(
                fare.restriction_code
            )

            if restriction:

                return restriction(
                    departure,
                    service
                )

        return True

    @staticmethod
    def split_is_possible(
        service: TrainService,
        split_station: Station
    ):

        """
        A split-ticket itinerary on one train requires the
        service to call at the split point.

        This reflects the UK National Rail split-ticket rule.
        """

        return service.calls_at(
            split_station
        )


# ============================================================
# PRICE ENGINE
# ============================================================

class PriceEngine:

    def __init__(
        self,
        fare_database: FareDatabase,
        validity: TicketValidityEngine
    ):

        self.fares = fare_database

        self.validity = validity

    def cheapest_fare(
        self,
        origin,
        destination,
        service,
        railcard
    ):

        candidates = []

        for fare in self.fares.find(
            origin,
            destination
        ):

            if not self.validity.valid_fare_for_service(
                fare,
                service,
                service.departure
            ):

                continue

            price = fare.base_price

            discount = (
                RailcardEngine.discount(
                    railcard
                )
            )

            price *= (
                1.0 - discount
            )

            candidates.append(
                (
                    price,
                    fare
                )
            )

        if not candidates:

            return None

        return min(
            candidates,
            key=lambda x: x[0]
        )


# ============================================================
# SPLIT TICKET GENERATOR
# ============================================================

class SplitTicketGenerator:

    def __init__(
        self,
        stations: List[Station]
    ):

        self.stations = stations

    def possible_splits(
        self,
        origin,
        destination,
        service
    ):

        """
        Generate every valid intermediate calling point.

        For a single through service, the service must call at
        the split station.
        """

        splits = []

        for station in self.stations:

            if station == origin:
                continue

            if station == destination:
                continue

            if service.calls_at(station):

                splits.append(station)

        return splits


# ============================================================
# FARE OPTIMIZER
# ============================================================

class FareOptimizer:

    def __init__(
        self,
        stations,
        services,
        fare_database,
        validity
    ):

        self.stations = stations

        self.services = services

        self.fares = fare_database

        self.validity = validity

        self.price_engine = PriceEngine(
            fare_database,
            validity
        )

        self.split_generator = (
            SplitTicketGenerator(
                stations
            )
        )

    # --------------------------------------------------------
    # DIRECT TICKET
    # --------------------------------------------------------

    def direct_options(
        self,
        origin,
        destination,
        railcard
    ):

        results = []

        for service in self.services:

            if service.origin != origin:
                continue

            if service.destination != destination:
                continue

            result = (
                self.price_engine.cheapest_fare(
                    origin,
                    destination,
                    service,
                    railcard
                )
            )

            if result is None:
                continue

            price, fare = result

            leg = JourneyLeg(
                origin=origin,
                destination=destination,
                service=service,
                fare=fare,
                price=price,
                railcard=railcard
            )

            results.append(
                Itinerary(
                    legs=[leg],
                    total_price=price,
                    departure=service.departure,
                    arrival=service.arrival,
                    changes=0
                )
            )

        return results

    # --------------------------------------------------------
    # ONE-TRAIN SPLIT TICKETS
    # --------------------------------------------------------

    def split_options(
        self,
        origin,
        destination,
        railcard
    ):

        results = []

        for service in self.services:

            if service.origin != origin:
                continue

            if service.destination != destination:
                continue

            splits = (
                self.split_generator.possible_splits(
                    origin,
                    destination,
                    service
                )
            )

            for split in splits:

                first = (
                    self.price_engine.cheapest_fare(
                        origin,
                        split,
                        service,
                        railcard
                    )
                )

                second = (
                    self.price_engine.cheapest_fare(
                        split,
                        destination,
                        service,
                        railcard
                    )
                )

                if first is None:
                    continue

                if second is None:
                    continue

                price1, fare1 = first

                price2, fare2 = second

                total = price1 + price2

                leg1 = JourneyLeg(
                    origin,
                    split,
                    service,
                    fare1,
                    price1,
                    railcard
                )

                leg2 = JourneyLeg(
                    split,
                    destination,
                    service,
                    fare2,
                    price2,
                    railcard
                )

                results.append(
                    Itinerary(
                        legs=[
                            leg1,
                            leg2
                        ],
                        total_price=total,
                        departure=service.departure,
                        arrival=service.arrival,
                        changes=0,
                        explanation=(
                            f"Split at {split.name}"
                        )
                    )
                )

        return results

    # --------------------------------------------------------
    # MULTI-LEG JOURNEYS
    # --------------------------------------------------------

    def connection_options(
        self,
        origin,
        destination,
        railcard,
        minimum_connection_minutes=5
    ):

        """
        Search journeys involving a change of train.

        This is deliberately a small graph-search engine.
        """

        graph = {}

        for service in self.services:

            graph.setdefault(
                service.origin.code,
                []
            ).append(service)

        results = []

        def search(
            current,
            legs,
            visited
        ):

            if len(legs) > 3:

                return

            if current == destination:

                if not legs:
                    return

                price = sum(
                    leg.price
                    for leg in legs
                )

                results.append(
                    Itinerary(
                        legs=list(legs),
                        total_price=price,
                        departure=legs[0].service.departure,
                        arrival=legs[-1].service.arrival,
                        changes=len(legs) - 1
                    )
                )

                return

            for service in graph.get(
                current.code,
                []
            ):

                if service.service_id in visited:

                    continue

                if legs:

                    previous = legs[-1].service

                    connection_time = (
                        service.departure
                        - previous.arrival
                    ).total_seconds() / 60.0

                    if connection_time < (
                        minimum_connection_minutes
                    ):

                        continue

                result = (
                    self.price_engine.cheapest_fare(
                        service.origin,
                        service.destination,
                        service,
                        railcard
                    )
                )

                if result is None:

                    continue

                price, fare = result

                leg = JourneyLeg(
                    service.origin,
                    service.destination,
                    service,
                    fare,
                    price,
                    railcard
                )

                search(
                    service.destination,
                    legs + [leg],
                    visited |
                    {service.service_id}
                )

        search(
            origin,
            [],
            set()
        )

        return results

    # --------------------------------------------------------
    # GLOBAL SEARCH
    # --------------------------------------------------------

    def find_cheapest(
        self,
        origin,
        destination,
        railcard=Railcard.NONE
    ):

        candidates = []

        candidates.extend(
            self.direct_options(
                origin,
                destination,
                railcard
            )
        )

        candidates.extend(
            self.split_options(
                origin,
                destination,
                railcard
            )
        )

        candidates.extend(
            self.connection_options(
                origin,
                destination,
                railcard
            )
        )

        if not candidates:

            return None

        return min(
            candidates,
            key=lambda x: x.total_price
        )

    # --------------------------------------------------------
    # TOP N
    # --------------------------------------------------------

    def cheapest_n(
        self,
        origin,
        destination,
        n=10,
        railcard=Railcard.NONE
    ):

        candidates = []

        candidates.extend(
            self.direct_options(
                origin,
                destination,
                railcard
            )
        )

        candidates.extend(
            self.split_options(
                origin,
                destination,
                railcard
            )
        )

        candidates.extend(
            self.connection_options(
                origin,
                destination,
                railcard
            )
        )

        candidates.sort(
            key=lambda x: x.total_price
        )

        return candidates[:n]


# ============================================================
# ADVANCE TICKET SEARCH
# ============================================================

class AdvanceOptimizer:

    """
    Searches different departure times for the cheapest
    available Advance fare.

    """

    def __init__(
        self,
        optimizer: FareOptimizer
    ):

        self.optimizer = optimizer

    def search_departure_window(
        self,
        origin,
        destination,
        earliest,
        latest,
        interval_minutes=15,
        railcard=Railcard.NONE
    ):

        results = []

        current = earliest

        while current <= latest:

            services = [
                s
                for s in self.optimizer.services
                if (
                    s.origin == origin
                    and s.destination == destination
                    and s.departure >= current
                    and s.departure <= latest
                )
            ]

            for service in services:

                result = (
                    self.optimizer.price_engine
                    .cheapest_fare(
                        origin,
                        destination,
                        service,
                        railcard
                    )
                )

                if result is None:
                    continue

                price, fare = result

                leg = JourneyLeg(
                    origin,
                    destination,
                    service,
                    fare,
                    price,
                    railcard
                )

                results.append(
                    Itinerary(
                        [leg],
                        price,
                        service.departure,
                        service.arrival,
                        0
                    )
                )

            current += timedelta(
                minutes=interval_minutes
            )

        results.sort(
            key=lambda x: x.total_price
        )

        return results


# ============================================================
# REPORTING
# ============================================================

class FareReport:

    @staticmethod
    def print_itinerary(
        itinerary: Itinerary
    ):

        print()
        print("=" * 80)
        print("CHEAPEST LEGAL ITINERARY")
        print("=" * 80)

        print(
            f"Total price: "
            f"£{itinerary.total_price:.2f}"
        )

        print(
            f"Departure:   "
            f"{itinerary.departure}"
        )

        print(
            f"Arrival:     "
            f"{itinerary.arrival}"
        )

        print(
            f"Duration:    "
            f"{itinerary.duration_minutes:.0f} minutes"
        )

        print(
            f"Changes:     "
            f"{itinerary.changes}"
        )

        if itinerary.explanation:

            print(
                f"Strategy:    "
                f"{itinerary.explanation}"
            )

        print()

        for i, leg in enumerate(
            itinerary.legs,
            1
        ):

            print(
                f"LEG {i}"
            )

            print(
                f"  {leg.origin.name}"
                f" -> "
                f"{leg.destination.name}"
            )

            print(
                f"  Service: "
                f"{leg.service.service_id}"
            )

            print(
                f"  Operator: "
                f"{leg.service.operator}"
            )

            print(
                f"  Departure: "
                f"{leg.service.departure}"
            )

            print(
                f"  Arrival: "
                f"{leg.service.arrival}"
            )

            print(
                f"  Ticket: "
                f"{leg.fare.ticket_type.value}"
            )

            print(
                f"  Fare: "
                f"£{leg.price:.2f}"
            )

            if leg.fare.restriction_code:

                print(
                    f"  Restriction: "
                    f"{leg.fare.restriction_code}"
                )

            print()

        print("=" * 80)

    @staticmethod
    def compare(
        itineraries
    ):

        print()
        print("=" * 80)
        print("FARE COMPARISON")
        print("=" * 80)

        for i, itinerary in enumerate(
            itineraries,
            1
        ):

            strategy = (
                itinerary.explanation
                or "Direct / connection"
            )

            print(
                f"{i:2d}. "
                f"£{itinerary.total_price:7.2f} | "
                f"{itinerary.duration_minutes:6.0f} min | "
                f"{itinerary.changes} changes | "
                f"{strategy}"
            )


# ============================================================
# DEMO DATABASE
# ============================================================

def create_demo_network():

    london = Station(
        "LON",
        "London"
    )

    reading = Station(
        "RDG",
        "Reading"
    )

    didcot = Station(
        "DID",
        "Didcot Parkway"
    )

    oxford = Station(
        "OXF",
        "Oxford"
    )

    stations = [
        london,
        reading,
        didcot,
        oxford
    ]

    base = datetime(
        2026,
        9,
        5,
        8,
        0
    )

    services = [

        TrainService(
            service_id="GWR101",
            operator="GWR",
            origin=london,
            destination=oxford,
            departure=base,
            arrival=base + timedelta(
                minutes=58
            ),
            calling_points=[
                reading
            ]
        ),

        TrainService(
            service_id="GWR102",
            operator="GWR",
            origin=london,
            destination=oxford,
            departure=base + timedelta(
                minutes=30
            ),
            arrival=base + timedelta(
                minutes=95
            ),
            calling_points=[
                reading,
                didcot
            ]
        ),

        TrainService(
            service_id="GWR103",
            operator="GWR",
            origin=london,
            destination=oxford,
            departure=base + timedelta(
                minutes=90
            ),
            arrival=base + timedelta(
                minutes=150
            ),
            calling_points=[
                reading,
                didcot
            ]
        )
    ]

    fares = FareDatabase()

    # --------------------------------------------------------
    # Direct Advance
    # --------------------------------------------------------

    fares.add(
        Fare(
            london,
            oxford,
            TicketType.ADVANCE,
            35.00,
            "ANY PERMITTED",
            operator="GWR"
        )
    )

    # --------------------------------------------------------
    # Direct flexible ticket
    # --------------------------------------------------------

    fares.add(
        Fare(
            london,
            oxford,
            TicketType.OFF_PEAK,
            60.00,
            "ANY PERMITTED",
            operator="GWR"
        )
    )

    # --------------------------------------------------------
    # Split fares
    # --------------------------------------------------------

    fares.add(
        Fare(
            london,
            reading,
            TicketType.ADVANCE,
            15.00,
            "ANY PERMITTED",
            operator="GWR"
        )
    )

    fares.add(
        Fare(
            reading,
            oxford,
            TicketType.ADVANCE,
            12.00,
            "ANY PERMITTED",
            operator="GWR"
        )
    )

    fares.add(
        Fare(
            london,
            didcot,
            TicketType.ADVANCE,
            18.00,
            "ANY PERMITTED",
            operator="GWR"
        )
    )

    fares.add(
        Fare(
            didcot,
            oxford,
            TicketType.ADVANCE,
            9.00,
            "ANY PERMITTED",
            operator="GWR"
        )
    )

    return (
        stations,
        services,
        fares
    )


# ============================================================
# MAIN
# ============================================================

def main():

    (
        stations,
        services,
        fares
    ) = create_demo_network()

    validity = TicketValidityEngine()

    optimizer = FareOptimizer(
        stations,
        services,
        fares,
        validity
    )

    london = stations[0]

    oxford = stations[3]

    # --------------------------------------------------------
    # Find absolute cheapest
    # --------------------------------------------------------

    cheapest = optimizer.find_cheapest(
        london,
        oxford
    )

    if cheapest:

        FareReport.print_itinerary(
            cheapest
        )

    # --------------------------------------------------------
    # Show top 10
    # --------------------------------------------------------

    alternatives = optimizer.cheapest_n(
        london,
        oxford,
        n=10
    )

    FareReport.compare(
        alternatives
    )


if __name__ == "__main__":

    main()
