module RailPA

using Dates
using UUIDs

export TrainService,
       Announcement,
       AnnouncementEngine,
       create_announcement,
       queue_announcement!,
       process_queue!,
       station_departure,
       station_delay,
       station_platform,
       train_next_station,
       train_approaching_station,
       emergency_announcement


# ============================================================
# ANNOUNCEMENT TYPES
# ============================================================

@enum AnnouncementType begin
    SERVICE_INFO
    BOARDING
    PLATFORM
    DELAY
    CANCELLATION
    ARRIVAL
    DEPARTURE
    NEXT_STATION
    CONNECTION
    SAFETY
    EMERGENCY
    CREW
end


# ============================================================
# PRIORITY
# ============================================================

@enum Priority begin
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4
end


# ============================================================
# TRAIN SERVICE
# ============================================================

mutable struct TrainService

    id::String

    operator::String

    origin::String
    destination::String

    booked_time::DateTime

    platform::Union{String,Nothing}

    delay_minutes::Int

    calling_points::Vector{String}

    current_station::Union{String,Nothing}

    next_station::Union{String,Nothing}

    cancelled::Bool

end


# ============================================================
# ANNOUNCEMENT
# ============================================================

mutable struct Announcement

    id::String

    type::AnnouncementType

    priority::Priority

    text::String

    created::DateTime

    scheduled_time::DateTime

    zone::String

    language::String

    repeat_count::Int

    completed::Bool

end


# ============================================================
# ENGINE
# ============================================================

mutable struct AnnouncementEngine

    queue::Vector{Announcement}

    history::Vector{Announcement}

    default_language::String

    max_queue_size::Int

    minimum_gap_seconds::Float64

    last_played::Union{DateTime,Nothing}

end


# ============================================================
# ENGINE FACTORY
# ============================================================

function create_engine()

    return AnnouncementEngine(

        Announcement[],

        Announcement[],

        "en-GB",

        100,

        4.0,

        nothing

    )

end


# ============================================================
# ANNOUNCEMENT CREATION
# ============================================================

function create_announcement(
    engine::AnnouncementEngine,
    type::AnnouncementType,
    priority::Priority,
    text::String;
    zone="station",
    delay_seconds=0,
    repeat_count=1
)

    return Announcement(

        string(uuid4()),

        type,

        priority,

        text,

        now(),

        now() + Second(delay_seconds),

        zone,

        engine.default_language,

        repeat_count,

        false

    )

end


# ============================================================
# QUEUE
# ============================================================

function queue_announcement!(
    engine::AnnouncementEngine,
    announcement::Announcement
)

    if length(engine.queue) >=
       engine.max_queue_size

        error("Announcement queue full")

    end

    push!(
        engine.queue,
        announcement
    )

    # Highest priority first.
    sort!(
        engine.queue,
        by = a -> (
            -Int(a.priority),
            a.scheduled_time
        )
    )

    return announcement.id
end


# ============================================================
# DUPLICATE PROTECTION
# ============================================================

function duplicate_exists(
    engine::AnnouncementEngine,
    text::String,
    window_seconds::Float64=30.0
)

    cutoff =
        now() -
        Second(round(Int, window_seconds))

    for a in engine.history

        if a.created >= cutoff &&
           a.text == text

            return true

        end

    end

    return false
end


# ============================================================
# GENERIC SERVICE ANNOUNCEMENT
# ============================================================

function service_message(
    service::TrainService
)

    time_string =
        Dates.format(
            service.booked_time,
            "HH:MM"
        )

    return "The $time_string service " *
           "to $(service.destination)."

end


# ============================================================
# PLATFORM ANNOUNCEMENT
# ============================================================

function station_platform(
    engine::AnnouncementEngine,
    service::TrainService
)

    service.platform === nothing &&
        error("Platform not allocated")

    text =
        "$(service_message(service)) " *
        "will depart from platform " *
        "$(service.platform)."

    if duplicate_exists(engine, text)

        return nothing

    end

    a = create_announcement(
        engine,
        PLATFORM,
        HIGH,
        text
    )

    queue_announcement!(
        engine,
        a
    )

    return a
end


# ============================================================
# BOARDING
# ============================================================

function station_departure(
    engine::AnnouncementEngine,
    service::TrainService
)

    service.cancelled &&
        return nothing

    service.platform === nothing &&
        return nothing

    text =
        "$(service_message(service)) " *
        "is now ready for boarding " *
        "from platform $(service.platform)."

    a = create_announcement(
        engine,
        BOARDING,
        HIGH,
        text
    )

    queue_announcement!(
        engine,
        a
    )

    return a
end


# ============================================================
# DELAY
# ============================================================

function station_delay(
    engine::AnnouncementEngine,
    service::TrainService
)

    service.cancelled &&
        return nothing

    text =
        "$(service_message(service)) " *
        "is delayed by approximately " *
        "$(service.delay_minutes) minutes."

    a = create_announcement(
        engine,
        DELAY,
        HIGH,
        text
    )

    queue_announcement!(
        engine,
        a
    )

    return a
end


# ============================================================
# CANCELLATION
# ============================================================

