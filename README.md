# dtwow
A Discord bot for playing a Discord-oriented variant of Ten Words Of Wisdom (TWOW).

## Example Configuration File
An example `config.ini`:
```ini
[game]
preset = ibdp_twow

[discord]
token = <static token here>
status = online

[activity]
text = <custom text here>
type = listening

[test server]
id = <test server ID here>
```

## To run the bot
Run `bot.py` with your config `.ini` file.
```
python bot.py config.ini
```