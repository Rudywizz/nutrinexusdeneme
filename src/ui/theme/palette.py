from dataclasses import dataclass

@dataclass(frozen=True)
class Palette:
    # Dark / modern (referans: paylaştığın mockup)
    bg: str = "#0E1B22"
    surface: str = "#132531"
    surface2: str = "#173242"
    sidebar: str = "#203642"
    sidebar_hover: str = "#2A4B5A"
    border: str = "#2C4E5E"
    text: str = "#E9F1F5"
    text_muted: str = "#B8C7D1"

    # Accents
    accent_blue: str = "#2E86A6"
    accent_green: str = "#66B35A"
    accent_yellow: str = "#E5C55A"

    # States
    danger: str = "#E06767"
    warning: str = "#E5C55A"
    ok: str = "#66B35A"