function station_cancellation(
    engine::AnnouncementEngine,
    service::TrainService
)

    service.cancelled = true

    text =
        "$(service_message(service)) " *
        "has been cancelled."

    a = create_announcement(
        engine,
        CANCELLATION,
        CRITICAL,
        text
    )

    queue_announcement!(
        engine,
        a
    )

    return a
end


# ============================================================
# TRAIN — NEXT STATION
# ============================================================

function train_next_station(
    engine::AnnouncementEngine,
    service::TrainService
)

    service.next_station === nothing &&
        return nothing

    text =
        "The next station is " *
        "$(service.next_station)."

    a = create_announcement(
        engine,
        NEXT_STATION,
        NORMAL,
        text;
        zone="train"
    )

    queue_announcement!(
        engine,
        a
    )

    return a
end


# ============================================================
# TRAIN — APPROACHING
# ============================================================

function train_approaching_station(
    engine::AnnouncementEngine,
    service::TrainService
)

    service.next_station === nothing &&
        return nothing

    text =
        "We are now approaching " *
        "$(service.next_station). " *
        "Please make sure you have all your belongings."

    a = create_announcement(
        engine,
        ARRIVAL,
        NORMAL,
        text;
        zone="train"
    )

    queue_announcement!(
        engine,
        a
    )

    return a
end


# ============================================================
# CONNECTION
# ============================================================

function connection_message(
    engine::AnnouncementEngine,
    destination::String,
    platform::String
)

    text =
        "Passengers for connections to " *
        "$destination should change at " *
        "platform $platform."

    a = create_announcement(
        engine,
        CONNECTION,
        NORMAL,
        text
    )

    queue_announcement!(
        engine,
        a
    )

    return a
end


# ============================================================
# SAFETY
# ============================================================

function safety_announcement(
    engine::AnnouncementEngine,
    text::String
)

    a = create_announcement(
        engine,
        SAFETY,
        HIGH,
        text
    )

    queue_announcement!(
        engine,
        a
    )

    return a
end


# ============================================================
# EMERGENCY
# ============================================================

function emergency_announcement(
    engine::AnnouncementEngine,
    text::String
)

    a = create_announcement(
        engine,
        EMERGENCY,
        CRITICAL,
        text;
        repeat_count=3
    )

    queue_announcement!(
        engine,
        a
    )

    return a
end


# ============================================================
# AUDIO RENDERER INTERFACE
# ============================================================

function synthesize_audio(
    announcement::Announcement
)

    println(
        "[TTS] ",
        announcement.text
    )

    # Production implementation would call
    # a certified/approved speech generation
    # or pre-recorded audio subsystem.

    return true
end


# ============================================================
# AUDIO OUTPUT
# ============================================================

function play_audio(
    announcement::Announcement
)

    println()
    println(
        "--------------------------------------------"
    )

    println(
        "PA OUTPUT"
    )

    println(
        "ZONE: ",
        uppercase(announcement.zone)
    )

    println(
        "PRIORITY: ",
        announcement.priority
    )

    println(
        "LANGUAGE: ",
        announcement.language
    )

    println(
        announcement.text
    )

    println(
        "--------------------------------------------"
    )

    return synthesize_audio(
        announcement
    )
end


# ============================================================
# QUEUE PROCESSOR
# ============================================================

function process_queue!(
    engine::AnnouncementEngine
)

    while !isempty(engine.queue)

        announcement =
            first(engine.queue)

        # Don't play future announcements.
        if announcement.scheduled_time > now()

            break

        end

        # Safety/emergency messages override
        # normal waiting behaviour.
        if engine.last_played !== nothing

            elapsed =
                Dates.value(
                    now() -
                    engine.last_played
                ) / 1000

            if elapsed <
               engine.minimum_gap_seconds &&
               announcement.priority != CRITICAL

                break
            end
        end

        popfirst!(
            engine.queue
        )

        play_audio(
            announcement
        )

        announcement.completed =
            true

        engine.last_played =
            now()

        push!(
            engine.history,
            announcement
        )

    end

    return nothing
end


# ============================================================
# BOARD + PA SYNCHRONISATION
# ============================================================

function synchronize_with_cis(
    engine::AnnouncementEngine,
    service::TrainService
)

    if service.cancelled

        return station_cancellation(
            engine,
            service
        )

    elseif service.delay_minutes > 0

        return station_delay(
            engine,
            service
        )

    elseif service.platform !== nothing

        return station_platform(
            engine,
            service
        )

    end

    return nothing
end


# ============================================================
# DEMONSTRATION
# ============================================================

function demo()

    engine =
        create_engine()

    service = TrainService(

        "LNER801",

        "LNER",

        "London King's Cross",

        "Edinburgh",

        now() + Minute(10),

        "4",

        0,

        [
            "Stevenage",
            "Peterborough",
            "York",
            "Newcastle",
            "Edinburgh"
        ],

        nothing,

        "Stevenage",

        false
    )


    println(
        "\nRAILPA.JL DEMONSTRATION\n"
    )


    station_platform(
        engine,
        service
    )

    station_departure(
        engine,
        service
    )

    train_next_station(
        engine,
        service
    )

    train_approaching_station(
        engine,
        service
    )


    process_queue!(
        engine
    )

end


end # module
