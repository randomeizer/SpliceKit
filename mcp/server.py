#!/usr/bin/env python3
"""
FCPBridge MCP Server
Provides direct in-process control of Final Cut Pro via the FCPBridge dylib.
Connects to the FCPBridge JSON-RPC server at 127.0.0.1:9876.
"""

import socket
import json
import os
import sys
from typing import Optional
from mcp.server.fastmcp import FastMCP

FCPBRIDGE_HOST = "127.0.0.1"
FCPBRIDGE_PORT = 9876

mcp = FastMCP(
    "fcpbridge",
    instructions="""Direct in-process control of Final Cut Pro via injected FCPBridge dylib.
This MCP server connects to a JSON-RPC server running INSIDE the Final Cut Pro process,
giving you direct access to all 78,000+ ObjC classes and their methods via the ObjC runtime.

Key frameworks accessible:
- Flexo (FF*): Core engine - timeline, library, editing, media (2849 classes)
- Ozone (OZ*): Effects, compositing, color correction (841 classes)
- TimelineKit (TK*): Timeline UI and editing (111 classes)
- LunaKit (LK*): UI framework (220 classes)
- ProEditor (PE*): App controller, documents, windows (271 classes)

IMPORTANT: All editing operations should use the FFEditActionMgr command pattern
or FFAnchoredSequence transaction wrapping to ensure undo/redo works correctly.
"""
)


class BridgeConnection:
    """Persistent connection to the FCPBridge JSON-RPC server."""

    def __init__(self):
        self.sock = None
        self._buf = b""
        self._id = 0

    def ensure_connected(self):
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(30)
            self.sock.connect((FCPBRIDGE_HOST, FCPBRIDGE_PORT))
            self._buf = b""

    def call(self, method: str, **params) -> dict:
        try:
            self.ensure_connected()
        except (ConnectionRefusedError, OSError) as e:
            return {"error": f"Cannot connect to FCPBridge at {FCPBRIDGE_HOST}:{FCPBRIDGE_PORT}. "
                    f"Is the modded FCP running? Error: {e}"}

        self._id += 1
        req = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": self._id})
        try:
            self.sock.sendall(req.encode() + b"\n")
            while b"\n" not in self._buf:
                chunk = self.sock.recv(16777216)
                if not chunk:
                    self.sock = None
                    return {"error": "Connection closed by FCPBridge"}
                self._buf += chunk
            line, self._buf = self._buf.split(b"\n", 1)
            resp = json.loads(line)
            if "error" in resp:
                return {"error": resp["error"]}
            return resp.get("result", {})
        except Exception as e:
            self.sock = None
            return {"error": f"Bridge communication error: {e}"}


bridge = BridgeConnection()


# ============================================================
# System / Runtime Introspection Tools
# ============================================================

@mcp.tool()
def bridge_status() -> str:
    """Check if FCPBridge is running and get FCP version info."""
    r = bridge.call("system.version")
    if "error" in r:
        return f"FCPBridge NOT connected: {r['error']}"
    return json.dumps(r, indent=2)


@mcp.tool()
def get_classes(filter: str = "") -> str:
    """List ObjC classes loaded in FCP's process.
    Use filter to search by substring (e.g. 'FFAnchored', 'OZColor', 'PEApp').
    Common prefixes: FF (Flexo), OZ (Ozone), PE (ProEditor), LK (LunaKit), TK (TimelineKit), IX (Interchange).
    """
    r = bridge.call("system.getClasses", filter=filter) if filter else bridge.call("system.getClasses")
    if "error" in r:
        return f"Error: {r['error']}"
    classes = r.get("classes", [])
    count = r.get("count", len(classes))
    if count > 200:
        return f"Found {count} classes matching '{filter}'. Showing first 200:\n" + "\n".join(classes[:200])
    return f"Found {count} classes:\n" + "\n".join(classes)


