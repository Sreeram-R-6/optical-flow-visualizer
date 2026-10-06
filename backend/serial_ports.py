from serial.tools import list_ports

def available_ports() -> list[dict[str, str]]:
    return [{"device": p.device, "description": p.description or "Serial device"}
            for p in sorted(list_ports.comports(), key=lambda p: p.device)]
