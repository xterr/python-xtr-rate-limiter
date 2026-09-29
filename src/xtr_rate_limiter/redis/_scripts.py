"""The Lua scripts that count hits on the Redis server, one per policy.

Each script reads a limiter's state, works out the answer and writes the
state back in one step the server runs whole, so no lock is needed and no
two callers are ever granted the same token. The arithmetic is the same as
the policies' in :mod:`xtr_rate_limiter.policy`.

Every script answers ``{accepted, exceeded, remaining, retry_after,
time_to_act, reset_at}``, the last three as seconds from the instant the
script counted at. ``exceeded`` is 1 when the wait was longer than the
caller's maximum, in which case nothing was written.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ANCHORED_FIXED_WINDOW", "FIXED_WINDOW", "SLIDING_WINDOW", "TOKEN_BUCKET"]

_PROLOGUE: Final = """
local function fmt(value)
    return string.format("%.17g", value)
end

local key = KEYS[1]
local now = tonumber(ARGV[1])
if now == nil then
    local time = redis.call("TIME")
    now = tonumber(time[1]) + tonumber(time[2]) / 1000000
end
local tokens = tonumber(ARGV[2])
local max_time = tonumber(ARGV[3])

local function expire(seconds)
    redis.call("PEXPIRE", key, math.max(1, math.ceil(seconds * 1000)))
end

local function answer(accepted, exceeded, remaining, retry_after, time_to_act, reset_at)
    return {
        accepted, exceeded, fmt(remaining),
        fmt(retry_after - now), fmt(time_to_act - now), fmt(reset_at - now),
    }
end
"""

FIXED_WINDOW: Final = (
    _PROLOGUE
    + """
local limit = tonumber(ARGV[4])
local interval = tonumber(ARGV[5])

local state = redis.call("HMGET", key, "hits", "timer")
local hits = tonumber(state[1])
local timer = tonumber(state[2])
if hits == nil or timer == nil then
    hits = 0
    timer = now
end

-- the hits still owed after every window that has since ended
local function carried(at)
    local elapsed = at - timer
    if elapsed <= interval then
        return hits
    end
    return math.max(0, hits - math.floor(elapsed / interval) * limit)
end

local function available(at)
    return limit - carried(at)
end

local function availability(count, at)
    if limit - hits >= count then
        return at
    end
    return timer + interval * (math.ceil((hits + count) / limit) - 1)
end

local function add(count, at)
    if at - timer > interval then
        hits = carried(at)
        timer = at
    end
    hits = math.max(0, hits + count)
end

local accepted, time_to_act, retry_after
if tokens == 0 then
    time_to_act = now + math.max(0, availability(1, now) - now)
    retry_after = time_to_act
    accepted = 1
elseif available(now) >= tokens then
    local exhausts = available(now) == tokens
    add(tokens, now)
    retry_after = now
    if exhausts then
        retry_after = now + math.max(0, availability(1, now) - now)
    end
    time_to_act = now
    accepted = 1
else
    local wait = math.max(0, availability(tokens, now) - now)
    if max_time ~= nil and wait > max_time then
        return answer(0, 1, available(now), now + wait, now + wait, availability(limit, now))
    end
    add(tokens, now)
    time_to_act = now + wait
    retry_after = time_to_act
    accepted = 0
end

if tokens ~= 0 then
    redis.call("HSET", key, "hits", hits, "timer", fmt(timer))
    expire(interval * math.max(1, math.ceil(hits / limit)))
end

return answer(accepted, 0, available(now), retry_after, time_to_act, availability(limit, now))
"""
)

ANCHORED_FIXED_WINDOW: Final = (
    _PROLOGUE
    + """
local limit = tonumber(ARGV[4])
local period_end = tonumber(ARGV[5])

local state = redis.call("HMGET", key, "hits", "end")
local hits = tonumber(state[1])
if hits == nil or tonumber(state[2]) ~= period_end then
    hits = 0
end

local function availability(count)
    if limit - hits >= count then
        return now
    end
    return period_end
end

local accepted, time_to_act, retry_after
if tokens == 0 then
    time_to_act = availability(1)
    retry_after = time_to_act
    accepted = 1
elseif limit - hits >= tokens then
    local exhausts = limit - hits == tokens
    hits = hits + tokens
    retry_after = now
    if exhausts then
        retry_after = availability(1)
    end
    time_to_act = now
    accepted = 1
else
    local wait = math.max(0, period_end - now)
    if max_time ~= nil and wait > max_time then
        return answer(0, 1, limit - hits, now + wait, now + wait, availability(limit))
    end
    hits = hits + tokens
    time_to_act = now + wait
    retry_after = time_to_act
    accepted = 0
end

if tokens ~= 0 then
    redis.call("HSET", key, "hits", hits, "end", fmt(period_end))
    expire(period_end - now)
