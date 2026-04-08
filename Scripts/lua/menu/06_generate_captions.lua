-- Generate social-style captions on the timeline
-- Uses FCP Native transcription, then generates bold_pop captions.

-- Step 1: Transcribe the timeline
sk.toast("Transcribing timeline...")
sk.rpc("transcript.setEngine", {engine = "fcpNative"})
sk.rpc("transcript.open", {})

local words = nil
for i = 1, 60 do
    sk.sleep(1)
    local ts = sk.rpc("transcript.getState", {})
    if ts and ts.status == "error" then
        sk.alert("Captions", "Transcription failed:\n" .. (ts.errorMessage or "unknown"))
        return
    end
    if ts and ts.wordCount and ts.wordCount > 0 then
        words = ts.words
        break
    end
end
if not words then
    sk.alert("Captions", "Timed out waiting for transcription")
    return
end

-- Step 2: Feed words to caption panel and generate
sk.toast("Generating captions...")
sk.rpc("captions.open", {style = "bold_pop"})
sk.sleep(1)
sk.rpc("captions.setWords", {words = words})
sk.rpc("captions.setStyle", {preset_id = "bold_pop", position = "bottom"})
sk.rpc("captions.setGrouping", {mode = "social"})
sk.rpc("captions.generate", {style = "bold_pop"})

-- Step 3: Wait for generation to finish
for i = 1, 30 do
    sk.sleep(1)
    local state = sk.rpc("captions.getState", {})
    if state and state.status == "ready" then
        sk.alert("Captions", "Captions generated and placed on timeline")
        return
    end
    if state and state.error then
        local msg = type(state.error) == "table" and state.error.message or tostring(state.error)
        sk.alert("Captions", "Generation failed:\n" .. msg)
        return
    end
end
sk.alert("Captions", "Timed out waiting for caption generation")