@mcp.tool()
def get_methods(class_name: str, include_super: bool = False) -> str:
    """List all methods on an ObjC class. Returns both instance (-) and class (+) methods with type encodings.
    Set include_super=True to include inherited methods up to NSObject.
    """
    r = bridge.call("system.getMethods", className=class_name, includeSuper=include_super)
    if "error" in r:
        return f"Error: {r['error']}"

    lines = [f"=== {class_name} ==="]
    lines.append(f"\nInstance methods ({r.get('instanceMethodCount', 0)}):")
    for name in sorted(r.get("instanceMethods", {}).keys()):
        info = r["instanceMethods"][name]
        lines.append(f"  - {name}  ({info.get('typeEncoding', '')})")

    lines.append(f"\nClass methods ({r.get('classMethodCount', 0)}):")
    for name in sorted(r.get("classMethods", {}).keys()):
        info = r["classMethods"][name]
        lines.append(f"  + {name}  ({info.get('typeEncoding', '')})")

    return "\n".join(lines)


@mcp.tool()
def get_properties(class_name: str) -> str:
    """List declared @property definitions on an ObjC class."""
    r = bridge.call("system.getProperties", className=class_name)
    if "error" in r:
        return f"Error: {r['error']}"
    lines = [f"{class_name}: {r.get('count', 0)} properties"]
    for p in r.get("properties", []):
        lines.append(f"  {p['name']}: {p['attributes']}")
    return "\n".join(lines)


@mcp.tool()
def get_ivars(class_name: str) -> str:
    """List instance variables (ivars) of an ObjC class with their types."""
    r = bridge.call("system.getIvars", className=class_name)
    if "error" in r:
        return f"Error: {r['error']}"
    lines = [f"{class_name}: {r.get('count', 0)} ivars"]
    for iv in r.get("ivars", []):
        lines.append(f"  {iv['name']}: {iv['type']}")
    return "\n".join(lines)


@mcp.tool()
def get_protocols(class_name: str) -> str:
    """List protocols adopted by an ObjC class."""
    r = bridge.call("system.getProtocols", className=class_name)
    if "error" in r:
        return f"Error: {r['error']}"
    lines = [f"{class_name}: {r.get('count', 0)} protocols"]
    for p in r.get("protocols", []):
        lines.append(f"  {p}")
    return "\n".join(lines)


@mcp.tool()
def get_superchain(class_name: str) -> str:
    """Get the inheritance chain for an ObjC class (class -> superclass -> ... -> NSObject)."""
    r = bridge.call("system.getSuperchain", className=class_name)
    if "error" in r:
        return f"Error: {r['error']}"
    chain = r.get("superchain", [])
    return " -> ".join(chain)


@mcp.tool()
def call_method(class_name: str, selector: str, class_method: bool = True) -> str:
    """Call an ObjC method. For class methods, calls directly on the class.
    For instance methods, tries common singleton patterns (sharedInstance, shared, defaultManager).

    WARNING: Only call methods you understand. Calling random methods can crash FCP.
    For editing operations, use the FFEditActionMgr pattern.

    Examples:
      call_method("FFLibraryDocument", "copyActiveLibraries", class_method=True)
      call_method("FFLibraryDocument", "isAnyLibraryUpdating", class_method=True)
    """
    r = bridge.call("system.callMethod", className=class_name, selector=selector, classMethod=class_method)
    if "error" in r:
        return f"Error: {r['error']}"
    return json.dumps(r, indent=2, default=str)


# ============================================================
# Timeline Editing Operations (direct ObjC calls)
# ============================================================

@mcp.tool()
def timeline_action(action: str) -> str:
    """Perform a timeline editing action. These are direct ObjC calls into FCP's editing engine.

    Available actions:
      Blade/Split: blade, bladeAll
      Markers: addMarker, addTodoMarker, addChapterMarker, deleteMarker, nextMarker, previousMarker
      Transitions: addTransition
      Navigation: nextEdit, previousEdit, selectClipAtPlayhead
      Selection: selectAll, deselectAll
      Edit: delete, cut, copy, paste
      Undo: undo, redo
      Insert: insertGap
      Trim: trimToPlayhead

    Example: timeline_action("blade") - blades the clip at the current playhead
    """
    r = bridge.call("timeline.action", action=action)
    if "error" in r:
        return f"Error: {r['error']}"
    return json.dumps(r, indent=2)


