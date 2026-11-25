# Art sources

Where each piece of artwork in this repository comes from and how it was made. No art from
Dragon Quest VII is stored or shipped.

| Files | What it is | How it was made |
| --- | --- | --- |
| [`dq7tt_gui/assets/parchment.png`](dq7tt_gui/assets/parchment.png), [`band_top.png`](dq7tt_gui/assets/band_top.png), [`band_bottom.png`](dq7tt_gui/assets/band_bottom.png) | The window's parchment ground and engraved bands | Drawn from scratch by [`tools/build_gui_art.py`](tools/build_gui_art.py), a drawing script written by generative AI (Claude, Anthropic) |
| [`dq7tt_gui/assets/compass.svg`](dq7tt_gui/assets/compass.svg), [`compass_faint.svg`](dq7tt_gui/assets/compass_faint.svg), [`pointer.svg`](dq7tt_gui/assets/pointer.svg) | Compass rose and gold pointer | Drawn by `tools/build_gui_art.py` (as above) |
| [`dq7tt_gui/assets/tablets/*.svg`](dq7tt_gui/assets/tablets) | One carved stone per tablet kind (story, resident, DLC, StreetPass, unknown) | Drawn by `tools/build_gui_art.py` (as above) |
| [`dq7tt_gui/assets/icon_android.png`](dq7tt_gui/assets/icon_android.png) | Android launcher icon: the story stone in a gold ring | Drawn by [`tools/launcher_icon.py`](tools/launcher_icon.py) from the story stone, a drawing script written by generative AI (Claude, Anthropic) |

## Replacements welcome

I would rather use art made by people. If you would like to draw a replacement for any piece
above, open an issue or a pull request: it will be used with full credit to you, under the
licence you choose.
