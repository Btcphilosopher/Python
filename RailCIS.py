module RailCIS

using Dates
using Statistics

export Train,
       Station,
       Service,
       Platform,
       CISBoard,
       ETAEngine,
       BoardOptimizer,
       update_train!,
       calculate_eta,
       optimise_board!,
       render_board


# ============================================================
# ENUMS
# ============================================================

@enum TrainStatus begin
    SCHEDULED
    APPROACHING
    AT_PLATFORM
    BOARDING
    DEPARTED
    DELAYED
    CANCELLED
    TERMINATED
end

@enum DisplayMode begin
    DEPARTURES
    ARRIVALS
end


# ============================================================
# STATION
# ============================================================

mutable struct Station

    id::String
    name::String

    latitude::Float64
    longitude::Float64

    platforms::Vector{String}

    minimum_dwell::Float64
end


# ============================================================
# PLATFORM
# ============================================================

mutable struct Platform

    id::String

    occupied::Bool

    train_id::Union{String,Nothing}

    available_time::DateTime

end


# ============================================================
# TRAIN
# ============================================================

mutable struct Train

    id::String
    service_id::String

    operator::String

    origin::String
    destination::String

    booked_departure::DateTime
    booked_arrival::DateTime

    actual_departure::Union{DateTime,Nothing}
    actual_arrival::Union{DateTime,Nothing}

    current_location::String

    distance_remaining_km::Float64
    speed_kmh::Float64

    status::TrainStatus

    platform::Union{String,Nothing}

    calling_points::Vector{String}

    formation::String

    capacity::Int

    passengers::Int

    delay_minutes::Float64
end


# ============================================================
# SERVICE
# ============================================================

struct Service

    id::String

    operator::String

    origin::String
    destination::String

    booked_departure::DateTime
    booked_arrival::DateTime

    stopping_pattern::Vector{String}

    platform::Union{String,Nothing}

    priority::Int
end


# ============================================================
# ETA ENGINE
# ============================================================

mutable struct ETAEngine

    average_acceleration::Float64

    braking_margin::Float64

    station_dwell::Float64

    prediction_horizon::Float64
end


function calculate_eta(
    train::Train,
    engine::ETAEngine
)

    if train.status == CANCELLED
        return nothing
    end

    if train.distance_remaining_km <= 0
        return now()
    end

    speed = max(train.speed_kmh, 5.0)

    travel_hours =
        train.distance_remaining_km / speed

    travel_minutes =
        travel_hours * 60.0

    eta =
        now() +
        Minute(round(Int, travel_minutes))

    return eta
end


# ============================================================
# TRAIN UPDATE
# ============================================================

function update_train!(
    train::Train,
    location::String,
    distance_remaining_km::Float64,
    speed_kmh::Float64
)

    train.current_location = location
    train.distance_remaining_km =
        max(distance_remaining_km, 0.0)

    train.speed_kmh =
        max(speed_kmh, 0.0)

    return train
end


# ============================================================
# BOARD
# ============================================================

mutable struct CISBoard

    station::Station

    mode::DisplayMode

    trains::Vector{Train}

    rows::Int

    refresh_rate_seconds::Float64

    last_update::DateTime
end


# ============================================================
# DISPLAY RECORD
# ============================================================

struct DisplayRecord

    train_id::String

    time::String

    destination::String

    platform::String

    status::String

    priority::Float64
end


# ============================================================
# BOARD OPTIMIZER
# ============================================================

mutable struct BoardOptimizer

    eta_engine::ETAEngine

    display_horizon_minutes::Float64

    disruption_priority::Float64

    approaching_priority::Float64

    boarding_priority::Float64

    delayed_priority::Float64

    platform_priority::Float64
end


# ============================================================
# PRIORITY ENGINE
# ============================================================

function display_priority(
    train::Train,
    optimizer::BoardOptimizer
)

    score = 0.0

    # Soonest train gets priority
    minutes_to_depart =
        Dates.value(
            train.booked_departure - now()
        ) / 60000

    score +=
        max(
            0.0,
            100.0 - minutes_to_depart
        )

    # Approaching trains become more important
    if train.status == APPROACHING

        score +=
            optimizer.approaching_priority

    end

    # Boarding is extremely important
    if train.status == BOARDING

        score +=
            optimizer.boarding_priority

    end

    # Delayed trains require clear information
    if train.status == DELAYED

        score +=
            optimizer.delayed_priority

    end

    # Platform allocated
    if train.platform !== nothing

        score +=
            optimizer.platform_priority

    end

    return score
end


# ============================================================
# STATUS GENERATION
# ============================================================

function display_status(
    train::Train,
    optimizer::BoardOptimizer
)

    if train.status == CANCELLED

        return "CANCELLED"

    elseif train.status == BOARDING

        return "BOARDING"

    elseif train.status == AT_PLATFORM

        return "AT PLATFORM"

    elseif train.status == APPROACHING

        return "APPROACHING"

    elseif train.status == DELAYED

        return "DELAYED"

    elseif train.status == DEPARTED

        return "DEPARTED"

    else

        return "ON TIME"

    end
end


# ============================================================
# TIME DISPLAY
# ============================================================