@mcp.tool()
def playback_action(action: str) -> str:
    """Control playback. Direct ObjC calls to FCP's player.

    Available actions:
      playPause - toggle play/pause
      play - start playing
      pause - stop playing
      goToStart - jump to beginning of timeline
      goToEnd - jump to end of timeline
      nextFrame - advance one frame
      prevFrame - go back one frame
      playForward - play forward
      playBackward - play in reverse

    Example: playback_action("goToStart")
    """
    r = bridge.call("playback.action", action=action)
    if "error" in r:
        return f"Error: {r['error']}"
    return json.dumps(r, indent=2)


@mcp.tool()
def timeline_get_state() -> str:
    """Get current timeline state: playhead position, sequence info, list of clips/items.
    Returns playhead time in seconds, item count, and description of each timeline item.
    """
    r = bridge.call("timeline.getState")
    if "error" in r:
        return f"Error: {r['error']}"
    return json.dumps(r, indent=2, default=str)


# ============================================================
# Library & Project Management
# ============================================================

@mcp.tool()
def get_active_libraries() -> str:
    """Get list of currently open libraries in FCP."""
    r = bridge.call("system.callMethod", className="FFLibraryDocument",
                    selector="copyActiveLibraries", classMethod=True)
    if "error" in r:
        return f"Error: {r['error']}"
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
def is_library_updating() -> str:
    """Check if any library is currently being updated/saved."""
    r = bridge.call("system.callMethod", className="FFLibraryDocument",
                    selector="isAnyLibraryUpdating", classMethod=True)
    if "error" in r:
        return f"Error: {r['error']}"
    return json.dumps(r, indent=2, default=str)


# ============================================================
# Exploration helpers
# ============================================================

@mcp.tool()
def explore_class(class_name: str) -> str:
    """Get a comprehensive overview of an ObjC class: superchain, protocols, properties, ivars, and method summary.
    Great for understanding what a class does before calling its methods.
    """
    lines = [f"=== {class_name} ===\n"]

    # Superchain
    r = bridge.call("system.getSuperchain", className=class_name)
    if "error" not in r:
        lines.append("Inheritance: " + " -> ".join(r.get("superchain", [])))

    # Protocols
    r = bridge.call("system.getProtocols", className=class_name)
    if "error" not in r and r.get("count", 0) > 0:
        lines.append(f"\nProtocols ({r['count']}): " + ", ".join(r.get("protocols", [])))

    # Properties
    r = bridge.call("system.getProperties", className=class_name)
    if "error" not in r and r.get("count", 0) > 0:
        lines.append(f"\nProperties ({r['count']}):")
        for p in r.get("properties", [])[:30]:
            lines.append(f"  {p['name']}")
        if r["count"] > 30:
            lines.append(f"  ... and {r['count'] - 30} more")

    # Ivars
    r = bridge.call("system.getIvars", className=class_name)
    if "error" not in r and r.get("count", 0) > 0:
        lines.append(f"\nIvars ({r['count']}):")
        for iv in r.get("ivars", [])[:20]:
            lines.append(f"  {iv['name']}: {iv['type']}")
        if r["count"] > 20:
            lines.append(f"  ... and {r['count'] - 20} more")

    # Methods summary
    r = bridge.call("system.getMethods", className=class_name)
    if "error" not in r:
        im = r.get("instanceMethodCount", 0)
        cm = r.get("classMethodCount", 0)
        lines.append(f"\nMethods: {im} instance, {cm} class ({im + cm} total)")

        # Show class methods (usually fewer and more important)
        if cm > 0:
            lines.append(f"\nClass methods ({cm}):")
            for name in sorted(r.get("classMethods", {}).keys()):
                lines.append(f"  + {name}")

        # Show interesting instance methods (filtered)
        interesting_keywords = ['get', 'set', 'current', 'active', 'selected', 'add', 'remove',
                               'create', 'delete', 'open', 'close', 'play', 'pause', 'name',
                               'title', 'url', 'path', 'count', 'items', 'library', 'timeline',
                               'project', 'clip', 'effect', 'marker', 'export', 'render']
        instance_methods = sorted(r.get("instanceMethods", {}).keys())
        notable = [m for m in instance_methods if any(k in m.lower() for k in interesting_keywords)]
        if notable:
            lines.append(f"\nNotable instance methods ({len(notable)} of {im}):")
            for m in notable[:50]:
                lines.append(f"  - {m}")
            if len(notable) > 50:
                lines.append(f"  ... and {len(notable) - 50} more")

    return "\n".join(lines)


