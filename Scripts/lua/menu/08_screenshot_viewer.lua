-- Capture a screenshot of the viewer to Desktop
local path = os.getenv("HOME") .. "/Desktop/viewer_" .. os.date("%Y%m%d_%H%M%S") .. ".png"
local r = sk.rpc("viewer.capture", {path = path})
if r and r.error then
    sk.toast("Screenshot failed: " .. tostring(r.error))
else
    sk.toast("Screenshot saved to Desktop")
end
