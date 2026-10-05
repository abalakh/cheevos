# Setup

Cheevos needs two things: your RetroAchievements **username** and your **Web API key**.

## Username
Cheevos uses the account you're already signed in with on the device. It looks in:
1. Spruce's settings: **Settings → RetroAchievements**, the username field.
2. RetroArch's achievements login, if you signed in there instead.

If neither has a username, Cheevos asks you to sign in first and exits. Sign in, then start it
again.

## Web API key
The Web API key lets apps read RetroAchievements data through its Web API. It isn't your
password, and you can reset it on the site at any time.

**Find your key:** sign in at [retroachievements.org](https://retroachievements.org), open
**Settings**, and look for **Keys → Web API Key**. It's 32 letters and digits.

**Give it to Cheevos**, in either of two ways. The setup screen offers both:
- **Enter it now:** type it with the on-screen keyboard. Press Start to confirm.
- **Put it in a file:** save the key as `Saves/cheevos/apikey.txt` on the SD card (one line),
  then choose **Check again**. That's easier if you have the card in a computer anyway.

Cheevos checks the key with RetroAchievements. If you're offline, it keeps the key and checks it
on the next sync.

To change the key later: **Settings → Web API key**.

## Unlock screenshots (optional)
RetroArch can save a screenshot every time you unlock an achievement, and Cheevos then shows it
on the achievement. It's off by default. To turn it on, open RetroArch's menu during a game:
**Settings → Achievements → Automatic Screenshot**, and save the configuration. Cheevos only
reads these screenshots and never changes RetroArch's settings.
