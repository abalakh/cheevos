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

**Give it to Cheevos**, in either of two ways:
- **Type it:** on the first start, Cheevos asks for the key. Press **A** and type it with the
  on-screen keyboard, then press **Start**. Cheevos checks the key with RetroAchievements. If
  you're offline, it keeps the key and checks it on the next sync.
- **Put it in a file:** with the SD card in a computer, save the key as
  `Saves/cheevos/apikey.txt`: just the key, on one line. Notepad on Windows works fine. That's
  easier than typing 32 characters, and Cheevos then starts without asking.

If RetroAchievements rejects the key later (you reset it on the site, or the file has a typo),
the bottom bar says **API key rejected**. Press **Start** to type the right one.

To change the key at any time: **Settings → Web API key**.

Cheevos normally connects over verified HTTPS. If TLS fails (including an unset or incorrect
device clock), it automatically falls back to HTTP. The fallback sends your Web API key and
account data unencrypted, so someone able to observe the connection could read them. A correct
clock and working TLS keep connections on HTTPS; network time sync isn't required to use Cheevos.

## Unlock screenshots (optional)
RetroArch can save a screenshot every time you unlock an achievement, and Cheevos then shows it
on the achievement. It's off by default. To turn it on, open RetroArch's menu during a game:
**Settings → Achievements → Automatic Screenshot**, and save the configuration. Cheevos only
reads these screenshots and never changes RetroArch's settings.