@mcp.tool()
def search_methods(class_name: str, keyword: str) -> str:
    """Search for methods on a class by keyword. Searches both instance and class method names.
    Example: search_methods("FFAnchoredTimelineModule", "blade")
    """
    r = bridge.call("system.getMethods", className=class_name)
    if "error" in r:
        return f"Error: {r['error']}"

    lines = []
    for name in sorted(r.get("instanceMethods", {}).keys()):
        if keyword.lower() in name.lower():
            info = r["instanceMethods"][name]
            lines.append(f"  - {name}  ({info.get('typeEncoding', '')})")
    for name in sorted(r.get("classMethods", {}).keys()):
        if keyword.lower() in name.lower():
            info = r["classMethods"][name]
            lines.append(f"  + {name}  ({info.get('typeEncoding', '')})")

    if not lines:
        return f"No methods matching '{keyword}' on {class_name}"
    return f"Methods matching '{keyword}' on {class_name} ({len(lines)}):\n" + "\n".join(lines)


@mcp.tool()
def find_classes_with_method(method_keyword: str, class_filter: str = "FF") -> str:
    """Find which classes have methods matching a keyword.
    Searches classes with the given prefix (default 'FF' for Flexo).
    Example: find_classes_with_method("blade", "FF") to find blade-related methods.
    """
    # Get filtered classes
    r = bridge.call("system.getClasses", filter=class_filter)
    if "error" in r:
        return f"Error: {r['error']}"

    classes = r.get("classes", [])
    if len(classes) > 100:
        classes = classes[:100]  # Limit to avoid timeout

    results = []
    for cls_name in classes:
        r2 = bridge.call("system.getMethods", className=cls_name)
        if "error" in r2:
            continue
        matches = []
        for m in r2.get("instanceMethods", {}).keys():
            if method_keyword.lower() in m.lower():
                matches.append(f"- {m}")
        for m in r2.get("classMethods", {}).keys():
            if method_keyword.lower() in m.lower():
                matches.append(f"+ {m}")
        if matches:
            results.append(f"\n{cls_name}:")
            results.extend(f"  {m}" for m in matches[:10])
            if len(matches) > 10:
                results.append(f"  ... and {len(matches) - 10} more")

    if not results:
        return f"No classes with prefix '{class_filter}' have methods matching '{method_keyword}'"
    return f"Classes with methods matching '{method_keyword}':" + "\n".join(results)


@mcp.tool()
def raw_call(method: str, params: str = "{}") -> str:
    """Send a raw JSON-RPC call to FCPBridge. The method is the JSON-RPC method name,
    params is a JSON string of parameters.

    Example: raw_call("system.getClasses", '{"filter": "FFPlayer"}')
    """
    try:
        p = json.loads(params)
    except json.JSONDecodeError as e:
        return f"Invalid JSON params: {e}"
    r = bridge.call(method, **p)
    return json.dumps(r, indent=2, default=str)


if __name__ == "__main__":
    mcp.run(transport="stdio")