end

return answer(accepted, 0, limit - hits, retry_after, time_to_act, availability(limit))
"""
)

SLIDING_WINDOW: Final = (
    _PROLOGUE
    + """
local limit = tonumber(ARGV[4])
local interval = tonumber(ARGV[5])

local state = redis.call("HMGET", key, "hits", "last", "end")
local hits = tonumber(state[1])
local last = tonumber(state[2])
local window_end = tonumber(state[3])
if hits == nil or last == nil or window_end == nil then
    hits = 0
    last = 0
    window_end = now + interval
elseif now > window_end then
    -- the window ended: carry its hits only when it ended less than a window ago
    if now < window_end + interval then
        last = hits
        window_end = window_end + interval
    else
        last = 0
        window_end = now + interval
    end
    hits = 0
end

local function count(at)
    local percent = math.min((at - (window_end - interval)) / interval, 1)
    return math.floor(last * (1 - percent) + hits)
end

local function full_capacity(at)
    if hits > 0 then
        return window_end + interval * (1 - 1 / hits)
    end
    if last > 0 then
        return window_end - interval / last
    end
    return at
end

local function time_for(max_size, needed_tokens, at)
    local remaining = max_size - count(at)
    if remaining >= needed_tokens then
        return 0
    end
    local passed = at - (window_end - interval)
    local window_passed = math.min(passed / interval, 1)
    local releasable = math.max(1, max_size - math.floor(last * (1 - window_passed)))
    local remaining_window = interval - passed
    local needed = needed_tokens - remaining
    if releasable >= needed then
        return needed * (remaining_window / math.max(1, releasable))
    end
    return (window_end - at) + (needed - releasable) * (interval / max_size)
end

local function reset_at(at)
    if count(at) == 0 then
        return at
    end
    return math.floor(math.max(at, full_capacity(at))) + 1
end

local available = limit - count(now)
if tokens == 0 then
    local retry_after = now
    if available <= 0 then
        retry_after = now + time_for(limit, count(now), now)
    end
    return answer(1, 0, available, retry_after, now, reset_at(now))
end

local accepted, time_to_act, retry_after
if available >= tokens then
    hits = math.max(0, hits + tokens)
    retry_after = now
    if available == tokens then
        retry_after = now + time_for(limit, count(now), now)
    end
    time_to_act = now
    accepted = 1
else
    local wait = time_for(limit, tokens, now)
    if max_time ~= nil and wait > max_time then
        return answer(0, 1, limit - count(now), now + wait, now + wait, reset_at(now))
    end
    hits = math.max(0, hits + tokens)
    time_to_act = now + wait
    retry_after = time_to_act
    accepted = 0
end

redis.call("HSET", key, "hits", hits, "last", last, "end", fmt(window_end))
expire(window_end + interval - now)

return answer(accepted, 0, limit - count(now), retry_after, time_to_act, reset_at(now))
"""
)

TOKEN_BUCKET: Final = (
    _PROLOGUE
    + """
local burst = tonumber(ARGV[4])
local cycle = tonumber(ARGV[5])
local amount = tonumber(ARGV[6])

local state = redis.call("HMGET", key, "tokens", "timer")
local stored = tonumber(state[1])
local timer = tonumber(state[2])
if stored == nil or timer == nil then
    stored = burst
    timer = now
end

-- only whole cycles move the timer, so a partial one is never lost
local function available_at(at)
    local cycles = math.floor(math.max(0, at - timer) / cycle)
    if cycles > 0 then
        timer = timer + cycles * cycle
    end
    return math.min(burst, stored + cycles * amount)
end

local function time_for(count)
    return math.ceil(count / amount) * cycle
end

local function reset_at(left)
    return now + time_for(math.max(0, burst - left))
end

local available = math.min(available_at(now), burst)
local accepted, remaining, time_to_act, retry_after, left
if available >= tokens then
    stored = available - tokens
    left = stored
    retry_after = now
    if available == tokens then
        retry_after = now + time_for(1)
    end
    remaining = available_at(now)
    time_to_act = now
    accepted = 1
else
    local wait = time_for(tokens - available)
    if max_time ~= nil and wait > max_time then
        return answer(0, 1, available, now + wait, now + wait, reset_at(available))
    end
    -- every token until then is booked for this caller: none is left for anyone else
    stored = available - tokens
    left = stored
    remaining = 0
    time_to_act = now + wait
    retry_after = time_to_act
    accepted = 0
end

if tokens ~= 0 then
    redis.call("HSET", key, "tokens", stored, "timer", fmt(timer))
    expire(time_for(math.max(burst, burst - stored)))
end

return answer(accepted, 0, remaining, retry_after, time_to_act, reset_at(left))
"""
)