function format_time(t::DateTime)

    return Dates.format(t, "HH:MM")

end


# ============================================================
# BOARD OPTIMISATION
# ============================================================

function optimise_board!(
    board::CISBoard,
    optimizer::BoardOptimizer
)

    records = DisplayRecord[]

    for train in board.trains

        # Ignore services outside display window
        minutes_until =
            Dates.value(
                train.booked_departure - now()
            ) / 60000

        if minutes_until >
           optimizer.display_horizon_minutes

            continue
        end

        # Calculate predicted time
        eta =
            calculate_eta(
                train,
                optimizer.eta_engine
            )

        display_time =
            train.booked_departure

        if eta !== nothing &&
           train.status == APPROACHING

            display_time = eta

        elseif train.status == DELAYED

            display_time =
                train.booked_departure +
                Minute(round(Int,
                    train.delay_minutes
                ))

        end

        score =
            display_priority(
                train,
                optimizer
            )

        platform =
            train.platform === nothing ?
            "TBC" :
            train.platform

        record = DisplayRecord(

            train.id,

            format_time(display_time),

            train.destination,

            platform,

            display_status(
                train,
                optimizer
            ),

            score
        )

        push!(
            records,
            record
        )
    end

    # Highest operational priority first,
    # then chronological order.
    sort!(
        records,
        by = x -> (
            -x.priority,
            x.time
        )
    )

    # Limit to physical display capacity
    if length(records) > board.rows

        records =
            records[1:board.rows]

    end

    return records
end


# ============================================================
# BOARD RENDERER
# ============================================================

function render_board(
    board::CISBoard,
    optimizer::BoardOptimizer
)

    records =
        optimise_board!(
            board,
            optimizer
        )

    println()
    println(
        "============================================================"
    )

    if board.mode == DEPARTURES

        println(
            "                 DEPARTURES"
        )

    else

        println(
            "                  ARRIVALS"
        )

    end

    println(
        "============================================================"
    )

    println(
        rpad("TIME", 10),
        rpad("DESTINATION", 28),
        rpad("PLAT", 8),
        "STATUS"
    )

    println(
        "------------------------------------------------------------"
    )

    for r in records

        println(
            rpad(r.time, 10),
            rpad(r.destination, 28),
            rpad(r.platform, 8),
            r.status
        )

    end

    println(
        "============================================================"
    )

    return records
end


# ============================================================
# DISRUPTION ENGINE
# ============================================================

function apply_delay!(
    train::Train,
    delay_minutes::Float64
)

    train.delay_minutes +=
        delay_minutes

    if delay_minutes > 0

        train.status = DELAYED

    end

    return train
end


function cancel_train!(
    train::Train
)

    train.status =
        CANCELLED

    return train
end


# ============================================================
# PLATFORM ASSIGNMENT
# ============================================================

function assign_platform!(
    train::Train,
    platform::String
)

    train.platform =
        platform

    return train
end


# ============================================================
# BOARD FACTORY
# ============================================================

function create_optimizer()

    eta = ETAEngine(

        0.65,      # acceleration model
        1.15,      # braking margin
        1.0,       # dwell
        90.0       # prediction horizon
    )

    return BoardOptimizer(

        eta,

        120.0,     # display horizon

        20.0,      # disruption

        35.0,      # approaching

        60.0,      # boarding

        30.0,      # delayed

        15.0       # platform
    )
end


# ============================================================
# DEMO
# ============================================================

function demo()

    station = Station(

        "KGX",
        "London King's Cross",

        51.5308,
        -0.1238,

        [
            "1","2","3","4",
            "5","6","7","8",
            "9","10"
        ],

        1.0
    )

    t = now()

    trains = [

        Train(
            "LNER801",
            "1A20",
            "LNER",
            "London King's Cross",
            "Edinburgh",
            t + Minute(8),
            t + Minute(308),
            nothing,
            nothing,
            "Finsbury Park",
            3.2,
            0.0,
            APPROACHING,
            "4",
            ["Stevenage",
             "Peterborough",
             "York",
             "Newcastle"],
            "Azuma 9-car",
            650,
            480,
            0.0
        ),

        Train(
            "LNER803",
            "1A22",
            "LNER",
            "London King's Cross",
            "Leeds",
            t + Minute(19),
            t + Minute(142),
            nothing,
            nothing,
            "Depot",
            12.0,
            0.0,
            SCHEDULED,
            "6",
            ["Peterborough",
             "Doncaster"],
            "Azuma 5-car",
            350,
            170,
            0.0
        ),

        Train(
            "LNER805",
            "1A24",
            "LNER",
            "London King's Cross",
            "York",
            t + Minute(31),
            t + Minute(151),
            nothing,
            nothing,
            "Stevenage",
            38.0,
            90.0,
            DELAYED,
            nothing,
            ["Stevenage",
             "Peterborough"],
            "Azuma 9-car",
            650,
            520,
            7.0
        )
    ]

    board = CISBoard(

        station,
        DEPARTURES,
        trains,
        8,
        1.0,
        t
    )

    optimizer =
        create_optimizer()

    render_board(
        board,
        optimizer
    )

end


end # module
