# Cheevos for PyUI

1. Copy the ZIP's `App/` folder onto the SD card, merging it with the existing folder.
   Cheevos goes in `App/PyUI/main-ui/cheevos/`.
2. From the SpruceOS repository root, apply `spruceos-pyui.patch` once:

   ```sh
   git apply --ignore-space-change /path/to/spruceos-pyui.patch
   ```

   Deploy the two patched files to their matching SD-card paths. The patch targets PyUI
   commit `2c563837`; it adds the Apps entry and background preload after the first menu frame.
3. Restart PyUI and open **Apps → Cheevos**. B on Home returns to Apps.
