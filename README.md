# dtwow
A Discord bot for playing a Discord-oriented variant of Ten Words Of Wisdom (TWOW).

## Example Configuration File
An example `config.json`:
```js
{
    "token": "static token goes here",
    "status": "online",
    "activity": {
        "text": "activity text",
        "type": "activity type"
    },
    "game": "ibdp_twow",
    "db": "sqlite+aiosqlite:///twow_data.db"
}
```