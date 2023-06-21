# dtwow
A Discord bot for playing a Discord-oriented variant of Ten Words Of Wisdom (TWOW).

## Example Configuration File
An example `config.ini`:
```ini
token = <static token goes here>
status = online
game = ibdp_twow
db = sqlite+aiosqlite:///twow_data.db

[activity]
text = activity text here
type = activity type here
```

## To run the bot
Run `bot.py` with your config `.ini` file.
```
python bot.py config.ini
```